# -*- coding: utf-8 -*-
"""第5期流程与制度包回归。除幂等用例会在原地重跑真实派生器外只读已落盘产物，不手改派生文件。

跑法：python 工具/test_flows.py（工作目录＝设定集根）
"""
import datetime
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))

CANON = json.loads((ROOT / '数据' / '流程制度正典.json').read_text(encoding='utf-8'))
SRC = json.loads((ROOT / '数据' / '流程制度源表.json').read_text(encoding='utf-8'))
RUN = json.loads((ROOT / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))
ADMISSION = json.loads((ROOT / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))
OCCUPATION = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))


class SummaryPins(unittest.TestCase):
    EXPECTED = {
        '节庆条数': 18, '节庆占天次': 23, '机构数': 12, '公职条目数': 24,
        '公职编制合计': 7453, '机构编制合计': 31960, '登记对象数': 5, '门禁项数': 12,
        '共创步骤数': 7, '删除步骤数': 6, '删除字段数': 10, '调解主体数': 5,
        '争议类别数': 6, '拉黑动作数': 5, '合同存续数': 9, '事件模板数': 20,
        '负面模板数': 6, '随机触发数': 2, '税种数': 6, '采购档数': 4,
        '关系阶数': 7, '文化层数': 4, '失真档数': 4, '界面层级数': 6,
        '导出格式数': 6, '自由层条数': 8, '停止确认条数': 8, '版本兼容行数': 7,
    }

    def test_summary_counts(self):
        got = {k: CANON['汇总'][k] for k in self.EXPECTED}
        self.assertEqual(got, self.EXPECTED)

    def test_season_day_split(self):
        self.assertEqual(CANON['汇总']['节庆逐季占天'], {'SEA-1': 8, 'SEA-2': 4, 'SEA-3': 6, 'SEA-4': 5})
        self.assertEqual(sum(CANON['汇总']['节庆逐季占天'].values()), CANON['汇总']['节庆占天次'])

    def test_level_counts_add_up(self):
        self.assertEqual(CANON['汇总']['各级模板数'], {'个人': 6, '家庭': 5, '社区': 5, '城市': 4})
        self.assertEqual(sum(CANON['汇总']['各级模板数'].values()), CANON['汇总']['事件模板数'])


class FestivalCalendar(unittest.TestCase):
    def test_every_festival_is_recomputable_from_public_calendar(self):
        weekdays = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
        for f in CANON['节庆年历']:
            d = datetime.date(CANON['setting_year'], f['月'], f['日'])
            end = d + datetime.timedelta(days=f['日期跨度天'] - 1)
            self.assertEqual(f['星期'], weekdays[d.weekday()], f['编号'])
            self.assertEqual(f['年内第几天'], d.timetuple().tm_yday, f['编号'])
            self.assertEqual(f['SEA'], RUN['月季节'][str(f['月'])], f['编号'])
            self.assertEqual((f['结束月'], f['结束日']), (end.month, end.day), f['编号'])
            self.assertLessEqual(end.year, CANON['setting_year'], f['编号'])

    def test_year_is_2013_and_rows_sorted(self):
        self.assertEqual(CANON['setting_year'], 2013)
        days = [f['年内第几天'] for f in CANON['节庆年历']]
        self.assertEqual(days, sorted(days))
        self.assertEqual(len({f['编号'] for f in CANON['节庆年历']}), 18)

    def test_no_anchor_is_double_booked_on_the_same_day(self):
        seen = set()
        for f in CANON['节庆年历']:
            start = datetime.date(CANON['setting_year'], f['月'], f['日'])
            for k in range(f['日期跨度天']):
                day = start + datetime.timedelta(days=k)
                for a in f['范围锚点']:
                    self.assertNotIn((day.toordinal(), a), seen, f'{a} 在 {day} 撞档')
                    seen.add((day.toordinal(), a))
        self.assertEqual(len(seen), sum(f['日期跨度天'] * len(f['范围锚点']) for f in CANON['节庆年历']))
        self.assertEqual(len(seen), 41)

    def test_city_level_festivals_span_at_least_two_districts(self):
        types = {e['id']: e['type'] for e in REGISTRY['entries']}
        city = [f for f in CANON['节庆年历'] if f['级别'] == '城市']
        self.assertEqual([f['编号'] for f in city], ['FE-02', 'FE-01', 'FE-06', 'FE-17'])
        for f in city:
            self.assertIn('城市片区', {types.get(a, '构件') for a in f['范围锚点']}, f['编号'])
            self.assertGreaterEqual(len(f['范围锚点']), 2, f['编号'])


class GovernmentAndPosts(unittest.TestCase):
    def test_posts_never_enter_the_job_registry(self):
        reg_ids = {e['id'] for e in REGISTRY['entries']}
        corp_ids = {c['id'] for c in OCCUPATION['公司']}
        card_ids = {k['id'] for c in OCCUPATION['公司'] for k in c['岗位卡']}
        for p in CANON['公职']:
            self.assertNotIn(p['编号'], reg_ids | corp_ids | card_ids, p['编号'])
            self.assertNotIn('薪酬', json.dumps(p, ensure_ascii=False))
            self.assertIn(p['参照层'], {l['层'] for l in OCCUPATION['岗位层']})

    def test_org_quotas_cover_registered_posts_and_anchor_scale(self):
        for o in CANON['机构']:
            self.assertLessEqual(o['登记编制小计'], o['编制'], o['编号'])
            if o['锚点岗位规模'] is not None:
                self.assertLessEqual(o['同锚点编制合计'], o['锚点岗位规模'], o['编号'])
            else:
                # D/R 类锚点在公司名录里没有岗位规模读数，机构编制只能靠自身编制封顶，缺读数以 None 明写
                self.assertTrue(o['驻地锚点'][0] in 'DLR', o['编号'])
            self.assertEqual({p['层级'] for p in CANON['公职'] if p['机构'] == o['编号']} - {o['层级']}, set())

    def test_anchors_resolve_to_registry_or_period5_components(self):
        component_codes = {r['码'] for key in ('桥梁', '渡位', '山口通道', '轮渡航线')
                           for r in json.loads((ROOT / '数据' / '空间通行正典.json').read_text(encoding='utf-8'))[key]}
        ids = {e['id'] for e in REGISTRY['entries']} | component_codes
        for f in CANON['节庆年历']:
            for a in f['范围锚点']:
                self.assertIn(a, ids, f['编号'])
        for o in CANON['机构']:
            self.assertIn(o['驻地锚点'], ids, o['编号'])


class CrossSourcePins(unittest.TestCase):
    def test_event_cooldown_and_advance_follow_period4(self):
        cool, advance = RUN['参数']['事件']['冷却天'], RUN['参数']['事件']['预告天']
        for e in CANON['事件目录']:
            self.assertEqual(e['冷却天'], cool[e['级别']], e['编号'])
            self.assertEqual(e['冷却天声明'], cool[e['级别']], e['编号'])
            self.assertEqual(e['预告天'], advance.get(f'{e["级别"]}级', 0), e['编号'])

    def test_contract_rows_equal_the_contract_dictionary(self):
        want = {c['id']: c for c in ADMISSION['合同类型']}
        self.assertEqual({c['合同类型'] for c in CANON['合同存续']}, set(want))
        for c in CANON['合同存续']:
            src = want[c['合同类型']]
            self.assertEqual(c['名称'], src['名称'])
            self.assertEqual(c['用工形态'], src['用工形态'])
            self.assertEqual(c['薪酬结算周期'], src['薪酬结算周期'])
            self.assertEqual(c['解除条件数'], len(src['解除条件']))

    def test_version_matrix_equals_on_disk_versions(self):
        for r in CANON['版本兼容']:
            actual = (CANON['version'] if r['对象'] == '数据/流程制度正典.json'
                      else json.loads((ROOT / r['对象']).read_text(encoding='utf-8'))['version'])
            self.assertEqual((r['声明版本'], r['实际版本']), (actual, actual), r['对象'])
            self.assertEqual(r['旧轮次下限'], 2013, r['对象'])

    def test_every_gate_item_and_export_carrier_is_on_disk(self):
        for g in CANON['门禁项']:
            self.assertTrue((ROOT / '工具' / g['承载脚本']).exists(), g['编号'])
        for o in CANON['登记对象']:
            self.assertTrue((ROOT / o['落点源表']).exists(), o['码'])
            for t in [o['校验工具']] + o['附校验']:
                self.assertTrue((ROOT / '工具' / t).exists(), f'{o["码"]}:{t}')
        for e in CANON['导出格式']:
            self.assertTrue(e['产物存在'], e['码'])
            self.assertTrue((ROOT / e['承载产物']).exists(), e['码'])


class ThresholdsAndUi(unittest.TestCase):
    def test_relation_and_rumour_thresholds_are_monotonic(self):
        self.assertEqual([r['阶'] for r in CANON['关系层级']], list(range(1, 8)))
        self.assertEqual([r['累计有效互动下限'] for r in CANON['关系层级']], [0, 3, 8, 15, 30, 45, 60])
        self.assertEqual([x['失真比例千分比'] for x in CANON['传闻失真']], [0, 100, 300, 600])
        self.assertEqual(CANON['传闻失真'][-1]['判定影响'], '禁止')

    def test_purchase_tiers_seam_and_tax_rates_in_range(self):
        self.assertEqual([(t['金额下限_钛币'], t['金额上限_钛币'], t['公示天']) for t in CANON['采购分档']],
                         [(0, 50000, 3), (50000, 500000, 7), (500000, 5000000, 14), (5000000, None, 21)])
        for t in CANON['税种']:
            self.assertTrue(0 < t['税率千分比'] < 1000, t['码'])

    def test_quiet_mode_covers_every_ui_item_and_only_fact_line_is_unmuted(self):
        ui = CANON['参数']['界面与导出']
        known = {u['码'] for u in CANON['界面层级']} | {s['码'] for s in ui['摘要跨度']}
        covered = [m for lvl in ui['免打扰分级'] for m in lvl['成员']]
        self.assertEqual(set(covered), known)
        self.assertEqual(len(covered), len(set(covered)))
        self.assertEqual(ui['免打扰分级'][0]['成员'], ['UI-01'])

    def test_ai_free_layer_has_a_correction_channel_for_every_item(self):
        ai = CANON['参数']['AI自由层']
        codes = {f['码'] for f in ai['可自由补全']} | {s['码'] for s in ai['须停止确认']}
        referenced = {w for c in ai['更正提示'] for w in c['适用'].replace('、', ' ').split() if w in codes}
        self.assertEqual(referenced, codes)
        self.assertTrue(any('不适用，一律拒绝' in s['确认主体'] for s in ai['须停止确认']))


class RenderedTable(unittest.TestCase):
    def setUp(self):
        self.table = (ROOT / '数据' / '流程制度总表.md').read_text(encoding='utf-8')

    def test_section_and_row_counts(self):
        import re
        self.assertEqual(len(re.findall(r'^## ', self.table, re.M)), 15)
        self.assertEqual(len(re.findall(r'^\| FE-\d\d ', self.table, re.M)), 18)
        self.assertEqual(len(re.findall(r'^\| ORG-\d\d ', self.table, re.M)), 12)
        self.assertEqual(len(re.findall(r'^\| GOV-\d\d ', self.table, re.M)), 24)
        self.assertEqual(len(re.findall(r'^\| GT-\d\d ', self.table, re.M)), 12)
        self.assertEqual(len(re.findall(r'^\| EVT-\d\d ', self.table, re.M)), 20)
        self.assertEqual(len(re.findall(r'^\| CTR-\d\d ', self.table, re.M)), 9)
        self.assertEqual(len(re.findall(r'^\| (BR-|WH-|PA-|FR-|EXP-|TAX-|CUL-|UI-|STP-|COR-|MED-|DSP-|OBJ-)',
                                        self.table, re.M)), 57)

    def test_festival_rows_have_twelve_columns(self):
        for line in self.table.splitlines():
            if line.startswith('| FE-'):
                self.assertEqual(line.count('|'), 13, line[:40])

    def test_no_transport_damage_and_markdown_pipes_are_escaped(self):
        for token in ('禁止手改', '锚点岗位规模', '不适用，一律拒绝', '占天次', '第4期'):
            self.assertIn(token, self.table)
        self.assertNotIn('\ufffd', self.table)
        self.assertNotIn('\u2026', self.table)
        self.assertNotIn('\u200b', self.table)
        body = self.table.split('## 一、', 1)[1]
        for line in body.splitlines():
            if line.startswith('| ') and not line.startswith('| ---'):
                self.assertNotIn('||', line, line[:40])

    def test_source_table_is_clean_too(self):
        text = (ROOT / '数据' / '流程制度源表.json').read_text(encoding='utf-8')
        self.assertNotIn('\ufffd', text)
        self.assertNotIn('\u2026', text)
        self.assertEqual(SRC['version'], 'THC-FLOW-2013-1.0')
        self.assertEqual(sorted(SRC['参数']), sorted(
            ['AI自由层', '事件目录', '公共财政', '关系与文化阈值', '共创转永久', '匿名化与删除',
             '节庆', '界面与导出', '新条目登记', '机构与公职', '版本兼容', '调解与争议', '拉黑后合同']))


class GateReport(unittest.TestCase):
    def test_gate_has_twenty_three_checks_and_is_green(self):
        report = json.loads((ROOT / '数据' / '流程制度核验.json').read_text(encoding='utf-8'))
        self.assertEqual(report['检查项数'], 23)
        self.assertEqual(report['失败数'], 0)
        self.assertEqual(report['失败明细'], [])
        self.assertEqual(report['检查项'], CANON_CHECKS)

    def test_every_check_has_a_negative_case(self):
        import negtest_flows
        injected = {expected for _, _, expected in negtest_flows.cases()}
        self.assertEqual(injected, set(CANON_CHECKS))
        self.assertEqual(len(negtest_flows.cases()), 24)


CANON_CHECKS = json.loads((ROOT / '数据' / '流程制度核验.json').read_text(encoding='utf-8'))['检查项']


class Idempotency(unittest.TestCase):
    ARTIFACTS = ('流程制度正典.json', '流程制度总表.md')

    def test_deriver_is_byte_idempotent(self):
        before = {a: hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest() for a in self.ARTIFACTS}
        for _ in range(2):
            subprocess.run([sys.executable, str(ROOT / '工具' / 'build_flows.py')],
                           check=True, capture_output=True)
            for a in self.ARTIFACTS:
                self.assertEqual(hashlib.sha1((ROOT / '数据' / a).read_bytes()).hexdigest(),
                                 before[a], f'{a} 双跑不幂等')


if __name__ == '__main__':
    unittest.main(verbosity=2)
