# ✅ デプロイメントチェックリスト

## 📋 公開前の最終確認

### ステップ1: パスワードハッシュの準備 ✅

**方法A: カスタムパスワードを設定（推奨）**

ターミナルで実行：
```bash
cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
python3 generate_password.py
```

生成されたハッシュ値をメモ：
```
パスワード: ____________（安全な場所に保管）
ハッシュ値: ________________________________________________________________
```

**方法B: デフォルトパスワードを使用（後で変更推奨）**

- ユーザー名: `admin`
- パスワード: `password`
- ハッシュ値: `5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8`

---

### ステップ2: GitHubリポジトリの作成 ⏳

1. **GitHubにログイン**
   - https://github.com にアクセス

2. **新しいリポジトリを作成**
   - 右上の「+」→「New repository」
   - リポジトリ名: `battery-exchange-app`（任意）
   - 説明: `バッテリー交換実績集計アプリ`
   - **Public**を選択 ⚠️
   - **Initialize this repository with: 何もチェックしない**
   - 「Create repository」をクリック

3. **リポジトリURLをメモ**
   ```
   https://github.com/YOUR_USERNAME/battery-exchange-app.git
   ```

---

### ステップ3: ローカルリポジトリの初期化 ⏳

ターミナルで実行：

```bash
cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"

# Git初期化
git init

# ファイルを追加
git add .

# 最終確認（機密ファイルが含まれていないか確認）
git status
# ✅ .xlsx ファイルが表示されないこと
# ✅ token ファイルが表示されないこと
# ✅ バッテリー交換_全国_先月.xlsx が表示されないこと

# コミット
git commit -m "Initial commit: バッテリー交換実績集計アプリ"

# GitHubに接続（YOUR_USERNAMEを実際のユーザー名に変更）
git remote add origin https://github.com/YOUR_USERNAME/battery-exchange-app.git

# メインブランチに変更
git branch -M main

# プッシュ
git push -u origin main
```

**Git認証について:**
- GitHubのPersonal Access Tokenが必要な場合があります
- Settings > Developer settings > Personal access tokens で作成

---

### ステップ4: Streamlit Community Cloudでデプロイ ⏳

1. **Streamlit Community Cloudにアクセス**
   - https://share.streamlit.io
   - 「Continue with GitHub」でログイン

2. **新しいアプリをデプロイ**
   - 「New app」ボタンをクリック
   
   **基本設定:**
   - Repository: `YOUR_USERNAME/battery-exchange-app`
   - Branch: `main`
   - Main file path: `app.py`
   
   **Advanced settings（重要！）をクリック:**
   - Environment variables に以下を追加:
     ```
     ENABLE_AUTH=true
     ```

3. **Deploy!** をクリック

---

### ステップ5: Secrets の設定 ⏳

デプロイ後（2-3分待つ）：

1. **アプリの設定を開く**
   - デプロイされたアプリのページで「⚙️」→「Settings」

2. **Secrets を設定**
   - 「Secrets」タブを開く
   - 以下を貼り付け（ハッシュ値は実際のものに変更）:

```toml
# 認証用パスワード（ハッシュ値）
[passwords]
admin = "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"

# 追加ユーザー（オプション）
# user1 = "別のハッシュ値"
# user2 = "さらに別のハッシュ値"

# Snowflake接続情報（オプション）
[snowflake]
account = "your_account.ap-northeast-1.aws"
user = "your_username"
password = "your_password"
warehouse = "COMPUTE_WH"
database = "your_database"
schema = "PUBLIC"
```

3. **Save** をクリック
4. アプリが自動的に再起動します

---

### ステップ6: 動作確認 ⏳

1. **アプリのURLにアクセス**
   - 例: `https://YOUR_USERNAME-battery-exchange-app-app-xxxxx.streamlit.app`

2. **ログイン画面が表示されることを確認**
   - ユーザー名: `admin`
   - パスワード: 設定したパスワード（デフォルトは `password`）

3. **ログイン後、アプリが正常に動作することを確認**
   - Excelファイルをアップロード
   - 集計を実行
   - 結果を確認

---

## 🎉 完了後の作業

### セキュリティ強化（推奨）

1. **パスワードを変更**（デフォルトを使用した場合）
   ```bash
   python3 generate_password.py
   ```
   新しいハッシュ値でSecretsを更新

2. **複数ユーザーの追加**
   必要に応じてSecretsに追加のユーザーを設定

3. **URLを限られたメンバーのみに共有**

### メンテナンス

- **アプリの更新**: コードを変更して `git push` すると自動デプロイ
- **ログの確認**: Streamlit Cloud の「Manage app」→「Logs」
- **リソース監視**: メモリやCPU使用状況を確認

---

## 🆘 トラブルシューティング

### ログイン画面が表示されない
→ Environment variables で `ENABLE_AUTH=true` が設定されているか確認

### パスワードが認証されない
→ Secrets のハッシュ値が正しいか確認

### Excelファイルがリポジトリに含まれてしまった
→ `git rm --cached *.xlsx` で削除してから再プッシュ

### デプロイエラー
→ Logs を確認、requirements.txt のパッケージバージョンを確認

---

## 📞 サポート

問題が発生した場合：
1. Streamlit Cloud の Logs を確認
2. `PUBLIC_DEPLOY.md` の詳細ガイドを参照
3. GitHubのissuesで質問

---

**準備完了！上記の手順に従って、ステップバイステップで進めてください！** 🚀

