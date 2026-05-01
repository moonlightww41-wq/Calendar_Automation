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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
