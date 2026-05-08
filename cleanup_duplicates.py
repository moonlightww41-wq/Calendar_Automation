"""
重複イベント削除スクリプト
対象: 5/8 の「打合せ」「社内打合せ」の重複を1件だけ残して削除
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
TARGET_TITLES = ["打合せ", "社内打合せ"]
TARGET_DATE   = "2026-05-08"


async def cleanup_google():
    from services.gcal_service import _get_service
    import config

    print("\n── Google Calendar ──")
    service = _get_service()
    calendar_id = config.GOOGLE_CALENDAR_ID

    result = service.events().list(
        calendarId=calendar_id,
        timeMin=f"{TARGET_DATE}T00:00:00+09:00",
        timeMax=f"{TARGET_DATE}T23:59:59+09:00",
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])

    for title in TARGET_TITLES:
        matched = [e for e in events if e.get("summary", "") == title]
        print(f"\n  [{title}] 該当件数: {len(matched)}件")
        if len(matched) <= 1:
            print(f"  → 重複なし、スキップ")
            continue
        # 1件目を残し、2件目以降を削除
        for e in matched[1:]:
            try:
                service.events().delete(calendarId=calendar_id, eventId=e["id"]).execute()
                start = e.get("start", {}).get("dateTime", "?")[:16]
                print(f"  ✅ 削除: {e['id']} ({start})")
            except Exception as ex:
                print(f"  ❌ 削除失敗: {ex}")
        print(f"  → {len(matched)-1}件削除、1件残しました")


async def cleanup_outlook():
    from services.outlook_service import _headers, _get_access_token
    import httpx
    import config

    print("\n── Outlook Calendar ──")
    headers = _headers()
    user = config.OUTLOOK_USER_EMAIL

    # Microsoft Graph calendarView はUTC形式が必要
    url = (
        f"https://graph.microsoft.com/v1.0/users/{user}/calendarView"
        f"?startDateTime={TARGET_DATE}T00:00:00Z"
        f"&endDateTime={TARGET_DATE}T15:00:00Z"
        f"&$select=id,subject,start"
        f"&$top=50"
    )

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        events = resp.json().get("value", [])

    for title in TARGET_TITLES:
        matched = [e for e in events if e.get("subject", "") == title]
        print(f"\n  [{title}] 該当件数: {len(matched)}件")
        if len(matched) <= 1:
            print(f"  → 重複なし、スキップ")
            continue
        for e in matched[1:]:
            del_url = f"https://graph.microsoft.com/v1.0/users/{user}/events/{e['id']}"
            async with httpx.AsyncClient() as client:
                try:
                    r = await client.delete(del_url, headers=headers)
                    if r.status_code == 204:
                        print(f"  ✅ 削除: {e['id'][:30]}...")
                    else:
                        print(f"  ❌ 削除失敗 (status={r.status_code}): {r.text[:100]}")
                except Exception as ex:
                    print(f"  ❌ 削除失敗: {ex}")
        print(f"  → {len(matched)-1}件削除、1件残しました")


async def main():
    now = datetime.now(JST)
    print("=" * 50)
    print("  重複イベント削除")
    print(f"  実行日時: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"  対象日: {TARGET_DATE}")
    print("=" * 50)

    await cleanup_google()
    await cleanup_outlook()

    print("\n" + "=" * 50)
    print("  完了")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
