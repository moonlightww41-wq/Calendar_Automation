"""
Google Calendar Service - Google Calendar API操作
==================================================
予定の追加・変更・削除・検索を行う
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

logger = logging.getLogger("gcal_service")

JST = ZoneInfo("Asia/Tokyo")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None


def _get_service():
    """Google Calendar API サービスを取得する（シングルトン）"""
    global _service
    if _service is None:
        creds = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_PATH,
            scopes=SCOPES,
        )
        _service = build("calendar", "v3", credentials=creds)
    return _service


async def add_gcal_event(
    title: str, start_at: str, end_at: str,
    location: str = None, description: str = None,
) -> dict:
    """Google Calendarに予定を追加する"""
    service = _get_service()

    event_body = {
        "summary": title,
        "start": {"dateTime": start_at, "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_at, "timeZone": "Asia/Tokyo"},
    }
    if location:
        event_body["location"] = location
    if description:
        event_body["description"] = description

    event = service.events().insert(
        calendarId=config.GOOGLE_CALENDAR_ID,
        body=event_body,
    ).execute()

    logger.info(f"GCal追加: {title} ({event.get('id')})")
    return event


async def update_gcal_event(
    event_id: str, title: str = None, start_at: str = None,
    end_at: str = None, location: str = None, description: str = None,
) -> dict:
    """Google Calendarの予定を変更する"""
    service = _get_service()

    # 既存イベントを取得
    event = service.events().get(
        calendarId=config.GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()

    # 変更内容を適用
    if title:
        event["summary"] = title
    if start_at:
        event["start"] = {"dateTime": start_at, "timeZone": "Asia/Tokyo"}
    if end_at:
        event["end"] = {"dateTime": end_at, "timeZone": "Asia/Tokyo"}
    if location is not None:
        event["location"] = location
    if description is not None:
        event["description"] = description

    updated = service.events().update(
        calendarId=config.GOOGLE_CALENDAR_ID,
        eventId=event_id,
        body=event,
    ).execute()

    logger.info(f"GCal更新: {event_id}")
    return updated


async def delete_gcal_event(event_id: str):
    """Google Calendarの予定を削除する"""
    service = _get_service()
    service.events().delete(
        calendarId=config.GOOGLE_CALENDAR_ID,
        eventId=event_id,
    ).execute()
    logger.info(f"GCal削除: {event_id}")


async def find_gcal_event(
    title_hint: str = "", start_iso: str = None, query: dict = None,
) -> dict | None:
    """
    Google Calendarから予定を検索する
    変更・削除時にevent_idが不明な場合に使用
    """
    service = _get_service()

    # 検索範囲を決定（前後30日）
    now = datetime.now(JST)
    time_min = (now - timedelta(days=30)).isoformat()
    time_max = (now + timedelta(days=60)).isoformat()

    if query:
        if query.get("range_start"):
            # range_start がMM/DD形式の場合の処理
            pass  # AI側でISO変換済みの前提

    events_result = service.events().list(
        calendarId=config.GOOGLE_CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])

    # タイトルヒントでフィルタ
    if title_hint:
        for event in events:
            summary = event.get("summary", "")
            if title_hint in summary or summary in title_hint:
                # 開始日時でも絞り込み
                if start_iso:
                    event_start = event.get("start", {}).get("dateTime", "")
                    if start_iso[:16] == event_start[:16]:
                        return event
                else:
                    return event

    # タイトルヒントなしの場合、開始日時で検索
    if start_iso:
        for event in events:
            event_start = event.get("start", {}).get("dateTime", "")
            if start_iso[:16] == event_start[:16]:
                return event

    return None
