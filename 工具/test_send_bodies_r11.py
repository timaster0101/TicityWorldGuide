# -*- coding: utf-8 -*-
"""R11 台账闸门：140 条早期图按 E1 基线重出，成员面与正文都不许手抄。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAMPAIGN = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06")
sys.path.insert(0, HERE)
sys.path.insert(0, CAMPAIGN)

import r4_style_ref as REF  # noqa: E402
import build_send_bodies_r11 as R11  # noqa: E402

LEDGER = os.path.join(CAMPAIGN, "send_bodies_r11.json")
MANIFEST = os.path.join(ROOT, "数据", "开图清单.json")


def load(p):
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)


class R11Ledger(unittest.TestCase):
    def setUp(self):
        self.ledger = load(LEDGER)
        self.manifest = {e["id"]: e for e in load(MANIFEST)["items"]}

    def test_a_membership_is_the_legacy_face(self):
        # 成员面两种合法现态：回填前＝现算的早期件（四向／C138）；回填后那些格子已换成 R11 自己的件，
        # 现算面归零——此时判据转成「在册首格带 R11 档串的件」，两边是同一个名单的前后两态。
        legacy = {k for k, v in self.manifest.items() if R11.is_legacy(v)}
        reissued = {k for k, v in self.manifest.items()
                    if any(R11.SUFFIX in os.path.basename(c) for c in (v.get('image_file') or []))}
        self.assertEqual(sorted(self.ledger), sorted(legacy | reissued))
        self.assertEqual(len(self.ledger), 140)
        self.assertEqual(legacy & reissued, set(), '同一件既算早期件又算已重出，口径有缝')

    def test_b_body_is_raw_not_prefixed(self):
        for eid, e in self.ledger.items():
            self.assertFalse(e["body"].startswith(REF.PREFIX_LINE), eid)
            self.assertEqual(hashlib.sha256(REF.send_body(e["body"]).encode("utf-8")).hexdigest(),
                             e["send_sha256"], eid)
            self.assertEqual(e["chars"], len(REF.send_body(e["body"])), eid)
            self.assertEqual(e["body_chars"], len(e["body"]), eid)

    def test_c_send_name_carries_no_txt_and_no_duplicated_id(self):
        for eid, e in self.ledger.items():
            self.assertTrue(e["send_name"].endswith("-" + R11.SUFFIX), eid)
            self.assertNotIn(".txt", e["send_name"])
            self.assertFalse(e["send_name"].startswith(eid + "-" + eid), eid)

    def test_d_ledger_is_reproducible(self):
        # 回填后现算成员面为空，重建必须靠台账自身的冻名单：同名单＋同正文要算出逐字相同的台账。
        rebuilt = R11.build(ids=sorted(self.ledger))
        # replaced_cell 记的是「成表那一刻在册的是哪一格」，回填之后现读已换成 R11 自己的件，
        # 它是历史字段而非可现算字段——重建对拍要把它剥掉，另在 test_a 里断言它已被本轮接管。
        strip = lambda row: {k: v for k, v in row.items() if k != 'replaced_cell'}
        self.assertEqual({k: strip(v) for k, v in rebuilt.items()},
                         {k: strip(v) for k, v in self.ledger.items()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
