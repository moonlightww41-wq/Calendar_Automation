"""
LINE Service - LINE Messaging API操作
=======================================
メッセージの返信・プッシュ送信を行う
"""
import logging
import httpx

import config

logger = logging.getLogger("line_service")

LINE_API_BASE = "https://api.line.me/v2/bot"


def _headers() -> dict:
    """LINE API用の認証ヘッダーを返す"""
    return {
        "Authorization": f"Bearer {config.LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


async def reply_message(reply_token: str, text: str):
    """replyToken を使って返信する"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LINE_API_BASE}/message/reply",
            headers=_headers(),
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": text}],
            },
        )
        if response.status_code != 200:
            logger.error(f"LINE返信エラー: {response.status_code} {response.text}")
        else:
            logger.info("LINE返信送信完了")


async def push_message(to: str, text: str):
    """プッシュメッセージを送信する"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LINE_API_BASE}/message/push",
            headers=_headers(),
            json={
                "to": to,
                "messages": [{"type": "text", "text": text}],
            },
        )
        if response.status_code != 200:
            logger.error(f"LINEプッシュエラー: {response.status_code} {response.text}")
        else:
            logger.info(f"LINEプッシュ送信完了 → {to[:8]}...")
