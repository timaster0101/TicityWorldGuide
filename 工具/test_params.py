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


class CanonDerived(unittest.TestCase):
    ARTIFACTS = ('运行参数正典.json', '运行参数总表.md')

    def setUp(self):
        self.canon = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))

    def test_matrix_shape_33_usable_17_dash(self):
        cells = self.canon['交通矩阵']
        self.assertEqual(len(cells), 50)
        self.assertEqual(sum(1 for c in cells if c['耗时分钟'] is not None), 33)
        self.assertEqual(sum(1 for c in cells if c['耗时分钟'] is None), 17)

    def test_matrix_spot_values(self):
        got = {(c['圈层对'], c['方式']): c['耗时分钟'] for c in self.canon['交通矩阵']}
        self.assertEqual(got[('内湖环|外城环', 'TR-BUS')], 50)
        self.assertEqual(got[('内湖环|产业小镇', 'TR-CAR')], 85)
        self.assertEqual(got[('内湖环|特色村落', 'TR-RAIL')], 50)
        self.assertEqual(got[('产业小镇|特色村落', 'TR-BUS')], 165)
        self.assertEqual(got[('特色村落|特色村落', 'TR-CAR')], 115)
        self.assertIsNone(got[('内湖环|内湖环', 'TR-RAIL')])
        self.assertIsNone(got[('内湖环|产业小镇', 'TR-WALK')])

    def test_year_table_and_month_lookup(self):
        year = self.canon['天气年历']
        self.assertEqual(len(year), 365)
        self.assertEqual(year[0], dict(year[0], **{'年内第几天': 1, '月': 1, '日': 1,
                                                   'SEA': 'SEA-4', '态': 'WX-OVC', '名': '阴'}))
        self.assertEqual(year[-1]['年内第几天'], 365)
        self.assertEqual(year[-1]['月'], 12)
        self.assertEqual(self.canon['月季节'],
                         {'1': 'SEA-4', '2': 'SEA-4', '3': 'SEA-1', '4': 'SEA-1', '5': 'SEA-1',
                          '6': 'SEA-2', '7': 'SEA-2', '8': 'SEA-2', '9': 'SEA-3', '10': 'SEA-3',
                          '11': 'SEA-3', '12': 'SEA-4'})

    def test_deriver_is_byte_idempotent(self):
        import hashlib
        import subprocess
        before = {a: hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest() for a in self.ARTIFACTS}
        for _ in range(2):
            subprocess.run([sys.executable, str(ROOT / '工具' / 'build_params.py')],
                           check=True, capture_output=True)
            for a in self.ARTIFACTS:
                self.assertEqual(hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest(),
                                 before[a], f'{a} 双跑不幂等')


class RenderedTable(unittest.TestCase):
    def test_table_row_counts(self):
        import re
        table = (ROOT / '数据' / '运行参数总表.md').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'^\| TR-[A-Z]+ \|', table, re.M)), 50)
        self.assertEqual(len(re.findall(r'^\| \d+ \| \d+ \| \d+ \| SEA-[1-4] \| WX-[A-Z]+ \|',
                                        table, re.M)), 365)
        self.assertEqual(len(re.findall(r'^\| 内湖环 \||^\| 外城环 \||^\| 产业小镇 \||^\| 特色村落 \|',
                                        table, re.M)), 10)
        self.assertEqual(len(re.findall(r'^\| SEA-[1-4] \|', table, re.M)), 4)
        for token in ('禁止手改', '中位直线 km', '最大偏差 km', '延后方式', '用户自助回档'):
            self.assertIn(token, table)
        # 圈层对键名里的竖线必须转义，否则 markdown 表格会把一格拆成两列
        self.assertNotIn('内湖环|内湖环', table)
        self.assertGreaterEqual(table.count('内湖环\\|内湖环'), 1)

    def test_no_ellipsis_or_replacement_in_artifacts(self):
        for name in ('运行参数正典.json', '运行参数总表.md'):
            text = (ROOT / '数据' / name).read_text(encoding='utf-8')
            self.assertNotIn('\ufffd', text, name)
            self.assertNotIn('\u2026', text, f'{name} 混入 U+2026 省略号')


class GateExtended(unittest.TestCase):
    def setUp(self):
        import verify_occupations as vo
        self.vo = vo

    def test_twenty_five_checks_registered(self):
        self.assertEqual(len(self.vo.CHECKS), 25)
        self.assertEqual(self.vo.CHECKS[20:],
                         ['参数完整性', '交通矩阵可复算', '天气年历闭合', '技能阈值同源', '事件与检查点自洽'])

    def test_gate_green_and_report_records_params(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / '工具' / 'verify_occupations.py')],
                           check=True, capture_output=True, text=True)
        self.assertIn('二十五条判红', r.stdout)
        rep = json.loads((ROOT / '数据' / '产业就业核验.json').read_text(encoding='utf-8'))
        self.assertEqual(rep['检查项数'], 25)
        self.assertEqual(rep['参数汇总']['矩阵格数'], 50)
        self.assertEqual(rep['参数汇总']['年历格数'], 365)


class DocsSynced(unittest.TestCase):
    TOKENS = ('各交通方式固定耗时', '天气的画面演进与表现规则', '事件冷却与负面配额',
              '技能成长与退化阈值', '检查点频率')

    def test_index_param_gap_line_removed(self):
        index = (ROOT / '城市运行规则索引.md').read_text(encoding='utf-8')
        self.assertNotIn('- 参数类：', index)
        for token in self.TOKENS:
            self.assertEqual(index.count(token), 1, token)
            self.assertTrue(any(token in l and l.startswith('- 已收口（第4期运行参数')
                                for l in index.splitlines()), token)
        self.assertIn('已收口（第4期运行参数，见《运行参数设定》）', index)

    def test_narrative_doc_matches_canon_numbers(self):
        canon = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))
        doc = (ROOT / '运行参数设定.md').read_text(encoding='utf-8')
        for token in ('0／12／24／48／96', '1.35', '33 格', '17 格', '365 格',
                      '个人 7 天', '每自然月 2 次', '00:00', '不提供用户自助回档'):
            self.assertIn(token, doc)
        self.assertEqual(canon['汇总']['可用格数'], 33)

    def test_manual_and_entry_and_book_wired(self):
        manual = (ROOT / 'AI创作使用手册.md').read_text(encoding='utf-8')
        self.assertIn('运行参数源表.json', manual)
        self.assertIn('build_params.py', manual)
        self.assertIn('二十五条判据', manual)
        self.assertIn('四十五类改坏', manual)
        self.assertLess(manual.index('build_occupations.py'), manual.index('build_params.py'))
        entry = (ROOT / '阅读入口.md').read_text(encoding='utf-8')
        self.assertIn('运行参数设定.md', entry)
        self.assertIn('运行参数总表.md', entry)
        book = (ROOT / '钛湖城城市设定集-完整合订本.md').read_text(encoding='utf-8')
        self.assertIn('# 钛湖城运行参数设定', book)
        self.assertNotIn('标签升阶与退化阈值留给第4期', book)


class RulingsEightyEight(unittest.TestCase):
    PHASE_IDS = ['C75', 'C76', 'C77', 'C78', 'C79', 'C80', 'C81']

    def test_seven_new_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 93)
        self.assertEqual(rows[-1]['编号'], 'C93')


if __name__ == '__main__':
    unittest.main()
