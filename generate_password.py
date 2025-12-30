#!/usr/bin/env python3
"""
パスワードハッシュ生成ツール
Streamlit認証用のパスワードハッシュ（SHA256）を生成します
"""
import hashlib

def generate_password_hash(password: str) -> str:
    """
    パスワードのSHA256ハッシュ値を生成
    
    Args:
        password: 平文のパスワード
        
    Returns:
        str: SHA256ハッシュ値（16進数文字列）
    """
    return hashlib.sha256(password.encode()).hexdigest()


def main():
    """メイン処理"""
    print("=" * 70)
    print("パスワードハッシュ生成ツール")
    print("=" * 70)
    print()
    print("このツールは、Streamlit認証用のパスワードハッシュを生成します。")
    print("生成されたハッシュ値を .streamlit/secrets.toml に設定してください。")
    print()
    print("例:")
    print('[passwords]')
    print('admin = "生成されたハッシュ値"')
    print('user1 = "別のハッシュ値"')
    print()
    print("=" * 70)
    print()
    
    # サンプルハッシュ値を表示
    print("📝 参考: よく使用されるパスワードのハッシュ値")
    print("-" * 70)
    samples = [
        ("password", "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"),
        ("123456", "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92"),
        ("admin", "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"),
    ]
    
    for pwd, hash_val in samples:
        print(f'"{pwd}" → {hash_val}')
    
    print("-" * 70)
    print()
    print("⚠️  注意: 上記は例です。本番環境では独自の安全なパスワードを使用してください")
    print()
    print("=" * 70)
    print()
    
    # パスワードハッシュ生成ループ
    while True:
        password = input("新しいパスワードを入力 (終了: 'q' または Ctrl+C): ").strip()
        
        if password.lower() == 'q':
            print("\n終了します。")
            break
        
        if not password:
            print("❌ パスワードが空です。もう一度入力してください。\n")
            continue
        
        # パスワードの強度チェック
        if len(password) < 6:
            print("⚠️  警告: パスワードが短すぎます（6文字以上を推奨）")
        
        # ハッシュ値を生成
        hash_value = generate_password_hash(password)
        
        print()
        print("✅ ハッシュ値が生成されました:")
        print("-" * 70)
        print(f"パスワード: {password}")
        print(f"ハッシュ値: {hash_value}")
        print("-" * 70)
        print()
        print("📋 Secrets の設定例:")
        print(f'username = "{hash_value}"')
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n中断されました。")
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")

