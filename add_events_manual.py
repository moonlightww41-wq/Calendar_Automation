"""
画像の2イベントを直接Google & Outlookカレンダーに登録するスクリプト
対象: 5/8 13:00 打合せ / 5/8 13:00 社内打合せ
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

EVENTS = [
    {
        "title": "打合せ",
        "start": "2026-05-08T13:00:00+09:00",
        "end":   "2026-05-08T14:00:00+09:00",
    },
    {
        "title": "社内打合せ",
        "start": "2026-05-08T13:00:00+09:00",
        "end":   "2026-05-08T14:00:00+09:00",
    },
]


async def main():
    from services.gcal_service import add_gcal_event
    from services.outlook_service import add_outlook_event

    print("=" * 50)
    print("  イベント直接登録")
    print(f"  実行日時: {datetime.now(JST).strftime('%Y-%m-%d %H:%M')} JST")
    print("=" * 50)

    for ev in EVENTS:
        title = ev["title"]
        start = ev["start"]
        end   = ev["end"]

        print(f"\n📅 [{title}] {start[:16]} 〜 {end[11:16]}")

        # Google Calendar
        try:
            gcal_id = await add_gcal_event(
                title=title,
                start_at=start,
                end_at=end,
                description="",
            )
            print(f"  ✅ Google登録完了: {gcal_id}")
        except Exception as e:
            print(f"  ❌ Google登録失敗: {e}")

        # Outlook Calendar
        try:
            outlook_id = await add_outlook_event(
                title=title,
                start_at=start,
                end_at=end,
                description="",
            )
            print(f"  ✅ Outlook登録完了: {outlook_id}")
        except Exception as e:
            print(f"  ❌ Outlook登録失敗: {e}")

    print("\n" + "=" * 50)
    print("  完了")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
