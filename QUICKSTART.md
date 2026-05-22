# 🚀 クイックスタートガイド

バッテリー交換実績集計アプリを今すぐ公開する方法を説明します。

## 📋 公開前のチェックリスト

- [x] アプリが正常に動作することを確認
- [x] 機密情報が`.gitignore`に含まれている
- [x] Excelファイルがリポジトリに含まれていない
- [x] `token`ファイルがリポジトリに含まれていない

## 🎯 最も簡単な方法: Streamlit Community Cloud

### 所要時間: 約10分

### ステップ1: GitHubリポジトリの作成（5分）

1. **GitHubにログイン**
   - https://github.com にアクセス
   - アカウントを持っていない場合は作成

2. **新しいリポジトリを作成**
   - 右上の「+」→「New repository」をクリック
   - リポジトリ名: `battery-exchange-app`（任意）
   - **必ず「Private」を選択**（重要！）
   - 「Create repository」をクリック

3. **ローカルからプッシュ**
   ```bash
   cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
   
   # Gitの初期化
   git init
   
   # ファイルを追加
   git add .
   
   # コミット
   git commit -m "Initial commit: バッテリー交換実績集計アプリ"
   
   # GitHubに接続（YOUR_USERNAMEを自分のユーザー名に変更）
   git remote add origin https://github.com/YOUR_USERNAME/battery-exchange-app.git
   
   # プッシュ
   git branch -M main
   git push -u origin main
   ```

### ステップ2: Streamlit Community Cloudでデプロイ（5分）

1. **Streamlit Community Cloudにアクセス**
   - https://share.streamlit.io にアクセス
   - 「Sign in」→「Continue with GitHub」でログイン

2. **アプリをデプロイ**
   - 「New app」ボタンをクリック
   - 以下を入力:
     - **Repository**: `YOUR_USERNAME/battery-exchange-app`
     - **Branch**: `main`
     - **Main file path**: `app.py`
   - 「Deploy!」をクリック

3. **完了！**
   - 数分でアプリがデプロイされます
   - URLが発行されます（例: `https://your-app.streamlit.app`）

### ステップ3: Snowflake接続情報の設定（オプション）

アプリの設定画面から「Secrets」を開き、以下を入力:

```toml
[snowflake]
account = "your_account.ap-northeast-1.aws"
user = "your_username"
password = "your_password"
warehouse = "COMPUTE_WH"
database = "your_database"
schema = "PUBLIC"
```

## 🔒 セキュリティ設定

### URLの共有
- ✅ アプリのURLは社内のメンバーのみに共有
- ❌ 公開のウェブサイトには掲載しない

### アクセス制限
Streamlit Community Cloudでは基本認証がないため:
1. URLを知っている人のみがアクセス可能
2. より強固な認証が必要な場合は、社内サーバーでのホスティングを検討

## 🏢 社内サーバーでの公開（代替方法）

より高いセキュリティが必要な場合:

### 簡単な方法: デプロイスクリプトを使用

```bash
cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
./deploy.sh
```

オプション2「ローカル/社内サーバー」を選択すると、すぐに起動できます。

### Docker を使用する場合

```bash
# Docker イメージのビルド
docker build -t battery-exchange-app .

# コンテナの起動
docker run -p 8501:8501 battery-exchange-app

# または docker-compose を使用
docker-compose up -d
```

アクセス: http://localhost:8501

## 📱 使い方

1. アプリのURLにアクセス
2. Excelファイルをアップロードまたはデフォルトファイルを使用
3. 「🔄 集計実行」ボタンをクリック
4. PT企業を選択して結果を確認
5. 必要に応じてExcel出力またはSnowflakeにアップロード

## 🆘 トラブルシューティング

### GitHubへのプッシュでエラーが出る

**問題**: `git push`でエラーが発生

**解決策**:
```bash
# GitHubの認証設定
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Personal Access Tokenを使用
# GitHub Settings > Developer settings > Personal access tokens で作成
```

### Streamlitアプリが起動しない

**問題**: デプロイ後にエラーが表示される

**解決策**:
1. ログを確認（Streamlit Cloud の「Manage app」→「Logs」）
2. `requirements.txt`のパッケージバージョンを確認
3. Pythonのバージョンを確認（3.9以上）

### メモリエラー

**問題**: 大量データ処理時にメモリ不足

**解決策**:
- Streamlit Community Cloud: 有料プランにアップグレード
- 社内サーバー: メモリを増設

## 📚 詳細情報

より詳しい情報は以下を参照:
- `DEPLOYMENT.md`: 詳細なデプロイガイド
- `README.md`: アプリの機能説明
- Streamlit公式ドキュメント: https://docs.streamlit.io

## 💡 ヒント

- **定期的な更新**: アプリを改善したら `git push` でデプロイが自動更新されます
- **バックアップ**: GitHubがバージョン管理をしてくれるので安心
- **共同開発**: チームメンバーをGitHubリポジトリに招待して共同開発可能

---

**準備完了！** 上記の手順に従って、今すぐアプリを公開できます！🎉

