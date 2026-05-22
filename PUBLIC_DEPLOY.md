# 🌐 パブリックリポジトリでの公開ガイド

Streamlit Community CloudのPrivate枠を使用済みの場合、パブリックリポジトリで安全に公開する方法を説明します。

## ⚠️ 重要な注意事項

パブリックリポジトリ = 誰でもコードを見ることができる

**必須対策:**
1. ✅ 機密データを含めない
2. ✅ 認証機能を有効化
3. ✅ パスワードをハッシュ化
4. ✅ Snowflake接続情報は環境変数で管理

## 🔐 セキュリティ対策（実装済み）

### 1. 認証機能
- ユーザー名・パスワード認証を実装
- パスワードはSHA256でハッシュ化
- ログイン成功後のみアプリにアクセス可能

### 2. 機密データの除外
- `.gitignore` で以下を除外:
  - Excelファイル（`*.xlsx`, `*.xls`）
  - tokenファイル
  - secrets.toml
  - 環境変数ファイル

### 3. 環境変数での設定
- Snowflake接続情報は Streamlit Secrets で管理
- パスワードハッシュも Secrets で管理

## 📋 公開手順

### ステップ1: パスワードハッシュの生成

1. **ターミナルでハッシュ生成スクリプトを実行**
   ```bash
   cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
   python3 auth.py
   ```

2. **パスワードを入力**
   ```
   パスワードを入力 (終了する場合は 'q'): your_secure_password
   ハッシュ値: abc123...xyz789
   ```

3. **生成されたハッシュ値をメモ**

### ステップ2: GitHubにプッシュ

1. **Gitリポジトリの初期化**
   ```bash
   cd "/Users/tar0/Library/CloudStorage/OneDrive-個人用/Documents/シナネン/smp_dev/battery"
   git init
   ```

2. **機密ファイルが除外されているか確認**
   ```bash
   git status
   # .xlsx ファイル、token ファイルが表示されないことを確認
   ```

3. **コミットとプッシュ**
   ```bash
   git add .
   git commit -m "Initial commit: バッテリー交換実績集計アプリ"
   
   # GitHubでパブリックリポジトリを作成後
   git remote add origin https://github.com/YOUR_USERNAME/battery-exchange-app.git
   git branch -M main
   git push -u origin main
   ```

### ステップ3: Streamlit Community Cloudでデプロイ

1. **アプリをデプロイ**
   - https://share.streamlit.io にアクセス
   - 「New app」をクリック
   - リポジトリ、ブランチ、ファイル（`app.py`）を選択
   - 「Advanced settings」をクリック
   - 「Environment variables」に以下を追加:
     ```
     ENABLE_AUTH=true
     ```
   - 「Deploy!」をクリック

2. **Secrets の設定**
   - デプロイ後、「Settings」→「Secrets」を開く
   - 以下を貼り付け:

   ```toml
   # 認証用パスワード（ハッシュ値）
   [passwords]
   admin = "ステップ1で生成したハッシュ値"
   user1 = "別のユーザーのハッシュ値"
   user2 = "さらに別のユーザーのハッシュ値"
   
   # Snowflake接続情報
   [snowflake]
   account = "your_account.ap-northeast-1.aws"
   user = "your_username"
   password = "your_password"
   warehouse = "COMPUTE_WH"
   database = "your_database"
   schema = "PUBLIC"
   ```

3. **保存して再起動**
   - 「Save」をクリック
   - アプリが自動的に再起動されます

### ステップ4: 動作確認

1. **アプリにアクセス**
   - 発行されたURLにアクセス（例: `https://your-app.streamlit.app`）

2. **ログイン画面が表示されることを確認**
   - ユーザー名: `admin`（または設定したユーザー名）
   - パスワード: ハッシュ化前のパスワード

3. **アプリが正常に動作することを確認**

## 🔒 セキュリティレベル

### 実装済みのセキュリティ

| 対策 | 状態 | 説明 |
|-----|------|------|
| 機密データ除外 | ✅ | Excelファイル、tokenをGitから除外 |
| 認証機能 | ✅ | ユーザー名・パスワード認証 |
| パスワードハッシュ化 | ✅ | SHA256でハッシュ化 |
| HTTPS通信 | ✅ | Streamlit Cloud が自動提供 |
| 環境変数管理 | ✅ | Secrets で機密情報を管理 |

### 推奨される追加対策

- **IP制限**: より高度なセキュリティが必要な場合
- **多要素認証**: さらに強固な認証
- **セッションタイムアウト**: 一定時間後に自動ログアウト

これらが必要な場合は、社内サーバーでのホスティングを推奨します。

## 👥 ユーザー管理

### 新しいユーザーの追加

1. **パスワードハッシュを生成**
   ```bash
   python3 auth.py
   ```

2. **Streamlit Cloud の Secrets を更新**
   ```toml
   [passwords]
   admin = "既存のハッシュ"
   new_user = "新しいハッシュ"
   ```

3. **保存して再起動**

### ユーザーの削除

Secrets から該当行を削除して保存

## 🆘 トラブルシューティング

### ログイン画面が表示されない

**原因**: 環境変数 `ENABLE_AUTH` が設定されていない

**解決策**:
1. Streamlit Cloud の「Settings」→「Advanced settings」
2. Environment variables に `ENABLE_AUTH=true` を追加
3. アプリを再起動

### パスワードが認証されない

**原因**: ハッシュ値が正しくない、またはSecretsの設定ミス

**解決策**:
1. `python3 auth.py` でハッシュを再生成
2. Secrets の `[passwords]` セクションを確認
3. ユーザー名が正しいか確認

### Excelファイルがリポジトリに含まれてしまった

**原因**: `.gitignore` が正しく設定されていない、または既にコミット済み

**解決策**:
```bash
# Gitのキャッシュから削除
git rm --cached "バッテリー交換_全国_先月.xlsx"
git rm --cached token
git commit -m "機密ファイルを削除"
git push

# GitHubでもファイルが削除されたことを確認
```

## 📊 パフォーマンス

パブリックアプリでも、認証機能による速度低下はほとんどありません。
- ログイン時のみ認証チェック
- セッション中は認証状態を保持
- 通常の操作は影響なし

## 🔄 更新方法

アプリを更新する場合:

```bash
git add .
git commit -m "更新内容の説明"
git push
```

Streamlit Cloud が自動的に再デプロイします（約1-2分）

## 📱 アクセスURL

デプロイ後のURLは以下の形式:
```
https://YOUR_USERNAME-battery-exchange-app-app-xxxxx.streamlit.app
```

このURLを社内メンバーに共有してください。

---

**これで完了！** パブリックリポジトリでも安全にアプリを公開できます 🎉

