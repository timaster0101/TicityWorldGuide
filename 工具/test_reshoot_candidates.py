# -*- coding: utf-8 -*-
"""下一轮重投候选表的读数闸门（`数据/下一轮重投候选.json`）。

候选表不是判据面，但它的每个数字都得是真源现读，否则下一轮照着它投就会投错东西。这里钉三件事：
① 每个候选的在册件仍挂在清单上、sha12 与表里一致；
② R8 三枚的 sun_blob_px／字节／sha12 与 round_readings_r8.json 逐项相等；
③ 卡面与片区两组的读数分别与各自的复验读数件一致（互相指认，不复制两份真源）。
"""
import hashlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'reshoot_campaign_2026_11_06'))
import current_cells as cc

TABLE = os.path.join(ROOT, '数据', '下一轮重投候选.json')
R8 = os.path.join(HERE, 'reshoot_campaign_2026_11_06', 'round_readings_r8.json')
CARD = os.path.join(ROOT, '数据', '卡面附带观察复验.json')
PAIRS = os.path.join(ROOT, '数据', '片区重复构图复验.json')


def _jload(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.loads(fp.read())


class Candidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = _jload(TABLE)
        cls.rows = {r['id']: r for r in cls.t['候选']}
        _q, cells, exc = cc.current_cells(ROOT)
        assert not exc, exc
        cls.cells = {r['id']: r for r in cells}

    def test_a_members_and_counts(self):
        self.assertEqual(len(self.rows), 14, '候选条目数与总额不符')
        self.assertEqual(self.t['总额']['候选条目数'], len(self.rows))
        self.assertEqual(sum(r['预计调用'] for r in self.rows.values()), self.t['总额']['若全部放行所需调用'])
        self.assertEqual(self.t['总额']['若全部放行所需调用'], 3)
        self.assertEqual([i for i, r in self.rows.items() if r['探针']], ['D18'])
        self.assertEqual(sum(r['预计调用'] for r in self.rows.values() if r['现态裁定'].startswith('未定')), 3)

    def test_b_main_chain_cells_match_the_manifest(self):
        for eid in ('D18', 'D19', 'L069', 'D06', 'D10', 'D11', 'D15', 'D12', 'D20'):
            row = self.rows[eid]
            cell = self.cells[eid]['cell']
            base = os.path.basename(cell)
            later = ('C154取景二次重投', 'C154取景换档重投', 'C156E1基线重出', 'C156E1基线补出')
            self.assertTrue(base == row['在册件'] or any(t in base for t in later),
                            '%s 的在册件与清单不一致（既不是候选表记的那枚，也不被更晚一轮接管）：%s'
                            % (eid, base))
            if base != row['在册件']:
                # 已被更晚一轮接管：在册读数记的是候选表成表时那一枚，不该再对盘上现格取 sha。
                continue
            with io.open(os.path.join(ROOT, cell.replace('/', os.sep)), 'rb') as fp:
                sha = hashlib.sha256(fp.read()).hexdigest()[:12]
            self.assertIn('sha12 ' + sha, row['在册读数'], eid + ' 的 sha12 读数过期')

    def test_c_r8_rows_match_the_readings_file(self):
        r8 = {r['id']: r for r in _jload(R8)['rows']}
        for eid in ('D18', 'D19', 'L069'):
            r = r8[eid]
            s = self.rows[eid]['在册读数']
            for piece in ('%d 字节' % r['bytes'], 'sha12 %s' % r['sha256_12'], 'sun_blob_px %d' % r['sun_blob_px']):
                self.assertIn(piece, s, eid + ' 缺读数 %s' % piece)
            self.assertEqual(self.rows[eid]['在册件'], r['file'])

    def test_d_card_and_pair_groups_are_backed_by_their_own_records(self):
        card = _jload(CARD)
        self.assertEqual({r['编号'] for r in card['复验']}, {'①', '②', '③'})
        card_text = json.dumps(card, ensure_ascii=False)
        for eid in ('idx086', 'L027', 'L046', 'D09', 'L009'):
            self.assertIn(eid, card_text, '卡面复验件里找不到 %s' % eid)
        pairs = {r['id']: r for r in _jload(PAIRS)['在册件读数']}
        for eid in ('D06', 'D10', 'D11', 'D15', 'D12', 'D20'):
            self.assertIn('sha12 ' + pairs[eid]['sha12'], self.rows[eid]['在册读数'])

    def test_e_user_rulings_are_written_into_every_row(self):
        for eid, r in self.rows.items():
            self.assertTrue(r['现态裁定'], eid + ' 没写现态裁定')
            self.assertTrue(r['串面依据'], eid + ' 没写串面依据')
        for eid in ('D09', 'L009', 'L046', 'L027', 'idx086'):
            self.assertIn('不用管', self.rows[eid]['现态裁定'])
            self.assertEqual(self.rows[eid]['预计调用'], 0)
        for eid in ('D06', 'D10', 'D11', 'D15', 'D12', 'D20'):
            self.assertIn('默认', self.rows[eid]['现态裁定'])
            self.assertEqual(self.rows[eid]['预计调用'], 0)


if __name__ == '__main__':
    unittest.main()
