#!/bin/bash
# デプロイ用スクリプト

echo "=================================="
echo "バッテリー交換実績集計アプリ"
echo "デプロイスクリプト"
echo "=================================="
echo ""

# カラーコード
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}デプロイ方法を選択してください:${NC}"
echo "1) Streamlit Community Cloud (推奨・無料)"
echo "2) ローカル/社内サーバー"
echo "3) Docker コンテナ"
echo ""
read -p "選択 (1-3): " choice

case $choice in
    1)
        echo ""
        echo -e "${GREEN}Streamlit Community Cloud へのデプロイ準備${NC}"
        echo ""
        echo "手順:"
        echo "1. GitHubアカウントにログイン"
        echo "2. プライベートリポジトリを作成"
        echo "3. 以下のコマンドでプッシュ:"
        echo ""
        echo "  git init"
        echo "  git add ."
        echo "  git commit -m 'Initial commit'"
        echo "  git remote add origin YOUR_GITHUB_REPO_URL"
        echo "  git push -u origin main"
        echo ""
        echo "4. https://share.streamlit.io にアクセス"
        echo "5. GitHub でログインしてアプリをデプロイ"
        echo ""
        echo "詳細は DEPLOYMENT.md を参照してください"
        ;;
    2)
        echo ""
        echo -e "${GREEN}ローカル/社内サーバーでのデプロイ${NC}"
        echo ""
        read -p "ポート番号を指定 (デフォルト: 8501): " port
        port=${port:-8501}
        
        echo ""
        echo "依存パッケージをインストール中..."
        pip3 install -r requirements.txt
        
        echo ""
        echo -e "${GREEN}アプリを起動します...${NC}"
        echo "アクセスURL: http://localhost:$port"
        echo ""
        
        python3 -m streamlit run app.py --server.port=$port --server.headless=false
        ;;
    3)
        echo ""
        echo -e "${GREEN}Docker コンテナでのデプロイ${NC}"
        echo ""
        
        if ! command -v docker &> /dev/null; then
            echo -e "${RED}Docker がインストールされていません${NC}"
            echo "https://www.docker.com/get-started からインストールしてください"
            exit 1
        fi
        
        echo "Dockerfile を作成中..."
        cat > Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコピー
COPY . .

# ポート公開
EXPOSE 8501

# ヘルスチェック
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# アプリケーション起動
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
EOF
        
        echo ""
        echo "Docker イメージをビルド中..."
        docker build -t battery-exchange-app .
        
        echo ""
        echo -e "${GREEN}Docker コンテナを起動します...${NC}"
        docker run -p 8501:8501 battery-exchange-app
        ;;
    *)
        echo -e "${RED}無効な選択です${NC}"
        exit 1
        ;;
esac

