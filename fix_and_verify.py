"""
最終状態確認 + Outlookへ再登録（必要な場合のみ）
"""
import asyncio, httpx, config
from services.outlook_service import _headers
from services.gcal_service import _get_service

TARGET_DATE = "2026-05-08"
EVENTS = [
    {"title": "打合せ",   "start": "2026-05-08T13:00:00+09:00", "end": "2026-05-08T14:00:00+09:00"},
    {"title": "社内打合せ", "start": "2026-05-08T13:00:00+09:00", "end": "2026-05-08T14:00:00+09:00"},
]

async def check_and_fix():
    print("=" * 50)
    print("  最終確認 & 修正")
    print("=" * 50)

    # ─── Google確認 ───
    print("\n── Google Calendar ──")
    service = _get_service()
    cal_id = config.GOOGLE_CALENDAR_ID
    res = service.events().list(
        calendarId=cal_id,
        timeMin=f"{TARGET_DATE}T00:00:00+09:00",
        timeMax=f"{TARGET_DATE}T23:59:59+09:00",
        singleEvents=True, orderBy="startTime",
    ).execute()
    gevents = res.get("items", [])
    for ev in EVENTS:
        found = [e for e in gevents if e.get("summary") == ev["title"]]
        print(f"  [{ev['title']}] {len(found)}件 → {'✅OK' if len(found)==1 else '⚠️ '+str(len(found))+'件'}")

    # ─── Outlook確認 & 再登録 ───
    print("\n── Outlook Calendar ──")
    from services.outlook_service import add_outlook_event

    h = _headers()
    user = config.OUTLOOK_USER_EMAIL
    url = (
        f"https://graph.microsoft.com/v1.0/users/{user}/calendarView"
        f"?startDateTime=2026-05-07T15:00:00Z&endDateTime=2026-05-09T15:00:00Z"
        f"&$select=id,subject,start&$top=50"
    )
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=h)
        oevents = r.json().get("value", []) if r.status_code == 200 else []

    for ev in EVENTS:
        found = [e for e in oevents if e.get("subject") == ev["title"]]
        print(f"  [{ev['title']}] {len(found)}件", end="")
        if len(found) == 1:
            print(" → ✅OK")
        elif len(found) == 0:
            print(" → ❌なし → 再登録します")
            try:
                result = await add_outlook_event(
                    title=ev["title"],
                    start_at=ev["start"],
                    end_at=ev["end"],
                    description="",
                )
                print(f"    ✅ 再登録完了: {result['id'][:30]}...")
            except Exception as ex:
                print(f"    ❌ 再登録失敗: {ex}")
        else:
            # 重複あり → 1件残して削除
            print(f" → ⚠️ 重複あり → {len(found)-1}件削除します")
            for e in found[1:]:
                del_url = f"https://graph.microsoft.com/v1.0/users/{user}/events/{e['id']}"
                async with httpx.AsyncClient() as c:
                    r2 = await c.delete(del_url, headers=h)
                    print(f"    {'✅ 削除OK' if r2.status_code==204 else '❌ 失敗'}")

    print("\n" + "=" * 50)
    print("  完了")
    print("=" * 50)

asyncio.run(check_and_fix())
