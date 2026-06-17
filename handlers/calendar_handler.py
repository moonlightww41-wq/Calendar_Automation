"""
Calendar Handler - Google + Outlook カレンダー統合操作
======================================================
AI解析結果を受け取り、両方のカレンダーに対して
追加・変更・削除を実行し、EventIndexに記録する
"""
import logging

from services.gcal_service import (
    add_gcal_event,
    update_gcal_event,
    delete_gcal_event,
    find_gcal_event,
    find_gcal_events_in_range,
)
from services.outlook_service import (
    add_outlook_event,
    update_outlook_event,
    delete_outlook_event,
    find_outlook_event,
    find_outlook_events_in_range,
)
from services.sheets_service import append_event_index, search_event_index, get_outlook_event_id_by_gcal_id

logger = logging.getLogger("calendar_handler")


async def execute_calendar_operations(
    operations: list, user_id: str, line_to: str, request_id: str
) -> dict:
    """
    AI解析結果の操作リストを順番に実行する
    Google Calendar → Outlook Calendar の順で処理し、
    両方成功したらEventIndexに記録する
    """
    results = []

    for op in operations:
        action = op.get("action", "noop")

        if action == "noop":
            continue

        try:
            if action == "add":
                result = await _handle_add(op, user_id, line_to)
            elif action == "update":
                result = await _handle_update(op, user_id, line_to)
            elif action == "delete":
                result = await _handle_delete(op, user_id, line_to)
            else:
                result = {"action": action, "status": "skip", "reason": f"未知の操作: {action}"}

            results.append(result)

        except Exception as e:
            logger.error(f"操作実行エラー [{action}]: {e}", exc_info=True)
            results.append({
                "action": action,
                "status": "error",
                "error": str(e),
            })

    return {"results": results, "request_id": request_id}


def _adjust_start_at(start_at: str, end_at: str, recurrence: dict) -> tuple[str, str]:
    """定例イベントの場合、指定曜日になるよう開始日を未来にずらす"""
    if not start_at or not recurrence or recurrence.get("freq", "").upper() != "WEEKLY":
        return start_at, end_at
    byday = recurrence.get("byday", [])
    if not byday:
        return start_at, end_at
    if isinstance(byday, str):
        byday = [byday]
    day_map = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
    target_days = [day_map[d.upper()] for d in byday if d.upper() in day_map]
    if not target_days:
        return start_at, end_at

    from datetime import datetime, timedelta
    try:
        dt = datetime.fromisoformat(start_at)
        wd = dt.weekday()
        days_ahead = [(td - wd) % 7 for td in target_days]
        shift_days = min(days_ahead)
        if shift_days > 0:
            dt += timedelta(days=shift_days)
            start_at = dt.isoformat()
            if end_at:
                edt = datetime.fromisoformat(end_at) + timedelta(days=shift_days)
                end_at = edt.isoformat()
    except Exception:
        pass
    return start_at, end_at


async def _handle_add(op: dict, user_id: str, line_to: str) -> dict:
    """予定を追加する（Google + Outlook 両方）"""
    title = op.get("title") or "予定"
    start_at = op.get("start_at")
    end_at = op.get("end_at")
    location = op.get("location")
    description = op.get("description")
    recurrence = op.get("recurrence")  # 定例イベント情報

    start_at, end_at = _adjust_start_at(start_at, end_at, recurrence)

    # Google Calendar に追加
    gcal_event = await add_gcal_event(
        title=title,
        start_at=start_at,
        end_at=end_at,
        location=location,
        description=description,
        recurrence=recurrence,
    )
    gcal_event_id = gcal_event.get("id", "")

    # Outlook Calendar に追加
    try:
        outlook_event = await add_outlook_event(
            title=title,
            start_at=start_at,
            end_at=end_at,
            location=location,
            description=description,
            recurrence=recurrence,
        )
        outlook_event_id = outlook_event.get("id", "")
    except Exception as e:
        logger.error(f"Outlook連携エラー (add): {e}")
        outlook_event_id = ""

    # EventIndex に記録
    await append_event_index(
        line_user_id=user_id,
        event_id=gcal_event_id,
        action="add",
        title=title,
        start_at=start_at,
        end_at=end_at,
        line_to=line_to,
        outlook_event_id=outlook_event_id,
    )

    result = {
        "action": "add",
        "status": "ok",
        "title": title,
        "start_at": start_at,
        "end_at": end_at,
        "gcal_event_id": gcal_event_id,
        "outlook_event_id": outlook_event_id,
    }
    if recurrence:
        result["recurrence"] = recurrence
    return result


async def _handle_update(op: dict, user_id: str, line_to: str) -> dict:
    """予定を変更する（Google + Outlook 両方）"""
    query = op.get("query", {}) or {}
    patch = op.get("patch", {}) or {}
    title_hint = query.get("title_hint", "")
    range_start = query.get("range_start", "")

    # EventIndex から対象の event_id を検索
    index_entry = await search_event_index(
        title_hint=title_hint,
        range_start=range_start,
    )

    if not index_entry:
        # EventIndexで見つからない場合、Google Calendarから直接検索
        gcal_event = await find_gcal_event(
            title_hint=title_hint,
            start_iso=op.get("start_at"),
            query=query,
        )
        if gcal_event:
            gcal_event_id = gcal_event.get("id", "")
            # 直接検索で見つかった場合は、逆引きで対応する outlook_event_id を探す
            outlook_event_id = await get_outlook_event_id_by_gcal_id(gcal_event_id)
        else:
            return {
                "action": "update",
                "status": "skip",
                "reason": f"対象の予定が見つかりませんでした: {title_hint}",
            }
    else:
        # 安全のため、リストで返ってきた場合でも対応できるようにする
        target = index_entry[0] if isinstance(index_entry, list) else index_entry
        gcal_event_id = target.get("event_id", "")
        outlook_event_id = target.get("outlook_event_id", "")

    # 変更内容を組み立て
    new_title = patch.get("title") or op.get("title")
    new_start = patch.get("start_at") or op.get("start_at")
    new_end = patch.get("end_at") or op.get("end_at")
    new_location = patch.get("location")
    new_description = patch.get("description")

    # Google Calendar を更新
    if gcal_event_id:
        await update_gcal_event(
            event_id=gcal_event_id,
            title=new_title,
            start_at=new_start,
            end_at=new_end,
            location=new_location,
            description=new_description,
        )

    # Outlook Calendar を更新
    if outlook_event_id:
        try:
            await update_outlook_event(
                event_id=outlook_event_id,
                title=new_title,
                start_at=new_start,
                end_at=new_end,
                location=new_location,
                description=new_description,
            )
        except Exception as e:
            logger.error(f"Outlook連携エラー (update): {e}")

    # EventIndex に更新記録
    display_title = new_title or title_hint or "予定"
    await append_event_index(
        line_user_id=user_id,
        event_id=gcal_event_id,
        action="update",
        title=display_title,
        start_at=new_start,
        end_at=new_end,
        line_to=line_to,
        outlook_event_id=outlook_event_id,
    )

    return {
        "action": "update",
        "status": "ok",
        "title": display_title,
        "start_at": new_start,
        "end_at": new_end,
        "old_title": title_hint,
        "old_start": range_start,
    }


async def _handle_delete(op: dict, user_id: str, line_to: str) -> dict:
    """予定を削除する（Google + Outlook 両方）"""
    query = op.get("query", {}) or {}
    title_hint = query.get("title_hint", "")
    delete_all = op.get("delete_all_in_range", False)

    # ─── 一括削除（期間内の全イベント）───────────────────────────
    if delete_all:
        range_start = query.get("range_start", "")
        range_end = query.get("range_end", "")

        # 範囲が省略されていて、かつ予定名が指定されている場合は、今日〜年末をデフォルトとする
        if (not range_start or not range_end) and title_hint:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            JST = ZoneInfo("Asia/Tokyo")
            now = datetime.now(JST)
            range_start = range_start or f"{now.month}/{now.day}"
            range_end = range_end or "12/31"

        if not range_start or not range_end:
            return {"action": "delete", "status": "skip", "reason": "一括削除には範囲（range_start〜range_end）が必要です"}

        # Google と Outlook を並行して先に両方検索
        gcal_events = await find_gcal_events_in_range(range_start, range_end, inclusive_end=True)
        try:
            outlook_events = await find_outlook_events_in_range(range_start, range_end)
        except Exception as e:
            logger.error(f"Outlook期間検索エラー: {e}")
            outlook_events = []

        # 両方0件なら「見つかりませんでした」
        if not gcal_events and not outlook_events:
            return {"action": "delete", "status": "skip", "reason": f"{range_start}〜{range_end} の範囲に予定が見つかりませんでした（Google・Outlook両方）"}

        deleted_count = 0
        deleted_titles = []

        # Googleカレンダーから削除（title_hintがあれば一致するもののみ）
        for event in gcal_events:
            ev_id = event.get("id", "")
            ev_title = event.get("summary", "予定")
            if title_hint and title_hint not in ev_title and ev_title not in title_hint:
                continue

            ev_start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
            if ev_id:
                await delete_gcal_event(ev_id)
                await append_event_index(
                    line_user_id=user_id,
                    event_id=ev_id,
                    action="delete",
                    title=ev_title,
                    start_at=ev_start,
                    end_at=event.get("end", {}).get("dateTime", ""),
                    line_to=line_to,
                    outlook_event_id="",
                )
                deleted_count += 1
                deleted_titles.append((ev_title, ev_start))

        # Outlookカレンダーから削除（Googleと独立して実行・title_hintがあれば一致するもののみ）
        for ov in outlook_events:
            ov_id = ov.get("id", "")
            ov_title = ov.get("subject", "予定")
            if title_hint and title_hint not in ov_title and ov_title not in title_hint:
                continue

            ov_start = ov.get("start", {}).get("dateTime", "")
            if ov_id:
                try:
                    await delete_outlook_event(ov_id)
                    logger.info(f"Outlook一括削除: {ov_title}")
                    # Googleに同名がなかった場合のみリストに追加
                    already_listed = any(t == ov_title for t, _ in deleted_titles)
                    if not already_listed:
                        deleted_titles.append((ov_title, ov_start))
                        deleted_count += 1
                except Exception as e:
                    logger.error(f"Outlook一括削除エラー ({ov_title}): {e}")

        return {
            "action": "delete",
            "status": "ok",
            "deleted_count": deleted_count,
            "deleted_titles": deleted_titles,
            "range": f"{range_start}〜{range_end}",
        }

    # ─── 単件削除 ─────────────────────────────────────────────────
    # EventIndex から対象を検索
    index_entry = await search_event_index(
        title_hint=title_hint,
        range_start=query.get("range_start", ""),
    )

    if not index_entry:
        # Google Calendarから直接検索
        gcal_event = await find_gcal_event(
            title_hint=title_hint,
            start_iso=op.get("start_at"),
            query=query,
        )
        if gcal_event:
            gcal_event_id = gcal_event.get("id", "")
            outlook_event_id = ""
        else:
            # Googleで見つからなかった場合、Outlookも検索する
            try:
                ov_event = await find_outlook_event(
                    title_hint=title_hint,
                    start_iso=op.get("start_at"),
                )
            except Exception as e:
                logger.error(f"Outlook単件検索エラー: {e}")
                ov_event = None

            if ov_event:
                gcal_event_id = ""
                outlook_event_id = ov_event.get("id", "")
                # Outlookのみ削除ケースの情報を設定
                deleted_title = ov_event.get("subject", title_hint)
                deleted_start = ov_event.get("start", {}).get("dateTime", "")
                deleted_end = ov_event.get("end", {}).get("dateTime", "")

                if outlook_event_id:
                    try:
                        await delete_outlook_event(outlook_event_id)
                    except Exception as e:
                        logger.error(f"Outlook単件削除エラー: {e}")

                await append_event_index(
                    line_user_id=user_id,
                    event_id="",
                    action="delete",
                    title=deleted_title,
                    start_at=deleted_start,
                    end_at=deleted_end,
                    line_to=line_to,
                    outlook_event_id="",
                )
                return {
                    "action": "delete",
                    "status": "ok",
                    "title": deleted_title,
                    "start_at": deleted_start,
                    "end_at": deleted_end,
                }

            return {
                "action": "delete",
                "status": "skip",
                "reason": f"対象の予定が見つかりませんでした: {title_hint} {query.get('range_start', '')}",
            }
    else:
        gcal_event_id = index_entry.get("event_id", "")
        outlook_event_id = index_entry.get("outlook_event_id", "")

    deleted_title = index_entry.get("title", title_hint) if index_entry else title_hint
    deleted_start = index_entry.get("start_at", "") if index_entry else ""
    deleted_end = index_entry.get("end_at", "") if index_entry else ""

    # Google Calendar から削除（404はスキップ）
    if gcal_event_id:
        await delete_gcal_event(gcal_event_id)

    # Outlook Calendar から削除
    if outlook_event_id:
        try:
            await delete_outlook_event(outlook_event_id)
        except Exception as e:
            logger.error(f"Outlook連携エラー (delete): {e}")

    # EventIndex に削除記録
    await append_event_index(
        line_user_id=user_id,
        event_id=gcal_event_id,
        action="delete",
        title=deleted_title,
        start_at=deleted_start,
        end_at=deleted_end,
        line_to=line_to,
        outlook_event_id="",
    )

    return {
        "action": "delete",
        "status": "ok",
        "title": deleted_title,
        "start_at": deleted_start,
        "end_at": deleted_end,
    }

