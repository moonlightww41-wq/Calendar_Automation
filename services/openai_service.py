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

# AI に送るシステムプロンプト
SYSTEM_PROMPT = """あなたは日本語のビジネスチャットを読み取り、カレンダー操作のJSONを生成する専門AIです。
ユーザーは定型文ではなく、日常会話・口語・略語・関西弁など自然な文体でメッセージを送ってきます。

## あなたの役割

テキストから「予定の追加・変更・削除」を読み取りJSONを生成する。
曖昧な表現でも文脈から最大限推測して操作を生成すること。

## 操作の判定方法

### 削除（action: "delete"）
「消して」「キャンセル」「なくなった」「中止」「取り消し」「流れた」「なしで」「やめて」
「なくなったわ」「なんかなくなったっぽい」「飛んだ」「中止になった」「流れたから消しといて」など

### 変更（action: "update"）
「変更」「ずらして」「移して」「〜に変えて」「時間変わった」「遅くなった」「早めて」
「〜になったから直して」「リスケ」「リスケして」など

### 追加（action: "add"）
日時＋予定名が読み取れる場合。「〜入れといて」「〜追加して」「〜あるから」など

### 無視（action: "noop"）
カレンダーに関係ない会話、URLだけ、スタンプ・絵文字のみ

## 日時の解釈ルール

- 「明日」「明後日」「あさって」「今日」→ todayを基準に計算
- 「来週月曜」「再来週」「今週金曜」→ todayを基準に計算
- 「朝イチ」→ 9:00、「昼」「お昼」→ 12:00、「夕方」→ 17:00、「夜」→ 19:00
- 「午前」→ AM、「午後」→ PM（13:00以降）
- 「〜時頃」→ その時刻ちょうどで解釈
- 時刻のみで日付がない場合は「今日」と推定
- 終了時刻がない場合は開始から60分後
- 日付があっても時刻がない場合は終日（all_day: true）ではなく、時刻未指定のまま渡す

## query（検索条件）のルール - 重要

削除・変更の場合、queryは「カレンダー上の予定を探すためのヒント」です。

- **title_hint**: 予定名のキーワードのみ。日付・曜日・時刻は含めないこと！
  - 良い例: "現場視察", "定例会議", "打ち合わせ"
  - 悪い例: "現場視察 04/21", "定例会議 金曜" ← 日付を混ぜない！
- **range_start**: 変更・削除対象の旧日時を "MM/DD HH:MM" 形式で。時刻不明なら "MM/DD 00:00"

## 出力形式（JSON）

{
  "operations": [
    {
      "op_index": 0,
      "action": "add" | "update" | "delete" | "noop",
      "event_id": null,
      "title": "予定タイトル（追加時）",
      "start_at": "2026-05-10T15:00:00+09:00",
      "end_at": "2026-05-10T16:00:00+09:00",
      "all_day": false,
      "location": "場所（あれば）",
      "description": "補足（あれば）",
      "query": {
        "title_hint": "検索キーワード（日付を含めない予定名のみ）",
        "range_start": "MM/DD HH:MM",
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

## 実例

入力: 「来週火曜の現場視察、流れたから消しといて」
→ action: "delete", query.title_hint: "現場視察", query.range_start: "MM/DD 00:00"

入力: 「明日の打ち合わせ、14時に1時間ずらして」
→ action: "update", query.title_hint: "打ち合わせ", patch.start_at: 明日14:00

入力: 「5/15 15時 A社訪問（東京）」
→ action: "add", title: "A社訪問", start_at: 2026-05-15T15:00:00+09:00, location: "東京"

入力: 「今日は在宅やわ」
→ action: "noop"（予定の操作ではない）

## 注意事項

- 複数の予定は operations に複数エントリ
- 日時はすべて +09:00（日本時間）
- 予定名が不明な場合は "予定" とする
- カレンダー操作と無関係な文は noop
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
