"""
日付パーサー - テキスト内の日付検出＋自然言語対応
===================================================
DateGate（カレンダー操作関連かの判定）
口語・曖昧表現にも対応させる
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 日付っぽいパターン
DATE_PATTERNS = [
    r"\d{1,2}/\d{1,2}",                     # 5/10, 12/25
    r"\d{1,2}月\d{1,2}日",                   # 5月10日
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",         # 2026-05-10, 2026/5/10
    r"\d{1,2}時",                             # 14時、朝9時
    r"明日", r"明後日", r"あさって",
    r"今日", r"本日",
    r"来週", r"今週", r"再来週",
    r"月曜", r"火曜", r"水曜", r"木曜", r"金曜", r"土曜", r"日曜",
    r"月曜日", r"火曜日", r"水曜日", r"木曜日", r"金曜日", r"土曜日", r"日曜日",
    r"朝イチ", r"朝一",
    r"午前", r"午後",
]

# カレンダー操作キーワード（日付がなくても通過させる）
# 例：「あの打ち合わせ消して」「視察なくなった」など
CALENDAR_ACTION_PATTERNS = [
    # 削除系
    r"消して", r"消しといて", r"消しておいて",
    r"キャンセル", r"中止", r"なくなった", r"なくなったわ", r"なくなりました",
    r"流れた", r"流れました", r"流れちゃった",
    r"取り消し", r"取消",
    r"やめて", r"やめとく",
    r"飛んだ", r"なしで",
    # 変更系
    r"リスケ", r"ずらして", r"変更して", r"移して", r"早めて", r"遅らせて",
    r"時間変わった", r"時間が変わった",
    # 追加系（日付ありの場合が多いが念のため）
    r"入れといて", r"追加して", r"登録して",
]

DATE_REGEX = re.compile("|".join(DATE_PATTERNS))
ACTION_REGEX = re.compile("|".join(CALENDAR_ACTION_PATTERNS))


def contains_date(text: str) -> bool:
    """
    テキストにカレンダー操作の意図があるかを判定する（DateGate）
    ・日付・時刻表現がある
    ・または、削除・変更・追加の操作キーワードがある
    いずれかを満たせばTrueを返し、AI解析に進む
    """
    if DATE_REGEX.search(text):
        return True
    if ACTION_REGEX.search(text):
        return True
    return False
