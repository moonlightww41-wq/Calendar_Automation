FROM python:3.12-slim

WORKDIR /app

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリのコードをコピー
COPY . .

# credentialsフォルダを作成
RUN mkdir -p credentials

EXPOSE 8002

# シークレットからcredentialsファイルを復元してサーバー起動
CMD ["sh", "-c", "echo \"$GOOGLE_CREDENTIALS_JSON\" > credentials/google_credentials.json && uvicorn main:app --host 0.0.0.0 --port 8002"]
