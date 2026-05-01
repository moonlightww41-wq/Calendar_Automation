"""
LINE Calendar Sync - メインサーバー
====================================
FastAPI で LINE Webhook を受け付けるエントリポイント
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

import config
from handlers.webhook_handler import handle_line_webhook

# ── ログ設定 ──────────────────────────────────
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(log_dir, "app.log"), encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


# ── アプリ起動/停止 ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """サーバー起動時・停止時の処理"""
    logger.info("=" * 50)
    logger.info("LINE Calendar Sync サーバー起動")
    logger.info(f"  Google Calendar: {config.GOOGLE_CALENDAR_ID}")
    logger.info(f"  Outlook: {config.OUTLOOK_USER_EMAIL}")
    logger.info(f"  ポート: {config.PORT}")
    logger.info("=" * 50)
    yield
    logger.info("サーバー停止")


# ── FastAPI アプリ ───────────────────────────
app = FastAPI(
    title="LINE Calendar Sync",
    description="LINEメッセージからGoogleカレンダー＋Outlookカレンダーを自動操作",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """ヘルスチェック（動作確認用）"""
    return {"status": "ok", "service": "LINE Calendar Sync"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    LINE Webhook エンドポイント
    LINEプラットフォームからのイベントを受け取って処理する
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Line-Signature", "")

        if not signature:
            raise HTTPException(status_code=400, detail="署名がありません")

        # Webhook 処理（非同期で実行）
        await handle_line_webhook(body, signature)

        return JSONResponse(content={"status": "ok"}, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook処理でエラー: {e}", exc_info=True)
        # LINE側にはエラーを返さない（再送を防ぐため200を返す）
        return JSONResponse(content={"status": "error"}, status_code=200)


# ── サーバー起動 ─────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=False,
        log_level="info",
    )
