"""
Google Sheets Service - ログ記録
=================================
ExecLog / EventIndex シートへの書き込み・検索
"""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

logger = logging.getLogger("sheets_service")
JST = ZoneInfo("Asia/Tokyo")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_service = None


def _get_service():
    global _service
    if _service is None:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        if creds_json:
            import json as _json
            creds_info = _json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
        _service = build("sheets", "v4", credentials=creds)
    return _service


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


async def append_exec_log(request_id, line_user_id, source_text, ops_json, results_json, line_to):
    """ExecLogシートに1行追加する"""
    service = _get_service()
    row = [_now_jst(), request_id, line_user_id, source_text, ops_json, results_json, line_to]
    service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SPREADSHEET_ID,
        range=f"{config.EXEC_LOG_SHEET}!A:G",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    logger.info(f"ExecLog記録: {request_id}")


async def append_event_index(line_user_id, event_id, action, title, start_at, end_at, line_to, outlook_event_id=""):
    """EventIndexシートに1行追加する（ng_event_id列にoutlook_event_idを記録）"""
    service = _get_service()
    row = [_now_jst(), line_user_id, event_id, action, title, start_at, end_at, line_to, outlook_event_id]
    service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SPREADSHEET_ID,
        range=f"{config.EVENT_INDEX_SHEET}!A:I",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    logger.info(f"EventIndex記録: {action} - {title}")


async def search_event_index(title_hint="", range_start="") -> dict | None:
    """EventIndexからevent_idを検索する（変更・削除時に使用）"""
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=config.GOOGLE_SPREADSHEET_ID,
        range=f"{config.EVENT_INDEX_SHEET}!A:I",
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return None

    # title_hint から日付っぽいトークン（MM/DD形式）を除いてキーワード化
    # 例: "現場視察 04/21" → ["現場視察"]
    import re as _re
    keywords = []
    if title_hint:
        for token in title_hint.split():
            if not _re.match(r"^\d{1,2}/\d{1,2}$", token):  # MM/DD形式を除外
                keywords.append(token)

    def _matches(row_title: str) -> bool:
        """タイトルがキーワードのいずれかにマッチするか確認"""
        if not keywords:
            return False
        for kw in keywords:
            # キーワードがタイトルに含まれる、またはタイトルがキーワードに含まれる
            if kw in row_title or row_title in kw:
                return True
        return False

    # 最新のものから検索（逆順）
    for row in reversed(rows[1:]):  # ヘッダーをスキップ
        if len(row) < 7:
            continue
        row_action = row[3] if len(row) > 3 else ""
        row_title = row[4] if len(row) > 4 else ""
        row_start = row[5] if len(row) > 5 else ""

        # 削除済みはスキップ
        if row_action == "delete":
            continue

        # タイトルマッチ（キーワード方式）
        if _matches(row_title):
            return {
                "event_id": row[2] if len(row) > 2 else "",
                "title": row_title,
                "start_at": row_start,
                "end_at": row[6] if len(row) > 6 else "",
                "outlook_event_id": row[8] if len(row) > 8 else "",
            }

    return None

