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
        registry = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
        total = sum(r['推导户数'] for r in self.rows if r['住房类型ID'] == 'HOU-01')
        self.assertLessEqual(abs(total - registry['population']['regional_total'] / 2.47), 44)
        self.assertEqual(total, self.canon['汇总']['全城户数'])


class Clamp(unittest.TestCase):
    def setUp(self):
        import build_occupations as bo
        self.bo = bo
        self.costs = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))

    def test_band_lower_bound_never_below_effective_line(self):
        basket = self.costs['篮子']['内湖环']
        anchor = self.costs['保障']['内湖环']['押金_钛币']
        line = max(anchor / 0.4, anchor + basket)
        lo, _ = self.bo.monthly_band(anchor, 'LVL1', 0.85, 'T1', basket)
        self.assertGreaterEqual(lo, math.ceil(line / 10) * 10)

    def test_inner_ring_unchanged_by_new_clamp(self):
        b = self.costs['篮子']['内湖环']
        anchor = self.costs['保障']['内湖环']['押金_钛币']
        self.assertEqual(self.bo.monthly_band(anchor, 'LVL1', 1.0, 'T1', b)[0],
                         self.bo.monthly_band(anchor, 'LVL1', 1.0, 'T1', 0.0)[0])

    def test_periphery_lifted_by_new_clamp(self):
        b = self.costs['篮子']['产业小镇']
        anchor = self.costs['保障']['产业小镇']['押金_钛币']
        self.assertGreater(self.bo.monthly_band(anchor, 'LVL1', 1.0, 'T1', b)[0],
                           self.bo.monthly_band(anchor, 'LVL1', 1.0, 'T1', 0.0)[0])

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
        # 三条量级金标准：改人口或岗位量级要连带重定，不跟随自动派生（自动派生的守恒断言在 test_occupations）。
        self.assertEqual(canon['汇总']['公司数'], 2889)
        self.assertEqual(canon['汇总']['岗位卡数'], 10541)
        self.assertEqual(canon['汇总']['雇员总数'], 798140)


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

    def test_rulings_are_93(self):
        rulings = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rulings), 93)
        self.assertEqual(rulings[-1]['编号'], 'C93')
        self.assertEqual([r['编号'] for r in rulings[-10:]],
                         ['C84', 'C85', 'C86', 'C87', 'C88', 'C89', 'C90', 'C91', 'C92', 'C93'])
        by_id = {r['编号']: r for r in rulings}
        # C89 的「高度第一交给 L066、形态第一留在 L007」是本卷定价外溢的唯一出处，钉死措辞防止被改写后说明与价表脱钩。
        self.assertIn('458米/106层', by_id['C89']['裁定'])
        self.assertIn('唯一形态', by_id['C89']['裁定'])
        self.assertIn('D03 商业 23950→24000', by_id['C89']['影响'])
        # C90 的分档缺口收口与 180 米住宅上限是本卷 1.04/1.10 档外溢的唯一出处。
        self.assertIn('60—99 档由 1 条增至 40 条', by_id['C90']['裁定'])
        self.assertIn('R013 钛心云邸 96→180', by_id['C90']['裁定'])
        self.assertIn('定价外溢实测 17 条读数', by_id['C90']['影响'])
        # C91 只改画幅判定；这句「不改高度/坐标/占地/总建面」是价表与 2-D 之后名录不脱钩的唯一出处。
        self.assertIn('只改画幅判定', by_id['C91']['影响'])
        # C92 只改提示词取段与人群档位；这句是与价表、名录口径不脱钩的唯一出处。
        self.assertIn('只改提示词取段与人群档位', by_id['C92']['影响'])
        # 量级锚与「判据已定档、产物未落地」两处措辞钉死在裁定记录里，防止后人误当 D4／D2 已生效。
        self.assertIn('280000→700000', by_id['C86']['裁定'])
        self.assertIn('1280000→3200000', by_id['C86']['裁定'])
        self.assertIn('【已被C86取代】', by_id['C04']['裁定'])
        self.assertIn('不是已交付事实', by_id['C87']['影响'])
        # C93 把 C88 的「定档未执行」与 C85 的「通道分工」两句一起收掉：措辞钉随之前移，
        # 否则裁定记录一旦回退到旧口径，这里的说明与价表、tail 生成器就各说各话。
        self.assertIn('由 C93 于 2026-11-03 执行完毕', by_id['C88']['影响'])
        self.assertIn('【通道分工已被C88定档、并由C93于2026-11-03执行作废', by_id['C85']['裁定'])
        self.assertIn('只许以否定式出现在 NEGATIVE_TAG', by_id['C93']['裁定'])
        self.assertIn('312/312', by_id['C93']['影响'])
        self.assertIn('本条零出图、未花额度', by_id['C93']['影响'])


    def test_manual_chains_costs_before_occupations(self):
        manual = (ROOT / 'AI创作使用手册.md').read_text(encoding='utf-8')
        for token in ('build_costs.py', '物价生活源表.json', '物价与生活正典.json', '先跑物价再跑就业'):
            self.assertIn(token, manual)
        self.assertLess(manual.index('build_costs.py'), manual.index('build_occupations.py'))


class PricingModelNote(unittest.TestCase):
    """数据/房价模型说明.md 是人工维护、抄了生成 JSON 读数的第二份；逐字段对拍，防止说明停在旧量级。"""

    ROWS = [
        ('住宅全部', 'residential', None),
        ('住宅·内湖环', 'residential', '内湖环'),
        ('住宅·外城环', 'residential', '外城环'),
        ('住宅·产业小镇', 'residential', '产业小镇'),
        ('住宅·特色村落', 'residential', '特色村落'),
        ('办公（D/F/L）', 'office', None),
        ('商业（D/F/L，不含R/S底商）', 'retail', None),
    ]

    def setUp(self):
        self.records = json.loads((ROOT / '数据' / '参考房价租金.json').read_text(encoding='utf-8'))['records']
        self.by_id = {r['id']: r for r in self.records}
        self.note = (ROOT / '数据' / '房价模型说明.md').read_text(encoding='utf-8')

    def sample(self, field, ring):
        values = sorted(r[field]['sale_tt_per_m2'] for r in self.records
                        if field in r and (ring is None or r['ring'] == ring))
        return len(values), values[0], values[len(values) // 2], values[-1]

    @staticmethod
    def label(r):
        return r['id'] + r['name'].removesuffix('片区')

    def extreme(self, rows, field):
        return (min(rows, key=lambda r: r[field]['sale_tt_per_m2']),
                max(rows, key=lambda r: r[field]['sale_tt_per_m2']))

    def test_gradient_table_rows_match_generated_json(self):
        table = {name: (int(n), int(lo), int(med), int(hi))
                 for name, n, lo, med, hi in re.findall(r'^\| (\S.*?) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$', self.note, re.M)}
        self.assertEqual(len(table), len(self.ROWS), '第五节表格行数或行名与闸门约定不符')
        for name, field, ring in self.ROWS:
            self.assertEqual(table[name], self.sample(field, ring), name)

    def test_named_readings_in_prose_match_generated_json(self):
        d01, d01o, d01r = (self.by_id['D01'][k] for k in ('residential', 'office', 'retail'))
        l007 = self.by_id['L007']['office']
        districts = [r for r in self.records if r['id'].startswith('D')]
        residences = [r for r in self.records if r['id'].startswith('R')]
        all_homes = [r for r in self.records if 'residential' in r]
        dh_lo, dh_hi = self.extreme(districts, 'residential')
        do_lo, do_hi = self.extreme(districts, 'office')
        dr_lo, dr_hi = self.extreme(districts, 'retail')
        r_lo = min(residences, key=lambda r: r['residential']['sale_tt_per_m2'])
        s_lo = min(all_homes, key=lambda r: r['residential']['sale_tt_per_m2'])
        for token in [
            f"总代理权重{d01['sample_weight_gfa_m2']}平方米；住宅样本价{d01['sale_tt_per_m2']}，月租{d01['rent_tt_per_m2_month']}钛币/平方米",
            f"办公{d01o['sale_tt_per_m2']}、商业{d01r['sale_tt_per_m2']}。",
            f"L007 办公{l007['sale_tt_per_m2']}，日租{l007['rent_tt_per_m2_day']}钛币/平方米",
            f"D 住宅样本价最低{dh_lo['residential']['sale_tt_per_m2']}（{self.label(dh_lo)}），最高{dh_hi['residential']['sale_tt_per_m2']}（{self.label(dh_hi)}）",
            f"D 办公最低{do_lo['office']['sale_tt_per_m2']}（{self.label(do_lo)}）、最高{do_hi['office']['sale_tt_per_m2']}（{self.label(do_hi)}）",
            f"D 商业最低{dr_lo['retail']['sale_tt_per_m2']}（{self.label(dr_lo)}）、最高{dr_hi['retail']['sale_tt_per_m2']}（{self.label(dr_hi)}）",
            f"住宅全域低点是{s_lo['id']}{s_lo['name']}{s_lo['residential']['sale_tt_per_m2']}",
            f"城区 R 低点是{r_lo['id']}{r_lo['name']}{r_lo['residential']['sale_tt_per_m2']}",
        ]:
            self.assertIn(token, self.note)

        pull = sorted(((r['basis']['就业拉力系数'], r) for r in districts), key=lambda x: x[0])
        self.assertIn(f"就业系数为{pull[0][0]:.2f}（{self.label(pull[0][1])}）", self.note)
        self.assertIn(f"{pull[-1][0]:.2f}（{self.label(pull[-1][1])}）", self.note)


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
