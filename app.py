"""
バッテリー交換実績集計アプリ
PT企業(user_company)毎に、user_nameと自転車メーカー別の集計を行い、Snowflakeにアップロードします。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import snowflake.connector
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
    from auth import check_password, logout, get_authenticated_user
    
    if not check_password():
        st.stop()
    
    # ログアウトボタンをサイドバーに追加
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"👤 ログイン中: **{get_authenticated_user()}**")
        if st.button("🚪 ログアウト"):
            logout()

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

@st.cache_data(show_spinner=False)
def aggregate_by_company_and_maker(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    PT企業毎に、user_nameと自転車メーカー別の集計を行う
    基準内/基準外も含めて集計
    
    Returns:
        Dict[str, pd.DataFrame]: PT企業名をキー、集計結果DataFrameを値とする辞書
    """
    company_col = 'user_company(所属)'
    user_col = 'user_name'
    maker_col = '自転車メーカー名'
    
    # 基準判定列を追加
    df_with_standard = df.copy()
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
            
            # 各メーカーについて、基準内/基準外を集計
            makers = ['Panasonic', 'YAMAHA', 'DBS', 'glafit', 'シナネンサイクル', 'KUROAD']
            total = 0
            
            for maker in makers:
                maker_df = user_df[user_df[maker_col] == maker]
                
                # 基準内の件数
                kijun_nai = len(maker_df[maker_df['基準判定'] == '基準内'])
                # 基準外の件数
                kijun_gai = len(maker_df[maker_df['基準判定'] == '基準外'])
                # 合計（基準判定がNoneの場合も含む）
                maker_total = len(maker_df)
                
                row_data[f'{maker}_基準内'] = kijun_nai
                row_data[f'{maker}_基準外'] = kijun_gai
                row_data[f'{maker}_合計'] = maker_total
                
                total += maker_total
            
            row_data['総合計'] = total
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
                ordered_columns.extend([f'{maker}_基準内', f'{maker}_基準外', f'{maker}_合計'])
        ordered_columns.append('総合計')
        
        # 存在する列のみを選択
        existing_columns = [col for col in ordered_columns if col in result_df.columns]
        result_df = result_df[existing_columns]
        
        aggregated_data[company] = result_df
    
    return aggregated_data

def create_snowflake_connection(account: str, user: str, password: str, 
                               warehouse: str, database: str, schema: str):
    """Snowflakeへの接続を確立"""
    try:
        conn = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            warehouse=warehouse,
            database=database,
            schema=schema
        )
        return conn
    except Exception as e:
        st.error(f"Snowflake接続エラー: {e}")
        return None

def upload_raw_data_to_snowflake(conn, table_name: str, df: pd.DataFrame, batch_size: int = 10000):
    """生データをSnowflakeにアップロード（バッチ処理で高速化）"""
    try:
        from snowflake.connector.pandas_tools import write_pandas
        
        # カラム名をSnowflake用にクリーニング
        df_upload = df.copy()
        df_upload.columns = [col.replace(' ', '_').replace('(', '_').replace(')', '_') for col in df_upload.columns]
        
        # write_pandasを使用して高速アップロード
        success, nchunks, nrows, _ = write_pandas(
            conn=conn,
            df=df_upload,
            table_name=table_name.upper(),
            auto_create_table=True,
            overwrite=False,
            quote_identifiers=False
        )
        
        return success
    except Exception as e:
        st.error(f"生データアップロードエラー: {e}")
        import traceback
        st.code(traceback.format_exc())
        return False

def upload_aggregated_to_snowflake(conn, table_name: str, df: pd.DataFrame, company_name: str):
    """集計済みDataFrameをSnowflakeにアップロード"""
    try:
        # company_name列を追加
        df_upload = df.copy()
        df_upload.insert(0, 'PT企業名', company_name)
        
        # カーソルを取得
        cursor = conn.cursor()
        
        # テーブルが存在しない場合は作成
        columns = []
        columns.append('PT企業名 STRING')
        for col in df.columns:
            if col == 'user_name':
                columns.append(f'"{col}" STRING')
            else:
                columns.append(f'"{col}" NUMBER')
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {', '.join(columns)}
        )
        """
        cursor.execute(create_table_sql)
        
        # データを挿入
        for _, row in df_upload.iterrows():
            placeholders = ', '.join(['%s'] * len(row))
            columns_str = ', '.join([f'"{col}"' for col in df_upload.columns])
            insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
            cursor.execute(insert_sql, tuple(row))
        
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        st.error(f"集計データアップロードエラー: {e}")
        return False

def generate_aggregation_sql(raw_table_name: str, target_view_name: str = None) -> str:
    """Snowflake用の集計SQLクエリを生成（基準内/基準外含む）"""
    if target_view_name is None:
        target_view_name = f"{raw_table_name}_AGGREGATED"
    
    sql = f"""
-- バッテリー交換実績集計ビュー（基準内/基準外含む）
-- PT企業毎、ユーザー毎、自転車メーカー毎の集計

CREATE OR REPLACE VIEW {target_view_name} AS
WITH base_data AS (
    SELECT 
        user_company_所属_ AS pt_company,
        user_name,
        自転車メーカー名 AS bike_maker,
        battery_remaining,
        CASE 
            -- Panasonic: 25%以上が基準外
            WHEN 自転車メーカー名 = 'Panasonic' THEN 
                CASE WHEN battery_remaining >= 25 THEN '基準外' ELSE '基準内' END
            -- YAMAHA: 70%以上が基準外
            WHEN 自転車メーカー名 = 'YAMAHA' THEN 
                CASE WHEN battery_remaining >= 70 THEN '基準外' ELSE '基準内' END
            -- DBS: 50%以上が基準外（ただし100%は基準内）
            WHEN 自転車メーカー名 = 'DBS' THEN 
                CASE 
                    WHEN battery_remaining = 100 THEN '基準内'
                    WHEN battery_remaining >= 50 THEN '基準外' 
                    ELSE '基準内' 
                END
            -- glafit: 50%以上が基準外
            WHEN 自転車メーカー名 = 'glafit' THEN 
                CASE WHEN battery_remaining >= 50 THEN '基準外' ELSE '基準内' END
            -- シナネンサイクル: 40%以上が基準外
            WHEN 自転車メーカー名 = 'シナネンサイクル' THEN 
                CASE WHEN battery_remaining >= 40 THEN '基準外' ELSE '基準内' END
            ELSE NULL
        END AS standard_flag
    FROM {raw_table_name}
    WHERE user_company_所属_ IS NOT NULL
),
pivot_data AS (
    SELECT 
        pt_company,
        user_name,
        -- Panasonic
        SUM(CASE WHEN bike_maker = 'Panasonic' AND standard_flag = '基準内' THEN 1 ELSE 0 END) AS panasonic_kijun_nai,
        SUM(CASE WHEN bike_maker = 'Panasonic' AND standard_flag = '基準外' THEN 1 ELSE 0 END) AS panasonic_kijun_gai,
        SUM(CASE WHEN bike_maker = 'Panasonic' THEN 1 ELSE 0 END) AS panasonic_total,
        -- YAMAHA
        SUM(CASE WHEN bike_maker = 'YAMAHA' AND standard_flag = '基準内' THEN 1 ELSE 0 END) AS yamaha_kijun_nai,
        SUM(CASE WHEN bike_maker = 'YAMAHA' AND standard_flag = '基準外' THEN 1 ELSE 0 END) AS yamaha_kijun_gai,
        SUM(CASE WHEN bike_maker = 'YAMAHA' THEN 1 ELSE 0 END) AS yamaha_total,
        -- DBS
        SUM(CASE WHEN bike_maker = 'DBS' AND standard_flag = '基準内' THEN 1 ELSE 0 END) AS dbs_kijun_nai,
        SUM(CASE WHEN bike_maker = 'DBS' AND standard_flag = '基準外' THEN 1 ELSE 0 END) AS dbs_kijun_gai,
        SUM(CASE WHEN bike_maker = 'DBS' THEN 1 ELSE 0 END) AS dbs_total,
        -- glafit
        SUM(CASE WHEN bike_maker = 'glafit' AND standard_flag = '基準内' THEN 1 ELSE 0 END) AS glafit_kijun_nai,
        SUM(CASE WHEN bike_maker = 'glafit' AND standard_flag = '基準外' THEN 1 ELSE 0 END) AS glafit_kijun_gai,
        SUM(CASE WHEN bike_maker = 'glafit' THEN 1 ELSE 0 END) AS glafit_total,
        -- シナネンサイクル
        SUM(CASE WHEN bike_maker = 'シナネンサイクル' AND standard_flag = '基準内' THEN 1 ELSE 0 END) AS shinanen_kijun_nai,
        SUM(CASE WHEN bike_maker = 'シナネンサイクル' AND standard_flag = '基準外' THEN 1 ELSE 0 END) AS shinanen_kijun_gai,
        SUM(CASE WHEN bike_maker = 'シナネンサイクル' THEN 1 ELSE 0 END) AS shinanen_total,
        -- KUROAD
        SUM(CASE WHEN bike_maker = 'KUROAD' THEN 1 ELSE 0 END) AS kuroad_total,
        -- 総合計
        COUNT(*) AS grand_total
    FROM base_data
    GROUP BY 1, 2
),
company_totals AS (
    SELECT 
        pt_company,
        '合計' AS user_name,
        SUM(panasonic_kijun_nai) AS panasonic_kijun_nai,
        SUM(panasonic_kijun_gai) AS panasonic_kijun_gai,
        SUM(panasonic_total) AS panasonic_total,
        SUM(yamaha_kijun_nai) AS yamaha_kijun_nai,
        SUM(yamaha_kijun_gai) AS yamaha_kijun_gai,
        SUM(yamaha_total) AS yamaha_total,
        SUM(dbs_kijun_nai) AS dbs_kijun_nai,
        SUM(dbs_kijun_gai) AS dbs_kijun_gai,
        SUM(dbs_total) AS dbs_total,
        SUM(glafit_kijun_nai) AS glafit_kijun_nai,
        SUM(glafit_kijun_gai) AS glafit_kijun_gai,
        SUM(glafit_total) AS glafit_total,
        SUM(shinanen_kijun_nai) AS shinanen_kijun_nai,
        SUM(shinanen_kijun_gai) AS shinanen_kijun_gai,
        SUM(shinanen_total) AS shinanen_total,
        SUM(kuroad_total) AS kuroad_total,
        SUM(grand_total) AS grand_total
    FROM pivot_data
    GROUP BY 1
)
SELECT * FROM pivot_data
UNION ALL
SELECT * FROM company_totals
ORDER BY pt_company, 
         CASE WHEN user_name = '合計' THEN 1 ELSE 0 END,
         grand_total DESC;

-- 使用例: 特定のPT企業のデータを取得
-- SELECT * FROM {target_view_name} WHERE pt_company = '渓濱商事';

-- 使用例: 全PT企業の基準外率
-- SELECT 
--     pt_company,
--     SUM(panasonic_kijun_gai + yamaha_kijun_gai + dbs_kijun_gai + glafit_kijun_gai + shinanen_kijun_gai) as total_kijun_gai,
--     SUM(grand_total) as total,
--     ROUND(100.0 * SUM(panasonic_kijun_gai + yamaha_kijun_gai + dbs_kijun_gai + glafit_kijun_gai + shinanen_kijun_gai) / SUM(grand_total), 2) as kijun_gai_rate
-- FROM {target_view_name}
-- WHERE user_name = '合計'
-- GROUP BY 1
-- ORDER BY 4 DESC;
"""
    return sql

def main():
    st.title("🔋 バッテリー交換実績集計アプリ")
    st.markdown("---")
    
    # サイドバー：ファイル選択とSnowflake設定
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # ファイルアップロード
        uploaded_file = st.file_uploader(
            "Excelファイルをアップロード",
            type=['xlsx', 'xls'],
            help="バッテリー交換実績データのExcelファイルをアップロードしてください"
        )
        
        st.markdown("---")
        st.subheader("Snowflake接続設定")
        
        sf_account = st.text_input("Account", help="例: abc12345.ap-northeast-1.aws")
        sf_user = st.text_input("User")
        sf_password = st.text_input("Password", type="password")
        sf_warehouse = st.text_input("Warehouse", value="COMPUTE_WH")
        sf_database = st.text_input("Database")
        sf_schema = st.text_input("Schema", value="PUBLIC")
        sf_table = st.text_input("Table Name", value="BATTERY_EXCHANGE_SUMMARY")
    
    # メインエリア
    if uploaded_file is not None:
        # アップロードされたファイルを読み込み
        try:
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
                        progress_bar.progress(20, text="PT企業を特定中...")
                        
                        # PT企業のリストを取得
                        companies = df['user_company(所属)'].dropna().unique()
                        total_companies = len(companies)
                        
                        status_text.text(f"📊 {total_companies}社のデータを集計中...")
                        progress_bar.progress(40, text=f"{total_companies}社の集計を実行中...")
                        
                        # 集計実行
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
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            # シート1: 集計結果
                            company_data.to_excel(writer, sheet_name='集計結果', index=False)
                            
                            # シート2: 生データ（該当企業のみ）
                            company_raw_data = df[df['user_company(所属)'] == selected_company].copy()
                            company_raw_data.to_excel(writer, sheet_name='生データ', index=False)
                        output.seek(0)
                        
                        st.download_button(
                            label=f"📥 {selected_company} のデータをダウンロード（集計+生データ）",
                            data=output,
                            file_name=f"{selected_company}_集計結果_生データ.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                        # データサマリーを表示
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("集計結果の行数", f"{len(company_data):,}行")
                        with col2:
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
                        
                        if download_option == "集計結果のみ":
                            output_all = io.BytesIO()
                            with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                for company, data in aggregated_data.items():
                                    # シート名は最大31文字
                                    sheet_name = company[:31]
                                    data.to_excel(writer, sheet_name=sheet_name, index=False)
                            output_all.seek(0)
                            
                            st.download_button(
                                label="📥 全PT企業のデータをダウンロード（集計のみ）",
                                data=output_all,
                                file_name="全PT企業_集計結果.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("⚠️ 生データを含むため、ファイルサイズが大きくなります")
                            
                            output_all = io.BytesIO()
                            with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                for company, data in aggregated_data.items():
                                    # 集計結果シート
                                    sheet_name = company[:28] + "_集計"
                                    data.to_excel(writer, sheet_name=sheet_name, index=False)
                                    
                                    # 生データシート
                                    company_raw = df[df['user_company(所属)'] == company].copy()
                                    sheet_name_raw = company[:28] + "_生"
                                    company_raw.to_excel(writer, sheet_name=sheet_name_raw, index=False)
                            output_all.seek(0)
                            
                            st.download_button(
                                label="📥 全PT企業のデータをダウンロード（集計+生データ）",
                                data=output_all,
                                file_name="全PT企業_集計結果_生データ.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                
                # Snowflakeアップロード
                st.markdown("---")
                st.header("☁️ Snowflakeへのアップロード")
                
                # アップロードモード選択
                upload_mode = st.radio(
                    "アップロードモードを選択",
                    options=["🔍 集計済みデータ", "📊 生データ（推奨）", "🔄 両方"],
                    help="""
                    - 集計済みデータ: Python側で集計した結果をアップロード
                    - 生データ（推奨）: 全データをアップロードし、Snowflake側で集計
                    - 両方: 生データと集計済みデータの両方をアップロード
                    """,
                    horizontal=True
                )
                
                if upload_mode == "🔍 集計済みデータ" or upload_mode == "🔄 両方":
                    st.subheader("📋 集計済みデータのアップロード")
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        upload_companies = st.multiselect(
                            "アップロードするPT企業を選択",
                            options=sorted(aggregated_data.keys()),
                            default=sorted(aggregated_data.keys())[:5],
                            key="aggregated_companies"
                        )
                    
                    with col2:
                        st.write("")
                        st.write("")
                        upload_agg_button = st.button("☁️ 集計データをアップロード", type="secondary", key="upload_agg")
                    
                    if upload_agg_button:
                        if not all([sf_account, sf_user, sf_password, sf_warehouse, sf_database, sf_schema]):
                            st.error("❌ Snowflake接続情報をすべて入力してください")
                        elif not upload_companies:
                            st.error("❌ アップロードする企業を選択してください")
                        else:
                            with st.spinner("Snowflakeに接続中..."):
                                conn = create_snowflake_connection(
                                    sf_account, sf_user, sf_password,
                                    sf_warehouse, sf_database, sf_schema
                                )
                            
                            if conn:
                                st.success("✅ Snowflakeに接続しました")
                                
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                total = len(upload_companies)
                                success_count = 0
                                
                                for i, company in enumerate(upload_companies):
                                    status_text.text(f"アップロード中: {company}")
                                    
                                    if upload_aggregated_to_snowflake(conn, sf_table, aggregated_data[company], company):
                                        success_count += 1
                                    
                                    progress_bar.progress((i + 1) / total)
                                
                                conn.close()
                                status_text.empty()
                                progress_bar.empty()
                                
                                if success_count == total:
                                    st.success(f"✅ {success_count}/{total}社のデータをSnowflakeにアップロードしました！")
                                else:
                                    st.warning(f"⚠️ {success_count}/{total}社のデータをアップロードしました")
                
                if upload_mode == "📊 生データ（推奨）" or upload_mode == "🔄 両方":
                    if upload_mode == "🔄 両方":
                        st.markdown("---")
                    
                    st.subheader("📊 生データのアップロード")
                    
                    st.info(f"""
                    💡 **推奨**: 生データ（全{len(df):,}行）をSnowflakeにアップロードします。
                    
                    **メリット:**
                    - ✅ Snowflakeで自由に集計・分析が可能
                    - ✅ 高速な処理（Snowflakeのクラスタリング機能を活用）
                    - ✅ SQLクエリで再集計が簡単
                    - ✅ 他のメンバーもアクセス可能
                    """)
                    
                    raw_table_name = st.text_input(
                        "生データテーブル名",
                        value="BATTERY_EXCHANGE_RAW",
                        key="raw_table_name"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        upload_raw_button = st.button(
                            "📤 生データをアップロード",
                            type="primary",
                            key="upload_raw",
                            use_container_width=True
                        )
                    
                    with col2:
                        generate_sql_button = st.button(
                            "📝 集計SQLを生成",
                            key="generate_sql",
                            use_container_width=True
                        )
                    
                    if upload_raw_button:
                        if not all([sf_account, sf_user, sf_password, sf_warehouse, sf_database, sf_schema]):
                            st.error("❌ Snowflake接続情報をすべて入力してください")
                        else:
                            with st.spinner("Snowflakeに接続中..."):
                                conn = create_snowflake_connection(
                                    sf_account, sf_user, sf_password,
                                    sf_warehouse, sf_database, sf_schema
                                )
                            
                            if conn:
                                st.success("✅ Snowflakeに接続しました")
                                
                                with st.spinner(f"📊 生データをアップロード中...（{len(df):,}行）"):
                                    progress_bar = st.progress(0, text="データを準備中...")
                                    
                                    # アップロード実行
                                    progress_bar.progress(30, text="Snowflakeにアップロード中...")
                                    success = upload_raw_data_to_snowflake(conn, raw_table_name, df)
                                    
                                    progress_bar.progress(100, text="完了！")
                                    progress_bar.empty()
                                
                                conn.close()
                                
                                if success:
                                    st.success(f"✅ 生データ（{len(df):,}行）をテーブル `{raw_table_name}` にアップロードしました！")
                                    st.balloons()
                                    
                                    # SQL生成の案内
                                    st.info("👉 次に「📝 集計SQLを生成」ボタンをクリックして、集計用のSQLクエリを取得してください。")
                                else:
                                    st.error("❌ 生データのアップロードに失敗しました")
                    
                    if generate_sql_button:
                        view_name = f"{raw_table_name}_AGGREGATED"
                        sql = generate_aggregation_sql(raw_table_name, view_name)
                        
                        st.success("✅ 集計SQLを生成しました")
                        
                        st.markdown("### 📝 生成されたSQLクエリ")
                        st.markdown(f"""
                        このSQLをSnowflakeで実行すると、`{view_name}` ビューが作成されます。
                        このビューは、PT企業毎、ユーザー毎、自転車メーカー毎の集計結果を提供します。
                        """)
                        
                        st.code(sql, language="sql")
                        
                        # SQLをダウンロード
                        st.download_button(
                            label="📥 SQLファイルをダウンロード",
                            data=sql,
                            file_name=f"{raw_table_name}_aggregation.sql",
                            mime="text/plain",
                            key="download_sql"
                        )
                        
                        # 使用例
                        with st.expander("📚 SQLクエリの使用例"):
                            st.markdown(f"""
                            ```sql
                            -- 特定のPT企業のデータを取得
                            SELECT * FROM {view_name} 
                            WHERE pt_company = '渓濱商事';
                            
                            -- 全PT企業のサマリー
                            SELECT 
                                pt_company,
                                SUM(total_count) as total_exchanges
                            FROM {view_name}
                            WHERE user_name = '合計'
                            GROUP BY 1
                            ORDER BY 2 DESC;
                            
                            -- メーカー別のシェア
                            SELECT 
                                SUM(panasonic_count) as panasonic,
                                SUM(yamaha_count) as yamaha,
                                SUM(dbs_count) as dbs,
                                SUM(glafit_count) as glafit,
                                SUM(shinanen_count) as shinanen_cycle,
                                SUM(kuroad_count) as kuroad
                            FROM {view_name}
                            WHERE user_name != '合計';
                            
                            -- ユーザーランキング（全体）
                            SELECT 
                                user_name,
                                pt_company,
                                total_count
                            FROM {view_name}
                            WHERE user_name != '合計'
                            ORDER BY total_count DESC
                            LIMIT 20;
                            ```
                            """)

        
        except Exception as e:
            st.error(f"❌ エラーが発生しました: {e}")
    
    else:
        # ファイルが選択されていない場合
        st.info("👈 サイドバーからExcelファイルをアップロードしてください")
        
        # デフォルトファイルの読み込みオプション
        default_file = "バッテリー交換_全国_先月.xlsx"
        if st.button(f"📂 デフォルトファイル ({default_file}) を使用"):
            try:
                with st.spinner("📂 ファイルを読み込み中..."):
                    df = load_excel_data(default_file)
                if df is not None:
                    st.session_state['df'] = df
                    st.session_state['default_file_loaded'] = True
                    st.success(f"✅ ファイル読み込み完了: {len(df):,}行のデータ")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ デフォルトファイルの読み込みに失敗しました: {e}")
        
        # デフォルトファイルが読み込まれている場合の処理
        if 'default_file_loaded' in st.session_state and st.session_state['default_file_loaded']:
            df = st.session_state['df']
            
            st.success(f"✅ ファイル読み込み完了: {len(df):,}行のデータ")
            
            # データプレビュー
            with st.expander("📊 データプレビュー（最初の10行）"):
                st.dataframe(df.head(10))
            
            # 集計実行ボタン
            if st.button("🔄 集計実行", type="primary", use_container_width=True, key="aggregate_default"):
                progress_bar = st.progress(0, text="集計を開始しています...")
                status_text = st.empty()
                
                try:
                    status_text.text("📊 データを分析中...")
                    progress_bar.progress(20, text="PT企業を特定中...")
                    
                    # PT企業のリストを取得
                    companies = df['user_company(所属)'].dropna().unique()
                    total_companies = len(companies)
                    
                    status_text.text(f"📊 {total_companies}社のデータを集計中...")
                    progress_bar.progress(40, text=f"{total_companies}社の集計を実行中...")
                    
                    # 集計実行
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
            
            # 集計結果の表示（既存のコードと同じ）
            if 'aggregated_data' in st.session_state:
                aggregated_data = st.session_state['aggregated_data']
                
                st.markdown("---")
                st.header("📈 集計結果")
                
                # PT企業選択
                selected_company = st.selectbox(
                    "PT企業を選択",
                    options=sorted(aggregated_data.keys()),
                    index=0,
                    key="company_select_default"
                )
                
                if selected_company:
                    company_data = aggregated_data[selected_company]
                    
                    # タブで表示を切り替え
                    tab1, tab2, tab3 = st.tabs(["📋 集計表", "📊 グラフ", "💾 Excel出力"])
                    
                    with tab1:
                        st.subheader(f"{selected_company} の集計結果")
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
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            # シート1: 集計結果
                            company_data.to_excel(writer, sheet_name='集計結果', index=False)
                            
                            # シート2: 生データ（該当企業のみ）
                            company_raw_data = df[df['user_company(所属)'] == selected_company].copy()
                            company_raw_data.to_excel(writer, sheet_name='生データ', index=False)
                        output.seek(0)
                        
                        st.download_button(
                            label=f"📥 {selected_company} のデータをダウンロード（集計+生データ）",
                            data=output,
                            file_name=f"{selected_company}_集計結果_生データ.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_single_default"
                        )
                        
                        # データサマリーを表示
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("集計結果の行数", f"{len(company_data):,}行")
                        with col2:
                            st.metric("生データの行数", f"{len(company_raw_data):,}行")
                        
                        # 全企業のデータを1つのExcelファイルに出力
                        st.markdown("---")
                        st.subheader("全PT企業のデータを一括ダウンロード")
                        
                        download_option_default = st.radio(
                            "ダウンロード形式を選択",
                            options=["集計結果のみ", "集計結果 + 生データ"],
                            horizontal=True,
                            key="download_all_option_default"
                        )
                        
                        if download_option_default == "集計結果のみ":
                            output_all = io.BytesIO()
                            with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                for company, data in aggregated_data.items():
                                    # シート名は最大31文字
                                    sheet_name = company[:31]
                                    data.to_excel(writer, sheet_name=sheet_name, index=False)
                            output_all.seek(0)
                            
                            st.download_button(
                                label="📥 全PT企業のデータをダウンロード（集計のみ）",
                                data=output_all,
                                file_name="全PT企業_集計結果.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_all_default"
                            )
                        else:
                            st.warning("⚠️ 生データを含むため、ファイルサイズが大きくなります")
                            
                            output_all = io.BytesIO()
                            with pd.ExcelWriter(output_all, engine='openpyxl') as writer:
                                for company, data in aggregated_data.items():
                                    # 集計結果シート
                                    sheet_name = company[:28] + "_集計"
                                    data.to_excel(writer, sheet_name=sheet_name, index=False)
                                    
                                    # 生データシート
                                    company_raw = df[df['user_company(所属)'] == company].copy()
                                    sheet_name_raw = company[:28] + "_生"
                                    company_raw.to_excel(writer, sheet_name=sheet_name_raw, index=False)
                            output_all.seek(0)
                            
                            st.download_button(
                                label="📥 全PT企業のデータをダウンロード（集計+生データ）",
                                data=output_all,
                                file_name="全PT企業_集計結果_生データ.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="download_all_default_with_raw"
                            )
                
                # Snowflakeアップロード
                st.markdown("---")
                st.header("☁️ Snowflakeへのアップロード")
                
                # アップロードモード選択
                upload_mode_default = st.radio(
                    "アップロードモードを選択",
                    options=["🔍 集計済みデータ", "📊 生データ（推奨）", "🔄 両方"],
                    help="""
                    - 集計済みデータ: Python側で集計した結果をアップロード
                    - 生データ（推奨）: 全データをアップロードし、Snowflake側で集計
                    - 両方: 生データと集計済みデータの両方をアップロード
                    """,
                    horizontal=True,
                    key="upload_mode_default"
                )
                
                if upload_mode_default == "🔍 集計済みデータ" or upload_mode_default == "🔄 両方":
                    st.subheader("📋 集計済みデータのアップロード")
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        upload_companies_default = st.multiselect(
                            "アップロードするPT企業を選択",
                            options=sorted(aggregated_data.keys()),
                            default=sorted(aggregated_data.keys())[:5],
                            key="upload_companies_default"
                        )
                    
                    with col2:
                        st.write("")
                        st.write("")
                        upload_agg_button_default = st.button("☁️ 集計データをアップロード", type="secondary", key="upload_agg_default")
                    
                    if upload_agg_button_default:
                        if not all([sf_account, sf_user, sf_password, sf_warehouse, sf_database, sf_schema]):
                            st.error("❌ Snowflake接続情報をすべて入力してください")
                        elif not upload_companies_default:
                            st.error("❌ アップロードする企業を選択してください")
                        else:
                            with st.spinner("Snowflakeに接続中..."):
                                conn = create_snowflake_connection(
                                    sf_account, sf_user, sf_password,
                                    sf_warehouse, sf_database, sf_schema
                                )
                            
                            if conn:
                                st.success("✅ Snowflakeに接続しました")
                                
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                total = len(upload_companies_default)
                                success_count = 0
                                
                                for i, company in enumerate(upload_companies_default):
                                    status_text.text(f"アップロード中: {company}")
                                    
                                    if upload_aggregated_to_snowflake(conn, sf_table, aggregated_data[company], company):
                                        success_count += 1
                                    
                                    progress_bar.progress((i + 1) / total)
                                
                                conn.close()
                                status_text.empty()
                                progress_bar.empty()
                                
                                if success_count == total:
                                    st.success(f"✅ {success_count}/{total}社のデータをSnowflakeにアップロードしました！")
                                else:
                                    st.warning(f"⚠️ {success_count}/{total}社のデータをアップロードしました")
                
                if upload_mode_default == "📊 生データ（推奨）" or upload_mode_default == "🔄 両方":
                    if upload_mode_default == "🔄 両方":
                        st.markdown("---")
                    
                    st.subheader("📊 生データのアップロード")
                    
                    st.info(f"""
                    💡 **推奨**: 生データ（全{len(df):,}行）をSnowflakeにアップロードします。
                    
                    **メリット:**
                    - ✅ Snowflakeで自由に集計・分析が可能
                    - ✅ 高速な処理（Snowflakeのクラスタリング機能を活用）
                    - ✅ SQLクエリで再集計が簡単
                    - ✅ 他のメンバーもアクセス可能
                    """)
                    
                    raw_table_name_default = st.text_input(
                        "生データテーブル名",
                        value="BATTERY_EXCHANGE_RAW",
                        key="raw_table_name_default"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        upload_raw_button_default = st.button(
                            "📤 生データをアップロード",
                            type="primary",
                            key="upload_raw_default",
                            use_container_width=True
                        )
                    
                    with col2:
                        generate_sql_button_default = st.button(
                            "📝 集計SQLを生成",
                            key="generate_sql_default",
                            use_container_width=True
                        )
                    
                    if upload_raw_button_default:
                        if not all([sf_account, sf_user, sf_password, sf_warehouse, sf_database, sf_schema]):
                            st.error("❌ Snowflake接続情報をすべて入力してください")
                        else:
                            with st.spinner("Snowflakeに接続中..."):
                                conn = create_snowflake_connection(
                                    sf_account, sf_user, sf_password,
                                    sf_warehouse, sf_database, sf_schema
                                )
                            
                            if conn:
                                st.success("✅ Snowflakeに接続しました")
                                
                                with st.spinner(f"📊 生データをアップロード中...（{len(df):,}行）"):
                                    progress_bar = st.progress(0, text="データを準備中...")
                                    
                                    # アップロード実行
                                    progress_bar.progress(30, text="Snowflakeにアップロード中...")
                                    success = upload_raw_data_to_snowflake(conn, raw_table_name_default, df)
                                    
                                    progress_bar.progress(100, text="完了！")
                                    progress_bar.empty()
                                
                                conn.close()
                                
                                if success:
                                    st.success(f"✅ 生データ（{len(df):,}行）をテーブル `{raw_table_name_default}` にアップロードしました！")
                                    st.balloons()
                                    
                                    # SQL生成の案内
                                    st.info("👉 次に「📝 集計SQLを生成」ボタンをクリックして、集計用のSQLクエリを取得してください。")
                                else:
                                    st.error("❌ 生データのアップロードに失敗しました")
                    
                    if generate_sql_button_default:
                        view_name = f"{raw_table_name_default}_AGGREGATED"
                        sql = generate_aggregation_sql(raw_table_name_default, view_name)
                        
                        st.success("✅ 集計SQLを生成しました")
                        
                        st.markdown("### 📝 生成されたSQLクエリ")
                        st.markdown(f"""
                        このSQLをSnowflakeで実行すると、`{view_name}` ビューが作成されます。
                        このビューは、PT企業毎、ユーザー毎、自転車メーカー毎の集計結果を提供します。
                        """)
                        
                        st.code(sql, language="sql")
                        
                        # SQLをダウンロード
                        st.download_button(
                            label="📥 SQLファイルをダウンロード",
                            data=sql,
                            file_name=f"{raw_table_name_default}_aggregation.sql",
                            mime="text/plain",
                            key="download_sql_default"
                        )
                        
                        # 使用例
                        with st.expander("📚 SQLクエリの使用例"):
                            st.markdown(f"""
                            ```sql
                            -- 特定のPT企業のデータを取得
                            SELECT * FROM {view_name} 
                            WHERE pt_company = '渓濱商事';
                            
                            -- 全PT企業のサマリー
                            SELECT 
                                pt_company,
                                SUM(total_count) as total_exchanges
                            FROM {view_name}
                            WHERE user_name = '合計'
                            GROUP BY 1
                            ORDER BY 2 DESC;
                            
                            -- メーカー別のシェア
                            SELECT 
                                SUM(panasonic_count) as panasonic,
                                SUM(yamaha_count) as yamaha,
                                SUM(dbs_count) as dbs,
                                SUM(glafit_count) as glafit,
                                SUM(shinanen_count) as shinanen_cycle,
                                SUM(kuroad_count) as kuroad
                            FROM {view_name}
                            WHERE user_name != '合計';
                            
                            -- ユーザーランキング（全体）
                            SELECT 
                                user_name,
                                pt_company,
                                total_count
                            FROM {view_name}
                            WHERE user_name != '合計'
                            ORDER BY total_count DESC
                            LIMIT 20;
                            ```
                            """)


if __name__ == "__main__":
    main()

