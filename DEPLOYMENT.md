# 🚀 デプロイメントガイド

バッテリー交換実績集計アプリのデプロイ方法について説明します。

## 📋 目次

1. [公開オプションの選択](#公開オプションの選択)
2. [Streamlit Community Cloudでの公開](#streamlit-community-cloudでの公開)
3. [社内サーバーでの公開](#社内サーバーでの公開)
4. [クラウドプラットフォームでの公開](#クラウドプラットフォームでの公開)
5. [セキュリティとプライバシー](#セキュリティとプライバシー)

## 公開オプションの選択

### オプション1: Streamlit Community Cloud（推奨 - 最も簡単）

**メリット:**
- ✅ 無料で使用可能
- ✅ GitHubと連携して自動デプロイ
- ✅ HTTPS対応
- ✅ 簡単なシークレット管理
- ✅ メンテナンスが不要

**デメリット:**
- ❌ パブリックまたはプライベートGitHubリポジトリが必要
- ❌ 基本的にインターネット経由でアクセス
- ❌ リソース制限あり（無料プラン）

**適している場合:**
- 社内の限られたメンバーで使用
- GitHubのプライベートリポジトリで管理可能
- パスワード認証で十分なセキュリティレベル

### オプション2: 社内サーバーでの公開

**メリット:**
- ✅ 完全に社内ネットワーク内で完結
- ✅ セキュリティレベルが高い
- ✅ カスタマイズ可能

**デメリット:**
- ❌ サーバーの準備とメンテナンスが必要
- ❌ IT部門の協力が必要

**適している場合:**
- 高いセキュリティが必要
- 既存の社内サーバーインフラがある
- 社外からのアクセスが不要

### オプション3: クラウドプラットフォーム（AWS/Azure/GCP）

**メリット:**
- ✅ スケーラブル
- ✅ 高いセキュリティ設定が可能
- ✅ VPN経由でのアクセス制限可能

**デメリット:**
- ❌ 費用がかかる
- ❌ 設定が複雑
- ❌ クラウド知識が必要

**適している場合:**
- 既にクラウドインフラを使用している
- 大規模な利用を想定
- 高度なセキュリティ要件がある

## Streamlit Community Cloudでの公開

### ステップ1: GitHubリポジトリの準備

1. **GitHubアカウントの作成**（未作成の場合）
   - https://github.com にアクセス
   - アカウントを作成

2. **プライベートリポジトリの作成**
   ```bash
   # 現在のディレクトリでGitリポジトリを初期化
   cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
   git init
   git add .
   git commit -m "Initial commit: バッテリー交換実績集計アプリ"
   
   # GitHubにプッシュ（事前にGitHubでリポジトリを作成しておく）
   git remote add origin https://github.com/YOUR_USERNAME/battery-exchange-app.git
   git branch -M main
   git push -u origin main
   ```

3. **リポジトリをプライベートに設定**
   - GitHubのリポジトリ設定で「Private」を選択

### ステップ2: Streamlit Community Cloudでのデプロイ

1. **Streamlit Community Cloudにアクセス**
   - https://share.streamlit.io にアクセス
   - GitHubアカウントでログイン

2. **新しいアプリをデプロイ**
   - 「New app」をクリック
   - リポジトリ、ブランチ、メインファイル（app.py）を選択
   - 「Deploy!」をクリック

3. **シークレットの設定**
   - アプリの設定から「Secrets」を開く
   - 以下の形式でSnowflake接続情報を設定：

```toml
# .streamlit/secrets.toml (Streamlit Cloudの設定画面で入力)

[snowflake]
account = "your_account.ap-northeast-1.aws"
user = "your_username"
password = "your_password"
warehouse = "COMPUTE_WH"
database = "your_database"
schema = "PUBLIC"
```

4. **アプリコードでシークレットを使用**
   - サイドバーの入力フィールドにデフォルト値として設定可能

### ステップ3: アクセス制限の設定

Streamlit Community Cloudでは基本認証がないため、以下の方法でアクセスを制限します：

1. **方法1: URLを非公開にする**
   - URLを知っている人のみアクセス可能
   - 社内のみで共有

2. **方法2: 認証機能を追加**（オプション）
   - `streamlit-authenticator`パッケージを使用
   - ユーザー名・パスワード認証を実装

## 社内サーバーでの公開

### 必要な環境
- Python 3.9以上
- サーバーOS（Linux推奨）
- ネットワークアクセス

### デプロイ手順

1. **アプリケーションのコピー**
   ```bash
   # サーバーにアプリをコピー
   scp -r battery user@server:/path/to/apps/
   ```

2. **依存関係のインストール**
   ```bash
   cd /path/to/apps/battery
   python3 -m pip install -r requirements.txt
   ```

3. **systemdサービスの作成**（自動起動）
   ```bash
   sudo nano /etc/systemd/system/battery-app.service
   ```

   内容:
   ```ini
   [Unit]
   Description=Battery Exchange App
   After=network.target

   [Service]
   Type=simple
   User=your_user
   WorkingDirectory=/path/to/apps/battery
   ExecStart=/usr/bin/python3 -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

4. **サービスの起動**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable battery-app
   sudo systemctl start battery-app
   ```

5. **ファイアウォールの設定**
   ```bash
   sudo ufw allow 8501/tcp
   ```

6. **リバースプロキシの設定**（HTTPS化）
   - Nginx または Apache を使用
   - Let's Encrypt で SSL証明書を取得

## クラウドプラットフォームでの公開

### AWS（例）

1. **EC2インスタンスの起動**
2. **セキュリティグループの設定**
3. **アプリのデプロイ**（社内サーバーと同様）
4. **ELB（ロードバランサー）の設定**（オプション）
5. **Route 53でドメイン設定**（オプション）

### Azure（例）

1. **App Serviceの作成**
2. **コンテナイメージのビルド**
3. **Azure Container Registryへのプッシュ**
4. **App Serviceでのデプロイ**

## セキュリティとプライバシー

### 重要な注意事項

1. **機密情報の管理**
   - ✅ `.gitignore` でExcelファイル、tokenファイルを除外済み
   - ✅ Snowflake接続情報は環境変数またはシークレット管理
   - ❌ ハードコードしない

2. **データの暗号化**
   - 通信は必ずHTTPS経由
   - Snowflakeへの接続も暗号化

3. **アクセス制御**
   - 必要最小限のメンバーのみアクセス可能に
   - ログイン認証の実装を検討

4. **監査ログ**
   - アクセスログの記録
   - 定期的な確認

### 認証機能の追加（オプション）

`streamlit-authenticator`を使用した認証実装例：

```python
import streamlit_authenticator as stauth

# ユーザー情報
names = ['田中太郎', '佐藤花子']
usernames = ['tanaka', 'sato']
passwords = ['password1', 'password2']  # 実際にはハッシュ化

hashed_passwords = stauth.Hasher(passwords).generate()

authenticator = stauth.Authenticate(
    names, usernames, hashed_passwords,
    'battery_app', 'abcdef', cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status:
    authenticator.logout('Logout', 'main')
    # ここにアプリのメインコード
elif authentication_status == False:
    st.error('ユーザー名またはパスワードが正しくありません')
elif authentication_status == None:
    st.warning('ユーザー名とパスワードを入力してください')
```

## トラブルシューティング

### よくある問題

1. **メモリエラー**
   - 解決: サーバーのメモリを増やす、またはバッチサイズを調整

2. **接続タイムアウト**
   - 解決: ファイアウォール設定を確認

3. **パッケージのインストールエラー**
   - 解決: Python のバージョンを確認（3.9以上）

## サポート

デプロイに関する質問や問題があれば、開発チームまでお問い合わせください。

