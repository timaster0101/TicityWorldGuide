# -*- coding: utf-8 -*-
"""第3期物价与生活成本包回归。除 Idempotency 会重跑生成器外只读已落盘产物，不改动仓库内容。

跑法：python 工具/test_costs.py（工作目录＝设定集根）
"""
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))


class AnchorModule(unittest.TestCase):
    def test_anchors_are_relocated_not_recomputed(self):
        import anchors
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        self.assertEqual(anchors.dwelling_anchors(), canon['住所锚'])
        self.assertEqual(len(anchors.dwelling_anchors()), canon['汇总']['岗位锚点数'])

    def test_ring_lookup_covers_all_64_anchors(self):
        import anchors
        by_id = {e['id']: e for e in anchors.REGISTRY}
        rings = {anchors.entry_ring(by_id[k], by_id) for k in anchors.dwelling_anchors()}
        self.assertEqual(rings, {'内湖环', '外城环', '产业小镇', '特色村落'})


class SourceTableShape(unittest.TestCase):
    DOMAINS = {'PRD-FOOD': 26, 'PRD-UTIL': 18, 'PRD-TRANS': 16, 'PRD-DOM': 22, 'PRD-CARE': 20, 'PRD-CULT': 18}

    def setUp(self):
        self.src = json.loads((ROOT / '数据' / '物价生活源表.json').read_text(encoding='utf-8'))

    def test_domain_row_counts(self):
        from collections import Counter
        got = Counter(c['域'] for c in self.src['品类'])
        self.assertEqual(dict(got), self.DOMAINS)
        self.assertEqual(len(self.src['品类']), 120)

    def test_only_two_hand_filled_columns_per_category(self):
        for c in self.src['品类']:
            self.assertEqual(sorted(c.keys()), sorted(['id', '名称', '域', '必需档基准价', '标准月消耗量']))

    def test_category_ids_match_domain_and_sequence(self):
        from collections import defaultdict
        seen = defaultdict(list)
        for c in self.src['品类']:
            prefix, _, seq = c['id'].rpartition('-')
            self.assertEqual(prefix, c['域'], c['id'])
            self.assertTrue(seq.isdigit() and len(seq) == 2, c['id'])
            seen[c['域']].append(int(seq))
        for dom, nums in seen.items():
            self.assertEqual(nums, list(range(1, len(nums) + 1)), dom)

    def test_service_list_shape(self):
        self.assertEqual(len(self.src['服务']), 12)
        self.assertEqual([s['id'] for s in self.src['服务']], [f'SVC-{i:02d}' for i in range(1, 13)])
        for s in self.src['服务']:
            self.assertIn(s['减免档'], ('WEL-A', 'WEL-B', 'WEL-C'))

    def test_parameters_present(self):
        p = self.src['参数']
        self.assertEqual(len(p['商品圈层系数']), 4)
        self.assertEqual(len(p['季节系数']), 4)
        self.assertGreater(p['奢侈乘数'], p['改善乘数'])
        self.assertGreater(p['改善乘数'], 1.0)
        self.assertEqual(self.src['散居农村人口'], 42000)
        for ring, ratios in self.src['类型配比'].items():
            self.assertAlmostEqual(sum(ratios), 1.0, places=9, msg=ring)

    def test_second_hand_caps_within_unit_interval(self):
        caps = [d['二手折价上限'] for d in self.src['域表'] if d.get('二手适用')]
        self.assertTrue(caps and all(0.0 < c < 1.0 for c in caps))
        for extra in (self.src.get('服饰上限覆写', {}), self.src.get('耐用品覆写', {})):
            self.assertTrue(all(0.0 < v < 1.0 for v in extra.values()))


class DerivedPrices(unittest.TestCase):
    def setUp(self):
        import build_costs
        self.b = build_costs
        self.src = json.loads((ROOT / '数据' / '物价生活源表.json').read_text(encoding='utf-8'))
        self.p = self.src['参数']

    def test_two_multipliers_produce_three_tiers(self):
        self.assertEqual(self.b.tier_prices(10.0, self.p), {'必需': 10.0, '改善': 18.0, '奢侈': 45.0})

    def test_tier_prices_round_to_min_unit(self):
        self.assertEqual(self.b.tier_prices(7.3, self.p)['改善'], 13.1)

    def test_seasonal_flag_is_derived_not_written(self):
        self.assertTrue(self.b.is_seasonal({'域': 'PRD-FOOD'}))
        self.assertFalse(self.b.is_seasonal({'域': 'PRD-CULT'}))

    def test_second_hand_cap_prefers_override(self):
        self.assertIsNone(self.b.second_hand_cap({'id': 'PRD-FOOD-01', '域': 'PRD-FOOD'}))
        self.assertEqual(self.b.second_hand_cap({'id': 'PRD-DOM-20', '域': 'PRD-DOM'}), 0.4)
        self.assertEqual(self.b.second_hand_cap({'id': 'PRD-DOM-16', '域': 'PRD-DOM'}), 0.5)
        self.assertEqual(self.b.second_hand_cap({'id': 'PRD-CULT-09', '域': 'PRD-CULT'}), 0.55)

    def test_relief_ids_point_at_real_relief_tiers(self):
        """减免归属只能指向 参数.减免比例 里的 WEL-A/B/C，不得枚举下标生成 WEL-0 这类悬空引用。"""
        canon = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))
        tiers = set(canon['参数']['减免比例'])
        for c in canon['品类']:
            self.assertEqual(sorted(c['减免归属']), ['A', 'B', 'C'], c['id'])
            self.assertTrue(set(c['减免归属'].values()) <= tiers, c['id'])
        self.assertEqual(canon['品类'][0]['减免归属'], {'A': 'WEL-A', 'B': 'WEL-B', 'C': 'WEL-C'})


class Basket(unittest.TestCase):
    def setUp(self):
        self.canon = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))

    def test_inner_ring_basket_hits_target_band(self):
        self.assertLessEqual(3000.0, self.canon['篮子']['内湖环'])
        self.assertLessEqual(self.canon['篮子']['内湖环'], 3300.0)

    def test_basket_scales_by_ring_coefficient_only(self):
        base = self.canon['篮子基线_内湖环']
        for coef, ring in zip(self.canon['参数']['商品圈层系数'], self.canon['参数']['圈层顺序']):
            self.assertEqual(self.canon['篮子'][ring], round(base * coef, 1))

    def test_seasonal_view_is_display_only_and_four_values(self):
        view = self.canon['季节展示']
        self.assertEqual(sorted(view), ['SEA-1', 'SEA-2', 'SEA-3', 'SEA-4'])
        self.assertGreater(view['SEA-4'], view['SEA-3'])
        self.assertNotIn('季节', self.canon['篮子'])

    def test_welfare_has_no_hand_filled_amount(self):
        for ring, w in self.canon['保障'].items():
            self.assertEqual(w['生活保障标准_钛币'], self.canon['篮子'][ring])
            self.assertEqual(w['初始资金_钛币'], round(3 * w['生活保障标准_钛币'] + w['押金_钛币'], 1))
            self.assertGreater(w['押金_钛币'], 0)


class Inventory(unittest.TestCase):
    def setUp(self):
        self.canon = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))
        self.rows = self.canon['库存']

    def test_176_rows_44_units(self):
        self.assertEqual(len(self.rows), 176)
        self.assertEqual(len({r['单元ID'] for r in self.rows}), 44)

    def test_rows_cover_four_rings_taken_from_registry_not_hand_written(self):
        self.assertEqual({r['圈层'] for r in self.rows}, {'内湖环', '外城环', '产业小镇', '特色村落'})
        self.assertEqual({r['住房类型ID'] for r in self.rows},
                         {'HOU-01', 'HOU-02', 'HOU-03', 'HOU-04'})

    def test_sparse_rural_reaches_exactly_42000_and_only_on_settlements(self):
        self.assertEqual(sum(r['挂靠人口'] for r in self.rows) // 4, 42000)
        self.assertTrue(all(r['挂靠人口'] == 0 for r in self.rows if r['单元ID'].startswith('D')))

    def test_row_sums_to_households_of_unit(self):
        for u in {r['单元ID'] for r in self.rows}:
            rows = [r for r in self.rows if r['单元ID'] == u]
            self.assertEqual(len(rows), 4, u)
            self.assertEqual(sum(r['总量'] for r in rows), rows[0]['推导户数'], u)
            self.assertEqual(sum(r['登记人口'] for r in rows) // 4 + sum(r['挂靠人口'] for r in rows) // 4,
                             rows[0]['单元人口'], u)

    def test_quota_floor_and_identity(self):
        for r in self.rows:
            self.assertEqual(r['兜底配额'], max(1, math.floor(r['总量'] * 0.05)))
            self.assertEqual(r['可分配'], r['兜底配额'])
            self.assertEqual(r['已占用'] + r['可分配'], r['总量'])
            self.assertGreaterEqual(r['总量'], r['兜底配额'])

    def test_city_households_match_division(self):
        total = sum(r['推导户数'] for r in self.rows if r['住房类型ID'] == 'HOU-01')
        self.assertLessEqual(abs(total - 1654200 / 2.47), 44)
        self.assertEqual(total, self.canon['汇总']['全城户数'])


class Clamp(unittest.TestCase):
    def setUp(self):
        import build_occupations as bo
        self.bo = bo
        self.costs = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))

    def test_band_lower_bound_never_below_effective_line(self):
        basket = self.costs['篮子']['内湖环']
        line = max(3280.2 / 0.4, 3280.2 + basket)
        lo, _ = self.bo.monthly_band(3280.2, 'LVL1', 0.85, 'T1', basket)
        self.assertGreaterEqual(lo, math.ceil(line / 10) * 10)

    def test_inner_ring_unchanged_by_new_clamp(self):
        b = self.costs['篮子']['内湖环']
        self.assertEqual(self.bo.monthly_band(3280.2, 'LVL1', 1.0, 'T1', b)[0],
                         self.bo.monthly_band(3280.2, 'LVL1', 1.0, 'T1', 0.0)[0])

    def test_periphery_lifted_by_new_clamp(self):
        b = self.costs['篮子']['产业小镇']
        self.assertGreater(self.bo.monthly_band(1223.8, 'LVL1', 1.0, 'T1', b)[0],
                           self.bo.monthly_band(1223.8, 'LVL1', 1.0, 'T1', 0.0)[0])

    def test_band_never_inverted_after_clamp(self):
        for ring, basket in self.costs['篮子'].items():
            for level in ('LVL1', 'LVL2', 'LVL3', 'LVL4', 'LVL5'):
                lo, hi = self.bo.monthly_band(928.0, level, 0.8, 'T1', basket)
                self.assertLessEqual(lo, hi, f'{ring}/{level}')

    def test_missing_cost_canon_exits(self):
        with self.assertRaises(SystemExit):
            self.bo.load_baskets(ROOT / '数据' / '不存在的正典.json')

    def test_canon_records_both_candidate_lines(self):
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        card = canon['公司'][0]['岗位卡'][0]
        self.assertEqual(sorted(card['红线_钛币']), sorted(['住所四成线', '住所加篮子线', '是否被顶起']))
        self.assertEqual(canon['汇总']['公司数'], 1403)
        self.assertEqual(canon['汇总']['岗位卡数'], 5151)
        self.assertEqual(canon['汇总']['雇员总数'], 378140)


class CanonConsistency(unittest.TestCase):
    """叙事层与总表的规模数字必须来自正典，且正典自身条数不变。"""

    EXPECTED = {'域数': 6, '品类数': 120, '服务数': 12, '库存行数': 176}
    DOC_PHRASES = ['6 个商品域', '120 条品类', '12 项公共服务', '176 行']

    def setUp(self):
        self.canon = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))

    def test_canon_counts_are_as_ruled(self):
        actual = {'域数': len(self.canon['域表']), '品类数': len(self.canon['品类']),
                  '服务数': len(self.canon['服务']), '库存行数': len(self.canon['库存'])}
        self.assertEqual(actual, self.EXPECTED)
        self.assertEqual(self.canon['汇总']['单元数'], 44)
        self.assertEqual(self.canon['汇总']['住房类型数'], 4)

    def test_narrative_doc_states_the_same_counts(self):
        doc = (ROOT / '物价与生活设定.md').read_text(encoding='utf-8')
        for phrase in self.DOC_PHRASES:
            self.assertIn(phrase, doc, f'叙事层缺规模口径：{phrase}')

    def test_generated_table_row_counts_match_canon(self):
        table = (ROOT / '数据' / '物价与生活总表.md').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'^\| PRD-[A-Z]+-\d+ \|', table, re.M)), self.EXPECTED['品类数'])
        self.assertEqual(len(re.findall(r'^\| SVC-\d+ \|', table, re.M)), self.EXPECTED['服务数'])
        units = len(re.findall(r'^\| [DHS]\w+ \| (?:内湖环|外城环|产业小镇|特色村落) \|', table, re.M))
        self.assertEqual(units, self.canon['汇总']['单元数'])
        self.assertEqual(units * self.canon['汇总']['住房类型数'], self.EXPECTED['库存行数'])

    def test_rulings_are_83(self):
        rulings = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rulings), 83)
        self.assertEqual(rulings[-1]['编号'], 'C83')
        self.assertEqual([r['编号'] for r in rulings[-9:]],
                         ['C75', 'C76', 'C77', 'C78', 'C79', 'C80', 'C81', 'C82', 'C83'])


    def test_manual_chains_costs_before_occupations(self):
        manual = (ROOT / 'AI创作使用手册.md').read_text(encoding='utf-8')
        for token in ('build_costs.py', '物价生活源表.json', '物价与生活正典.json', '先跑物价再跑就业'):
            self.assertIn(token, manual)
        self.assertLess(manual.index('build_costs.py'), manual.index('build_occupations.py'))


class Idempotency(unittest.TestCase):
    ARTIFACTS = ['物价与生活正典.json', '物价与生活总表.md']

    def test_costs_products_are_byte_stable(self):
        import hashlib
        import subprocess
        before = {a: hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest() for a in self.ARTIFACTS}
        for _ in range(2):
            subprocess.run([sys.executable, str(ROOT / '工具' / 'build_costs.py')],
                           check=True, capture_output=True)
            for a in self.ARTIFACTS:
                after = hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest()
                self.assertEqual(after, before[a], f'{a} 双跑不幂等')


if __name__ == '__main__':
    unittest.main()
