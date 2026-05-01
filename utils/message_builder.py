"""
メッセージビルダー - LINE返信メッセージの組み立て
=================================================
操作結果をユーザーフレンドリーなテキストに変換する
"""
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 曜日の日本語表記
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _format_datetime(iso_str: str) -> str:
    """ISO日時を '5/10（土）15:00' 形式に変換する"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        weekday = WEEKDAYS_JP[dt.weekday()]
        return f"{dt.month}/{dt.day}（{weekday}）{dt.hour}:{dt.minute:02d}"
    except (ValueError, TypeError):
        return iso_str


def _format_time_range(start_iso: str, end_iso: str) -> str:
    """開始〜終了の時間範囲を表示する"""
    start_str = _format_datetime(start_iso)
    if not end_iso:
        return f"📅 {start_str}"
    try:
        end_dt = datetime.fromisoformat(end_iso)
        end_time = f"{end_dt.hour}:{end_dt.minute:02d}"
        return f"📅 {start_str}〜{end_time}"
    except (ValueError, TypeError):
        return f"📅 {start_str}"


def build_reply_message(results: dict) -> str:
    """
    カレンダー操作結果からLINE返信メッセージを組み立てる
    """
    result_list = results.get("results", [])

    if not result_list:
        return "⚠️ 処理する操作がありませんでした"

    messages = []

    for result in result_list:
        action = result.get("action", "")
        status = result.get("status", "")

        if status == "error":
            messages.append(
                f"⚠️ 予定の{_action_label(action)}に失敗しました\n"
                f"原因：{result.get('error', '不明なエラー')}"
            )
            continue

        if status == "skip":
            messages.append(
                f"⚠️ {result.get('reason', '対象の予定が見つかりませんでした')}"
            )
            continue

        if action == "add":
            title = result.get("title", "予定")
            time_range = _format_time_range(
                result.get("start_at", ""), result.get("end_at", "")
            )
            messages.append(
                f"✅ 予定を登録しました\n\n"
                f"{time_range}\n"
                f"📝 {title}\n\n"
                f"Google・Outlook 両方に登録済み"
            )

        elif action == "update":
            title = result.get("title", "予定")
            old_start = result.get("old_start", "")
            new_range = _format_time_range(
                result.get("start_at", ""), result.get("end_at", "")
            )
            if old_start:
                old_str = _format_datetime(old_start) if "T" in str(old_start) else old_start
                messages.append(
                    f"🔄 予定を変更しました\n\n"
                    f"【変更前】{old_str}\n"
                    f"【変更後】{new_range.replace('📅 ', '')}\n"
                    f"📝 {title}\n\n"
                    f"Google・Outlook 両方を更新済み"
                )
            else:
                messages.append(
                    f"🔄 予定を変更しました\n\n"
                    f"{new_range}\n"
                    f"📝 {title}\n\n"
                    f"Google・Outlook 両方を更新済み"
                )

        elif action == "delete":
            deleted_count = result.get("deleted_count")
            if deleted_count is not None:
                # 一括削除
                date_range = result.get("range", "")
                messages.append(
                    f"🗑️ {deleted_count}件の予定を削除しました\n\n"
                    f"📅 期間：{date_range}\n\n"
                    f"Google両方から削除済み"
                )
            else:
                # 単件削除
                title = result.get("title", "予定")
                time_range = _format_time_range(
                    result.get("start_at", ""), result.get("end_at", "")
                )
                messages.append(
                    f"🗑️ 予定を削除しました\n\n"
                    f"{time_range}\n"
                    f"📝 {title}\n\n"
                    f"Google・Outlook 両方から削除済み"
                )

    return "\n\n---\n\n".join(messages) if messages else "処理が完了しました"


def build_error_message(error: str) -> str:
    """エラー時のメッセージを作る"""
    return (
        f"⚠️ 予定の処理に失敗しました\n\n"
        f"原因：{error}\n\n"
        f"例）「5/10 15時 打ち合わせ」のように送ってください"
    )


def _action_label(action: str) -> str:
    """操作種別を日本語ラベルに変換する"""
    labels = {
        "add": "登録",
        "update": "変更",
        "delete": "削除",
    }
    return labels.get(action, "操作")
