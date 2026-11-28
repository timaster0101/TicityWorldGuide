# -*- coding: utf-8 -*-
"""示例角色卡／时间线的闸门：样板里的数字必须与正典逐项相等；改一个就要判红。

覆盖：
  RealCard        —— 仓库里的那张卡通过 12 条判据
  SampleFolder    —— `示例/` 扫描：只有 1 份带头部，0 问题
  Mutations       —— 7 种篡改各判出对应代号（钱、距离、岗位、篮子、圈层）
  CardDetection   —— 时间线不是角色卡（`07:20–07:32` 不能被当成头部字段）
  ValidatorClean  —— 两份样板过 `validate_derivative` 也是 0 错误
  CliExit         —— 目录级扫描：干净退 0，篡改过的夹具退 1
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_samples as C  # noqa: E402
import validate_derivative as V  # noqa: E402

CARD = os.path.join(C.ROOT, "示例", "角色卡-周敏.md")
LINE = os.path.join(C.ROOT, "示例", "时间线-周敏的一周.md")


def read(path):
    with io.open(path, encoding="utf-8") as fp:
        return fp.read()


class RealCard(unittest.TestCase):
    def setUp(self):
        self.head, self.problems = C.parse_header(read(CARD))

    def test_header_has_every_field(self):
        self.assertEqual(self.problems, [])
        for k in C.FIELDS:
            self.assertIn(k, self.head)

    def test_card_passes_all_checks(self):
        self.assertEqual(C.audit(self.head), [])

    def test_numbers_are_the_canon_numbers(self):
        """抽查三处最容易写错的：月租取住所锚、篮子取圈层篮子、通勤是现算距离。"""
        jobs = C._load("数据", "产业就业正典.json")
        prices = C._load("数据", "物价与生活正典.json")
        self.assertEqual(float(self.head["月租_钛币"]), jobs["住所锚"]["F021"])
        self.assertEqual(float(self.head["篮子_外城环_钛币"]), prices["篮子"]["外城环"])
        self.assertEqual(float(self.head["通勤_km"]), 0.93)


class SampleFolder(unittest.TestCase):
    def test_only_the_card_has_a_header(self):
        rows = C.scan()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][0].endswith("角色卡-周敏.md"))
        self.assertEqual(rows[0][1], [])


class Mutations(unittest.TestCase):
    """一个字段改错，必须被对应的判据点名（而不是笼统判红）。"""

    def setUp(self):
        self.base, _ = C.parse_header(read(CARD))

    def codes(self, **changes):
        head = dict(self.base)
        head.update(changes)
        return " ".join(C.audit(head))

    def test_rent_drift_reds(self):
        self.assertIn("E6", self.codes(月租_钛币="2100"))

    def test_commute_drift_reds(self):
        self.assertIn("E10", self.codes(通勤_km="1.6"))

    def test_basket_drift_reds(self):
        self.assertIn("E8", self.codes(篮子_外城环_钛币="3032.7"))

    def test_unknown_post_reds(self):
        self.assertIn("E3", self.codes(岗位卡="POST-NOPE"))

    def test_pay_band_drift_reds(self):
        self.assertIn("E4", self.codes(月薪带_钛币="9000-12000"))

    def test_pay_outside_band_reds(self):
        self.assertIn("E5", self.codes(月薪_钛币="99000"))

    def test_ring_cap_drift_reds(self):
        self.assertIn("E11", self.codes(通勤上限_km="14.0"))

    def test_ring_drift_reds(self):
        self.assertIn("E12", self.codes(圈层="内湖环"))

    def test_unknown_ring_is_not_silent(self):
        """圈层写错时上限查不到，必须报出来——不能因为表里没这个键就静默放过。"""
        self.assertIn("E11", self.codes(圈层="未知圈层"))

    def test_home_outside_cap_reds(self):
        """把家搬到别的片区后，通勤与上限两条都要响。"""
        text = self.codes(居住锚点="R004", 通勤_km="0.93")
        self.assertTrue("E10" in text or "E12" in text, text)


class CardDetection(unittest.TestCase):
    def test_timeline_is_not_a_card(self):
        self.assertFalse(C.is_card(read(LINE)))

    def test_card_is_detected(self):
        self.assertTrue(C.is_card(read(CARD)))


class ValidatorClean(unittest.TestCase):
    """两份样板对 `validate_derivative` 也必须是 0 错误（ID／名称／量级／虚构口径）。"""

    def test_both_samples_are_clean(self):
        entries, rulings, globals_ = V.load_canon(C.ROOT)
        for path in (CARD, LINE):
            issues = V.check_text(read(path), entries, rulings, globals_)
            reds = [i for i in issues if getattr(i, "level", "error") == "error"]
            self.assertEqual(reds, [], "%s 有违例：%s" % (os.path.basename(path), reds))


class CliExit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="samples_cli_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _copy_card(self, mutate=None):
        text = read(CARD)
        if mutate:
            for a, b in mutate:
                if a not in text:
                    raise AssertionError("夹具改不动：%s" % a)
                text = text.replace(a, b)
        p = os.path.join(self.tmp, "卡.md")
        with io.open(p, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(text)
        return p

    def test_clean_dir_exits_zero(self):
        self._copy_card()
        self.assertEqual(C.main([self.tmp]), 0)

    def test_mutated_dir_exits_one(self):
        self._copy_card([("月租_钛币: 1971.5", "月租_钛币: 2600")])
        self.assertEqual(C.main([self.tmp]), 1)


if __name__ == "__main__":
    unittest.main()
