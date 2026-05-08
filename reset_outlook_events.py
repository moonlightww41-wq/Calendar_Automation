"""
Outlook 5/8 の対象イベントを全削除 → 正しい時刻で再登録
"""
import asyncio, httpx, config, requests
from services.outlook_service import _headers, _to_graph_dt, _cal_url
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
USER = config.OUTLOOK_USER_EMAIL
TITLES = ["打合せ", "社内打合せ"]
EVENTS = [
    {"title": "打合せ",    "start": "2026-05-08T13:00:00+09:00", "end": "2026-05-08T14:00:00+09:00"},
    {"title": "社内打合せ", "start": "2026-05-08T13:00:00+09:00", "end": "2026-05-08T14:00:00+09:00"},
]

async def reset_outlook():
    h = _headers()
    print("=" * 50)
    print("  Outlook イベントリセット")
    print(f"  実行: {datetime.now(JST).strftime('%H:%M')} JST")
    print("=" * 50)

    # ── STEP1: 今日の全イベントを検索 ──
    print("\n[STEP1] 5/8 のOutlookイベントを検索...")
    url = (
        f"https://graph.microsoft.com/v1.0/users/{USER}/calendarView"
        f"?startDateTime=2026-05-07T00:00:00Z&endDateTime=2026-05-09T00:00:00Z"
        f"&$select=id,subject,start&$top=50"
    )
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=h)
        all_events = r.json().get("value", []) if r.status_code == 200 else []

    # 対象タイトルだけ絞り込んで表示
    targets = [e for e in all_events if e.get("subject") in TITLES]
    print(f"  対象イベント: {len(targets)}件")
    for e in targets:
        print(f"    - {e['subject']} / {e['start']['dateTime'][:16]} UTC (id={e['id'][:25]}...)")

    # ── STEP2: 全削除 ──
    print("\n[STEP2] 全削除...")
    for e in targets:
        del_url = f"https://graph.microsoft.com/v1.0/users/{USER}/events/{e['id']}"
        async with httpx.AsyncClient() as c:
            r2 = await c.delete(del_url, headers=h)
            status = "✅ 削除OK" if r2.status_code == 204 else f"❌ {r2.status_code}"
            print(f"  {status}: {e['subject']}")

    # ── STEP3: 変換確認（デバッグ）──
    print("\n[STEP3] タイムゾーン変換確認...")
    test_dt = _to_graph_dt("2026-05-08T13:00:00+09:00")
    print(f"  入力: 2026-05-08T13:00:00+09:00")
    print(f"  変換結果: {test_dt}")

    # ── STEP4: 正しい時刻で再登録 ──
    print("\n[STEP4] 再登録...")
    for ev in EVENTS:
        body = {
            "subject": ev["title"],
            "start": _to_graph_dt(ev["start"]),
            "end":   _to_graph_dt(ev["end"]),
        }
        print(f"  登録リクエスト: {body['subject']} start={body['start']}")
        r = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{USER}/events",
            headers=h,
            json=body,
            timeout=15
        )
        if r.status_code in (200, 201):
            res = r.json()
            actual_start = res.get("start", {}).get("dateTime", "?")[:16]
            print(f"  ✅ 登録完了: {ev['title']} → Outlookが受け取った開始時刻: {actual_start}")
        else:
            print(f"  ❌ 失敗 {r.status_code}: {r.text[:150]}")

    # ── STEP5: 最終確認 ──
    print("\n[STEP5] 最終確認...")
    async with httpx.AsyncClient() as c:
        r = await c.get(url, headers=h)
        final_events = r.json().get("value", []) if r.status_code == 200 else []
    for t in TITLES:
        found = [e for e in final_events if e.get("subject") == t]
        start_utc = found[0]['start']['dateTime'][:16] if found else "-"
        # UTC→JST変換表示
        if found:
            from datetime import timezone, timedelta
            dt_utc = datetime.fromisoformat(start_utc + ":00Z").replace(tzinfo=timezone.utc)
            dt_jst = dt_utc.astimezone(JST)
            jst_str = dt_jst.strftime("%H:%M JST")
        else:
            jst_str = "なし"
        print(f"  [{t}] {len(found)}件 / 開始時刻: {jst_str}")

    print("\n" + "=" * 50)
    print("  完了")
    print("=" * 50)

asyncio.run(reset_outlook())
