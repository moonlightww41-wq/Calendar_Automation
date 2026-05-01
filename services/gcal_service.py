"""
Google Calendar Service - Google Calendar API操作
==================================================
予定の追加・変更・削除・検索を行う
"""
import logging
import os
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
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        if creds_json:
            import json as _json
            creds_info = _json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        else:
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
    """Google Calendarの予定を削除する（404の場合はスキップ）"""
    from googleapiclient.errors import HttpError
    service = _get_service()
    try:
        service.events().delete(
            calendarId=config.GOOGLE_CALENDAR_ID,
            eventId=event_id,
        ).execute()
        logger.info(f"GCal削除: {event_id}")
    except HttpError as e:
        if e.resp.status == 404:
            logger.warning(f"GCal削除スキップ(不在): {event_id}")
        else:
            raise


async def find_gcal_events_in_range(range_start: str, range_end: str, inclusive_end: bool = False) -> list:
    """
    指定期間内の全イベントを取得する（一括削除用）
    range_start/range_end: MM/DD HH:MM 形式 or ISO形式
    inclusive_end=True: 終端日の当日のイベントも含める（翌日0時まで検索）
    """
    import re as _re
    from datetime import timedelta as _td
    now = datetime.now(JST)

    def _parse_date(date_str: str, is_end: bool = False) -> str:
        """MM/DD HH:MM 形式またはISO形式をISOに変換"""
        if not date_str:
            return None
        m = _re.match(r"^(\d{1,2})/(\d{1,2})", date_str)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = now.year if month >= now.month - 6 else now.year + 1
            dt = datetime(year, month, day, 0, 0, tzinfo=JST)
            if is_end and inclusive_end:
                dt = dt + _td(days=1)  # 終端日の翌日0時 → 終端日を含める
            return dt.isoformat()
        return date_str  # すでにISO形式ならそのまま返す

    time_min = _parse_date(range_start, is_end=False)
    time_max = _parse_date(range_end, is_end=True)

    if not time_min or not time_max:
        return []

    service = _get_service()
    events_result = service.events().list(
        calendarId=config.GOOGLE_CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=250,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return events_result.get("items", [])



async def find_gcal_event(
    title_hint: str = "", start_iso: str = None, query: dict = None,
) -> dict | None:
    """
    Google Calendarから予定を検索する
    変更・削除時にevent_idが不明な場合に使用
    """
    import re as _re
    service = _get_service()

    # range_start（MM/DD形式）から年込みのISO日付を組み立てる
    range_start = (query or {}).get("range_start", "")
    range_date_str = None
    if range_start:
        m = _re.match(r"^(\d{1,2})/(\d{1,2})", range_start)
        if m:
            now = datetime.now(JST)
            month, day = int(m.group(1)), int(m.group(2))
            year = now.year if month >= now.month - 2 else now.year + 1
            range_date_str = f"{year:04d}-{month:02d}-{day:02d}"

    # 検索範囲を決定（前後60日）
    now = datetime.now(JST)
    time_min = (now - timedelta(days=60)).isoformat()
    time_max = (now + timedelta(days=60)).isoformat()

    events_result = service.events().list(
        calendarId=config.GOOGLE_CALENDAR_ID,
        timeMin=time_min,
        timeMax=time_max,
        maxResults=100,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])

    # title_hintからMM/DD形式を除いたキーワードリストを作成
    keywords = []
    if title_hint:
        for token in title_hint.split():
            if not _re.match(r"^\d{1,2}/\d{1,2}$", token):
                keywords.append(token)

    def _title_matches(summary: str) -> bool:
        if not keywords:
            return False
        for kw in keywords:
            if kw in summary or summary in kw:
                return True
        return False

    def _date_matches(event: dict) -> bool:
        """イベントがrange_dateと同じ日付か確認"""
        if not range_date_str:
            return True  # 日付指定なしは全てOK
        ev_start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
        return ev_start.startswith(range_date_str)

    # タイトル＋日付でフィルタ
    if keywords:
        for event in events:
            summary = event.get("summary", "")
            if _title_matches(summary) and _date_matches(event):
                return event
        # 日付なしでタイトルだけの再検索（フォールバック）
        for event in events:
            summary = event.get("summary", "")
            if _title_matches(summary):
                return event

    # start_isoが指定されている場合
    if start_iso:
        for event in events:
            event_start = event.get("start", {}).get("dateTime", "")
            if start_iso[:16] == event_start[:16]:
                return event

    return None

