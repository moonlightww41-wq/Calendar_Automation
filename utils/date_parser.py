"""
日付パーサー - テキスト内の日付検出＋正規化
===========================================
DateGate（日付を含むかの判定）と
MM/DD形式→ISO形式への変換を行う
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 日付っぽいパターン（DateGate用）
DATE_PATTERNS = [
    r"\d{1,2}/\d{1,2}",                     # 5/10, 12/25
    r"\d{1,2}月\d{1,2}日",                   # 5月10日
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",         # 2026-05-10, 2026/5/10
    r"明日", r"明後日", r"あさって",
    r"今日",
    r"来週",
    r"今週",
]
DATE_REGEX = re.compile("|".join(DATE_PATTERNS))


def contains_date(text: str) -> bool:
    """
    テキストに日付情報が含まれているかを判定する（DateGate）
    日付がなければ False → カレンダー操作をスキップ
    """
    return bool(DATE_REGEX.search(text))
