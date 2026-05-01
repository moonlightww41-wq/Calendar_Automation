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
    if r.status_code != 204:
        raise RuntimeError(f"Outlook削除失敗: {r.status_code}")
    logger.info(f"Outlook削除: {event_id[:20]}...")


async def find_outlook_event(title_hint="", start_iso=None) -> dict | None:
    now = datetime.now(JST)
    t_min = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    t_max = (now + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {"$filter": f"start/dateTime ge '{t_min}' and start/dateTime le '{t_max}'", "$top": 50}
    r = requests.get(_cal_url(), headers=_headers(), params=params)
    if r.status_code != 200:
        return None
    for ev in r.json().get("value", []):
        if title_hint and (title_hint in ev.get("subject", "") or ev.get("subject", "") in title_hint):
            return ev
    return None
