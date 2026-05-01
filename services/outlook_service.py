"""
Outlook Service - Microsoft Graph API操作
==========================================
Outlookカレンダーの予定追加・変更・削除を行う
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import msal
import requests

import config

logger = logging.getLogger("outlook_service")
JST = ZoneInfo("Asia/Tokyo")
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
_access_token = None
_token_expiry = None


def _get_access_token() -> str:
    """MSALでアクセストークンを取得（キャッシュ付き）"""
    global _access_token, _token_expiry
    if _access_token and _token_expiry and datetime.now() < _token_expiry:
        return _access_token

    authority = f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}"
    app = msal.ConfidentialClientApplication(
        config.AZURE_CLIENT_ID, authority=authority,
        client_credential=config.AZURE_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    if "access_token" not in result:
        raise RuntimeError(f"Outlook認証失敗: {result.get('error_description', '不明')}")

    _access_token = result["access_token"]
    _token_expiry = datetime.now() + timedelta(minutes=50)
    logger.info("Outlookトークン取得成功")
    return _access_token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/json"}


def _cal_url() -> str:
    return f"{GRAPH_API_BASE}/users/{config.OUTLOOK_USER_EMAIL}/events"


def _to_graph_dt(iso_str: str) -> dict:
    dt = datetime.fromisoformat(iso_str)
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Tokyo Standard Time"}


async def add_outlook_event(title, start_at, end_at, location=None, description=None) -> dict:
    body = {"subject": title, "start": _to_graph_dt(start_at), "end": _to_graph_dt(end_at)}
    if location:
        body["location"] = {"displayName": location}
    if description:
        body["body"] = {"contentType": "text", "content": description}

    r = requests.post(_cal_url(), headers=_headers(), json=body)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Outlook追加失敗: {r.status_code}")
    logger.info(f"Outlook追加: {title}")
    return r.json()


import urllib.parse

async def update_outlook_event(event_id, title=None, start_at=None, end_at=None, location=None, description=None) -> dict:
    body = {}
    if title: body["subject"] = title
    if start_at: body["start"] = _to_graph_dt(start_at)
    if end_at: body["end"] = _to_graph_dt(end_at)
    if location is not None: body["location"] = {"displayName": location}
    if description is not None: body["body"] = {"contentType": "text", "content": description}

    encoded_id = urllib.parse.quote(event_id)
    r = requests.patch(f"{_cal_url()}/{encoded_id}", headers=_headers(), json=body)
    if r.status_code != 200:
        raise RuntimeError(f"Outlook更新失敗: {r.status_code}")
    logger.info(f"Outlook更新: {event_id[:20]}...")
    return r.json()

async def delete_outlook_event(event_id: str):
    encoded_id = urllib.parse.quote(event_id)
    r = requests.delete(f"{_cal_url()}/{encoded_id}", headers=_headers())
    if r.status_code == 404:
        logger.warning(f"Outlook削除スキップ(不在): {event_id[:20]}...")
        return
    if r.status_code != 204:
        raise RuntimeError(f"Outlook削除失敗: {r.status_code}")
    logger.info(f"Outlook削除: {event_id[:20]}...")


async def find_outlook_events_in_range(range_start: str, range_end: str) -> list:
    """
    指定期間内のOutlookイベントを全件取得（一括削除用）
    calendarView APIを使用（$filterより確実）
    range_start/range_end: MM/DD HH:MM 形式 or ISO形式
    """
    from utils.date_parser import parse_mmdd_to_date
    now = datetime.now(JST)

    def _resolve(date_str: str, is_end: bool) -> str:
        dt = parse_mmdd_to_date(date_str, now, is_end=is_end)
        if dt:
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        return date_str[:19]

    t_min = _resolve(range_start, is_end=False)
    t_max = _resolve(range_end, is_end=True)

    # calendarView APIを使用（日付範囲の正確な検索に最適）
    url = f"{GRAPH_API_BASE}/users/{config.OUTLOOK_USER_EMAIL}/calendarView"
    params = {
        "startDateTime": t_min,
        "endDateTime": t_max,
        "$select": "id,subject,start,end",
        "$top": 250,
    }
    r = requests.get(url, headers=_headers(), params=params)
    if r.status_code != 200:
        logger.warning(f"Outlook期間検索失敗: {r.status_code} {r.text[:200]}")
        return []
    events = r.json().get("value", [])
    logger.info(f"Outlook calendarView: {t_min}〜{t_max} → {len(events)}件")
    return events




async def find_outlook_event(title_hint: str = "", start_iso: str = None) -> dict | None:
    """Outlookカレンダーから単件予定を検索する（変更・削除用）"""
    import re as _re
    now = datetime.now(JST)

    # 検索範囲: 前後180日
    t_min = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S")
    t_max = (now + timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S")

    url = f"{GRAPH_API_BASE}/users/{config.OUTLOOK_USER_EMAIL}/calendarView"
    params = {
        "startDateTime": t_min,
        "endDateTime": t_max,
        "$select": "id,subject,start,end",
        "$top": 250,
    }
    r = requests.get(url, headers=_headers(), params=params)
    if r.status_code != 200:
        logger.warning(f"Outlook単件検索失敗: {r.status_code}")
        return None

    events = r.json().get("value", [])

    # title_hintからMM/DD形式を除いたキーワードで検索
    keywords = []
    if title_hint:
        for token in title_hint.split():
            if not _re.match(r"^\d{1,2}/\d{1,2}$", token):
                keywords.append(token)

    for ev in events:
        subject = ev.get("subject", "")
        if keywords and any(kw in subject or subject in kw for kw in keywords):
            return ev
        if not keywords and start_iso:
            ev_start = ev.get("start", {}).get("dateTime", "")
            if start_iso[:16] in ev_start:
                return ev

    return None

