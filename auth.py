"""
認証機能モジュール
Streamlit Community Cloud上でGoogle OAuth2.0によるログイン機能を提供
"""
import streamlit as st
import os
import requests

def check_password():
    """
    Google認証を求めて画面をロックする機能
    認証が成功するまでメインアプリを表示しない
    
    Returns:
        bool: 認証成功時True
    """
    # 既に認証済みの場合
    if st.session_state.get("authenticated_user"):
        return True

    if "google" not in st.secrets:
        st.error("⚠️ 認証設定エラー: コントロールパネルで Secrets を設定してください")
        st.code("""
[google]
client_id = "YOUR_CLIENT_ID"
client_secret = "YOUR_CLIENT_SECRET"
redirect_uri = "http://localhost:8501" # 実際のURLに合わせて変更
        """)
        return False

    client_id = st.secrets["google"]["client_id"]
    client_secret = st.secrets["google"]["client_secret"]
    redirect_uri = st.secrets["google"].get("redirect_uri", "http://localhost:8501")

    # コールバック判定 (URLに code クエリパラメータがあるか)
    if "code" in st.query_params:
        code = st.query_params["code"]
        
        # 安全のためにURLから認証コードを削除する
        st.query_params.clear()
        
        # トークン取得APIのデータ構築
        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        
        try:
            # トークンを取得 (PKCE不要のスタンダードWebサーバーフロー)
            res = requests.post("https://oauth2.googleapis.com/token", data=data)
            
            if res.status_code == 200:
                tokens = res.json()
                access_token = tokens["access_token"]
                
                # Google UserInfo API を叩いてメールアドレス等を取得
                user_info_response = requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_info = user_info_response.json()
                
                # メールアドレスをセッションに保存
                email = user_info.get("email", "Unknown Email")
                st.session_state["authenticated_user"] = email
                
                st.rerun() # リロードしてログイン状態を反映
            else:
                st.error(f"トークンの取得に失敗しました: {res.text}")
                
        except Exception as e:
            st.error(f"認証中にエラーが発生しました: {e}")

    # ログインフォームを表示（未認証時）
    st.markdown("## 🔐 ログイン")
    st.markdown("このアプリは認証が必要です。Googleアカウントでログインしてください。")
    
    # 手動でOAuth2用URLを構築
    authorization_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope=openid%20email%20profile&"
        f"access_type=online&"
        f"prompt=consent"
    )
    
    # ログインボタン風リンクをHTMLで出力
    html_button = f"""
    <div style="margin-top: 20px;">
        <a href="{authorization_url}" target="_blank" rel="noopener noreferrer"
           style="display: inline-block; padding: 10px 20px; 
                  background-color: #4285F4; color: white; 
                  text-decoration: none; border-radius: 4px; font-weight: bold; border: 1px solid #357AE8;">
           Googleアカウントでログイン
        </a>
    </div>
    """
    
    st.markdown(html_button, unsafe_allow_html=True)
    
    return False


def logout():
    """ログアウト機能"""
    for key in ["authenticated_user"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def get_authenticated_user():
    """
    認証済みのユーザー名(Email)を取得
    """
    return st.session_state.get("authenticated_user", "Unknown")
