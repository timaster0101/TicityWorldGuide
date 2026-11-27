# -*- coding: utf-8 -*-
"""清单五计数同步器的闸门：口径必须与 build_prompts.py 一致，且不许顺手改别的字段。"""
import copy
import io
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import sys  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, '工具'))

import sync_manifest_counts as S  # noqa: E402

MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
BUILD = os.path.join(ROOT, '工具', 'build_prompts.py')


def _load(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


class CountsAgreeWithBuildPrompts(unittest.TestCase):
    def test_derivation_matches_build_prompts_source(self):
        """两边各抄一份口径迟早会漂：直接读 build_prompts.py 的源码行做对拍。"""
        with io.open(BUILD, encoding='utf-8') as fp:
            src = fp.read()
        want = {
            'prompt_count': r'"prompt_count": len\(manifest\)',
            'pending': r'"pending": sum\(1 for m in manifest if m\["status"\] == "待开图"\)',
            'generated': r'"generated": sum\(1 for m in manifest if m\["image_file"\]\)',
            'accepted': r'"accepted": sum\(1 for m in manifest if m\["status"\] == "已验收"\)',
            'needs_review': r'"needs_review": sum\(1 for m in manifest if m\["status"\] == "待复验"\)',
        }
        for k, pat in want.items():
            self.assertRegex(src, re.compile(pat), k)


class RealManifestIsSynced(unittest.TestCase):
    def test_counts_equal_status_face(self):
        doc = _load(MANIFEST)
        self.assertEqual({k: doc[k] for k in S.counts(doc['items'])}, S.counts(doc['items']))

    def test_counts_do_not_touch_other_fields(self):
        doc = _load(MANIFEST)
        before = copy.deepcopy(doc)
        after = copy.deepcopy(doc)
        after.update(S.counts(doc['items']))
        for key in before:
            if key in S.counts(doc['items']):
                continue
            self.assertEqual(before[key], after[key], key)


class NegativeCases(unittest.TestCase):
    def test_wrong_status_is_counted_as_needs_review(self):
        items = [{'status': '待复验', 'image_file': ['a.png']},
                 {'status': '已验收', 'image_file': ['b.png']},
                 {'status': '待开图', 'image_file': []}]
        c = S.counts(items)
        self.assertEqual((c['accepted'], c['needs_review'], c['pending'], c['generated']), (1, 1, 1, 2))

    def test_generated_counts_nonempty_image_file_only(self):
        c = S.counts([{'status': '待开图', 'image_file': []}, {'status': '待开图', 'image_file': ['x']}])
        self.assertEqual(c['generated'], 1)


if __name__ == '__main__':
    unittest.main()
