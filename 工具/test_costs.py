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

    def test_rulings_are_108(self):
        rulings = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rulings), 108)
        self.assertEqual(rulings[-1]['编号'], 'C108')
        self.assertEqual([r['编号'] for r in rulings[-10:]],
                         ['C99', 'C100', 'C101', 'C102', 'C103', 'C104', 'C105', 'C106', 'C107', 'C108'])
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
        # C93 原尾句「本条零出图、未花额度」与「四张片区定档属未做」由 C94 执行后订正；
        # 措辞钉随之前移，否则裁定记录回退到旧口径时这里仍会空转判绿。
        self.assertIn('四张片区定档与放量前探针已由 C94 于 2026-11-03 执行完毕', by_id['C93']['影响'])
        # C94 的两条唯一出处：L007 塔冠按画风分档、E1 通道标识格式与交付判据不兼容。
        self.assertIn('写实档失效、E1 档已兑现', by_id['C94']['裁定'])
        self.assertIn('19492 字节的 C2PA 清单', by_id['C94']['影响'])
        self.assertIn('不回填 image_file', by_id['C94']['影响'])
        # C95 的画框可纳性算式与 23/5 分档是 A6 结论的唯一出处；少了算式，下一轮高度档再抬时无人知道 need/vFOV 怎么算。
        self.assertIn('vFOV = 2·arctan(18/焦距毫米)', by_id['C95']['裁定'])
        self.assertIn('23 条 need ≤ vFOV', by_id['C95']['裁定'])
        self.assertIn('唯一点名屋顶物件的是 L083', by_id['C95']['裁定'])
        # 摘要覆盖范围的订正是放量口径的前提：这句一旦被回退成「本就不含文件头」，投喂与摘要的关系又会各说各话。
        self.assertIn('投喂时剥文件头属操作口径，与摘要范围不是一回事', by_id['C95']['裁定'])
        self.assertIn('改机位 0 条，取景段措辞改 1 条（L083）', by_id['C95']['影响'])
        self.assertIn('prompt_sha256 变更 1/312', by_id['C95']['影响'])
        # C95 的口径落成一条新判据，配同轮违例注入负测；这句在，闸门与裁定的对应关系才有唯一出处。
        self.assertIn('本轮新增判据进 工具/test_prompts.py', by_id['C95']['影响'])
        self.assertIn('注入 L083 订正前的旧写法判红', by_id['C95']['影响'])
        # C96 的分诊读数与批次编排是 B4 不判红、B6 单独成批的唯一出处。
        self.assertIn('B4 的触发条件「出图普遍空街」不成立', by_id['C96']['裁定'])
        self.assertIn('夜光批 4 条、清晨批 4 条、雨后批 7 条、晴日批 1 条', by_id['C96']['裁定'])
        self.assertIn('验收不互相覆盖', by_id['C96']['裁定'])
        self.assertIn('B4 缺席类命中 3/118', by_id['C96']['影响'])
        self.assertIn('两项均为零额度、零出图', by_id['C96']['影响'])
        # C97 双容器与 C98 纵深次序交还的措辞钉：两句分别是对应闸门与对应 tail 的唯一出处。
        self.assertIn('接受 C2PA 容器', by_id['C97']['裁定'])
        self.assertIn('补写是伪造，认容器是识别', by_id['C97']['裁定'])
        self.assertIn('工具/test_image_assets.py 同轮配违例负测四条', by_id['C97']['影响'])
        self.assertIn('"behind old layer"', by_id['C98']['裁定'])
        self.assertIn('其余五类 tail 的接触动词', by_id['C98']['裁定'])
        self.assertIn('prompt_sha256 变更 20/312', by_id['C98']['影响'])
        self.assertIn('模块实跑 30/30', by_id['C98']['影响'])
        # C99 的日面可纳性算式与「侧别≠可见」两句是本轮 tail 改动和判据的唯一出处；
        # 少了算式，下一轮焦距或方位档再动时无人知道 in/out 分支怎么判，也容易退回静态句。
        self.assertIn('atan(18/焦距)', by_id['C99']['裁定'])
        self.assertIn('「在哪个侧别」与「日面可不可见」是两件事', by_id['C99']['裁定'])
        self.assertIn('keep the sun disc, the setting-sun glow and any lens flare out of the picture entirely',
                      by_id['C99']['裁定'])
        self.assertIn('可入画 59／须画外 237／变体静态句 16', by_id['C99']['影响'])
        self.assertIn('模块实跑 32/32', by_id['C99']['影响'])
        # C100 的「锚点提到首句」与 C101 的「远景按机位算可纳性」是本轮两处 tail 改动的唯一出处；
        # 前者若不钉住，下一轮容易又退回「往尾串叠画风词」，后者若不钉住 38/47 根塔那个失败方案会被重捡。
        self.assertIn('模型按题材定档、不按尾串改档', by_id['C100']['裁定'])
        self.assertIn('只写 rather than a snapshot', by_id['C100']['裁定'])
        self.assertIn('5 张出成照片质感', by_id['C100']['裁定'])
        self.assertIn('ANCHOR_MARKS 五个短语', by_id['C100']['影响'])
        self.assertIn('实测不可用', by_id['C101']['裁定'])
        self.assertIn('静态分支不写高度是为了不把名录的 L007／L066 高度串进 244 条', by_id['C101']['原因'])
        self.assertIn('computed 68／static 244', by_id['C101']['影响'])
        self.assertIn('偏右111.5°', by_id['C101']['影响'])
        self.assertIn('大面积误判红 188 项', by_id['C101']['影响'])
        # C102 的「人工记录＋摘要绑定」与 C103 的「套件不进链、不写结论」是本轮两处收口的唯一出处：
        # 这两句一旦从裁定里被删，rendering_verified 的失效条件与复看套件的边界就重新变成口头承诺。
        self.assertIn('重导即失效，须重看', by_id['C102']['裁定'])
        self.assertIn('`rendering_verified` 不进 `passed`', by_id['C102']['裁定'])
        self.assertIn('24+148+120=292 与全书 312 条对不上', by_id['C102']['裁定'])
        self.assertIn('常量 false，没有任何人工入口', by_id['C102']['原因'])
        self.assertIn('18/18 与书签实际页逐一相等', by_id['C102']['影响'])
        self.assertIn('先因摘要不匹配自动回落 false', by_id['C102']['影响'])
        self.assertIn('套件不进闸门链、不写结论', by_id['C103']['裁定'])
        self.assertIn('`atan(18/焦距)` 独立复算一遍', by_id['C103']['裁定'])
        self.assertIn('唯一可编辑源仍是 `数据/开图验收备注.json`', by_id['C103']['裁定'])
        self.assertIn('suite items 264 cells 1060 pages 33 notes 8', by_id['C103']['影响'])
        self.assertIn('C2PA 在位 4 格', by_id['C103']['影响'])
        self.assertIn('`git ls-files -i -c` 为 0', by_id['C103']['影响'])
        # C104 的「唯一出处归位」与「不可生产档否决」是本轮画幅口径的两条硬话，一旦从裁定里被删，
        # 手册与卡面规范就重新变成两份互不指向的数字来源，统一画幅的提议也会每轮重问一次。
        self.assertIn('画幅口径归位并锁死三档，否决统一改幅', by_id['C104']['裁定'])
        self.assertIn('唯一出处移到《卡面标准样式规范》第七节', by_id['C104']['裁定'])
        self.assertIn('出图通道可选尺寸不含 16:9 与 3:5', by_id['C104']['裁定'])
        self.assertIn('124 张尺寸全部 1020×1360', by_id['C104']['裁定'])
        self.assertIn('数字有出处，但出处不在真源层', by_id['C104']['原因'])
        self.assertIn('没有脚本会再生成这两个数字', by_id['C104']['影响'])
        self.assertIn('绑定 docx `6b82dfcb…`', by_id['C104']['影响'])
        self.assertIn('本轮零出图、未花额度', by_id['C104']['影响'])
        # C105 的硬话是「只加媒介强度、不动画幅」与「soft airbrushed gradient sky 被换掉」这两条边界：
        # 前者挡住下一轮拿换画幅当改画风（画幅归 C104），后者挡住 tail 退回与诊断B 冲突的平滑渐变天空。
        self.assertIn('E1 档内加媒介强度，只改措辞不改画幅', by_id['C105']['裁定'])
        self.assertIn('soft airbrushed gradient sky 换成 sky laid in with visible cloud strokes', by_id['C105']['裁定'])
        self.assertIn('SIZE_BY_TYPE 三档画幅与 150 米级竖幅覆盖', by_id['C105']['裁定'])
        self.assertIn('人物特写英文 tag 一并换掉 smooth airbrushed skin', by_id['C105']['裁定'])
        self.assertIn('312 条 prompt_sha256 全部更换（312/312）', by_id['C105']['裁定'])
        self.assertIn('由 37 条增至 40 条', by_id['C105']['裁定'])
        self.assertIn('判废主因是媒介措辞的强度，不是画幅', by_id['C105']['原因'])
        self.assertIn('B 只换首句媒介串、画幅不动，结果全幅落地', by_id['C105']['原因'])
        self.assertIn('而不是再加一遍「不是照片」这类否定式', by_id['C105']['原因'])
        self.assertIn('新判据只报 D11 且缺失项恰为三个媒介词', by_id['C105']['影响'])
        self.assertIn('312 条全报且首句判据不被牵连', by_id['C105']['影响'])
        self.assertIn('每个子批先按 B1 探针放行', by_id['C105']['影响'])
        # C106 的硬话是「形体来源与远景可纳性是两条判据」与「城市名只许以否定式出现」；
        # 一旦这两句从裁定里被删，下一轮又会把「远景画了三栋楼」当成已经管住了轮廓来源。
        self.assertIn('远景塔形不得取自现实城市天际线，形体来源单立一条判据', by_id['C106']['裁定'])
        self.assertIn('接在 `background_phrase` 的 `FAR_VIEW_RULE` 之后，312 条全部带上', by_id['C106']['裁定'])
        self.assertIn('城市名只许以否定式出现', by_id['C106']['裁定'])
        self.assertIn('复看套件 `CHECKS` 由九条增至十条', by_id['C106']['裁定'])
        self.assertIn('`test_prompts` 41→44、`test_review_suite` 6/6 OK', by_id['C106']['裁定'])
        self.assertIn('C101 的判据只问「点名了没有」，问不出「像不像别的城市」', by_id['C106']['原因'])
        self.assertIn('必须同时钉进 English tail 的正向与负向', by_id['C106']['原因'])
        self.assertIn('打表栏由九列增至十列', by_id['C106']['影响'])
        self.assertIn('证明正向与负向是两处独立钉', by_id['C106']['影响'])
        self.assertIn('L083 v05 依本条判废', by_id['C106']['影响'])
        # C107 的硬话是「只挂 16 条、296 条逐字不动」的范围隔离与「串外试投不回填」的口径；
        # 这两句一旦丢，下一轮就会把复述句挂到全部 312 条、或把换串前/换串外的图一并回填洗白。
        self.assertIn('只挂 16 条 labeled variant、296 条默认光条逐字不动', by_id['C107']['裁定'])
        self.assertIn('VARIANT_LOCK_CLAUSE', by_id['C107']['裁定'])
        self.assertIn('不改分卷原稿、不改使用手册', by_id['C107']['裁定'])
        self.assertIn('埋在长串尾部的全局句被题材压倒', by_id['C107']['原因'])
        self.assertIn('S23 两赌用尽、第三赌不投', by_id['C107']['原因'])
        self.assertIn('R053 v02／R086 v02 判达标但不回填', by_id['C107']['影响'])
        self.assertIn('回填即把未经该串复验的图洗成该串产物', by_id['C107']['影响'])
        self.assertIn('计数钉 106→107', by_id['C107']['影响'])
        # C108 的硬话是「位置只限地面与四角，不写墙面与店招」和「换串不洗白任何一张图」：
        # 前者一旦丢，下一轮就会把负向扩到墙面、连 D3／C93 要求的招牌实体一起否掉；
        # 后者一旦丢，就会有人把新串摘要补到旧串图上，把未经该串复验的图洗成该串产物。
        self.assertIn('位置只限地面、路缘石与画面四角', by_id['C108']['裁定'])
        self.assertIn('GROUND_MARKS_NEG', by_id['C108']['裁定'])
        self.assertIn('不进【全局硬设定】的正向中文段', by_id['C108']['裁定'])
        self.assertIn('不改分卷原稿、不改使用手册', by_id['C108']['裁定'])
        self.assertIn('段内已有该句仍失手', by_id['C108']['原因'])
        self.assertIn('单变量证据来自 R015', by_id['C108']['原因'])
        self.assertIn('换串不洗白任何一张图', by_id['C108']['影响'])
        self.assertIn('`test_prompts` 47→50', by_id['C108']['影响'])
        self.assertIn('计数钉 107→108', by_id['C108']['影响'])


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
