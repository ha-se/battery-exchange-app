"""
認証機能モジュール
Streamlit Community Cloud のパブリックアプリに認証を追加
"""
import streamlit as st
import hashlib
import hmac

def check_password():
    """
    パスワード認証を実装
    認証が成功するまでメインアプリを表示しない
    
    Returns:
        bool: 認証成功時True
    """
    
    def password_entered():
        """パスワードが入力されたときのコールバック"""
        username = st.session_state["username"]
        password = st.session_state["password"]
        
        # ユーザー情報（実際の値は secrets.toml に保存）
        # デフォルトのユーザー情報（テスト用）
        if "passwords" in st.secrets:
            # secrets.toml から読み込み
            users = st.secrets["passwords"]
        else:
            # デフォルト（開発時のみ）
            users = {
                "admin": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",  # password
                "user1": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",  # 123456
            }
        
        # パスワードをハッシュ化
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # 認証チェック
        if username in users and users[username] == password_hash:
            st.session_state["password_correct"] = True
            st.session_state["authenticated_user"] = username
            del st.session_state["password"]  # パスワードを削除
        else:
            st.session_state["password_correct"] = False

    # 既に認証済みの場合
    if st.session_state.get("password_correct", False):
        return True

    # ログインフォームを表示
    st.markdown("## 🔐 ログイン")
    st.markdown("このアプリは認証が必要です。ユーザー名とパスワードを入力してください。")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.text_input("ユーザー名", key="username", on_change=password_entered)
        st.text_input("パスワード", type="password", key="password", on_change=password_entered)
        
        if st.session_state.get("password_correct", None) == False:
            st.error("😕 ユーザー名またはパスワードが正しくありません")
        
        st.markdown("---")
        st.caption("💡 初期ユーザー名: `admin`, パスワード: `password` (変更してください)")
    
    return False


def logout():
    """ログアウト機能"""
    for key in ["password_correct", "authenticated_user", "username", "password"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def get_authenticated_user():
    """
    認証済みのユーザー名を取得
    
    Returns:
        str: ユーザー名
    """
    return st.session_state.get("authenticated_user", "Unknown")


def generate_password_hash(password: str) -> str:
    """
    パスワードのハッシュ値を生成（セットアップ用）
    
    Args:
        password: 平文のパスワード
        
    Returns:
        str: SHA256ハッシュ値
    """
    return hashlib.sha256(password.encode()).hexdigest()

