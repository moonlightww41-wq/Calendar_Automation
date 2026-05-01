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


def resolve_month_to_year(month: int, day: int, now: datetime) -> int:
    """
    月・日から最も適切な「年」を決定する。
    「今日に一番近い日付」を基準に判断する。

    例（今日が2026年5月2日の場合）:
    ・4月  → 2026年4月（10日前 → 近い）
    ・1月  → 2026年1月（4ヶ月前 → 許容範囲内）
    ・12月 → 2026年12月（7ヶ月後 → 近い）

    例（今日が2026年12月15日の場合）:
    ・1月  → 2027年1月（今年は11ヶ月前→遠い、来年は17日後→近い）
    ・11月 → 2026年11月（先月）

    ルール: this_year版とnext_year版のうち、
    「今日との差の絶対値が小さい方」を選ぶ。
    ただし「過去イベントへの操作」もあるため、
    過去6ヶ月以内はthis_yearを優先する。
    """
    import calendar as _calendar

    # 月末を超える日の補正
    try:
        this_year = datetime(now.year, month, day, tzinfo=now.tzinfo)
    except ValueError:
        # 月末オーバー（例：2月31日）→ 月末に丸める
        last_day = _calendar.monthrange(now.year, month)[1]
        this_year = datetime(now.year, month, last_day, tzinfo=now.tzinfo)

    try:
        next_year = datetime(now.year + 1, month, day, tzinfo=now.tzinfo)
    except ValueError:
        last_day = _calendar.monthrange(now.year + 1, month)[1]
        next_year = datetime(now.year + 1, month, last_day, tzinfo=now.tzinfo)

    try:
        prev_year = datetime(now.year - 1, month, day, tzinfo=now.tzinfo)
    except ValueError:
        prev_year = this_year  # フォールバック

    diff_this = abs((this_year - now).days)
    diff_next = abs((next_year - now).days)
    diff_prev = abs((prev_year - now).days)

    # 過去6ヶ月以内（180日以内の過去）はthis_yearを優先
    # これにより「先月の予定を操作する」が正しく動く
    days_ago = (now - this_year).days
    if 0 <= days_ago <= 180:
        return now.year

    # this_yearが未来の場合、prev_yearは候補から除外（過去年の未来日はあり得ない）
    # → next_year vs this_year の比較のみ
    if this_year > now:
        return now.year + 1 if diff_next < diff_this else now.year

    # それ以外は最も今日に近い年を選ぶ（prev_yearも候補）
    best_diff = min(diff_this, diff_next, diff_prev)
    if best_diff == diff_next:
        return now.year + 1
    elif best_diff == diff_prev and prev_year < now:  # 過去のprev_yearのみ
        return now.year - 1
    return now.year


def parse_mmdd_to_date(mmdd_str: str, now: datetime, is_end: bool = False) -> datetime | None:
    """
    "MM/DD" または "MM/DD HH:MM" 形式の文字列を datetime に変換する。
    年はresolve_month_to_yearで自動決定。
    is_end=True の場合、翌日0時（終端日を含む検索に使用）。
    """
    m = re.match(r"^(\d{1,2})/(\d{1,2})", mmdd_str)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    year = resolve_month_to_year(month, day, now)
    dt = datetime(year, month, day, 0, 0, tzinfo=now.tzinfo)
    if is_end:
        dt = dt + timedelta(days=1)
    return dt

