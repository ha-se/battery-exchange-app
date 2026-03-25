"""
バッテリー交換実績集計アプリ
PT企業(user_company)毎に、user_nameと自転車メーカー別の集計を行います。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import io
import os
import zipfile

try:
    import snowflake.connector
    from snowflake.connector.pandas_tools import write_pandas
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False

from constants import TEMP_COLS
from processing import aggregate_by_company_and_maker

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
        df_clean = df_clean.drop(columns=[col for col in TEMP_COLS if col in df_clean.columns], errors='ignore')

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
        st.caption("Version: 2025-12-30-v10 (全企業ダウンロード改善:統合Excel+ZIP)")

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

                    status_text.text(f"🔍 重複データを検出中...（{len(df):,}行）")
                    progress_bar.progress(30, text="重複チェック実行中...")

                    # 集計実行（重複検出を含む、自社交換分を除外）
                    aggregated_data, aggregated_by_bike, self_exchange_df = aggregate_by_company_and_maker(df)

                    progress_bar.progress(90, text="集計結果を準備中...")
                    st.session_state['aggregated_data'] = aggregated_data
                    st.session_state['aggregated_by_bike'] = aggregated_by_bike
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
                        zip_buffer = io.BytesIO()

                        # 生データから一時列を削除
                        df_clean = df.copy()
                        df_clean = df_clean.drop(columns=[col for col in TEMP_COLS if col in df_clean.columns], errors='ignore')

                        # 自社交換分のデータを準備
                        self_exchange_clean = None
                        if 'self_exchange_df' in st.session_state and not st.session_state['self_exchange_df'].empty:
                            self_exchange_clean = st.session_state['self_exchange_df'].copy()
                            self_exchange_clean = self_exchange_clean.drop(columns=[col for col in TEMP_COLS if col in self_exchange_clean.columns], errors='ignore')

                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                            progress_bar = st.progress(0)
                            total = len(aggregated_data) + 1  # 企業ごとのファイル + 全企業まとめファイル

                            # 全企業の集計結果をまとめたExcelファイルを作成
                            all_companies_excel = io.BytesIO()
                            with pd.ExcelWriter(all_companies_excel, engine='openpyxl') as writer:
                                all_companies_data = []

                                for company, data in aggregated_data.items():
                                    company_with_name = data.copy()
                                    company_with_name.insert(0, 'PT企業名', company)
                                    all_companies_data.append(company_with_name)

                                combined_df = pd.concat(all_companies_data, ignore_index=True)
                                combined_df.to_excel(writer, sheet_name='全PT企業集計', index=False)

                                if self_exchange_clean is not None and not self_exchange_clean.empty:
                                    self_exchange_clean.to_excel(writer, sheet_name='自社交換分', index=False)

                            all_companies_excel.seek(0)
                            zip_file.writestr("全企業_集計結果.xlsx", all_companies_excel.getvalue())
                            progress_bar.progress(1 / total)

                            # 各企業ごとに1つのExcelファイルを作成
                            for idx, (company, data) in enumerate(aggregated_data.items()):
                                excel_buffer = io.BytesIO()

                                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                    data.to_excel(writer, sheet_name='集計結果', index=False)

                                    company_raw = df_clean[df_clean['user_company(所属)'] == company].copy()
                                    company_raw.to_excel(writer, sheet_name='生データ', index=False)

                                    if self_exchange_clean is not None and not self_exchange_clean.empty:
                                        company_self_exchange = self_exchange_clean[self_exchange_clean['user_company(所属)'] == company].copy()
                                        if not company_self_exchange.empty:
                                            company_self_exchange.to_excel(writer, sheet_name='自社交換分', index=False)

                                safe_company_name = company.replace('/', '_').replace('\\', '_')
                                zip_file.writestr(
                                    f"{safe_company_name}_集計結果_生データ.xlsx",
                                    excel_buffer.getvalue()
                                )

                                progress_bar.progress((idx + 2) / total)

                            # bike_company毎のローデータエクセルを作成
                            e_col_name = df.attrs.get('e_column_name', None) if hasattr(df, 'attrs') else None
                            if not e_col_name and len(df.columns) > 4:
                                e_col_name = df.columns[4]

                            if e_col_name and e_col_name in df_clean.columns:
                                bike_excel_buffer = io.BytesIO()
                                with pd.ExcelWriter(bike_excel_buffer, engine='openpyxl') as writer:
                                    bike_companies = df_clean[e_col_name].dropna().unique()
                                    for bike_company in bike_companies:
                                        company_raw = df_clean[df_clean[e_col_name] == bike_company].copy()
                                        safe_sheet_name = str(bike_company)[:31].replace('/', '_').replace('\\', '_').replace('[', '').replace(']', '').replace('*', '').replace('?', '').replace(':', '')
                                        if not safe_sheet_name:
                                            safe_sheet_name = "不明"
                                        company_raw.to_excel(writer, sheet_name=safe_sheet_name, index=False)

                                bike_excel_buffer.seek(0)
                                zip_file.writestr("bike_company毎_ローデータ.xlsx", bike_excel_buffer.getvalue())

                            progress_bar.empty()

                        zip_buffer.seek(0)
                        st.session_state['all_excel_data'] = zip_buffer.getvalue()
                        st.session_state['all_excel_filename'] = "全PT企業_集計結果_生データ.zip"
                        st.session_state['all_excel_mime'] = "application/zip"
                        st.success(f"✅ ZIPファイルの準備完了！（全企業_集計結果.xlsx + {len(aggregated_data)}社のExcelファイル + bike_company毎_ローデータ.xlsx）")

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
