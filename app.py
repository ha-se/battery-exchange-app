"""
バッテリー交換実績集計アプリ
PT企業(user_company)毎に、user_nameと自転車メーカー別の集計を行います。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, List, Tuple
import io
import os
import zipfile

try:
    import snowflake.connector
    from snowflake.connector.pandas_tools import write_pandas
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False

# ページ設定
st.set_page_config(
    page_title="バッテリー交換実績集計",
    page_icon="🔋",
    layout="wide"
)

# 認証機能（パブリックデプロイ時は常に有効）
# ローカル開発時のみ無効化する場合は環境変数 DISABLE_AUTH=true を設定
ENABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() != "true"

if ENABLE_AUTH:
    try:
        from auth import check_password, logout, get_authenticated_user
        
        if not check_password():
            st.stop()
        
        # ログアウトボタンをサイドバーに追加
        with st.sidebar:
            st.markdown("---")
            st.markdown(f"👤 ログイン中: **{get_authenticated_user()}**")
            if st.button("🚪 ログアウト"):
                logout()
    except Exception as e:
        st.error(f"🔐 認証モジュールのエラー: {e}")
        st.error("Secretsに [passwords] セクションが設定されているか確認してください")
        st.code("""
[passwords]
admin = "パスワードハッシュ値"
        """)
        st.stop()

@st.cache_data(show_spinner=False)
def load_excel_data(file_path: str) -> pd.DataFrame:
    """Excelファイルを読み込む"""
    try:
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        return None

@st.cache_data(show_spinner=False)
def load_excel_from_uploaded_file(uploaded_file) -> pd.DataFrame:
    """アップロードされたファイルを読み込む"""
    try:
        df = pd.read_excel(uploaded_file)
        # E列（インデックス4）とV列（インデックス21）の列名を保存
        if len(df.columns) > 4:
            df.attrs['e_column_name'] = df.columns[4]  # E列
        if len(df.columns) > 21:
            df.attrs['v_column_name'] = df.columns[21]  # V列（user_company(所属)）
        return df
    except Exception as e:
        st.error(f"ファイル読み込みエラー: {e}")
        return None

def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    前後1時間で同じ車両番号（code）のレコードを重複として検出
    
    Args:
        df: 元データ（do_date列とcode列が必要）
    
    Returns:
        重複フラグ列（is_duplicate）を追加したDataFrame
    """
    df = df.copy()
    
    # 重複フラグを初期化
    df['is_duplicate'] = False
    
    # do_date列をdatetime型に変換
    if 'do_date' not in df.columns:
        return df
    
    # code列の存在確認
    if 'code' not in df.columns:
        return df
    
    # do_date列をdatetime型に変換（エラーは無視）
    df['do_date'] = pd.to_datetime(df['do_date'], errors='coerce')
    
    # 車両番号が空でない、かつ日時が有効なレコードのみ処理
    valid_mask = df['code'].notna() & df['do_date'].notna()
    
    if not valid_mask.any():
        return df
    
    # 車両番号と日時でソート
    df_sorted = df.sort_values(['code', 'do_date'])
    
    # 前のレコードとの差分を計算（ベクトル化）
    df_sorted['prev_code'] = df_sorted['code'].shift(1)
    df_sorted['prev_date'] = df_sorted['do_date'].shift(1)
    
    # 同じ車両番号で、前のレコードとの時間差が1時間以内の場合は重複
    df_sorted['time_diff'] = df_sorted['do_date'] - df_sorted['prev_date']
    df_sorted['is_duplicate'] = (
        (df_sorted['code'] == df_sorted['prev_code']) & 
        (df_sorted['time_diff'] <= pd.Timedelta(hours=1))
    )
    
    # 元のインデックス順に戻す
    df.loc[df_sorted.index, 'is_duplicate'] = df_sorted['is_duplicate']
    
    return df

def upload_to_snowflake(df: pd.DataFrame, connection_params: dict, table_name: str) -> bool:
    """
    DataFrameをSnowflakeにアップロード
    
    Args:
        df: アップロードするDataFrame
        connection_params: Snowflake接続パラメータ
        table_name: テーブル名
    
    Returns:
        成功したかどうか
    """
    if not SNOWFLAKE_AVAILABLE:
        st.error("❌ Snowflakeモジュールがインストールされていません")
        return False
    
    conn = None
    try:
        # Snowflakeに接続
        conn = snowflake.connector.connect(**connection_params)

        # カラム名をSnowflake用にクリーニング
        df_clean = df.copy()
        df_clean.columns = [
            col.replace(' ', '_')
               .replace('(', '_')
               .replace(')', '_')
               .replace('-', '_')
               .replace('.', '_')
            for col in df_clean.columns
        ]

        # 一時列を削除
        temp_cols = ['is_duplicate', '基準判定', 'prev_code', 'prev_date', 'time_diff']
        df_clean = df_clean.drop(columns=[col for col in temp_cols if col in df_clean.columns], errors='ignore')

        # write_pandasを使用して高速アップロード
        success, nchunks, nrows, _ = write_pandas(
            conn=conn,
            df=df_clean,
            table_name=table_name.upper(),
            auto_create_table=True,
            overwrite=True,
            quote_identifiers=False
        )

        return success

    except Exception as e:
        st.error(f"❌ Snowflakeアップロードエラー: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()

def is_self_exchange(df: pd.DataFrame, row_index: int) -> bool:
    """
    E列とV列を参照して、自社交換分かどうかを判定
    
    Args:
        df: DataFrame（E列とV列の列名がattrsに保存されている）
        row_index: 判定する行のインデックス
    
    Returns:
        bool: 自社交換分の場合True
    """
    # E列とV列の列名を取得
    e_col_name = df.attrs.get('e_column_name', None)
    v_col_name = df.attrs.get('v_column_name', 'user_company(所属)')
    
    if e_col_name is None or e_col_name not in df.columns:
        return False
    
    # 自社交換分の組み合わせ定義
    self_exchange_mapping = {
        'トヨタモビリティ東京株式会社': 'TMT',
        '江ノ島電鉄株式会社': '江ノ電',
        'モビリティプラットフォーム株式会社': 'MPF',
        '東急バス株式会社': '東急バス'
    }
    
    # 対象PT企業のリスト
    target_pt_companies = ['TMT', '江ノ電', 'MPF', '東急バス']
    
    # 行のデータを取得
    row = df.iloc[row_index]
    e_value = row.get(e_col_name, None)
    v_value = row.get(v_col_name, None)
    
    # E列とV列の値が自社交換分の組み合わせかチェック
    if pd.notna(e_value) and pd.notna(v_value):
        e_str = str(e_value).strip()
        v_str = str(v_value).strip()
        
        # PT企業が対象企業で、かつE列とV列の組み合わせが自社交換分の場合
        if v_str in target_pt_companies:
            if e_str in self_exchange_mapping:
                if self_exchange_mapping[e_str] == v_str:
                    return True
    
    return False

def check_battery_standard(row):
    """
    バッテリー残量が基準外かどうかを判定
    
    基準:
    - Panasonic: 25%以上が基準外
    - YAMAHA: 70%以上が基準外
    - DBS: 50%以上が基準外（ただし100%は基準内）
    - glafit: 50%以上が基準外
    - シナネンサイクル: 40%以上が基準外
    
    Returns:
        str: '基準内' or '基準外'
    """
    maker = row['自転車メーカー名']
    battery = row['battery_remaining']
    
    if pd.isna(battery):
        return None
    
    if maker == 'Panasonic':
        return '基準外' if battery >= 25 else '基準内'
    elif maker == 'YAMAHA':
        return '基準外' if battery >= 70 else '基準内'
    elif maker == 'DBS':
        if battery == 100:
            return '基準内'
        return '基準外' if battery >= 50 else '基準内'
    elif maker == 'glafit':
        return '基準外' if battery >= 50 else '基準内'
    elif maker == 'シナネンサイクル':
        return '基準外' if battery >= 40 else '基準内'
    else:
        return None

def aggregate_by_company_and_maker(df: pd.DataFrame) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    PT企業毎に、user_nameと自転車メーカー別の集計を行う
    基準内/基準外、重複除外も含めて集計
    自社交換分（E列とV列の特定組み合わせ）は除外し、別途返す

    Returns:
        tuple: (集計結果Dict, 自社交換分DataFrame)
            - 集計結果Dict: PT企業名をキー、集計結果DataFrameを値とする辞書
            - 自社交換分DataFrame: 自社交換分のレコード
    """
    # V列の列名を動的に取得
    company_col = df.attrs.get('v_column_name', 'user_company(所属)')
    if company_col not in df.columns:
        # フォールバック: 列名に「所属」を含む列を探す
        company_cols = [col for col in df.columns if '所属' in str(col) or 'company' in str(col).lower()]
        if company_cols:
            company_col = company_cols[0]
        else:
            raise KeyError(f"PT企業列が見つかりません。列: {list(df.columns)}")

    user_col = 'user_name'
    maker_col = '自転車メーカー名'
    
    # 重複検出を実行
    df_with_standard = detect_duplicates(df)
    
    # attrsを継承（E列とV列の列名情報）
    if hasattr(df, 'attrs'):
        df_with_standard.attrs.update(df.attrs)
    
    # 基準判定列を追加
    df_with_standard['基準判定'] = df_with_standard.apply(check_battery_standard, axis=1)
    
    # 自社交換分を判定（is_self_exchange列を追加）
    # より効率的にベクトル化して処理
    df_with_standard['is_self_exchange'] = False
    
    # E列とV列の列名を取得
    e_col_name = df_with_standard.attrs.get('e_column_name', None)
    v_col_name = df_with_standard.attrs.get('v_column_name', 'user_company(所属)')
    
    if e_col_name and e_col_name in df_with_standard.columns:
        # 自社交換分の組み合わせ定義
        self_exchange_mapping = {
            'トヨタモビリティ東京株式会社': 'TMT',
            '江ノ島電鉄株式会社': '江ノ電',
            'モビリティプラットフォーム株式会社': 'MPF',
            '東急バス株式会社': '東急バス'
        }
        
        # 対象PT企業のリスト
        target_pt_companies = ['TMT', '江ノ電', 'MPF', '東急バス']
        
        # ベクトル化して判定
        e_values = df_with_standard[e_col_name].astype(str).str.strip()
        v_values = df_with_standard[v_col_name].astype(str).str.strip()
        
        # 条件: V列が対象PT企業で、かつE列とV列の組み合わせが自社交換分
        mask = v_values.isin(target_pt_companies) & e_values.isin(self_exchange_mapping.keys())
        for e_str, v_expected in self_exchange_mapping.items():
            df_with_standard.loc[mask & (e_values == e_str) & (v_values == v_expected), 'is_self_exchange'] = True
    
    # 自社交換分を分離
    self_exchange_df = df_with_standard[df_with_standard['is_self_exchange'] == True].copy()
    df_for_aggregation = df_with_standard[df_with_standard['is_self_exchange'] == False].copy()
    
    # PT企業毎に集計（自社交換分を除外したデータで集計）
    aggregated_data = {}
    
    companies = df_for_aggregation[company_col].dropna().unique()
    
    for i, company in enumerate(companies):
        # 該当企業のデータを抽出（自社交換分を除外）
        company_df = df_for_aggregation[df_for_aggregation[company_col] == company]
        
        # 各メーカーの結果を格納する辞書
        result_data = []
        
        # ユーザー毎に集計
        for user in company_df[user_col].dropna().unique():
            user_df = company_df[company_df[user_col] == user]
            row_data = {'user_name': user}
            
            # 重複を除外したデータ
            user_df_no_dup = user_df[user_df['is_duplicate'] == False]
            # 重複データ
            user_df_dup = user_df[user_df['is_duplicate'] == True]
            
            # 各メーカーについて、基準内/基準外を集計
            makers = ['Panasonic', 'YAMAHA', 'DBS', 'glafit', 'シナネンサイクル', 'KUROAD']
            total = 0
            total_duplicates = 0
            
            for maker in makers:
                # 重複除外データで集計（重複は含まない）
                maker_df = user_df_no_dup[user_df_no_dup[maker_col] == maker]
                # 重複データの件数（参考値）
                maker_dup_count = len(user_df_dup[user_df_dup[maker_col] == maker])
                
                # 基準内の件数（重複除外後）
                kijun_nai = len(maker_df[maker_df['基準判定'] == '基準内'])
                # 基準外の件数（重複除外後）
                kijun_gai = len(maker_df[maker_df['基準判定'] == '基準外'])
                # 合計（重複除外後、基準判定がNoneの場合も含む）
                maker_total = len(maker_df)
                
                # 検証: 基準内 + 基準外 = 合計 (KUROADなど基準判定がないものを除く)
                # maker_total = kijun_nai + kijun_gai + (基準判定なし)
                
                row_data[f'{maker}_基準内'] = kijun_nai
                row_data[f'{maker}_基準外'] = kijun_gai
                row_data[f'{maker}_合計'] = maker_total
                row_data[f'{maker}_重複除外数'] = maker_dup_count
                
                total += maker_total
                total_duplicates += maker_dup_count
            
            row_data['総合計'] = total
            row_data['総重複除外数'] = total_duplicates
            result_data.append(row_data)
        
        # DataFrameに変換
        result_df = pd.DataFrame(result_data)
        
        # 合計行を追加
        total_row = {'user_name': '合計'}
        for col in result_df.columns:
            if col != 'user_name':
                total_row[col] = result_df[col].sum()
        
        result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)
        
        # 列の順序を整理
        ordered_columns = ['user_name']
        for maker in makers:
            if f'{maker}_基準内' in result_df.columns:
                ordered_columns.extend([
                    f'{maker}_基準内', 
                    f'{maker}_基準外', 
                    f'{maker}_合計',
                    f'{maker}_重複除外数'
                ])
        ordered_columns.extend(['総合計', '総重複除外数'])
        
        # 存在する列のみを選択
        existing_columns = [col for col in ordered_columns if col in result_df.columns]
        result_df = result_df[existing_columns]
        
        aggregated_data[company] = result_df
    
    return aggregated_data, self_exchange_df

def main():
    st.title("🔋 バッテリー交換実績集計アプリ")
    st.markdown("---")
    
    # サイドバー：ファイル選択
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # ファイルアップロード
        uploaded_file = st.file_uploader(
            "Excelファイルをアップロード",
            type=['xlsx', 'xls'],
            help="バッテリー交換実績データのExcelファイルをアップロードしてください"
        )
        
        # Snowflake設定
        if SNOWFLAKE_AVAILABLE:
            st.markdown("---")
            with st.expander("☁️ Snowflake自動転送設定", expanded=False):
                st.markdown("ファイルアップロード時に自動的にSnowflakeへ転送します")
                
                enable_snowflake = st.checkbox("Snowflake自動転送を有効化", value=False)
                
                if enable_snowflake:
                    sf_account = st.text_input("Account", help="例: abc12345.ap-northeast-1.aws")
                    sf_user = st.text_input("User")
                    sf_password = st.text_input("Password", type="password")
                    sf_warehouse = st.text_input("Warehouse", value="COMPUTE_WH")
                    sf_database = st.text_input("Database")
                    sf_schema = st.text_input("Schema", value="PUBLIC")
                    sf_table = st.text_input("Table Name", value="BATTERY_EXCHANGE_RAW")
                    
                    # 接続パラメータを保存
                    if all([sf_account, sf_user, sf_password, sf_warehouse, sf_database, sf_schema, sf_table]):
                        st.session_state['snowflake_params'] = {
                            'account': sf_account,
                            'user': sf_user,
                            'password': sf_password,
                            'warehouse': sf_warehouse,
                            'database': sf_database,
                            'schema': sf_schema
                        }
                        st.session_state['snowflake_table'] = sf_table
                        st.session_state['snowflake_enabled'] = True
                    else:
                        st.session_state['snowflake_enabled'] = False
                else:
                    st.session_state['snowflake_enabled'] = False
        
        # バージョン情報（デバッグ用）
        st.markdown("---")
        st.caption("Version: 2026-02-03-v11 (列名の動的取得対応)")
    
    # メインエリア
    if uploaded_file is not None:
        # アップロードされたファイルを読み込み
        with st.spinner("📂 ファイルを読み込み中..."):
            df = load_excel_from_uploaded_file(uploaded_file)
        
        if df is not None:
            st.success(f"✅ ファイル読み込み完了: {len(df):,}行のデータ")
            
            # Snowflakeへの自動転送
            if st.session_state.get('snowflake_enabled', False):
                if 'snowflake_uploaded' not in st.session_state or st.session_state.get('current_file') != uploaded_file.name:
                    with st.spinner("☁️ Snowflakeへデータを転送中..."):
                        success = upload_to_snowflake(
                            df,
                            st.session_state['snowflake_params'],
                            st.session_state['snowflake_table']
                        )
                        
                        if success:
                            st.success(f"✅ Snowflakeへのアップロード完了: {st.session_state['snowflake_table']}")
                            st.session_state['snowflake_uploaded'] = True
                            st.session_state['current_file'] = uploaded_file.name
                        else:
                            st.error("❌ Snowflakeへのアップロードに失敗しました")
                else:
                    st.info(f"ℹ️ このファイルは既にSnowflakeにアップロード済みです（テーブル: {st.session_state['snowflake_table']}）")
                
            # データプレビュー
            with st.expander("📊 データプレビュー（最初の10行）"):
                st.dataframe(df.head(10))
            
            # 集計実行ボタン
            if st.button("🔄 集計実行", type="primary", use_container_width=True):
                progress_bar = st.progress(0, text="集計を開始しています...")
                status_text = st.empty()
                
                try:
                    status_text.text("📊 データを分析中...")
                    progress_bar.progress(10, text="重複データを検出中...")

                    # PT企業のリストを取得（V列の列名を動的に取得）
                    company_col = df.attrs.get('v_column_name', 'user_company(所属)')
                    if company_col not in df.columns:
                        # フォールバック: 列名に「所属」を含む列を探す
                        company_cols = [col for col in df.columns if '所属' in str(col) or 'company' in str(col).lower()]
                        if company_cols:
                            company_col = company_cols[0]
                        else:
                            raise KeyError(f"PT企業列が見つかりません。V列（22列目）に所属情報があるか確認してください。現在の列: {list(df.columns[:25])}")

                    companies = df[company_col].dropna().unique()
                    total_companies = len(companies)

                    # 列名をセッションに保存
                    st.session_state['company_col'] = company_col
                    
                    status_text.text(f"🔍 重複データを検出中...（{len(df):,}行）")
                    progress_bar.progress(30, text="重複チェック実行中...")
                    
                    # 集計実行（重複検出を含む、自社交換分を除外）
                    aggregated_data, self_exchange_df = aggregate_by_company_and_maker(df)
                    
                    progress_bar.progress(90, text="集計結果を準備中...")
                    st.session_state['aggregated_data'] = aggregated_data
                    st.session_state['self_exchange_df'] = self_exchange_df
                    
                    progress_bar.progress(100, text="完了！")
                    status_text.empty()
                    progress_bar.empty()
                    
                    self_exchange_count = len(self_exchange_df) if not self_exchange_df.empty else 0
                    success_msg = f"✅ 集計完了！{len(aggregated_data)}社のデータを集計しました"
                    if self_exchange_count > 0:
                        success_msg += f"（自社交換分: {self_exchange_count:,}件を除外）"
                    st.success(success_msg)
                    st.balloons()
                    
                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"❌ 集計エラー: {e}")
                    import traceback
                    with st.expander("詳細なエラー情報"):
                        st.code(traceback.format_exc())
            
            # 集計結果の表示
            if 'aggregated_data' in st.session_state:
                aggregated_data = st.session_state['aggregated_data']
            
                st.markdown("---")
                st.header("📈 集計結果")
            
                # 全企業のデータを1つのExcelファイルに出力
                st.subheader("全PT企業のデータを一括ダウンロード")
                
                st.info("💡 全PT企業の集計結果と生データを含むZIPファイルをダウンロードできます")
                st.warning("⚠️ 生データを含むため、ファイルサイズが大きくなります")
                
                if st.button("📦 全企業のExcelファイルを準備", key="prepare_all_excel"):
                    with st.spinner(f"全{len(aggregated_data)}社のExcelファイルをZIP化中..."):
                        # ZIPファイルを作成
                        zip_buffer = io.BytesIO()
                        
                        # 生データから一時列を削除
                        df_clean = df.copy()
                        temp_cols = ['is_duplicate', '基準判定', 'prev_code', 'prev_date', 'time_diff', 'is_self_exchange']
                        df_clean = df_clean.drop(columns=[col for col in temp_cols if col in df_clean.columns], errors='ignore')
                        
                        # 自社交換分のデータを準備
                        self_exchange_clean = None
                        if 'self_exchange_df' in st.session_state and not st.session_state['self_exchange_df'].empty:
                            self_exchange_clean = st.session_state['self_exchange_df'].copy()
                            self_exchange_clean = self_exchange_clean.drop(columns=[col for col in temp_cols if col in self_exchange_clean.columns], errors='ignore')
                        
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            progress_bar = st.progress(0)
                            total = len(aggregated_data) + 1  # 企業ごとのファイル + 全企業まとめファイル
                            
                            # 全企業の集計結果をまとめたExcelファイルを作成
                            all_companies_excel = io.BytesIO()
                            with pd.ExcelWriter(all_companies_excel, engine='openpyxl') as writer:
                                # 全企業の集計結果を1つのシートに統合
                                all_companies_data = []
                                
                                for company, data in aggregated_data.items():
                                    # 各企業のデータに企業名列を追加
                                    company_with_name = data.copy()
                                    company_with_name.insert(0, 'PT企業名', company)
                                    all_companies_data.append(company_with_name)
                                
                                # 全企業のデータを結合
                                combined_df = pd.concat(all_companies_data, ignore_index=True)
                                combined_df.to_excel(writer, sheet_name='全PT企業集計', index=False)
                                
                                # 自社交換分シートを追加
                                if self_exchange_clean is not None and not self_exchange_clean.empty:
                                    self_exchange_clean.to_excel(writer, sheet_name='自社交換分', index=False)
                            
                            all_companies_excel.seek(0)
                            zip_file.writestr(
                                "全企業_集計結果.xlsx",
                                all_companies_excel.getvalue()
                            )
                            progress_bar.progress(1 / total)
                            
                            # 各企業ごとに1つのExcelファイルを作成
                            # 列名を取得（セッションから、またはattrsから）
                            download_company_col = st.session_state.get('company_col', df.attrs.get('v_column_name', 'user_company(所属)'))

                            for idx, (company, data) in enumerate(aggregated_data.items()):
                                excel_buffer = io.BytesIO()

                                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                    # 集計結果シート
                                    data.to_excel(writer, sheet_name='集計結果', index=False)

                                    # 生データシート
                                    company_raw = df_clean[df_clean[download_company_col] == company].copy()
                                    company_raw.to_excel(writer, sheet_name='生データ', index=False)

                                    # 自社交換分シート（該当企業のみ）
                                    if self_exchange_clean is not None and not self_exchange_clean.empty:
                                        company_self_exchange = self_exchange_clean[self_exchange_clean[download_company_col] == company].copy()
                                        if not company_self_exchange.empty:
                                            company_self_exchange.to_excel(writer, sheet_name='自社交換分', index=False)
                                
                                # ZIPに追加（ファイル名をクリーンアップ）
                                safe_company_name = company.replace('/', '_').replace('\\', '_')
                                zip_file.writestr(
                                    f"{safe_company_name}_集計結果_生データ.xlsx",
                                    excel_buffer.getvalue()
                                )
                                
                                progress_bar.progress((idx + 2) / total)  # +2は全企業ファイル分とインデックス調整
                            
                            progress_bar.empty()
                        
                        zip_buffer.seek(0)
                        st.session_state['all_excel_data'] = zip_buffer.getvalue()
                        st.session_state['all_excel_filename'] = "全PT企業_集計結果_生データ.zip"
                        st.session_state['all_excel_mime'] = "application/zip"
                        st.success(f"✅ ZIPファイルの準備完了！（全企業_集計結果.xlsx + {len(aggregated_data)}社のExcelファイル）")
                
                # ダウンロードボタンを表示
                if 'all_excel_data' in st.session_state:
                    st.download_button(
                        label=f"📥 {st.session_state['all_excel_filename']} をダウンロード",
                        data=st.session_state['all_excel_data'],
                        file_name=st.session_state['all_excel_filename'],
                        mime=st.session_state.get('all_excel_mime', 'application/zip'),
                        key="download_all_excel"
                    )
            
    else:
        # ファイルが選択されていない場合
        st.info("👈 サイドバーからExcelファイルをアップロードしてください")
        

if __name__ == "__main__":
    main()

