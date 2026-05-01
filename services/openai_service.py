"""
OpenAI Service - テキスト解析
==============================
LINEメッセージを解析し、カレンダー操作のJSONを生成する
既存ワークフローのAI_CleanText + AI_ParseOps を1ステップに統合
"""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

import config

logger = logging.getLogger("openai_service")

JST = ZoneInfo("Asia/Tokyo")

_client = None

def _get_client():
    """OpenAI クライアントを取得（遅延初期化）"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client

# AI に送るシステムプロンプト（既存ワークフローのプロンプトを改良）
SYSTEM_PROMPT = """あなたはカレンダー予定の解析アシスタントです。
ユーザーのテキストメッセージを読み取り、カレンダー操作のJSONを生成してください。

## ルール

1. テキストから「追加」「変更」「削除」の操作を判定する
2. 「削除」「消して」「取り消し」「キャンセル」→ action: "delete"
3. 「変更」「移動」「〜に変更」「ずらして」→ action: "update"
4. それ以外で日時＋予定名がある → action: "add"
5. 日付情報がない → action: "noop"
6. 開始時刻のみの場合、終了時刻は開始から60分後とする
7. 「明日」「来週月曜」等の相対表現は、today を基準に計算する
8. 場所は括弧内や「にて」「で」の前にあればlocationに入れる
9. タイトルが判定できない場合は "予定" とする

## 出力形式（JSON）

{
  "operations": [
    {
      "op_index": 0,
      "action": "add" | "update" | "delete" | "noop",
      "event_id": null,
      "title": "予定タイトル",
      "start_at": "2026-05-10T15:00:00+09:00",
      "end_at": "2026-05-10T16:00:00+09:00",
      "all_day": false,
      "location": "場所（あれば）",
      "description": "補足（あれば）",
      "query": {
        "title_hint": "変更・削除時の検索キーワード",
        "range_start": "MM/DD HH:MM（旧日時）",
        "range_end": null
      },
      "patch": {
        "title": "新タイトル（あれば）",
        "start_at": "新開始日時",
        "end_at": "新終了日時",
        "location": null,
        "description": null
      },
      "delete_all_in_range": false
    }
  ],
  "notes": null
}

## 注意

- 複数の予定が含まれる場合は、operationsに複数エントリを追加する
- 変更の場合：queryに旧情報、patchに新情報を入れる
- 削除の場合：queryに検索条件を入れる
- 日時はすべて +09:00（日本時間）で出力する
- URLやゴミテキスト（スタンプ、絵文字のみ等）は無視する
"""


async def parse_calendar_operations(text: str) -> dict:
    """
    テキストをAIで解析し、カレンダー操作のJSONを返す
    """
    now = datetime.now(JST)
    today_str = now.strftime("%Y-%m-%d")
    weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]

    user_prompt = f"today: {today_str}（{weekday_jp}曜日）\n\n{text}"

    try:
        response = await _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        logger.info(f"Raw AI Output: {content}")
        
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)
            
        result = json.loads(content)

        # 基本的なバリデーション
        if "operations" not in result:
            result = {"operations": [{"op_index": 0, "action": "noop"}], "notes": "解析結果にoperationsがありません"}

        return result

    except json.JSONDecodeError as e:
        logger.error(f"AI出力のJSONパースに失敗: {e}")
        return {"operations": [{"op_index": 0, "action": "noop"}], "notes": f"JSONパースエラー: {e}"}
    except Exception as e:
        logger.error(f"OpenAI API呼び出しエラー: {e}", exc_info=True)
        raise
