# -*- coding: utf-8 -*-
"""开图图片资产核验回归。只读已落盘产物与真实图集，不生成、不修改任何图片。

跑法：python 工具/test_image_assets.py（工作目录＝设定集根）
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))


class ReviewNoteHistory(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.items = {i['id']: i for i in self.manifest['items']}
        self.notes = json.loads((ROOT / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))['备注']

    def test_four_long_notes_recovered(self):
        self.assertEqual(sorted(self.notes), ['D01', 'L007', 'L008', 'R043'])
        # 本轮实测：809ed08 的原始长度 518/226/231/151，各带一条同文派生原因，剥净后如下
        self.assertEqual({k: len(v[0]) for k, v in self.notes.items()},
                         {'D01': 204, 'L007': 491, 'L008': 199, 'R043': 124})
        for eid, rows in self.notes.items():
            self.assertTrue(all(r.strip() for r in rows), eid)
            self.assertNotIn('图片对应的基准提示词已变化', rows[-1], f'{eid} 手工源里混入了派生原因')

    def test_history_survives_and_note_still_derives(self):
        # 260 条没有人工长文本，历史是空数组：判"键在不在"而不是"值真不真"
        self.assertEqual(sum(1 for i in self.items.values() if 'review_note_history' in i), 264)
        self.assertEqual(sum(1 for i in self.items.values() if i['review_note_history']), 4)
        for eid in ('L007', 'L008', 'R043', 'D01'):
            hist = self.items[eid]['review_note_history']
            self.assertEqual(hist, self.notes[eid], eid)
            self.assertIn(self.notes[eid][-1], self.items[eid]['review_note'])
        self.assertEqual(self.manifest['needs_review'], 264)
        self.assertEqual(self.manifest['accepted'], 0)
        self.assertEqual(self.manifest['generated'], 264)
        self.assertEqual(self.manifest['pending'], 0)


if __name__ == '__main__':
    unittest.main()
