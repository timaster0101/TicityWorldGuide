# -*- coding: utf-8 -*-
"""R10 目视结论件的对拍闸门：结论必须与投送台账一一对应，且不达标名单与逐枚判词不矛盾。

守的是什么：目视结论是人工判词，没有代码可复算；唯一能机检的是「有没有漏判、有没有自相矛盾」。
漏一枚 = 那一枚既没判红也没判绿就悄悄过了；名单与判词不一致 = 后面引用的人会取到错的账。
"""
import io
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
VERDICT = os.path.join(ROOT, '数据', 'R10目视结论.json')
LEDGER = os.path.join(ROOT, '数据', 'R10方舟投送记录.json')


def _load(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


class VerdictMatchesLedger(unittest.TestCase):
    def setUp(self):
        self.v = _load(VERDICT)
        self.rows = _load(LEDGER)['rows']

    def test_ids_cover_ledger_exactly(self):
        self.assertEqual({r['ID'] for r in self.v['逐枚']}, {r['id'] for r in self.rows})

    def test_no_duplicate_ids(self):
        ids = [r['ID'] for r in self.v['逐枚']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_fail_list_agrees_with_rows(self):
        bad = sorted(r['ID'] for r in self.v['逐枚'] if r['取景与量级'] == '不达标')
        self.assertEqual(bad, sorted(self.v['统计']['不达标ID']))
        self.assertEqual(self.v['统计']['不达标'], len(bad))

    def test_accepted_list_agrees_with_rows(self):
        """「在册接受」是裁定档，不是达标档：判词原文必须留着，依据里必须写得出是哪一次裁定。"""
        acc = sorted(r['ID'] for r in self.v['逐枚'] if r['取景与量级'] == '在册接受')
        self.assertEqual(acc, sorted(self.v['统计']['在册接受ID']))
        self.assertEqual(self.v['统计']['取景与量级在册接受'], len(acc))
        for r in self.v['逐枚']:
            if r['取景与量级'] != '在册接受':
                continue
            self.assertIn(r['原判词'], ('不达标',), r['ID'])
            self.assertIn('裁定', r['依据'], r['ID'])

    def test_counts_agree(self):
        s = self.v['统计']
        self.assertEqual(s['投送'], len(self.v['逐枚']))
        self.assertEqual(
            s['投送'], s['取景与量级达标'] + s['取景与量级在册接受'] + s['不达标'], s)
        self.assertEqual(s['画风达标'], sum(1 for r in self.v['逐枚'] if r['画风'] == '达标'))

    def test_every_row_has_reason(self):
        for r in self.v['逐枚']:
            self.assertTrue(r['依据'].strip(), r['ID'])


if __name__ == '__main__':
    unittest.main()
