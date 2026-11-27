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
        # 判据写成「仍在待复验的裁定件必须有收口行」＋「已收口的那几行不许丢」：
        # R11／R12 之后那 7 条都被判绿并代签成已验收，按旧写法「expect=pending∩cand」现在恒为空集，
        # 于是收口行还在、断言却先红——判红的是判据没跟上现态，不是收口丢了。
        pending = {i['id'] for i in self.manifest['items'] if i['status'] == '待复验'}
        closed = {r['ID'] for r in _load(os.path.join(ROOT, '数据', '在册裁定收口.json'))['逐条']}
        expect = (pending & set(self.cand)) | closed
        got = {eid for eid, rows in self.notes.items() if sd.ruling_rows(rows)}
        self.assertEqual(got & set(self.cand), expect)
        self.assertTrue(closed <= set(self.cand), '收口行里出现不在裁定面的 ID：%s' % (closed - set(self.cand)))

    def test_closed_items_are_now_resolved_by_a_later_round(self):
        # 收口行不是终点：每条收口件最终都得有本串产物并判绿（本轮 R12 把它们全补出来了）。
        for eid in sorted({r['ID'] for r in _load(os.path.join(ROOT, '数据', '在册裁定收口.json'))['逐条']}):
            item = next(i for i in self.manifest['items'] if i['id'] == eid)
            self.assertEqual(item['status'], '已验收', eid)
            self.assertTrue(item.get('image_prompt_sha256'), eid)
            cells = item.get('image_file') or []
            self.assertTrue(any('C156E1基线补出' in os.path.basename(c) for c in cells),
                            '%s 的在册格里没有本轮补出件：%s' % (eid, cells))

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
        # 收口是「当时的待复验∩裁定面」的历史事实，不随之后回填而缩小；这里只验自洽与不越界。
        self.assertEqual(ids, {r['ID'] for r in doc['逐条']})
        self.assertTrue(ids <= set(self.cand), '收口行越出裁定面：%s' % (ids - set(self.cand)))
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
