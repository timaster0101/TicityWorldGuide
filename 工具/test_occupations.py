# -*- coding: utf-8 -*-
"""产业与就业层回归测试；生成类断言只在临时目录重跑真实脚本，不手改派生文件。"""
import json, math, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anchors

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / '数据' / '城市空间名录.json'

EXPECTED_S_JOBS = {
    'S01': 7200, 'S02': 10200, 'S03': 7800, 'S04': 4800, 'S05': 5600, 'S06': 4700,
    'S07': 5300, 'S08': 6300, 'S09': 3600, 'S10': 4100, 'S11': 5100, 'S12': 8000,
    'S13': 5700, 'S14': 6600, 'S15': 4500, 'S16': 5100, 'S17': 520, 'S18': 640,
    'S19': 360, 'S20': 280, 'S21': 480, 'S22': 560, 'S23': 240, 'S24': 460,
}


class SettlementJobs(unittest.TestCase):
    def setUp(self):
        self.entries = json.loads(REGISTRY.read_text(encoding='utf-8'))['entries']

    def test_all_24_settlements_carry_jobs(self):
        got = {e['id']: e.get('daily_workers') for e in self.entries if e['id'].startswith('S')}
        self.assertEqual(got, EXPECTED_S_JOBS)

    def test_city_job_total_unchanged_by_settlement_jobs(self):
        f_total = sum(e['daily_workers'] for e in self.entries if e['id'].startswith('F'))
        # 方案 A 量级重推（设计/2026-11-02-城市量级与天际线重构-design.md）后功能区岗位锚为 700000；聚落 98140 另记，不并入。
        self.assertEqual(f_total, 700000)


SOURCE = ROOT / '数据' / '产业就业源表.json'
SUBCLASS_COUNTS = {'A01':6,'A02':8,'A03':9,'A04':6,'A05':7,'A06':10,'A07':9,'A08':8,'A09':9,
                   'A10':10,'A11':10,'A12':6,'A13':9,'A14':8,'A15':7,'A16':8,'A17':8,
                   'A18':10,'A19':8,'A20':7}
FOUR_LAYER_CLASSES = {'A01','A07','A09','A10','A11','A12','A18','A19'}


class SourceTable(unittest.TestCase):
    def setUp(self):
        self.src = json.loads(SOURCE.read_text(encoding='utf-8'))

    def test_class_and_subclass_counts_match_spec(self):
        self.assertEqual(len(self.src['大类']), 20)
        self.assertEqual(len(self.src['小类']), 163)
        counted = {}
        for s in self.src['小类']:
            counted[s['父大类']] = counted.get(s['父大类'], 0) + 1
        self.assertEqual(counted, SUBCLASS_COUNTS)

    def test_subclass_ids_are_sequential_within_class(self):
        seen = set()
        for s in self.src['小类']:
            cid, _, seq = s['id'].partition('-')
            self.assertEqual(s['父大类'], cid)
            self.assertLess(int(seq[1:]), SUBCLASS_COUNTS[cid] + 1)
            self.assertNotIn(s['id'], seen)
            seen.add(s['id'])

    def test_layer_scheme_per_class(self):
        for c in self.src['大类']:
            self.assertEqual(c['层制'], 4 if c['id'] in FOUR_LAYER_CLASSES else 5)

    def test_every_job_anchor_has_an_employer_class(self):
        reg = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']
        ids = {e['id'] for e in reg}
        job_zones = {e['id'] for e in reg if 'daily_workers' in e and e['id'][0] in 'FS'}
        listed = {z for c in self.src['大类'] for z in c['可落锚点']}
        self.assertFalse(listed - ids, sorted(listed - ids)[:8])
        self.assertFalse(job_zones - listed, f'无雇主的大类覆盖缺口：{sorted(job_zones - listed)[:8]}')
        self.assertTrue(set(self.src['禁则']['低空作业小类']) <= {s['id'] for s in self.src['小类']})

    def test_wage_parameters_match_c52(self):
        p = self.src['参数']
        self.assertEqual(p['住所占比判据'], 0.40)
        self.assertEqual(p['月标准工时'], 174)
        self.assertEqual(p['层系数'], {'LVL1':1.00,'LVL2':1.45,'LVL3':2.10,'LVL4':3.05,'LVL5':4.40})
        self.assertEqual(p['档位加成'], {'T1':1.00,'T2':1.03,'T3':1.06,'T4':1.09,'T5':1.12})
        self.assertEqual(p['带宽'], [0.90, 1.15])
        shapes = [c['形状系数'] for c in self.src['大类']]
        self.assertTrue(all(0.88 <= v <= 1.18 for v in shapes))

    def test_start_year_within_one_round(self):
        for s in self.src['小类']:
            self.assertGreaterEqual(s['起始城市年'], 2013)
            self.assertLessEqual(s['起始城市年'], 2072)

    def test_t5_exactly_one_per_class_and_tier_bands(self):
        tiers = {t['档']: t for t in self.src['公司档']}
        self.assertEqual(tiers['T1']['雇员数'], [1, 5])
        self.assertEqual(tiers['T2']['雇员数'], [6, 49])
        self.assertEqual(tiers['T3']['雇员数'], [50, 249])
        self.assertEqual(tiers['T4']['雇员数'], [250, 1200])
        self.assertEqual(tiers['T5']['雇员数'], [1201, 3000])
        self.assertEqual(tiers['T5']['每区占比上限'], 0.45)
        self.assertEqual(len([c for c in self.src['大类'] if c['顶端雇主']]), 20)

    def test_blacklist_fields_absent(self):
        """禁词表本身合法地住在 禁则 里，门禁扫的是生成出来的正典；这里只保证参数与类目侧不出现禁词。"""
        blob = json.dumps({k: v for k, v in self.src.items() if k != '禁则'}, ensure_ascii=False)
        for word in self.src['禁则']['字段黑名单']:
            self.assertNotIn(word, blob)


BUILD = ROOT / '工具' / 'build_occupations.py'


def load_namespace():
    """exec 出来的模块没有 __file__，而 build_occupations 靠它定位 数据/；不补就跑不起。"""
    ns = {'__name__': 'build_occupations', '__file__': str(BUILD)}
    exec(compile(BUILD.read_text(encoding='utf-8'), str(BUILD), 'exec'), ns)
    return ns


class WageBand(unittest.TestCase):
    def setUp(self):
        self.ns = load_namespace()

    def test_settlement_anchors_match_measured_derivation(self):
        a = self.ns['dwelling_anchors']()
        self.assertAlmostEqual(a['S03'], 1299, delta=2)
        self.assertAlmostEqual(a['S20'], 928, delta=2)
        self.assertNotIn('D10', a)

    def test_office_anchor_inherits_parent_district(self):
        d, a = anchors.district_anchors(), self.ns['dwelling_anchors']()
        self.assertEqual(a['F019'], d['D10'])
        self.assertEqual(a['F031'], d['D16'])

    def test_city_core_anchors_span_measured_band(self):
        d = anchors.district_anchors()
        values = [v for k, v in d.items() if k.startswith('D')]
        self.assertAlmostEqual(min(values), 1723.0, places=1)
        self.assertAlmostEqual(max(values), 3585.5, places=1)

    def test_lvl1_floor_equals_anchor_over_ratio(self):
        """§5 第4条红线：全域 LVL1 全职月薪 ≥ 住所锚 ÷ 0.40，带下限就取这条线。"""
        band = self.ns['monthly_band'](2500.0, 'LVL1', 1.00, 'T1', 0.0)
        self.assertEqual(band[0], 2500.0 / 0.40)

    def test_lvl1_floor_survives_low_shape_and_low_tier(self):
        """形状系数 0.88（A18 农业）× T1 加成 1.00 × 带宽下限 0.90 会把公式值压到红线下，必须钳回线上。"""
        red = 2500.0 / 0.40
        for shape in (0.88, 1.00, 1.18):
            for tier in ('T1', 'T2', 'T3', 'T4', 'T5'):
                lo, hi = self.ns['monthly_band'](2500.0, 'LVL1', shape, tier, 0.0)
                self.assertGreaterEqual(lo, red, f'shape={shape} tier={tier}')
                self.assertGreater(hi, lo, f'带宽被钳平 shape={shape} tier={tier}')

    def test_clamp_only_binds_at_lvl1(self):
        """篮子取 0 即退化为第1期旧线：LVL2 起层系数 ≥1.45，公式值本就在线上，旧线钳不动 LVL2+ 的带下限。"""
        params = json.loads(SOURCE.read_text(encoding='utf-8'))['参数']
        for level in ('LVL2', 'LVL3', 'LVL4', 'LVL5'):
            base = 2500.0 / params['住所占比判据'] * params['层系数'][level] * 0.88 * params['档位加成']['T1']
            expected = int(math.floor(base * params['带宽'][0] / params['月薪取整']) * params['月薪取整'])
            lo, _ = self.ns['monthly_band'](2500.0, level, 0.88, 'T1', 0.0)
            self.assertEqual(lo, expected, level)

    def test_measured_sample_magnitudes(self):
        a = anchors.district_anchors()
        self.assertAlmostEqual(a['D10'] / 0.40, 6403.75, delta=6)
        self.assertAlmostEqual(a['D03'] / 0.40, 8963.75, delta=6)
        self.assertAlmostEqual(a['D17'] / 0.40, 4813.75, delta=6)

    def test_hourly_uses_174_hours(self):
        self.assertAlmostEqual(self.ns['hourly'](8540.0, 8540.0)[0], 8540.0 / 174, places=1)


class CompanySolver(unittest.TestCase):
    def setUp(self):
        self.ns = load_namespace()

    def test_split_sums_exactly_to_zone_workers(self):
        split, cap = self.ns['split_zone'], self.ns['per_company_cap']
        for w in (4000, 5550, 6600, 8000, 9200, 10000, 10200, 520, 640, 280, 97):
            rows = split(w, cap(w), 4)
            self.assertEqual(sum(e for _, e in rows), w, w)

    def test_split_respects_bands_and_cap(self):
        split, cap = self.ns['split_zone'], self.ns['per_company_cap']
        tiers = {t['档']: t['雇员数'] for t in self.ns['SOURCE']['公司档']}
        for w in (4000, 10000, 3600, 640, 97, 90, 20):
            rows = split(w, cap(w), 4)
            for tier, e in rows:
                if tier == 'T1':
                    continue
                lo, hi = tiers[tier]
                self.assertTrue(lo <= e <= hi, (w, tier, e))
                self.assertLessEqual(e, cap(w), (w, tier, e))
            self.assertLessEqual(sum(1 for t, _ in rows if t == 'T1'), 1, w)

    def test_split_zone_follows_tier_headcount_shares(self):
        split, cap = self.ns['split_zone'], self.ns['per_company_cap']
        share = self.ns['PARAMS']['档位人数配比']
        rows = split(7000, cap(7000), 4)
        for tier in ('T4', 'T3', 'T2'):
            self.assertEqual(sum(e for t, e in rows if t == tier), math.floor(7000 * share[tier] + .5), tier)
        self.assertEqual(sum(e for t, e in rows if t == 'T1'), 7000 - sum(math.floor(7000 * s + .5)
                                                                        for t, s in share.items() if t != 'T1'))

    def test_infeasible_tier_cascades_downward(self):
        """S17 白鹭渔村 520 岗：单公司上限 234 人装不下 T4 的 250 人门槛，预算必须整笔结转给 T3。"""
        split, cap = self.ns['split_zone'], self.ns['per_company_cap']
        self.assertLess(cap(520), 250)
        rows = split(520, cap(520), 4)
        self.assertEqual([t for t, _ in rows if t == 'T4'], [])
        t3 = sum(e for t, e in rows if t == 'T3')
        self.assertEqual(t3, math.floor(520 * self.ns['PARAMS']['档位人数配比']['T4'] + .5)
                            + math.floor(520 * self.ns['PARAMS']['档位人数配比']['T3'] + .5))
        self.assertEqual(sum(e for _, e in rows), 520)

    def test_t1_is_one_statistical_record_per_zone(self):
        companies, zw = self.ns['expand_companies'](), self.ns['zone_workers']()
        t1 = [c for c in companies if c['档位'] == 'T1']
        self.assertEqual(len(t1), len(zw))
        self.assertEqual(sorted(c['锚点'] for c in t1), sorted(zw))
        self.assertTrue(all(c['逐家具名'] is False for c in t1))
        self.assertTrue(all(c['逐家具名'] is True for c in companies if c['档位'] != 'T1'))

    def test_named_company_count_lands_in_the_forecast_band(self):
        """spec §4 预测 1200—1800 家 T2—T5 具名公司（378140 岗口径）；按 C86 量级下的 798140 岗等比放大 2.11 倍为 2500—3800。T1 统计条不计入。"""
        named = [c for c in self.ns['expand_companies']() if c['逐家具名'] is True]
        self.assertLessEqual(2500, len(named), len(named))
        self.assertLessEqual(len(named), 3800, len(named))

    def test_named_companies_stay_under_the_zone_quota(self):
        """门禁 3 的两种上限：任何具名公司 ≤ 所在区配额 45%，T1—T4 另受 1200 人天花板（T5 有自己 1201—3000 的档区间）。"""
        companies, zw = self.ns['expand_companies'](), self.ns['zone_workers']()
        ratio, ceiling = self.ns['PARAMS']['单公司占区配额上限'], self.ns['PARAMS']['单公司雇员上限']
        for c in companies:
            if not c['逐家具名']:
                continue
            self.assertLessEqual(c['雇员数'], zw[c['锚点']] * ratio, (c['id'], c['雇员数']))
            if c['档位'] != 'T5':
                self.assertLessEqual(c['雇员数'], ceiling, c['id'])

    def test_t4_never_lands_in_a_specialty_village(self):
        """spec §4：T4 可落地 F 与「须有专属功能区」的 S。特色村落没有专属功能区，250 人以上只能结转 T3。"""
        companies = self.ns['expand_companies']()
        villages = {z for z, e in self.ns['BY_ID'].items() if e.get('type') == '特色村落'}
        self.assertTrue(villages)
        for zid in villages:
            named = [c['档位'] for c in companies
                     if c['锚点'] == zid and c['逐家具名'] and c['雇员数'] >= 250]
            self.assertEqual(named, [], zid)

    def test_t4_count_per_zone_at_most_four(self):
        split, cap = self.ns['split_zone'], self.ns['per_company_cap']
        rows = split(10000, cap(10000), 4)
        self.assertLessEqual(sum(1 for t, _ in rows if t == 'T4'), 4)

    def test_t5_is_exactly_one_per_class_on_valid_host(self):
        hosts, zw = self.ns['t5_hosts'](), self.ns['zone_workers']()
        ratio, t5_lo = self.ns['PARAMS']['单公司占区配额上限'], self.ns['T5_BAND'][0]
        self.assertEqual(len(hosts), len(self.ns['SOURCE']['大类']))
        self.assertEqual(sorted(hosts), sorted(c['id'] for c in self.ns['SOURCE']['大类']))
        for cid, anchor in hosts.items():
            self.assertGreaterEqual(zw[anchor] * ratio, t5_lo, (cid, anchor))

    def test_level_slots_are_positive_and_sum_to_headcount(self):
        slots = self.ns['level_slots']
        tiers = {t['档']: t['可设岗位层'] for t in self.ns['SOURCE']['公司档']}
        for emp in (1, 3, 6, 20, 97, 250, 1200, 2000):
            for tier in tiers:
                for scheme in (4, 5):
                    rows = slots(emp, scheme, tiers[tier])
                    self.assertEqual(sum(n for _, n in rows), emp, (emp, tier, scheme))
                    self.assertTrue(all(n >= 1 for _, n in rows), (emp, tier, scheme, rows))
                    self.assertEqual(rows[0][0], 'LVL1', (emp, tier, scheme, rows))
                    self.assertTrue(all(l in tiers[tier] for l, _ in rows))

    def test_a01_companies_are_not_recruitable(self):
        rows = [c for c in self.ns['expand_companies']() if c['大类'] == 'A01']
        self.assertTrue(rows)
        self.assertTrue(all(c['可招聘'] is False for c in rows))

    def test_no_fly_anchor_never_takes_a_low_altitude_subclass(self):
        companies = self.ns['expand_companies']()
        banned = set(self.ns['SOURCE']['禁则']['低空作业小类'])
        for zid in self.ns['SOURCE']['禁则']['无人机禁区']:
            ids = {c['行业小类'] for c in companies if c['锚点'] == zid}
            self.assertTrue(ids, f'{zid} 没有公司，轮转剔除无从验证')
            self.assertFalse(ids & banned, (zid, sorted(ids & banned)))


    def test_a01_registers_only_three_levels(self):
        """spec §3：A01 是唯一只登记 LVL1—LVL3 的大类，LVL4／LVL5 不设——T4／T5 也不能给它开出高层卡。"""
        canon = canon_snapshot()
        high = [card['id'] for c in canon['公司'] if c['大类'] == 'A01' for card in c['岗位卡']
                if card['岗位层'] in ('LVL4', 'LVL5')]
        self.assertEqual(high, [])

    def test_level_ceiling_trims_the_tier_allowance(self):
        ns = load_namespace()
        row = ns['make_company']('F002', 'T5', 2160, 'A01', 1, 2000.0, {'A01': 0})
        self.assertNotIn('LVL4', [c['岗位层'] for c in row['岗位卡']])
        self.assertNotIn('LVL5', [c['岗位层'] for c in row['岗位卡']])


class CanonOutput(unittest.TestCase):
    def build_twice_into_temp(self):
        with tempfile.TemporaryDirectory() as td:
            out, blobs = Path(td), []
            for _ in range(2):
                subprocess.run([sys.executable, str(BUILD), '--out-dir', str(out)], check=True, cwd=ROOT)
                blobs.append((out / '产业就业正典.json').read_bytes())
            return blobs

    def test_double_run_is_idempotent(self):
        a, b = self.build_twice_into_temp()
        self.assertEqual(a, b)

    def test_canon_covers_all_64_job_zones_and_total_headcount(self):
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        reg = json.loads(REGISTRY.read_text(encoding='utf-8'))['entries']
        want = sorted(e['id'] for e in reg if 'daily_workers' in e and e['id'][0] in 'FS')
        self.assertEqual(sorted({c['锚点'] for c in canon['公司']}), want)
        self.assertEqual(sum(c['雇员数'] for c in canon['公司']),
                         sum(e['daily_workers'] for e in reg if e['id'] in want))

    def test_canon_summary_matches_its_own_records(self):
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        s, cs = canon['汇总'], canon['公司']
        self.assertEqual(s['公司数'], len(cs))
        self.assertEqual(s['雇员总数'], sum(c['雇员数'] for c in cs))
        self.assertEqual(s['雇员总数'], s['名录岗位总数'])
        self.assertEqual(s['T5数'], sum(1 for c in cs if c['档位'] == 'T5'))
        self.assertEqual(s['岗位卡数'], sum(len(c['岗位卡']) for c in cs))
        self.assertEqual(s['具名公司数'], sum(1 for c in cs if c['逐家具名']))

    def test_background_anchors_carry_no_recruitable_headcount(self):
        """C51：F001＋F002 的 8800 岗整标记为背景在册，可招聘=true 的公司一家都不许落在这两区。"""
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        src = json.loads(SOURCE.read_text(encoding='utf-8'))
        anchors = set(src['禁则']['不可申请锚点'])
        pool = sum(c['雇员数'] for c in canon['公司'] if c['可招聘'] and c['锚点'] in anchors)
        self.assertEqual(pool, 0)

    def test_every_lvl1_card_clears_the_housing_red_line(self):
        """整部正典层面复核 §5 第4条：任何一张 LVL1 岗位卡的月薪下限都不得跌破住所锚 ÷ 0.40。"""
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        ratio = canon['参数']['住所占比判据']
        below = [c['id'] for company in canon['公司'] for c in company['岗位卡']
                 if c['岗位层'] == 'LVL1' and c['月薪带_钛币'][0] < canon['住所锚'][company['锚点']] / ratio]
        self.assertEqual(below, [])

    def test_canon_is_derived_not_hand_edited(self):
        """派生正典必须带禁止手改声明，且不把源表的参数抄成两套。"""
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        src = json.loads(SOURCE.read_text(encoding='utf-8'))
        self.assertIn('不要手改本文件', canon['declaration'])
        self.assertEqual(canon['参数'], src['参数'])
        self.assertEqual(canon['行业']['小类'], src['小类'])


VERIFY = ROOT / '工具' / 'verify_occupations.py'


def load_verify():
    ns = {'__name__': 'verify_occupations', '__file__': str(VERIFY)}
    exec(compile(VERIFY.read_text(encoding='utf-8'), str(VERIFY), 'exec'), ns)
    return ns


def canon_snapshot():
    return json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))


class Gate(unittest.TestCase):
    def setUp(self):
        self.ns = load_verify()

    def issues(self, canon):
        adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
        costs = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))
        params = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))
        psource = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))['参数']
        layer = json.loads((ROOT / '数据' / '产业空间图层.json').read_text(encoding='utf-8'))
        osource = json.loads((ROOT / '数据' / '职业条目源表.json').read_text(encoding='utf-8'))
        return self.ns['issues'](canon, self.ns['SOURCE'], self.ns['REGISTRY'], adm, costs,
                                 params, psource, layer, osource)

    def test_clean_repo_passes(self):
        r = subprocess.run([sys.executable, str(VERIFY)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_gate_rejects_zone_conservation_break(self):
        canon = canon_snapshot()
        canon['公司'][0]['雇员数'] += 1
        self.assertTrue(any('守恒' in i for i in self.issues(canon)))

    def test_gate_rejects_second_t5_in_one_class(self):
        canon = canon_snapshot()
        canon['公司'].append(dict(canon['公司'][0], id='CORP-X-99', 档位='T5', 大类='A01', 逐家具名=True))
        self.assertTrue(any('T5' in i for i in self.issues(canon)))

    def test_gate_rejects_lvl1_below_red_line(self):
        canon = canon_snapshot()
        card = next(c for comp in canon['公司'] for c in comp['岗位卡'] if c['岗位层'] == 'LVL1')
        card['月薪带_钛币'][0] = 1
        self.assertTrue(any('住所覆盖红线' in i for i in self.issues(canon)))

    def test_gate_writes_thirty_four_check_report(self):
        report = json.loads((ROOT / '数据' / '产业就业核验.json').read_text(encoding='utf-8'))
        self.assertEqual(report['检查项数'], 34)
        self.assertEqual(report['失败数'], 0)
        self.assertEqual(report['图层汇总']['锚点数'], 64)
        self.assertEqual(report['图层汇总']['大类数'], 20)
        self.assertEqual(report['职业条目汇总']['正典条目数'], 684)
        self.assertEqual(report['职业条目汇总']['源表小类行数'], 162)
        relief = report['救助汇总']
        self.assertEqual([relief['全额月数'], relief['递减月数'], relief['最长连发月数']], [2, 4, 6])
        self.assertEqual(relief['逐圈层全额月'], {'内湖环': 1516.3, '外城环': 1395.0,
                                                 '产业小镇': 1288.9, '特色村落': 1197.9})
        self.assertEqual(relief['逐圈层递减月'], {'内湖环': 1061.4, '外城环': 976.5,
                                                '产业小镇': 902.2, '特色村落': 838.5})
        self.assertEqual(relief['逐圈层连发总额'], {'内湖环': 7278.2, '外城环': 6696.0,
                                                 '产业小镇': 6186.6, '特色村落': 5749.8})
        opening = report['开局汇总']
        self.assertEqual([opening['中位'], opening['满值罕见线'], opening['开局区间']], [50, 90, [30, 70]])
        self.assertEqual([opening['单类影响上限'], opening['同维度累计影响上限'], opening['候选组合数']],
                         [10, 20, 2400])
        self.assertEqual(opening['权重和'], 100)


NEGTEST = ROOT / '工具' / 'negtest_occupations.py'


class Negtest(unittest.TestCase):
    def test_every_injection_turns_the_gate_red(self):
        """违例自检必须 132 条全判红、夹具零残留，且被守护的四份正典字节不变。
        132 = 第 1 至 32 条判据各向注入 + C119 五例（刻度改而点数不改、卡牌点数手改、退化下限脱钩、比例块缺键、下界为负）
        + 第 33 条失业救助 17 例 + 第 34 条五维开局与背景卡权重 21 例。"""
        before = (ROOT / '数据' / '产业就业正典.json').read_bytes()
        adm_before = (ROOT / '数据' / '岗位准入正典.json').read_bytes()
        cost_before = (ROOT / '数据' / '物价与生活正典.json').read_bytes()
        param_before = (ROOT / '数据' / '运行参数正典.json').read_bytes()
        r = subprocess.run([sys.executable, str(NEGTEST)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        summary = json.loads(next(l for l in r.stdout.splitlines() if l.startswith('{')))
        self.assertEqual(summary['cases'], 132)
        self.assertEqual(summary['not_red'], 0)
        self.assertEqual(summary['fixture_leftover'], 0)
        self.assertEqual((ROOT / '数据' / '产业就业正典.json').read_bytes(), before)
        self.assertEqual((ROOT / '数据' / '岗位准入正典.json').read_bytes(), adm_before)
        self.assertEqual((ROOT / '数据' / '物价与生活正典.json').read_bytes(), cost_before)
        self.assertEqual((ROOT / '数据' / '运行参数正典.json').read_bytes(), param_before)


class BookChannel(unittest.TestCase):
    def test_book_contains_occupation_chapter(self):
        subprocess.run([sys.executable, str(ROOT / '工具' / 'compile_book.py')], check=True, cwd=ROOT,
                       capture_output=True, text=True)
        book = (ROOT / '钛湖城城市设定集-完整合订本.md').read_text(encoding='utf-8')
        self.assertIn('产业与就业设定', book)
        self.assertIn('20个大类', book)
        self.assertIn('163个小类', book)

    def test_occupation_doc_numbers_come_from_the_canon(self):
        """叙事文档里的规模数字必须与派生正典的汇总一致，不许自成一套。"""
        canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        doc = (ROOT / '产业与就业设定.md').read_text(encoding='utf-8')
        for n in (canon['汇总']['公司数'], canon['汇总']['岗位卡数'], canon['汇总']['雇员总数']):
            self.assertIn(f'{n:,}'.replace(',', ''), doc)
        reg = json.loads(REGISTRY.read_text(encoding='utf-8'))['entries']
        a01 = sum(e['daily_workers'] for e in reg if e['id'] in ('F001', 'F002'))
        self.assertIn(f'{a01} 岗', doc)

    def test_occupation_doc_reports_the_undelivered_layer(self):
        doc = (ROOT / '产业与就业设定.md').read_text(encoding='utf-8')
        self.assertLessEqual(doc.count('CORP-'), 2)
        # 第6期把名称文本与逐条职业内容都落地了，文档不能再声称只出框架；
        # 同时必须把唯一未展开的逐张卡牌实例留在原位，防止过度申报。
        self.assertIn('骨架与内容都已闭环', doc)
        self.assertNotIn('本期只出框架', doc)
        self.assertIn('逐张卡牌实例', doc)
        self.assertIn('属待用户点单项', doc)
        self.assertIn('禁则', doc)


class Rulings(unittest.TestCase):
    PHASE_IDS = ['C48', 'C49', 'C50', 'C51', 'C52', 'C53', 'C54', 'C55', 'C56']

    def test_nine_new_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        self.assertIsInstance(rows, list)
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 125)

    def test_manual_chains_occupation_steps(self):
        manual = (ROOT / 'AI创作使用手册.md').read_text(encoding='utf-8')
        for tool in ('build_occupations.py', 'verify_occupations.py', 'negtest_occupations.py'):
            self.assertIn(tool, manual)
        self.assertIn('产业就业正典.json', manual)


class AdmissionRulings(unittest.TestCase):
    PHASE_IDS = ['C57', 'C58', 'C59', 'C60', 'C61', 'C62', 'C63', 'C64', 'C65']

    def test_nine_new_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 125)

    def test_manual_chains_admission_before_occupations(self):
        manual = (ROOT / 'AI创作使用手册.md').read_text(encoding='utf-8')
        for tool in ('build_admission.py', '岗位准入正典.json', '岗位准入总表.md'):
            self.assertIn(tool, manual)
        self.assertLess(manual.index('build_admission.py'), manual.index('build_occupations.py'))


class PhaseSixRulings(unittest.TestCase):
    PHASE_IDS = ['C114', 'C115', 'C116', 'C117']

    def test_four_new_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 125)

    def test_phase_six_rulings_keep_the_hard_wording(self):
        """四条第6期裁定各钉一句只有真源侧才说得出的硬话：
        C114 的对账方向、C115 的拼接口径、C116 的单真源、C117 的零新增字段——措辞被改回话术即失去唯一出处。"""
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertIn('声明清单必须逐字等于正典实测的无引用集合', by_id['C114']['裁定'])
        self.assertIn('不新增也不删除任何公司、岗位卡与名额', by_id['C114']['裁定'])
        self.assertIn('名称不是起的而是拼的', by_id['C115']['裁定'])
        self.assertIn('生成器不内嵌任何名称常量', by_id['C115']['裁定'])
        self.assertIn('图层不新建真源', by_id['C116']['裁定'])
        self.assertIn('图层文件内不得存第二份坐标', by_id['C116']['裁定'])
        self.assertIn('连接键是卡片已有的 行业小类', by_id['C117']['裁定'])
        self.assertIn('条数带、总条数区间 500—900 与全部长度带只住在该表「规格」块', by_id['C117']['裁定'])

    def test_gate_check_names_are_written_in_the_setting_doc(self):
        """第26至34条的名称在叙事文档第6节逐条在位，闸门报告改了名字而文档没跟，就等于申报通过。"""
        doc = (ROOT / '产业与就业设定.md').read_text(encoding='utf-8')
        for name in ('具名命名完整', '名称逐段回查', '命名池齐套', '名称禁则与长度',
                     '零消费者对账', '产业图层对账', '职业条目对账', '失业救助对账', '五维开局对账'):
            self.assertIn(name, doc)


class PhaseSevenRulings(unittest.TestCase):
    PHASE_IDS = ['C120']

    def test_island_ruling_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 125)

    def test_island_ruling_keeps_the_hard_wording(self):
        """第7期裁定钉四句只有真源侧才说得出的硬话：无桥是用户给的硬约束、岛不进名录是三层落法的代价账、
        峰值与性质两条新判据各带变异验证——改回话术就查不出「顺手补第四通路」那种倒退。"""
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertIn('岛与城市之间没有任何桥', by_id['C120']['裁定'])
        self.assertIn('名录 entries 恒 312 条不变', by_id['C120']['裁定'])
        self.assertIn('进出岛只认三条通路', by_id['C120']['裁定'])
        self.assertIn('把它塞进 312 条名录就会连带触发', by_id['C120']['原因'])
        self.assertIn('59/59 判红', by_id['C120']['影响'])
        self.assertIn('28/28 判红', by_id['C120']['影响'])
        self.assertIn('计数钉 119→120', by_id['C120']['影响'])

    def test_island_gates_are_pinned(self):
        """第7期的通行闸门条数与构件数只写在闸机自己的输出里，单测此前一条没钉——
        删掉判据或把构件数改小都不会被单测抓到，所以在这里把盘上读数钉住。"""
        import negtest_spatial
        parts = json.loads((ROOT / '数据' / '河岸锚点核验.json').read_text(encoding='utf-8'))['构件']
        self.assertEqual(parts['判据数'], 25)
        self.assertEqual(parts['失败'], 0)
        self.assertEqual((parts['桥梁'], parts['渡位'], parts['航线'], parts['山口']), (8, 13, 7, 7))
        self.assertEqual((parts['岛上场地'], parts['湖底隧道'], parts['高空缆车']), (3, 1, 1))
        self.assertEqual(len(negtest_spatial.cases()), 59)


class PhaseEightRulings(unittest.TestCase):
    PHASE_IDS = ['C121']

    def test_phase_eight_ruling_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.PHASE_IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 125)

    def test_phase_eight_ruling_keeps_the_hard_wording(self):
        """第8期裁定钉四句只有真源侧才说得出的硬话：救助金额一律派生不手填、按本人发放不乘户均规模、
        开局只给区间不给种子、分布不属正典——改回话术就查不出「顺手加一档绝对金额」那种倒退。"""
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertIn('金额一个都不手填', by_id['C121']['裁定'])
        self.assertIn('发放主体是登记失业者本人，不乘户均规模', by_id['C121']['裁定'])
        self.assertIn('开局只给区间与中位', by_id['C121']['裁定'])
        self.assertIn('分布属运行时生成，不属正典', by_id['C121']['裁定'])
        self.assertIn('违例注入 94→132（救助侧 17 例、开局侧 21 例）', by_id['C121']['影响'])
        self.assertIn('注入实测 132/132 判红、夹具零残留', by_id['C121']['影响'])
        self.assertIn('脚本不得代签', by_id['C121']['影响'])

    def test_phase_eight_gates_are_written_in_the_setting_doc(self):
        """第 33／34 两条判据的口径要在叙事文档第6节各自成段：闸门加了判据而文档没写，
        读文档的人就会以为只有三十二条，申报覆盖面时按旧的算。"""
        doc = (ROOT / '产业与就业设定.md').read_text(encoding='utf-8')
        self.assertIn('三十四条门禁', doc)
        self.assertIn('132 条注入', doc)
        self.assertIn('失业救助对账', doc)
        self.assertIn('五维开局对账', doc)
        for needle in ('不乘户均规模', '递减月须低于本圈层住所锚中位', '候选组合数'):
            self.assertIn(needle, doc)


class AdmissionSource(unittest.TestCase):
    PATH = ROOT / '数据' / '岗位准入源表.json'

    def setUp(self):
        self.src = json.loads(self.PATH.read_text(encoding='utf-8'))

    def test_enums_are_closed_and_exact(self):
        self.assertEqual(self.src['阶'], ['见习', '熟练', '精通', '权威'])
        self.assertEqual(sorted(self.src['途径']), ['EVT', 'LEV', 'LRN', 'TRN', 'WKS'])
        self.assertEqual(len(self.src['通用技能池']), 12)
        self.assertEqual(len(self.src['合同类型']), 9)
        self.assertEqual(len(self.src['通用场景']), 8)
        self.assertEqual(len(self.src['卡牌族']), 12)
        self.assertEqual(len(self.src['释放状态']), 6)

    def test_every_card_family_repeats_the_five_global_rules(self):
        for fam in self.src['卡牌族']:
            self.assertEqual(fam['禁则'], self.src['全局禁则'])
            self.assertIn(fam['效果类型'], self.src['卡牌效果类型'])

    def test_contract_fields_are_complete(self):
        need = {'id', '名称', '用工形态', '月工时上限_相对174', '薪酬结算周期', '试用期_城市年',
                '年休假基准_天', '加班口径', '解除条件', '可叠加', '可适用岗位层', '可适用公司档', '占用名额'}
        for c in self.src['合同类型']:
            self.assertEqual(set(c), need, c['id'])
            self.assertLessEqual(c['月工时上限_相对174'] if c['月工时上限_相对174'] else 1.0, 1.0)

    def test_state_machine_release_only_goes_to_open_or_struck(self):
        moves = {s['id']: s['去向'] for s in self.src['释放状态']}
        self.assertEqual(moves['RLS-05'], ['RLS-02', 'RLS-06'])
        self.assertEqual(moves['RLS-06'], [])
        for sid, targets in moves.items():
            for t in targets:
                self.assertIn(t, moves, sid)


class AdmissionTags(unittest.TestCase):
    def setUp(self):
        self.adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
        self.occ = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))

    def test_tag_counts_and_ids_are_derived_not_hand_listed(self):
        tags = self.adm['标签']
        self.assertEqual(len(tags), 398)
        self.assertEqual(self.adm['汇总']['标签数'], 398)
        self.assertEqual({t['id'] for t in tags if t['族'] == '专属技能'},
                         {'SKL-' + s['id'] + '-' + k for s in self.occ['小类'] for k in ('S1', 'S2')})

    def test_qualification_tags_can_never_be_pushed_by_work(self):
        for t in self.adm['标签']:
            self.assertTrue(set(t['可推进途径']) <= set(self.adm['途径']), t['id'])
            self.assertEqual(t['可由日常活动推进'], 'LEV' in t['可推进途径'], t['id'])
            if t['族'] == '资质':
                self.assertNotIn('WKS', t['可推进途径'])

    def test_common_tags_cycle_over_twelve(self):
        ids = [t['id'] for t in self.adm['标签'] if t['族'] == '通用技能']
        self.assertEqual(len(ids), 12)
        self.assertEqual(self.adm['通用标签分配']['A01'], ['SKL-C01', 'SKL-C02', 'SKL-C03'])
        self.assertEqual(self.adm['通用标签分配']['A05'], ['SKL-C01', 'SKL-C02', 'SKL-C03'])


class AdmissionDicts(unittest.TestCase):
    def setUp(self):
        self.adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
        self.occ = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))

    def test_scene_counts_and_layer_coverage(self):
        self.assertEqual(len(self.adm['场景']), 48)
        by_id = {s['id']: s for s in self.adm['场景']}
        for d in self.occ['大类']:
            self.assertEqual(by_id['SCN-' + d['id'] + '-1']['触发岗位层'], ['LVL3'])
            self.assertEqual(by_id['SCN-' + d['id'] + '-2']['触发岗位层'], ['LVL4', 'LVL5'])
            self.assertEqual(by_id['SCN-' + d['id'] + '-1']['适用大类'], [d['id']])

    def test_result_wording_is_the_same_three_outcomes(self):
        for s in self.adm['场景']:
            self.assertEqual(sorted(s['结果口径']), ['挂起', '未通过', '通过'], s['id'])

    def test_contract_matrix_is_solvable_for_every_shape(self):
        sys.path.insert(0, str(ROOT / '工具'))
        from build_admission import contracts_for
        for level in ('LVL1', 'LVL2', 'LVL3', 'LVL4', 'LVL5'):
            for tier in ('T2', 'T3', 'T4', 'T5'):
                for form in ('受雇', '背景在册', '自由接单', '受雇或自由接单'):
                    self.assertTrue(contracts_for(level, tier, form), (level, tier, form))
        self.assertIn('CTR-07', contracts_for('LVL5', 'T4', '自由接单'))
        self.assertNotIn('CTR-07', contracts_for('LVL2', 'T3', '受雇'))


class AdmissionWiring(unittest.TestCase):
    def setUp(self):
        self.canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        self.adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
        self.cards = [x for c in self.canon['公司'] for x in c['岗位卡']]

    def test_every_card_carries_four_reference_fields(self):
        for card in self.cards:
            for field in ('准入标签', '关键场景', '合同类型', '释放状态'):
                self.assertIn(field, card, card['id'])
            self.assertTrue(card['准入标签'], card['id'])

    def test_level_three_and_above_require_a_scene_and_below_must_not(self):
        for card in self.cards:
            if card['岗位层'] in ('LVL3', 'LVL4', 'LVL5'):
                self.assertTrue(card['关键场景'], card['id'])
            else:
                self.assertEqual(card['关键场景'], [], card['id'])

    def test_no_card_refs_dangle_and_parent_matches(self):
        tag_ids = {t['id']: t for t in self.adm['标签']}
        scene_ids = {s['id'] for s in self.adm['场景']}
        contract_ids = {c['id'] for c in self.adm['合同类型']}
        for card in self.cards:
            for tid, level in card['准入标签']:
                self.assertIn(tid, tag_ids, card['id'])
                self.assertEqual(tag_ids[tid]['父小类'] or card['行业小类'], card['行业小类'], tid)
                self.assertIn(level, self.adm['阶'] + ['认定', '持有'], tid)
            self.assertTrue(set(card['关键场景']) <= scene_ids, card['id'])
            self.assertTrue(set(card['合同类型']) <= contract_ids, card['id'])

    def test_release_state_follows_start_year(self):
        base = self.canon['setting_year']
        for card in self.cards:
            self.assertEqual(card['释放状态'], 'RLS-01' if card['起始城市年'] > base else 'RLS-02', card['id'])
        # 量级金标准（C86 口径 10541 张卡）：改人口或岗位量级要连带重定。
        # 1518→1496 的位移来自第6期无消费者收编：大类卡数与名额逐类不变，但卡落在哪个小类整体轮转，
        # 起始晚于基准年的小类随之增减（C114）。
        self.assertEqual(sum(1 for x in self.cards if x['释放状态'] == 'RLS-01'), 1496)


class AdmissionGate(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / '工具'))
        import verify_occupations as vo
        self.vo = vo
        self.canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
        self.adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
        self.costs = json.loads((ROOT / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))
        self.params = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))
        self.psource = json.loads((ROOT / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))['参数']
        self.layer = json.loads((ROOT / '数据' / '产业空间图层.json').read_text(encoding='utf-8'))
        self.osource = json.loads((ROOT / '数据' / '职业条目源表.json').read_text(encoding='utf-8'))

    def bad(self):
        return self.vo.issues(self.canon, self.vo.SOURCE, self.vo.REGISTRY, self.adm,
                              self.costs, self.params, self.psource, self.layer, self.osource)

    def test_thirty_four_checks_and_clean_canon_passes(self):
        self.assertEqual(len(self.vo.CHECKS), 34)
        self.assertEqual(self.vo.CHECKS[25:],
                         ['具名命名完整', '名称逐段回查', '命名池齐套', '名称禁则与长度',
                          '零消费者对账', '产业图层对账', '职业条目对账', '失业救助对账', '五维开局对账'])
        self.assertEqual(self.bad(), [])

    def test_gate_detects_dangling_tag_and_empty_scene(self):
        c = json.loads(json.dumps(self.canon))
        card = next(x for comp in c['公司'] for x in comp['岗位卡'] if x['岗位层'] == 'LVL3')
        card['准入标签'][0][0] = 'SKL-Z99-B99-S1'
        self.assertTrue(any('引用完整性' in x for x in self.vo.issues(c, self.vo.SOURCE, self.vo.REGISTRY, self.adm, self.costs, self.params, self.psource, self.layer, self.osource)))
        c2 = json.loads(json.dumps(self.canon))
        for comp in c2['公司']:
            for x in comp['岗位卡']:
                if x['岗位层'] == 'LVL3':
                    x['关键场景'] = []
        self.assertTrue(any('关键场景' in x for x in self.vo.issues(c2, self.vo.SOURCE, self.vo.REGISTRY, self.adm, self.costs, self.params, self.psource, self.layer, self.osource)))


class AdmissionDoc(unittest.TestCase):
    def test_dictionary_counts_in_doc_come_from_admission_canon(self):
        adm = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))['汇总']
        doc = (ROOT / '产业与就业设定.md').read_text(encoding='utf-8')
        for key in ('标签数', '场景数', '合同类型数', '卡牌族数', '释放状态数'):
            self.assertIn(str(adm[key]), doc, key)
        self.assertIn('第8节', doc)

    def test_gate_wording_matches_check_count_in_generated_report(self):
        n = json.loads((ROOT / '数据' / '产业就业核验.json').read_text(encoding='utf-8'))['检查项数']
        report = (ROOT / '质量核验报告.md').read_text(encoding='utf-8')
        self.assertEqual(n, 34)
        self.assertIn(f'{n}条判据实测0失败', report)


if __name__ == '__main__':
    unittest.main()
