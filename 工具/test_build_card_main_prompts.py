# -*- coding: utf-8 -*-
"""build_card_main_prompts.py 正负测。夹具走 tempfile 并 monkeypatch OUT_DIR，不往被守护仓库写一个字节。"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import build_card_main_prompts as M


def manifest_codes():
    with open(os.path.join(M.ROOT, M.MANIFEST), encoding="utf-8") as fh:
        man = json.load(fh)["cards"]
    return [c["code"] for c in man if c["status"] in ("OK", "OVERFLOW") and c["code"]], man


class DeriveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _write(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def test_clause_is_prepended_and_canon_lines_survive_verbatim(self):
        base = ("前置行（不该进派生串）\n【画风锚点】medium is a semi-realistic digital painting\n"
                "【取景指令】东广场离地1.5米朝西，以35毫米拍摄完整四坡顶。\n"
                "【外观辨识】青石基座承托灰白抹灰塔身。\n")
        p = self._write("b.txt", base)
        out = M.derive(p)
        lines = out.split("\n")
        self.assertEqual(lines[0], "【画风锚点】medium is a semi-realistic digital painting")
        self.assertNotIn("前置行", out)
        self.assertTrue(lines[1].startswith("【取景指令】" + M.CLAUSE))
        self.assertTrue(lines[1].endswith("东广场离地1.5米朝西，以35毫米拍摄完整四坡顶。"))
        self.assertEqual(lines[2], "【外观辨识】青石基座承托灰白抹灰塔身。")
        self.assertEqual(out.count(M.CLAUSE), 1)

    def test_missing_sections_raise(self):
        with self.assertRaises(ValueError):
            M.derive(self._write("n1.txt", "没有锚点\n【取景指令】x\n"))
        with self.assertRaises(ValueError):
            M.derive(self._write("n2.txt", "【画风锚点】painting\n【外观辨识】x\n"))

    def test_clause_declares_precedence_over_the_frozen_3_2_wording(self):
        """底串【全局硬设定】仍写 3:2，派生串必须自带「冲突以本条为准」，否则两条画幅措辞互相抵消。"""
        self.assertIn("3:4竖幅", M.CLAUSE)
        self.assertIn("以本条为准", M.CLAUSE)
        self.assertIn("满幅", M.CLAUSE)
        # 探针（2026-11-08 L022）实测两处退化：竖幅被模型当成新的背景授权、底部带塞满人群反光。
        # 这两句是探针带回的订正，掉了就会放量放成同一形态，故钉在串上而不是写在文档里。
        self.assertIn("未点名的现代高层群", M.CLAUSE)
        self.assertIn("不放人群正面", M.CLAUSE)
        self.assertIn("不得有枝叶", M.CLAUSE)


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig = M.OUT_DIR
        M.OUT_DIR = self.tmp.name
        self.addCleanup(setattr, M, "OUT_DIR", self._orig)
        self._orig_root = os.getcwd()
        self.addCleanup(os.chdir, self._orig_root)
        self._orig_pending = M.PENDING
        self.addCleanup(setattr, M, "PENDING", self._orig_pending)

    def _run(self, argv=None):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = M.main(argv)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def _read(self, path):
        with open(path.replace("/", os.sep), encoding="utf-8") as fh:
            return fh.read()

    def _ledger(self):
        return json.loads(self._read(os.path.join(self.tmp.name, "台账.json")))

    def _pending_copy(self):
        """把待投真源整份取到 tempfile 再按用例改，绝不往被守护仓库写。"""
        with open(os.path.join(M.ROOT, self._orig_pending), encoding="utf-8") as fh:
            doc = json.load(fh)
        p = os.path.join(self.tmp.name, "pending_mutant.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        M.PENDING = p
        return doc, p

    def _write_pending(self, doc, p):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)

    def test_emits_derived_plus_pending_strings(self):
        """台账 114 行＝派生 80（有 3:2 底串，正文取自原文）＋待投 34（正文取自分段真源）。

        条数只按结构（有无 code）归因，不按 manifest 投放状态：34 张补投回填后 status 全转 OK，
        再按状态分档就会把这两条支路读成 114＋0。
        """
        codes, man = manifest_codes()
        pending = M.pending_indices(man)
        summary = self._run()
        self.assertEqual(len(codes), 80)
        self.assertEqual(len(pending), 34)
        self.assertEqual(summary["条数"], len(codes) + len(pending))
        self.assertEqual(summary["条数"], 114)
        files = [f for f in os.listdir(self.tmp.name) if f.endswith(".txt")]
        self.assertEqual(len(files), 114)
        ledger = self._ledger()
        self.assertEqual(ledger["条数"], len(ledger["items"]))
        self.assertEqual(ledger["画幅"], M.SIZE)
        self.assertEqual(sorted(int(x["id"][3:]) for x in ledger["items"] if x["id"].startswith("idx")), pending)
        self.assertEqual(sum(1 for x in ledger["items"] if not x["id"].startswith("idx")), 80)
        for it in ledger["items"]:
            self.assertEqual(it["size"], "768x1024")
            self.assertTrue(os.path.exists(os.path.join(M.ROOT, it["file"].replace("/", os.sep))))
            self.assertTrue(os.path.exists(os.path.join(M.ROOT, it["base_prompt_file"])))

    def test_derived_and_pending_lists_are_a_disjoint_partition(self):
        """两条支路必须互不相交且并起来正好等于实景卡全集：交集非空＝同一张卡产两份串，
        并集不足＝有卡既派生不到也拼不出来，悄悄少一份串。"""
        codes, man = manifest_codes()
        pending = M.pending_indices(man)
        by_idx = {c["idx"]: c["code"] for c in man}
        self.assertFalse(set(pending) & {c["idx"] for c in man if c["code"]},
                         "待投名单混进了有 3:2 底串的卡")
        covered = {c["idx"] for c in man if c["code"]} | set(pending)
        excluded = {c["idx"] for c in man if c["card_type"] == "模板正面" or c["template"] == "back"}
        self.assertEqual(covered | excluded, set(by_idx), "两条支路没盖满 124 张")
        self.assertFalse(covered & excluded, "模板面被投了实景＝违档 A")
        self.assertEqual(len(covered), 114)
        self._run()
        ledger = self._ledger()
        derived_ids = {it["id"] for it in ledger["items"] if not it["id"].startswith("idx")}
        self.assertEqual(derived_ids, set(codes), "派生行的 id 该是卡号，且与 code 集合逐字相等")

    def test_every_pending_card_gets_exactly_one_assembled_string(self):
        """待投卡只允许有拼装串：逐 idx 一一对平，模板正面（档 A 不投实景）一张都不许有。"""
        codes, man = manifest_codes()
        want = M.pending_indices(man)
        faces = sorted(c["idx"] for c in man if c["card_type"] == "模板正面")
        self.assertEqual(len(want), 34)
        self.assertEqual(len(faces), 5)
        self._run()
        ledger = self._ledger()
        got = sorted(int(it["id"][3:]) for it in ledger["items"] if it["id"].startswith("idx"))
        self.assertEqual(got, want)
        self.assertFalse(set(got) & set(faces), "模板正面被投实景＝违档 A")
        for it in ledger["items"]:
            if it["id"].startswith("idx"):
                text = self._read(os.path.join(M.ROOT, it["file"]))
                for field in ("【画面定位】", "【取景指令】", "【外观辨识】", "【人群与烟火气】", "【锁定与禁则】"):
                    self.assertIn(field, text, it["id"] + " 缺分段 " + field)
                self.assertNotIn(M.CLAUSE, text, "待投串走的是 CLAUSE_SCENE，不是派生 CLAUSE")

    def test_pending_skeleton_fingerprint_gate(self):
        """骨架五段承诺「逐字复用 80 张同源件」——手改任一段必须当场抛错，而不是拼进 34 条串。"""
        doc, p = self._pending_copy()
        doc["骨架"]["画风锚点"] = doc["骨架"]["画风锚点"] + " "
        self._write_pending(doc, p)
        with self.assertRaises(ValueError) as cm:
            M.main([])
        self.assertIn("骨架段 画风锚点", str(cm.exception))
        doc, p = self._pending_copy()
        doc["骨架"]["English tail 禁则后缀"] = ""
        self._write_pending(doc, p)
        with self.assertRaises(ValueError) as cm:
            M.main([])
        self.assertIn("待投真源骨架缺段", str(cm.exception))

    def test_pending_list_must_equal_manifest_pending_queue(self):
        """正文与 manifest 待投清单（结构判）差集非空即抛错：多写少写都不许产半份台账。"""
        doc, p = self._pending_copy()
        dropped = doc["items"].pop()
        self._write_pending(doc, p)
        with self.assertRaises(ValueError) as cm:
            M.main([])
        self.assertIn("待投正文与 manifest 待投清单不平", str(cm.exception))
        self.assertIn(str(dropped["idx"]), str(cm.exception))
        doc, p = self._pending_copy()
        doc["items"].append(dict(doc["items"][0]))
        self._write_pending(doc, p)
        with self.assertRaises(ValueError):
            M.main([])

    def test_pending_queue_survives_the_resend_flipping_status_to_ok(self):
        """34 张补投回填后 manifest status 全转 OK，待投名单仍须是这 34 条。

        这条是「口径单源化」的守门：谁把 pending_indices 换回 `status == "MISSING"`，
        名单立刻归零、拼装支路被静默关掉，而生成器仍会产 80 条串而不报错——只有这里能抓住。
        """
        codes, man = manifest_codes()
        pending = M.pending_indices(man)
        self.assertEqual(len(pending), 34)
        st = {c["idx"]: c["status"] for c in man}
        self.assertEqual({st[i] for i in pending}, {"OK"}, "待投卡已不全是回填后的 OK，本条前提变了要重写")
        self.assertFalse(any(st[i] == "MISSING" for i in pending))

    def test_pending_indices_is_structural_not_status_based(self):
        """合成 manifest 逐类喂给 pending_indices：有 code／模板正面／模板背面各归零，只剩空 code 实景卡。"""
        fixture = [
            {"idx": 0, "code": "D01", "card_type": "板块卡", "template": "district", "status": "OK"},
            {"idx": 1, "code": "", "card_type": "职业卡", "template": "info", "status": "MISSING"},
            {"idx": 2, "code": "", "card_type": "职业卡", "template": "info", "status": "OK"},
            {"idx": 3, "code": "", "card_type": "模板正面", "template": "info", "status": "MISSING"},
            {"idx": 4, "code": "", "card_type": "模板背面", "template": "back", "status": "BACK"},
            {"idx": 5, "code": "", "card_type": "兑换卡", "template": "info", "status": "BACK"},
        ]
        self.assertEqual(M.pending_indices(fixture), [1, 2, 5])
        # 反证：按投放状态筛的旧口径在这份夹具上只剩 idx1（idx2/5 已回填转 OK/BACK），
        # 少两条＝拼装支路静默关掉的现场，所以这条断言本身就是"不许换回状态判"的证据。
        self.assertEqual([c["idx"] for c in fixture
                          if c["status"] == "MISSING" and c["card_type"] != "模板正面"], [1])

    def test_tail_join_is_single_comma_and_keeps_compliance_clause(self):
        """四截拼 tail 的回归：拼接处不得出现双逗号，禁则后缀里的平台 AIGC 角标句必须逐条留住。"""
        with open(os.path.join(M.ROOT, self._orig_pending), encoding="utf-8") as fh:
            pend = json.load(fh)
        for it in pend["items"]:
            text = M.compose_pending(it, pend["骨架"], pend["CLAUSE_SCENE"])
            self.assertNotIn(",,", text, it["name"])
            self.assertNotIn("  ,", text, it["name"])
            tail = text.rstrip().split("\n")[-1]
            self.assertTrue(tail.startswith("English tail"), it["name"])
            self.assertIn("3:4 portrait 768x1024", tail, it["name"])
            self.assertIn("preserve mandatory platform AIGC labels and TC260 XMP metadata unchanged", tail,
                          it["name"])
            self.assertEqual(tail.count("overlaid text"), 1, it["name"])

    def test_argv_subset_is_respected(self):
        """派生支路按卡号取、待投支路按 idxNNN 取，两条支路各自命中一条时不产出半份台账。"""
        summary = self._run(["L009"])
        self.assertEqual(summary["条数"], 1)
        self.assertEqual(sorted(f for f in os.listdir(self.tmp.name) if f.endswith(".txt")),
                         ["L009-东岸企业会客厅.txt"])
        for f in os.listdir(self.tmp.name):
            os.remove(os.path.join(self.tmp.name, f))
        summary = self._run(["idx086"])
        self.assertEqual(summary["条数"], 1)
        self.assertEqual(len([f for f in os.listdir(self.tmp.name) if f.endswith(".txt")]), 1)
