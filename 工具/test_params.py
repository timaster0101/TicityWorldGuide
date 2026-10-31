# -*- coding: utf-8 -*-
"""第4期运行参数包回归。除 Idempotency 会重跑生成器外只读已落盘产物，不改动仓库内容。

跑法：python 工具/test_params.py（工作目录＝设定集根）
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))


class RingPairGeometry(unittest.TestCase):
    EXPECTED = {
        '内湖环|内湖环': (380, 6.948, 1.157, 9.501, 5.791),
        '内湖环|外城环': (400, 8.958, 2.849, 12.350, 6.108),
        '内湖环|产业小镇': (320, 26.401, 16.470, 36.754, 10.352),
        '内湖环|特色村落': (160, 22.257, 12.251, 42.931, 20.673),
        '外城环|外城环': (380, 11.116, 1.852, 15.200, 9.264),
        '外城环|产业小镇': (320, 26.958, 13.648, 39.598, 13.310),
        '外城环|特色村落': (160, 23.776, 9.402, 45.780, 22.004),
        '产业小镇|产业小镇': (240, 38.131, 6.403, 62.936, 31.728),
        '产业小镇|特色村落': (128, 34.365, 5.657, 69.354, 34.989),
        '特色村落|特色村落': (56, 36.020, 5.000, 62.610, 31.020),
    }

    def test_ten_pairs_with_measured_stats(self):
        import anchors
        stats = anchors.ring_pair_stats()
        self.assertEqual(sorted(stats), sorted(self.EXPECTED))
        for key, want in self.EXPECTED.items():
            got = stats[key]
            self.assertEqual((got['锚点对数'], got['中位直线km'], got['最小km'],
                              got['最大km'], got['最大偏差km']), want, key)

    def test_deviation_counts_short_side_too(self):
        import anchors
        got = anchors.ring_pair_stats()['内湖环|内湖环']
        # 6.948 − 1.157 = 5.791 > 9.501 − 6.948 = 2.553：定值失真主要来自相邻锚点这一侧
        self.assertEqual(got['最大偏差km'], round(got['中位直线km'] - got['最小km'], 3))
        self.assertGreater(got['最大偏差km'], round(got['最大km'] - got['中位直线km'], 3))


class SourceShape(unittest.TestCase):
    SECTIONS = ('技能', '季节月份', '交通', '圈层对', '天气', '事件', '检查点')

    def setUp(self):
        self.src = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))

    def test_seven_sections_present(self):
        self.assertEqual([k for k in self.SECTIONS if k not in self.src['参数']], [])
        self.assertEqual(len(self.src['参数']['交通']['方式']), 5)
        self.assertEqual(len(self.src['参数']['交通']['延后方式']), 3)
        self.assertEqual(len(self.src['参数']['圈层对']), 10)
        self.assertEqual(len(self.src['参数']['天气']['态']), 6)
        self.assertEqual(len(self.src['参数']['天气']['逐月游程']), 12)

    def test_month_runs_expand_to_2013_month_lengths(self):
        days = dict(zip(range(1, 13), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]))
        total = 0
        for month, runs in self.src['参数']['天气']['逐月游程'].items():
            span = sum(c for _, c in runs)
            self.assertEqual(span, days[int(month)], f'{month} 月游程合计 {span} 天')
            self.assertTrue(all(runs[i][0] != runs[i + 1][0] for i in range(len(runs) - 1)),
                            f'{month} 月存在相邻同态游程')
            self.assertTrue(all(c <= 10 for _, c in runs), f'{month} 月单游程超过 10 天')
            total += span
        self.assertEqual(total, 365)

    def test_declared_ring_pair_values_match_registry_geometry(self):
        import anchors
        stats = anchors.ring_pair_stats()
        for row in self.src['参数']['圈层对']:
            key = anchors.pair_key(row['A'], row['B'])
            got = stats[key]
            for src_field, stat_field in (('声明中位直线km', '中位直线km'), ('声明最小km', '最小km'),
                                          ('声明最大km', '最大km'), ('声明最大偏差km', '最大偏差km')):
                self.assertAlmostEqual(row[src_field], got[stat_field], delta=0.05,
                                       msg=f'{key} {src_field}')
            self.assertEqual(row['锚点对数'], got['锚点对数'], key)


if __name__ == '__main__':
    unittest.main()
