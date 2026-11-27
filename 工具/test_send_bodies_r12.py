# -*- coding: utf-8 -*-
"""R12 台账闸门：7 条待复验片区按今天的串补出，成员面与正文都不许手抄。"""
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
import build_send_bodies_r12 as R12  # noqa: E402

LEDGER = os.path.join(CAMPAIGN, "send_bodies_r12.json")
MANIFEST = os.path.join(ROOT, "数据", "开图清单.json")


def load(p):
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)


class R12Ledger(unittest.TestCase):
    def setUp(self):
        self.ledger = load(LEDGER)
        self.manifest = {e["id"]: e for e in load(MANIFEST)["items"]}

    def test_a_membership_is_exactly_the_pending_seven(self):
        # 回填前成员面＝7 条待复验；回填并代签之后那 7 条已是已验收，判据转成「在册首格带 R12 档串的件」。
        pending = {k for k, v in self.manifest.items() if v.get("status") == "待复验"}
        reissued = {k for k, v in self.manifest.items()
                    if any(R12.SUFFIX in os.path.basename(c) for c in (v.get("image_file") or []))}
        self.assertEqual(sorted(self.ledger), sorted(pending | reissued))
        self.assertEqual(len(self.ledger), 7)
        self.assertEqual(pending & reissued, set(), "同一件既算待复验又算已补出，口径有缝")

    def test_b_send_name_and_suffix(self):
        for eid, e in self.ledger.items():
            self.assertTrue(e["send_name"].endswith("-" + R12.SUFFIX), eid)
            self.assertNotIn(".txt", e["send_name"])
            self.assertFalse(e["send_name"].startswith(eid + "-" + eid), eid)

    def test_c_body_is_verbatim_and_ledger_is_reproducible(self):
        rebuilt = R12.build(ids=sorted(self.ledger))
        # 同上：replaced_cell 与 status_before 都是成表那一刻的历史字段（成表时 7 条是待复验、
        # 在册格是 C154母图重投件），回填并代签后现读已变，不参与逐字对拍；现态另由 test_a／test_e 断言。
        strip = lambda row: {k: v for k, v in row.items()
                             if k not in ('replaced_cell', 'status_before')}
        self.assertEqual({k: strip(v) for k, v in rebuilt.items()},
                         {k: strip(v) for k, v in self.ledger.items()})
        for eid, e in self.ledger.items():
            src = os.path.join(ROOT, e["file"].replace("/", os.sep))
            self.assertTrue(os.path.exists(src), eid)
            with io.open(src, encoding="utf-8") as fh:
                raw = fh.read()
            self.assertIn(e["body"], raw, eid)
            self.assertEqual(hashlib.sha256(REF.send_body(e["body"]).encode("utf-8")).hexdigest(),
                             e["send_sha256"], eid)

    def test_d_mother_image_exists_in_pool(self):
        pool = set(REF.LANDSCAPE) | set(REF.PORTRAIT)
        for eid, e in self.ledger.items():
            self.assertIn(e["ref_image"], pool, eid)
            self.assertTrue(os.path.exists(os.path.join(ROOT, e["ref_image"].replace("/", os.sep))), eid)

    def test_e_size_matches_manifest(self):
        for eid, e in self.ledger.items():
            self.assertEqual(e["size"], self.manifest[eid]["size"], eid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
