"""
バッテリー交換実績集計アプリ
PT企業(user_company)毎に、user_nameと自転車メーカー別の集計を行います。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, List
import io
import os

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
    
    # 一時列を削除
    if 'prev_code' in df.columns:
        df = df.drop(columns=['prev_code', 'prev_date', 'time_diff'], errors='ignore')
    
    return df

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

def aggregate_by_company_and_maker(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    PT企業毎に、user_nameと自転車メーカー別の集計を行う
    基準内/基準外、重複除外も含めて集計
    
    Returns:
        Dict[str, pd.DataFrame]: PT企業名をキー、集計結果DataFrameを値とする辞書
    """
    company_col = 'user_company(所属)'
    user_col = 'user_name'
    maker_col = '自転車メーカー名'
    
    # 重複検出を実行
    df_with_standard = detect_duplicates(df)
    
    # 基準判定列を追加
    df_with_standard['基準判定'] = df_with_standard.apply(check_battery_standard, axis=1)
    
    # PT企業毎に集計
    aggregated_data = {}
    
    companies = df[company_col].dropna().unique()
    
    for i, company in enumerate(companies):
        # 該当企業のデータを抽出
        company_df = df_with_standard[df_with_standard[company_col] == company]
        
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
                # 重複除外データで集計
                maker_df = user_df_no_dup[user_df_no_dup[maker_col] == maker]
                # 重複データの件数
                maker_dup_count = len(user_df_dup[user_df_dup[maker_col] == maker])
                
                # 基準内の件数
                kijun_nai = len(maker_df[maker_df['基準判定'] == '基準内'])
                # 基準外の件数
                kijun_gai = len(maker_df[maker_df['基準判定'] == '基準外'])
                # 合計（基準判定がNoneの場合も含む）
                maker_total = len(maker_df)
                
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
    
    return aggregated_data

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
        
        # バージョン情報（デバッグ用）
        st.markdown("---")
        st.caption("Version: 2025-12-30-v6 (Excel出力最適化:一時列削除)")
    
    # メインエリア
    if uploaded_file is not None:
        # アップロードされたファイルを読み込み
        with st.spinner("📂 ファイルを読み込み中..."):
            df = load_excel_from_uploaded_file(uploaded_file)
        
        if df is not None:
            st.success(f"✅ ファイル読み込み完了: {len(df):,}行のデータ")
                
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
                    
                    # PT企業のリストを取得
                    companies = df['user_company(所属)'].dropna().unique()
                    total_companies = len(companies)
                    
                    status_text.text(f"🔍 重複データを検出中...（{len(df):,}行）")
                    progress_bar.progress(30, text="重複チェック実行中...")
                    
                    # 集計実行（重複検出を含む）
                    aggregated_data = aggregate_by_company_and_maker(df)
                    
                    progress_bar.progress(90, text="集計結果を準備中...")
                    st.session_state['aggregated_data'] = aggregated_data
                    
                    progress_bar.progress(100, text="完了！")
                    status_text.empty()
                    progress_bar.empty()
                    
                    st.success(f"✅ 集計完了！{len(aggregated_data)}社のデータを集計しました")
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
            
                # PT企業選択
                selected_company = st.selectbox(
                    "PT企業を選択",
                    options=sorted(aggregated_data.keys()),
                    index=0
                )
            
                if selected_company:
                    company_data = aggregated_data[selected_company]
                
                    # タブで表示を切り替え
                    tab1, tab2, tab3 = st.tabs(["📋 集計表", "📊 グラフ", "💾 Excel出力"])
                
                    with tab1:
                        st.subheader(f"{selected_company} の集計結果")
                        
                        # 重複除外の統計情報を表示
                        if '総重複除外数' in company_data.columns:
                            total_row = company_data[company_data['user_name'] == '合計']
                            if len(total_row) > 0:
                                total_exchanges = int(total_row['総合計'].values[0])
                                total_duplicates = int(total_row['総重複除外数'].values[0])
                                total_with_duplicates = total_exchanges + total_duplicates
                                
                                st.info(f"""
                                📊 **データ統計**
                                - 総交換件数（重複除外後）: **{total_exchanges:,}件**
                                - 重複除外数: **{total_duplicates:,}件**
                                - 元データ件数: **{total_with_duplicates:,}件**
                                - 重複率: **{(total_duplicates / total_with_duplicates * 100):.2f}%**
                                
                                💡 前後1時間以内に同じ車両番号（code）で記録された交換は重複としてカウントされています。
                                """)
                        
                        st.dataframe(
                            company_data,
                            use_container_width=True,
                            height=600
                        )
                
                    with tab2:
                        st.subheader(f"{selected_company} - データビジュアライゼーション")
                    
                        # グラフ表示（合計行を除く）
                        chart_data = company_data[company_data['user_name'] != '合計'].copy()
                    
                        if len(chart_data) > 0 and '総合計' in chart_data.columns:
                            # 上位10名を取得
                            top_users = chart_data.nlargest(10, '総合計')['user_name'].tolist()
                            chart_data_top = chart_data[chart_data['user_name'].isin(top_users)]
                        
                            # 1. メーカー別合計のグラフ
                            st.markdown("#### メーカー別交換件数（上位10名）")
                            maker_total_cols = [col for col in chart_data.columns if col.endswith('_合計') and col != '総合計']
                        
                            if maker_total_cols:
                                chart_data_maker = pd.melt(
                                    chart_data_top,
                                    id_vars=['user_name'],
                                    value_vars=maker_total_cols,
                                    var_name='メーカー',
                                    value_name='件数'
                                )
                                # メーカー名をクリーンアップ（"_合計"を削除）
                                chart_data_maker['メーカー'] = chart_data_maker['メーカー'].str.replace('_合計', '')
                            
                                fig1 = px.bar(
                                    chart_data_maker,
                                    x='user_name',
                                    y='件数',
                                    color='メーカー',
                                    title=f"{selected_company} - ユーザー別・メーカー別実績（上位10名）",
                                    labels={'user_name': 'ユーザー名'},
                                    height=500
                                )
                                st.plotly_chart(fig1, use_container_width=True)
                        
                            # 2. 基準内/基準外のグラフ
                            st.markdown("#### 基準内/基準外の内訳（上位10名）")
                        
                            # 基準内と基準外の列を取得
                            kijun_nai_cols = [col for col in chart_data.columns if col.endswith('_基準内')]
                            kijun_gai_cols = [col for col in chart_data.columns if col.endswith('_基準外')]
                        
                            if kijun_nai_cols and kijun_gai_cols:
                                # 各ユーザーの基準内/基準外合計を計算
                                chart_data_top['基準内合計'] = chart_data_top[kijun_nai_cols].sum(axis=1)
                                chart_data_top['基準外合計'] = chart_data_top[kijun_gai_cols].sum(axis=1)
                            
                                chart_data_kijun = pd.melt(
                                    chart_data_top,
                                    id_vars=['user_name'],
                                    value_vars=['基準内合計', '基準外合計'],
                                    var_name='区分',
                                    value_name='件数'
                                )
                            
                                fig2 = px.bar(
                                    chart_data_kijun,
                                    x='user_name',
                                    y='件数',
                                    color='区分',
                                    title=f"{selected_company} - 基準内/基準外の内訳",
                                    labels={'user_name': 'ユーザー名'},
                                    color_discrete_map={'基準内合計': '#2ecc71', '基準外合計': '#e74c3c'},
                                    height=500
                                )
                                st.plotly_chart(fig2, use_container_width=True)
                        
                            # 3. 円グラフ：メーカー別シェア
                            st.markdown("#### メーカー別シェア")
                            maker_totals = company_data[company_data['user_name'] == '合計']
                            if len(maker_totals) > 0 and maker_total_cols:
                                maker_data = maker_totals[maker_total_cols].T
                                maker_data.columns = ['件数']
                                maker_data = maker_data[maker_data['件数'] > 0]
                                maker_data.index = maker_data.index.str.replace('_合計', '')
                            
                                col1, col2 = st.columns(2)
                            
                                with col1:
                                    fig_pie = px.pie(
                                        maker_data,
                                        values='件数',
                                        names=maker_data.index,
                                        title=f"{selected_company} - メーカー別シェア",
                                        height=400
                                    )
                                    st.plotly_chart(fig_pie, use_container_width=True)
                            
                                with col2:
                                    # 基準内/基準外の円グラフ
                                    if len(maker_totals) > 0 and kijun_nai_cols and kijun_gai_cols:
                                        kijun_data = pd.DataFrame({
                                            '区分': ['基準内', '基準外'],
                                            '件数': [
                                                maker_totals[kijun_nai_cols].sum(axis=1).values[0],
                                                maker_totals[kijun_gai_cols].sum(axis=1).values[0]
                                            ]
                                        })
                                    
                                        fig_pie2 = px.pie(
                                            kijun_data,
                                            values='件数',
                                            names='区分',
                                            title=f"{selected_company} - 基準内/基準外シェア",
                                            color='区分',
                                            color_discrete_map={'基準内': '#2ecc71', '基準外': '#e74c3c'},
                                            height=400
                                        )
                                        st.plotly_chart(fig_pie2, use_container_width=True)
                
                    with tab3:
                        st.subheader("Excel形式でダウンロード")
                    
                        st.info("💡 集計結果と生データの両方が含まれたExcelファイルをダウンロードできます")
                    
                        # 選択した企業のデータをExcel出力（集計結果 + 生データ）
                        if st.button("📦 Excelファイルを準備", key="prepare_single_excel"):
                            with st.spinner("Excelファイルを作成中..."):
                                output = io.BytesIO()
                                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                    # シート1: 集計結果
                                    company_data.to_excel(writer, sheet_name='集計結果', index=False)
                                
                                    # シート2: 生データ（該当企業のみ、一時列を除外）
                                    company_raw_data = df[df['user_company(所属)'] == selected_company].copy()
                                    # 一時列を削除
                                    temp_cols = ['is_duplicate', '基準判定', 'prev_code', 'prev_date', 'time_diff']
                                    company_raw_data = company_raw_data.drop(columns=[col for col in temp_cols if col in company_raw_data.columns], errors='ignore')
                                    company_raw_data.to_excel(writer, sheet_name='生データ', index=False)
                                output.seek(0)
                            
                                st.session_state['single_excel_data'] = output.getvalue()
                                st.success("✅ Excelファイルの準備完了！")
                        
                        # ダウンロードボタンを表示
                        if 'single_excel_data' in st.session_state:
                            st.download_button(
                                label=f"📥 {selected_company} のデータをダウンロード（集計+生データ）",
                                data=st.session_state['single_excel_data'],
                                file_name=f"{selected_company}_集計結果_生データ.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    
                        # データサマリーを表示
                        st.markdown("---")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("集計結果の行数", f"{len(company_data):,}行")
                        with col2:
                            company_raw_data = df[df['user_company(所属)'] == selected_company]
                            st.metric("生データの行数", f"{len(company_raw_data):,}行")
                    
                        # 全企業のデータを1つのExcelファイルに出力
                        st.markdown("---")
                        st.subheader("全PT企業のデータを一括ダウンロード")
                    
                        download_option = st.radio(
                            "ダウンロード形式を選択",
                            options=["集計結果のみ", "集計結果 + 生データ"],
                            horizontal=True,
                            key="download_all_option"
                        )
                    
                        if st.button("📦 全企業のExcelファイルを準備", key="prepare_all_excel"):
                            if download_option == "集計結果のみ":
                                with st.spinner(f"全{len(aggregated_data)}社の集計結果をExcelに出力中..."):
                                    output_all = io.BytesIO()
                                    with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                        for company, data in aggregated_data.items():
                                            # シート名は最大31文字
                                            sheet_name = company[:31]
                                            data.to_excel(writer, sheet_name=sheet_name, index=False)
                                    output_all.seek(0)
                                    st.session_state['all_excel_data'] = output_all.getvalue()
                                    st.session_state['all_excel_filename'] = "全PT企業_集計結果.xlsx"
                                    st.success("✅ Excelファイルの準備完了！")
                            else:
                                st.warning("⚠️ 生データを含むため、ファイルサイズが大きくなります")
                                
                                with st.spinner(f"全{len(aggregated_data)}社の集計結果と生データをExcelに出力中..."):
                                    output_all = io.BytesIO()
                                    
                                    # 生データから一時列を削除
                                    df_clean = df.copy()
                                    temp_cols = ['is_duplicate', '基準判定', 'prev_code', 'prev_date', 'time_diff']
                                    df_clean = df_clean.drop(columns=[col for col in temp_cols if col in df_clean.columns], errors='ignore')
                                    
                                    with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                        progress_bar = st.progress(0)
                                        total = len(aggregated_data)
                                        
                                        for idx, (company, data) in enumerate(aggregated_data.items()):
                                            # 集計結果シート
                                            sheet_name = company[:28] + "_集計"
                                            data.to_excel(writer, sheet_name=sheet_name, index=False)
                                        
                                            # 生データシート
                                            company_raw = df_clean[df_clean['user_company(所属)'] == company].copy()
                                            sheet_name_raw = company[:28] + "_生"
                                            company_raw.to_excel(writer, sheet_name=sheet_name_raw, index=False)
                                            
                                            progress_bar.progress((idx + 1) / total)
                                        
                                        progress_bar.empty()
                                    
                                    output_all.seek(0)
                                    st.session_state['all_excel_data'] = output_all.getvalue()
                                    st.session_state['all_excel_filename'] = "全PT企業_集計結果_生データ.xlsx"
                                    st.success("✅ Excelファイルの準備完了！")
                        
                        # ダウンロードボタンを表示
                        if 'all_excel_data' in st.session_state:
                            st.download_button(
                                label=f"📥 {st.session_state['all_excel_filename']} をダウンロード",
                                data=st.session_state['all_excel_data'],
                                file_name=st.session_state['all_excel_filename'],
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_all_excel"
                            )
            
    else:
        # ファイルが選択されていない場合
        st.info("👈 サイドバーからExcelファイルをアップロードしてください")
        

if __name__ == "__main__":
    main()

