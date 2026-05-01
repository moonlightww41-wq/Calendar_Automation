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
from services.sheets_service import append_event_index, search_event_index

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


async def _handle_add(op: dict, user_id: str, line_to: str) -> dict:
    """予定を追加する（Google + Outlook 両方）"""
    title = op.get("title") or "予定"
    start_at = op.get("start_at")
    end_at = op.get("end_at")
    location = op.get("location")
    description = op.get("description")

    # Google Calendar に追加
    gcal_event = await add_gcal_event(
        title=title,
        start_at=start_at,
        end_at=end_at,
        location=location,
        description=description,
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

    return {
        "action": "add",
        "status": "ok",
        "title": title,
        "start_at": start_at,
        "end_at": end_at,
        "gcal_event_id": gcal_event_id,
        "outlook_event_id": outlook_event_id,
    }


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
            outlook_event_id = ""
        else:
            return {
                "action": "update",
                "status": "skip",
                "reason": f"対象の予定が見つかりませんでした: {title_hint}",
            }
    else:
        gcal_event_id = index_entry.get("event_id", "")
        outlook_event_id = index_entry.get("outlook_event_id", "")

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
        if not range_start or not range_end:
            return {"action": "delete", "status": "skip", "reason": "一括削除には範囲（range_start〜range_end）が必要です"}

        gcal_events = await find_gcal_events_in_range(range_start, range_end, inclusive_end=True)
        if not gcal_events:
            return {"action": "delete", "status": "skip", "reason": f"{range_start}〜{range_end} の範囲に予定が見つかりませんでした"}

        deleted_count = 0
        deleted_titles = []

        # Googleカレンダーから全件削除
        for event in gcal_events:
            ev_id = event.get("id", "")
            ev_title = event.get("summary", "予定")
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

        # Outlookカレンダーからも全件削除
        try:
            outlook_events = await find_outlook_events_in_range(range_start, range_end)
            for ov in outlook_events:
                ov_id = ov.get("id", "")
                ov_title = ov.get("subject", "")
                if ov_id:
                    try:
                        await delete_outlook_event(ov_id)
                        logger.info(f"Outlook一括削除: {ov_title}")
                    except Exception as e:
                        logger.error(f"Outlook一括削除エラー ({ov_title}): {e}")
        except Exception as e:
            logger.error(f"Outlook期間検索エラー: {e}")

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
        # Google Calendarから直接検索して削除を試みる
        gcal_event = await find_gcal_event(
            title_hint=title_hint,
            start_iso=op.get("start_at"),
            query=query,
        )
        if gcal_event:
            gcal_event_id = gcal_event.get("id", "")
            outlook_event_id = ""
        else:
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

