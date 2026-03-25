"""
認証機能モジュール
Streamlit Secretsを使用し、設定されたユーザー名とパスワードハッシュでのシンプルな認証を提供
"""
import streamlit as st
import hashlib

def generate_password_hash(password: str) -> str:
    """パスワードのハッシュを計算"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password():
    """
    パスワード認証機能
    認証が成功するまでメインアプリを表示しない
    
    Returns:
        bool: 認証成功時True
    """
    if "authenticated_user" in st.session_state and st.session_state["authenticated_user"]:
        return True

    st.markdown("## 🔐 ログイン")
    
    if "passwords" not in st.secrets:
        st.error("⚠️ 認証設定エラー: .streamlit/secrets.toml に [passwords] を設定してください")
        st.code('''
[passwords]
# generate_password.py で生成したハッシュ値を設定します
admin = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
        ''')
        return False

    with st.form("login_form"):
        username = st.text_input("ユーザー名")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン")
        
        if submit:
            if username in st.secrets["passwords"]:
                # ユーザーの入力したパスワードのハッシュ値を計算
                input_hash = generate_password_hash(password)
                # Secretsに保存されているハッシュ値と比較
                stored_hash = st.secrets["passwords"][username]
                
                if input_hash == stored_hash:
                    st.session_state["authenticated_user"] = username
                    st.success("ログインに成功しました。")
                    st.rerun()
                else:
                    st.error("😕 パスワードが間違っています")
            else:
                st.error("😕 ユーザー名が間違っています")
                
    return False

def logout():
    """ログアウト機能"""
    if "authenticated_user" in st.session_state:
        del st.session_state["authenticated_user"]
    st.rerun()

def get_authenticated_user():
    """
    認証済みのユーザー名を取得
    """
    return st.session_state.get("authenticated_user", "Unknown")
