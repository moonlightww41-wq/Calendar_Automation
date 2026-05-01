"""
LINE Calendar Sync - 設定管理
==============================
.env ファイルから各種APIキー・設定値を読み込む
"""
import os
from dotenv import load_dotenv

# .env を読み込み（システム環境変数より優先）
load_dotenv(override=True)


# --- LINE Bot ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-5-nano"  # 最軽量モデル

# --- Google ---
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "noden.yy@gmail.com")
GOOGLE_SPREADSHEET_ID = os.getenv(
    "GOOGLE_SPREADSHEET_ID",
    "1BqKBRocWQSP-7JTCE-S9uk3WlEcU-9lTzgtIbqE1dyU"
)
GOOGLE_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "credentials", "google_credentials.json"
)

# --- Microsoft Outlook ---
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
OUTLOOK_USER_EMAIL = os.getenv("OUTLOOK_USER_EMAIL", "y-yamada@noden.co.jp")

# --- Server ---
PORT = int(os.getenv("PORT", "8002"))

# --- Sheets ---
EXEC_LOG_SHEET = "ExecLog"
EVENT_INDEX_SHEET = "EventIndex"

# --- 共通設定 ---
DEFAULT_DURATION_MINUTES = 60  # 終了時刻未指定時のデフォルト（60分）
TIMEZONE = "Asia/Tokyo"
