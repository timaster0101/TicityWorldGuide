# -*- coding: utf-8 -*-
"""片区图三对同构图的读数件闸门（`数据/片区重复构图复验.json`）。

守两件事：
① 六枚在册件仍是登记的那六枚（sha12），否则「三对同构图」的结论失去载体；
② 六条取景指令的机位句仍逐字是「外缘中轴公共观景屋面＋离地55米＋35毫米」这套模板，
   朝向清单不变——这是本件把根因判给「模板」而不是「母图」的前提。模板一改，本件要重做。
"""
import glob
import hashlib
import io
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.dont_write_bytecode = True
RECORD = os.path.join(ROOT, '数据', '片区重复构图复验.json')
PROMPTS = os.path.join(ROOT, '数据', '开图提示词')
IDS = ('D06', 'D10', 'D11', 'D15', 'D12', 'D20')
FACING = {'D06': '朝北', 'D10': '朝144°', 'D11': '朝南', 'D15': '朝324°', 'D12': '朝216°', 'D20': '朝144°'}


def _jload(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.loads(fp.read())


def prompt_of(cid):
    hits = sorted(glob.glob(os.path.join(PROMPTS, '%s-*.txt' % cid)))
    assert len(hits) == 1, (cid, hits)
    with io.open(hits[0], encoding='utf-8') as fp:
        return fp.read()


class PairsRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = _jload(RECORD)
        cls.rows = {r['id']: r for r in cls.rec['在册件读数']}

    def test_a_record_covers_exactly_the_three_named_pairs(self):
        self.assertEqual(sorted(self.rows), sorted(IDS))
        self.assertEqual(len(self.rows), 6)

    def test_b_on_disk_files_are_the_recorded_ones(self):
        for cid in IDS:
            p = os.path.join(ROOT, '数据', '图集', cid, self.rows[cid]['文件'])
            self.assertTrue(os.path.isfile(p), p + ' 不在盘')
            with io.open(p, 'rb') as fp:
                data = fp.read()
            self.assertEqual(len(data), self.rows[cid]['字节'], cid + ' 字节变了')
            self.assertEqual(hashlib.sha256(data).hexdigest()[:12], self.rows[cid]['sha12'],
                             cid + ' sha12 变了＝在册件换了，三对同构图的结论要重看')

    def test_c_framing_template_is_still_one_template(self):
        for cid in IDS:
            txt = prompt_of(cid)
            self.assertIn('外缘中轴公共观景屋面', txt, cid + ' 的机位句型变了')
            self.assertIn('机位离地55米', txt, cid)
            self.assertIn('35毫米' + FACING[cid], txt, cid + ' 的朝向与记录不一致')
        self.assertIn('机位离地55米', self.rec['串面取证（根因在模板，不只在母图）']['逐条机位句'][0])

    def test_d_note_on_same_facing_pair_outside_the_three(self):
        """D10 与 D20 朝向逐字相同却不在被点名的三对里：这条反例是本件「不能按朝向筛」的依据。"""
        self.assertEqual(FACING['D10'], FACING['D20'])
        self.assertIn(re.search(r'朝\d{3}°', prompt_of('D10')).group(0),
                      prompt_of('D20'), 'D10／D20 朝向不再相同，本件那条反例要改')
        self.assertIn('D10 与 D20 的朝向逐字相同', self.rec['串面取证（根因在模板，不只在母图）']['另一条硬事实'])


if __name__ == '__main__':
    unittest.main()
