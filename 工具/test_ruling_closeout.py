# -*- coding: utf-8 -*-
"""C155 在册裁定收口的闸门：裁定必须真的入账、必须不绑串、且不许把「本可签」的条误收成裁定。

守三件事：
1. 收口面与候选表的现态裁定一一对应（漏一条 = 那条又回到「说不清」状态）；
2. 收口条必须仍待复验且 image_prompt_sha256 为空（一旦绑串，就是把 C154 换档前的产物记成新串产物）；
3. 已在册格有本串投后读数的条不许走裁定收口（那种条该走 C139 代签，误收等于用裁定盖住一次可签的验收）。
"""
import io
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import sys  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, '工具'))

import ruling_closeout as rc  # noqa: E402
import signing_declaration as sd  # noqa: E402


def _load(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


class RealCloseoutIsOnDisk(unittest.TestCase):
    def setUp(self):
        self.manifest = _load(os.path.join(ROOT, '数据', '开图清单.json'))
        self.notes = _load(os.path.join(ROOT, '数据', '开图验收备注.json'))['备注']
        self.cand = rc.candidates_rows()

    def test_candidates_are_ruled(self):
        self.assertTrue(self.cand, '候选表现态裁定为空，收口面无从派生')
        for eid, raw in self.cand.items():
            self.assertTrue(raw.startswith(rc.KINDS), (eid, raw))

    def test_every_pending_ruled_item_has_closeout_row(self):
        pending = {i['id'] for i in self.manifest['items'] if i['status'] == '待复验'}
        expect = pending & set(self.cand)
        got = {eid for eid, rows in self.notes.items() if sd.ruling_rows(rows)}
        self.assertEqual(got & set(self.cand), expect)

    def test_closeout_items_are_unbound(self):
        for item in self.manifest['items']:
            if item['id'] not in self.cand:
                continue
            if item['status'] != '待复验':
                continue
            self.assertFalse(item.get('image_prompt_sha256'), item['id'])
            rows = sd.ruling_rows(self.notes.get(item['id'], []))
            self.assertTrue(rows, item['id'])
            self.assertEqual(rc.audit(rows[-1], item), [], item['id'])

    def test_summary_matches_rows(self):
        doc = _load(os.path.join(ROOT, '数据', '在册裁定收口.json'))
        ids = {r['ID'] for r in doc['逐条']}
        self.assertEqual(ids, {i['id'] for i in self.manifest['items']
                               if i['status'] == '待复验' and i['id'] in self.cand})
        self.assertEqual(doc['统计']['收口'], len(doc['逐条']))


class NegativeCases(unittest.TestCase):
    def _item(self, eid, status='待复验', cells=('X-片区-C154母图重投-v01_1_abcdef12.png',)):
        return {'id': eid, 'status': status, 'image_prompt_sha256': None,
                'image_file': list(cells)}

    def test_row_naming_another_id_reds(self):
        item = self._item('D06')
        row = rc.build_row(item, {}, '在册接受', set())
        bad = rc.audit(row.replace('收口D06：', '收口D10：'), item)
        self.assertIn('收口行抬头点名的 ID 与本条不符', bad)

    def test_row_without_no_binding_sentence_reds(self):
        item = self._item('D06')
        row = rc.build_row(item, {}, '在册接受', set()).replace('不绑串', '')
        self.assertIn('收口行缺要素:不绑串', rc.audit(row, item))

    def test_item_with_current_round_reading_is_refused(self):
        """在册格已有本串投后读数 → 该走代签，不许用裁定把它收掉。"""
        cell = 'D18-西门商贸片区-C154取景换档重投-v01_1795755878942_f1a5b661.png'
        manifest = {'items': [self._item('D18', cells=(cell,))]}
        notes = {'D18': ['C154取景换档申报D18：换档']}
        plan, refused = rc.ruleable(manifest, notes, {'D18': '在册接受'}, {cell})
        self.assertEqual(plan, [])
        self.assertTrue(any('已有本串投后读数' in r for r in refused), refused)

    def test_item_without_switch_declaration_is_refused(self):
        manifest = {'items': [self._item('D06')]}
        plan, refused = rc.ruleable(manifest, {'D06': []}, {'D06': '在册接受'}, set())
        self.assertEqual(plan, [])
        self.assertTrue(any('也没有换档申报' in r for r in refused), refused)


class VisualColumn(unittest.TestCase):
    def test_ruled_pending_shows_ruling(self):
        item = {'status': '待复验', 'image_file': ['a.png'],
                'review_note_history': ['C155在册裁定收口D06：裁定=在册接受']}
        self.assertIn('在册裁定收口', sd.visual_column(item))

    def test_plain_pending_stays_pending(self):
        item = {'status': '待复验', 'image_file': ['a.png'], 'review_note_history': []}
        self.assertEqual(sd.visual_column(item), '待人工复验')


if __name__ == '__main__':
    unittest.main()
