"""
デバッグテストスクリプト
========================
全機能を網羅した20+のテストケースを実行し、
AIが正しく解析できているかを確認する。
"""
import asyncio
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from utils.date_parser import contains_date
from services.openai_service import parse_calendar_operations

JST = ZoneInfo("Asia/Tokyo")

# ==========================================
# テストケース定義
# ==========================================
TEST_CASES = [
    # ─── 追加（add） ─────────────────────────────────────────
    {
        "id": "ADD-01",
        "text": "5/15 15時 A社打ち合わせ",
        "expect_action": "add",
        "expect_title_contains": "A社",
        "expect_gate": True,
    },
    {
        "id": "ADD-02",
        "text": "来週月曜の10時にB社訪問（東京）入れといて",
        "expect_action": "add",
        "expect_title_contains": "B社",
        "expect_gate": True,
    },
    {
        "id": "ADD-03",
        "text": "明日の午後2時に社内会議追加して",
        "expect_action": "add",
        "expect_title_contains": "会議",
        "expect_gate": True,
    },
    {
        "id": "ADD-04",
        "text": "6/10 終日 展示会",
        "expect_action": "add",
        "expect_gate": True,
    },
    {
        "id": "ADD-05",
        "text": "今週金曜の朝イチに電話会議があるから登録して",
        "expect_action": "add",
        "expect_gate": True,
    },
    # ─── 変更（update） ───────────────────────────────────────
    {
        "id": "UPD-01",
        "text": "5/15の打ち合わせ、16時に変更して",
        "expect_action": "update",
        "expect_gate": True,
    },
    {
        "id": "UPD-02",
        "text": "来週月曜のB社訪問、火曜の同じ時間に移して",
        "expect_action": "update",
        "expect_gate": True,
    },
    {
        "id": "UPD-03",
        "text": "明日の会議30分早めといて",
        "expect_action": "update",
        "expect_gate": True,
    },
    {
        "id": "UPD-04",
        "text": "6/10の展示会、6/12に変更で",
        "expect_action": "update",
        "expect_gate": True,
    },
    {
        "id": "UPD-05",
        "text": "今週金曜の電話会議リスケして来週月曜に",
        "expect_action": "update",
        "expect_gate": True,
    },
    # ─── 削除（delete）・口語・曖昧系 ─────────────────────────
    {
        "id": "DEL-01",
        "text": "明日の会議流れたから消して",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "DEL-02",
        "text": "今週金曜のミーティングキャンセルで",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "DEL-03",
        "text": "5/15の打ち合わせ取り消して",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "DEL-04",
        "text": "展示会なくなったわ",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "DEL-05",
        "text": "月曜の視察飛んだ消しといて",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "DEL-06",
        "text": "来週水曜の打ち合わせ中止になった",
        "expect_action": "delete",
        "expect_gate": True,
    },
    # ─── 一括削除（delete_all_in_range） ─────────────────────
    {
        "id": "RNG-01",
        "text": "5/1から5/31まで全部消して",
        "expect_action": "delete",
        "expect_delete_all": True,
        "expect_gate": True,
    },
    {
        "id": "RNG-02",
        "text": "今月の予定全部消してほしいんだけど",
        "expect_action": "delete",
        "expect_delete_all": True,
        "expect_gate": True,
    },
    # ─── 無視（noop） ─────────────────────────────────────────
    {
        "id": "NOP-01",
        "text": "おはようございます",
        "expect_action": "noop",
        "expect_gate": False,
    },
    {
        "id": "NOP-02",
        "text": "了解です",
        "expect_action": "noop",
        "expect_gate": False,
    },
    {
        "id": "NOP-03",
        "text": "https://example.com/meeting",
        "expect_action": "noop",
        "expect_gate": False,
    },
    # ─── 複数操作 ────────────────────────────────────────────
    {
        "id": "MLT-01",
        "text": "5/20 10時 C社訪問、5/21 14時 D社打ち合わせを入れといて",
        "expect_action": "add",  # 最初の操作
        "expect_multi": True,
        "expect_gate": True,
    },
    {
        "id": "MLT-02",
        "text": "4月21日の現場視察キャンセルで、4月24日の定例会議15時に変更して",
        "expect_multi": True,
        "expect_gate": True,
    },
    # ─── 自然言語バリエーション ────────────────────────────────
    {
        "id": "NAT-01",
        "text": "あの視察なんかなくなったっぽいから消しといて 4/21",
        "expect_action": "delete",
        "expect_gate": True,
    },
    {
        "id": "NAT-02",
        "text": "来週のやつ、2時間後にずらしてくれる？",
        "expect_action": "update",
        "expect_gate": True,
    },
]


async def run_tests():
    now = datetime.now(JST)
    print(f"{'='*60}")
    print(f"  LINEカレンダー デバッグテスト")
    print(f"  実行日時: {now.strftime('%Y-%m-%d %H:%M')} JST")
    print(f"{'='*60}\n")

    total = len(TEST_CASES)
    passed = 0
    failed = []
    errors = []

    for case in TEST_CASES:
        cid = case["id"]
        text = case["text"]
        print(f"[{cid}] {text}")

        # DateGate チェック
        gate_result = contains_date(text)
        gate_expected = case.get("expect_gate", True)
        gate_ok = gate_result == gate_expected

        if not gate_ok:
            icon = "❌"
            print(f"  {icon} DateGate: {gate_result}（期待: {gate_expected}）")
            failed.append(cid)
            continue

        # DateGateをパスしない場合はここで終了
        if not gate_result:
            print(f"  ✅ DateGate: パス不要（noop想定）")
            passed += 1
            print()
            continue

        # AI解析
        try:
            result = await parse_calendar_operations(text)
            ops = result.get("operations", [])
            first_op = ops[0] if ops else {}
            action = first_op.get("action", "")
            title = first_op.get("title", "")
            query = first_op.get("query", {}) or {}
            title_hint = query.get("title_hint", "")
            delete_all = first_op.get("delete_all_in_range", False)
            is_multi = len(ops) > 1

            # 期待値チェック
            checks = []

            if "expect_action" in case:
                ok = action == case["expect_action"]
                checks.append(("action", ok, f"{action}（期待: {case['expect_action']}）"))

            if "expect_title_contains" in case:
                search_text = title + title_hint
                ok = case["expect_title_contains"] in search_text
                checks.append(("title", ok, f"'{case['expect_title_contains']}' in '{search_text}'"))

            if case.get("expect_delete_all"):
                ok = delete_all
                checks.append(("delete_all", ok, f"delete_all_in_range={delete_all}"))

            if case.get("expect_multi"):
                ok = is_multi or len(ops) >= 2
                checks.append(("multi_ops", ok, f"操作数={len(ops)}"))

            all_ok = all(ok for _, ok, _ in checks)

            if all_ok:
                status = "✅"
                passed += 1
            else:
                status = "❌"
                failed.append(cid)

            print(f"  {status} action={action}, title='{title}', title_hint='{title_hint}'")
            if delete_all:
                range_s = query.get("range_start", "")
                range_e = query.get("range_end", "")
                print(f"       delete_all=True, range={range_s}〜{range_e}")
            if is_multi:
                print(f"       複数操作: {len(ops)}件")
                for i, op in enumerate(ops):
                    print(f"         [{i}] action={op.get('action')}, title={op.get('title')}, hint={op.get('query',{}).get('title_hint','')}")
            for name, ok, msg in checks:
                if not ok:
                    print(f"       ⚠️  {name}: {msg}")

        except Exception as e:
            print(f"  💥 エラー: {e}")
            errors.append(cid)
            failed.append(cid)

        print()

    print(f"{'='*60}")
    print(f"  結果: {passed}/{total} 合格")
    if failed:
        print(f"  ❌ 失敗: {', '.join(failed)}")
    if errors:
        print(f"  💥 エラー: {', '.join(errors)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(run_tests())
