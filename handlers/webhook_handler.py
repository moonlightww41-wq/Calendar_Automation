"""
Webhook Handler - LINE Webhookイベント処理
============================================
LINEから受信したテキストメッセージを解析し、
カレンダー操作→ログ記録→返信を行う
"""
import asyncio
import hashlib
import hmac
import base64
import json
import logging
import time

import config
from services.openai_service import parse_calendar_operations
from handlers.calendar_handler import execute_calendar_operations
from services.sheets_service import append_exec_log
from services.line_service import reply_message, push_message
from utils.message_builder import build_reply_message, build_error_message
from utils.date_parser import contains_date

logger = logging.getLogger("webhook")


def verify_signature(body: bytes, signature: str) -> bool:
    """LINE署名を検証する"""
    channel_secret = config.LINE_CHANNEL_SECRET
    if not channel_secret:
        logger.warning("LINE_CHANNEL_SECRETが未設定のため署名検証をスキップ")
        return True
    if not signature:
        return False
    hash_val = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)



def generate_request_id() -> str:
    """ユニークなリクエストIDを生成する"""
    ts = hex(int(time.time()))[2:]
    rand = hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:16]
    return f"req_{ts}_{rand}"


async def handle_line_webhook(body: bytes, signature: str):
    """
    LINE Webhookのメイン処理
    1. 署名検証
    2. テキストメッセージを抽出
    3. 日付を含むかチェック（DateGate）
    4. AI で解析
    5. カレンダー操作（Google + Outlook）
    6. ログ記録
    7. LINE返信
    """
    # 署名検証
    if not verify_signature(body, signature):
        logger.warning("署名検証に失敗しました")
        return

    # JSONパース
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error("JSONのパースに失敗しました")
        return

    events = payload.get("events", [])

    for event in events:
        # テキストメッセージのみ処理
        if event.get("type") != "message":
            continue
        if event.get("message", {}).get("type") != "text":
            continue

        text = event["message"]["text"]
        reply_token = event.get("replyToken", "")
        user_id = event.get("source", {}).get("userId", "")
        # グループからの場合はグループIDを返信先にする
        source_type = event.get("source", {}).get("type", "user")
        if source_type == "group":
            line_to = event["source"].get("groupId", user_id)
        elif source_type == "room":
            line_to = event["source"].get("roomId", user_id)
        else:
            line_to = user_id

        request_id = generate_request_id()
        logger.info(f"[{request_id}] 受信: {text[:50]}...")

        # ── DateGate: 日付を含まないメッセージはスキップ ──
        if not contains_date(text):
            logger.info(f"[{request_id}] 日付なし → スキップ")
            continue

        try:
            # ── AI 解析 ──
            logger.info(f"[{request_id}] AI解析開始")
            ops_result = await parse_calendar_operations(text)
            logger.info(f"[{request_id}] AI解析完了: {ops_result.get('operations', [])}")

            operations = ops_result.get("operations", [])

            # noop（操作なし）の場合はスキップ
            if not operations or (
                len(operations) == 1 and operations[0].get("action") == "noop"
            ):
                logger.info(f"[{request_id}] noop → スキップ")
                continue

            # ── カレンダー操作（Google + Outlook 同時） ──
            logger.info(f"[{request_id}] カレンダー操作開始")
            results = await execute_calendar_operations(
                operations, user_id, line_to, request_id
            )
            logger.info(f"[{request_id}] カレンダー操作完了")

            # ── ExecLog 記録 ──
            await append_exec_log(
                request_id=request_id,
                line_user_id=user_id,
                source_text=text,
                ops_json=json.dumps(ops_result, ensure_ascii=False),
                results_json=json.dumps(results, ensure_ascii=False),
                line_to=line_to,
            )

            # ── LINE 返信 ──
            reply_text = build_reply_message(results)
            if reply_token:
                await reply_message(reply_token, reply_text)
            else:
                # replyTokenがない場合はpushで送る
                await push_message(line_to, reply_text)

            logger.info(f"[{request_id}] 完了")

        except Exception as e:
            logger.error(f"[{request_id}] エラー: {e}", exc_info=True)
            # エラー時もユーザーに通知
            error_text = build_error_message(str(e))
            try:
                if reply_token:
                    await reply_message(reply_token, error_text)
                else:
                    await push_message(line_to, error_text)
            except Exception:
                logger.error("エラー通知の送信にも失敗しました")
