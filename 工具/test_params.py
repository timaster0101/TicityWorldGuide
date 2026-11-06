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
        self.assertEqual([m['码'] for m in self.src['参数']['交通']['延后方式']], [])
        self.assertEqual([m['码'] for m in self.src['参数']['交通']['矩阵外方式']],
                         ['TR-FERRY', 'TR-SHUTTLE', 'TR-TUNNEL', 'TR-CABLE', 'TR-AIR'])
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

    def test_matrix_outside_modes_are_carried_not_deferred(self):
        """轮渡、山外接驳、进岛的隧道／缆车与第9期的航空班线都在矩阵外单列查表，不进 50 格、也不留「延后」。"""
        self.assertEqual([m['码'] for m in self.canon['矩阵外方式']],
                         ['TR-FERRY', 'TR-SHUTTLE', 'TR-TUNNEL', 'TR-CABLE', 'TR-AIR'])
        self.assertEqual(self.canon['汇总']['延后方式数'], 0)
        self.assertEqual(self.canon['汇总']['矩阵外方式数'], 5)
        matrix_codes = {c['方式'] for c in self.canon['交通矩阵']}
        self.assertEqual(matrix_codes & {'TR-FERRY', 'TR-SHUTTLE', 'TR-AIR', 'TR-TUNNEL', 'TR-CABLE'}, set())
        air = next(m for m in self.canon['矩阵外方式'] if m['码'] == 'TR-AIR')
        self.assertEqual(air['真源'], '数据/空间通行源表.json')
        self.assertEqual(air['读数'], '数据/空间通行正典.json 的 航空班线')
        # 延后清空后小节不能悬空：总表要有一句「本期无延后方式」，而不是只剩表头
        table = (ROOT / '数据' / '运行参数总表.md').read_text(encoding='utf-8')
        self.assertIn('本期无延后方式', table)

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
        for token in ('禁止手改', '中位直线 km', '最大偏差 km', '延后方式', '矩阵外方式', '用户自助回档'):
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

    def test_thirty_five_checks_registered(self):
        self.assertEqual(len(self.vo.CHECKS), 35)
        self.assertEqual(self.vo.CHECKS[20:25],
                         ['参数完整性', '交通矩阵可复算', '天气年历闭合', '技能阈值同源', '事件与检查点自洽'])

    def test_gate_green_and_report_records_params(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / '工具' / 'verify_occupations.py')],
                           check=True, capture_output=True, text=True)
        self.assertIn('三十五条判红', r.stdout)
        rep = json.loads((ROOT / '数据' / '产业就业核验.json').read_text(encoding='utf-8'))
        self.assertEqual(rep['检查项数'], 35)
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
        # 第9期 9a 多了第三份手填真源：手册若漏了它，改卡牌正文的人就不知道门禁的条数带住在哪。
        self.assertIn('卡牌实例源表.json', manual)
        self.assertIn('三十五条判据', manual)
        self.assertIn('一百四十八类改坏', manual)
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
        self.assertEqual(len(rows), 132)
        self.assertEqual(rows[-1]['编号'], 'C132')


class FiveStatScaleC119(unittest.TestCase):
    """刻度一换，卡牌点数与三份正文必须同时跟着重算：这条纪律以前只住在「有人记得改」里，
    现在由跨度反推一次、再拿反推值去比对真源与正文，刻度改了而点数没改就红。"""

    def test_points_and_prose_follow_the_scale(self):
        skill = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))['参数']['技能']
        lo, hi = skill['五维刻度']
        span = hi - lo
        ratio = skill['五维微调比例']
        per_card = round(span * ratio['单卡占跨度上限'])
        per_dim = round(span * ratio['同维度累计占跨度上限'])
        step = round(span * ratio['退化下限占跨度'])
        self.assertEqual(skill['五维退化下限'], step)
        adm = json.loads((ROOT / '数据' / '岗位准入源表.json').read_text(encoding='utf-8'))
        family = next(f for f in adm['卡牌族'] if f['id'] == 'CRD-A3')
        self.assertEqual(family['幅度上限'], f'单卡 {per_card} 点，同维度累计 {per_dim} 点')
        prose = {
            '运行参数设定.md': [f'{lo}—{hi} 的整数刻度', f'单卡微调 ≤{per_card} 点、同维度累计 ≤{per_dim} 点',
                                f'每 12 个训练月 +{step} 点（上限 {hi}）', f'−{step} 点（下限 {step}'],
            '产业与就业设定.md': [f'五维单卡不超过 {per_card} 点、同维度累计不超过 {per_dim} 点',
                                  f'{lo}—{hi} 刻度下为 {per_card}／{per_dim} 点'],
            '城市运行与居民生活模拟-待确认大纲.md': [f'单卡五维微调不超过 {per_card} 点、同维度累计不超过 {per_dim} 点'],
        }
        for doc, needles in prose.items():
            text = (ROOT / doc).read_text(encoding='utf-8')
            for needle in needles:
                self.assertIn(needle, text)

    def test_c119_records_the_hard_wording(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertEqual(set(by_id['C119']), {'编号', '裁定', '原因', '影响'})
        self.assertIn('三处数值一律改为按跨度反推', by_id['C119']['裁定'])
        self.assertIn('下界非负且上界大于下界', by_id['C119']['裁定'])
        self.assertIn('单卡 10 点，同维度累计 20 点', by_id['C119']['裁定'])
        self.assertIn('旧校验把 2 与 4 两个点数直接写进', by_id['C119']['原因'])
        self.assertIn('94/94 判红', by_id['C119']['影响'])
        self.assertIn('分卷/原稿/*.md 零改动', by_id['C119']['影响'])
        self.assertIn('计数钉 118→119', by_id['C119']['影响'])


class PhaseEightOpening(unittest.TestCase):
    """第8期三组开局等式（C121）：中位、上下界、影响上限、组合数、权重和全部从源表反推，
    正典只许复述反推值——任何一处被写成第二个字面量，这里与门禁第 34 条会各红一次。"""

    def test_opening_band_is_reverse_derived_from_the_source(self):
        skill = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))['参数']['技能']
        lo, hi = skill['五维刻度']
        span = hi - lo
        opening = skill['五维开局']
        weight = skill['背景卡权重']
        canon = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))['五维开局']
        mid = round(span * opening['中位占跨度'])
        per_dim = round(span * skill['五维微调比例']['同维度累计占跨度上限'])
        per_card = round(span * skill['五维微调比例']['单卡占跨度上限'])
        self.assertEqual(opening['中位'], mid)
        self.assertEqual(canon['中位'], mid)
        self.assertEqual(canon['开局区间'], [mid - per_dim, mid + per_dim])
        self.assertEqual(canon['刻度跨度'], span)
        self.assertEqual(canon['半宽'], per_dim)
        self.assertEqual([canon['单类影响上限'], canon['同维度累计影响上限']], [per_card, per_dim])
        self.assertEqual([canon['微调单卡点数'], canon['微调累计点数']], [per_card, per_dim])
        self.assertEqual([weight['单类影响占跨度'], weight['同维度累计影响占跨度']],
                         [skill['五维微调比例']['单卡占跨度上限'],
                          skill['五维微调比例']['同维度累计占跨度上限']])
        combos = 1
        for cat in weight['类别']:
            combos *= cat['候选数']
        self.assertEqual(canon['候选组合数'], combos)
        self.assertEqual(canon['权重和'], sum(c['权重'] for c in weight['类别']))
        self.assertGreater(opening['满值罕见线'], canon['开局区间'][1] + per_card)
        self.assertLess(canon['开局区间'][0], lo + span)
        self.assertGreaterEqual(canon['开局区间'][0], lo)

    def test_background_cards_stay_out_of_the_card_dictionary(self):
        adm = json.loads((ROOT / '数据' / '岗位准入源表.json').read_text(encoding='utf-8'))
        self.assertTrue(all(not f['id'].startswith('BG-') for f in adm['卡牌族']))
        self.assertTrue(all(not str(k).startswith('BG-') for k in adm['持有上限']))

    def test_c121_records_the_hard_wording(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertEqual(set(by_id['C121']), {'编号', '裁定', '原因', '影响'})
        self.assertIn('三十四条判红', by_id['C121']['影响'])
        self.assertIn('132/132 判红', by_id['C121']['影响'])
        self.assertIn('计数钉 120→121', by_id['C121']['影响'])


if __name__ == '__main__':
    unittest.main()
