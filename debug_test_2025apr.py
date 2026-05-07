"""
2025年4月 カレンダーテスト
============================
対象: 2025年4月の予定のみ（2026年の予定には一切触れない）
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


async def run_tests():
    from services.openai_service import parse_calendar_operations

    now = datetime.now(JST)
    print("=" * 60)
    print("  2025年4月 カレンダーテスト")
    print(f"  実行日時: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print("  ※ 2025年4月の予定のみ対象")
    print("=" * 60)

    CASES = [
        # ─── 追加（ADD）
        ("ADD-01", "2025/4/5 15時 A社打ち合わせ",
         {"action": "add", "year_check": 2025, "month_check": 4, "day_check": 5}),

        ("ADD-02", "2025年4月10日 10時 現場視察（能代）入れといて",
         {"action": "add", "year_check": 2025, "month_check": 4, "day_check": 10}),

        ("ADD-03", "2025/4/15 14時 定例会議 追加して",
         {"action": "add", "year_check": 2025, "month_check": 4, "day_check": 15}),

        ("ADD-04", "2025/4/20 終日 展示会",
         {"action": "add", "year_check": 2025, "month_check": 4}),

        ("ADD-05", "2025年4月25日 朝イチ 社内MTG入れといて",
         {"action": "add", "year_check": 2025, "month_check": 4, "day_check": 25}),

        # ─── 変更（UPDATE）
        ("UPD-01", "2025/4/5の打ち合わせ、16時に変更して",
         {"action": "update", "hint_check": "打ち合わせ"}),

        ("UPD-02", "2025/4/10の現場視察、2025/4/11の同じ時間に移して",
         {"action": "update", "hint_check": "現場視察"}),

        ("UPD-03", "2025年4月15日の定例会議30分早めといて",
         {"action": "update", "hint_check": "定例会議"}),

        ("UPD-04", "2025/4/20の展示会、2025/4/22に変更で",
         {"action": "update", "hint_check": "展示会"}),

        # ─── 削除（DELETE）
        ("DEL-01", "2025/4/5の打ち合わせ流れたから消して",
         {"action": "delete", "hint_check": "打ち合わせ"}),

        ("DEL-02", "2025/4/10の現場視察キャンセルで",
         {"action": "delete", "hint_check": "現場視察"}),

        ("DEL-03", "2025年4月25日の社内MTGなくなったわ",
         {"action": "delete", "hint_check": "MTG"}),

        # ─── 期間削除（RANGE DELETE）
        ("RNG-01", "2025/4/1から2025/4/30まで全部消して",
         {"action": "delete", "delete_all": True, "year_check": 2025}),

        ("RNG-02", "2025年4月の予定を全部削除して",
         {"action": "delete", "delete_all": True}),

        # ─── 複数操作（MULTI）
        ("MLT-01", "2025/4/5 15時 A社訪問と、2025/4/10 14時 B社打ち合わせを入れといて",
         {"action": "add", "multi": True, "count": 2}),

        ("MLT-02", "2025/4/5の現場視察キャンセルで、2025/4/15の定例会議16時に変更して",
         {"action": "delete", "multi": True, "count": 2}),

        # ─── 自然言語（NATURAL）
        ("NAT-01", "あの2025/4/21の視察なんかなくなったっぽいから消しといて",
         {"action": "delete", "hint_check": "視察"}),

        ("NAT-02", "2025年4月3日のex_第2回定例会って消えてたっけ？なかったら消して",
         {"action": "delete", "hint_check": "定例"}),
    ]

    passed = 0
    failed = 0
    errors = []

    for case_id, text, expect in CASES:
        try:
            result = await parse_calendar_operations(text)
            ops = result.get("operations", [])
            op = ops[0] if ops else {}

            action = op.get("action", "")
            query = op.get("query") or {}
            title_hint = query.get("title_hint", "") or ""
            start_at = op.get("start_at", "") or ""
            delete_all = op.get("delete_all_in_range", False)

            ok = True
            fail_reasons = []

            # アクション確認
            if expect.get("action") and action != expect["action"]:
                ok = False
                fail_reasons.append(f"action={action}（期待: {expect['action']}）")

            # 年チェック
            if expect.get("year_check"):
                yr = expect["year_check"]
                rs = query.get("range_start", "") or ""
                re_ = query.get("range_end", "") or ""
                found_year = str(yr) in start_at or str(yr) in rs or str(yr) in re_
                if not found_year and not delete_all:
                    ok = False
                    fail_reasons.append(f"年{yr}がstart_atに見つからない（start_at={start_at}）")

            # 月チェック
            if expect.get("month_check") and start_at:
                m = expect["month_check"]
                if f"-0{m}-" not in start_at and f"-{m:02d}-" not in start_at:
                    if not delete_all:
                        ok = False
                        fail_reasons.append(f"{m}月がstart_atにない（{start_at}）")

            # 日チェック
            if expect.get("day_check") and start_at:
                d = expect["day_check"]
                day_str = f"-{d:02d}T"
                if day_str not in start_at:
                    if not delete_all:
                        ok = False
                        fail_reasons.append(f"{d}日がstart_atにない（{start_at}）")

            # キーワードチェック
            if expect.get("hint_check"):
                kw = expect["hint_check"]
                title = op.get("title", "") or ""
                if kw not in title_hint and kw not in title:
                    ok = False
                    fail_reasons.append(f"'{kw}' が見つからない（hint={title_hint}, title={title}）")

            # 削除一括
            if expect.get("delete_all") and not delete_all:
                ok = False
                fail_reasons.append("delete_all_in_rangeがTrueでない")

            # 複数操作
            if expect.get("multi") and len(ops) < expect.get("count", 2):
                ok = False
                fail_reasons.append(f"複数操作が{len(ops)}件（期待: {expect['count']}件以上）")

            if ok:
                passed += 1
                print(f"\n[{case_id}] {text[:45]}")
                print(f"  ✅ action={action}, start_at={start_at[:16] if start_at else 'N/A'}, hint={title_hint}")
                if expect.get("multi"):
                    print(f"       複数操作: {len(ops)}件")
                    for i, o in enumerate(ops):
                        q2 = o.get("query") or {}
                        h = q2.get("title_hint", "") or ""
                        print(f"         [{i}] action={o.get('action')}, hint={h}")
            else:
                failed += 1
                errors.append((case_id, text, fail_reasons))
                print(f"\n[{case_id}] {text[:45]}")
                print(f"  ❌ 失敗: {' / '.join(fail_reasons)}")
                print(f"       action={action}, start_at={start_at}, hint={title_hint}")

        except Exception as e:
            import traceback
            failed += 1
            errors.append((case_id, text, [str(e)]))
            print(f"\n[{case_id}] {text[:45]}")
            print(f"  💥 例外: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  結果: {passed}/{passed + failed} 合格")
    if errors:
        print("\n  失敗一覧:")
        for cid, txt, reasons in errors:
            print(f"  [{cid}] {txt[:35]}... → {', '.join(reasons)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
