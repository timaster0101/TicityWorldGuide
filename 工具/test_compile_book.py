import collections
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import compile_book as compiler

ROOT = Path(__file__).resolve().parents[1]


def sections_of(body):
    result = {}
    for index, tag in enumerate(compiler.TAGS):
        start = body.index(f'**{tag}**') + len(f'**{tag}**')
        end = body.index(f'**{compiler.TAGS[index + 1]}**', start) if index + 1 < len(compiler.TAGS) else len(body)
        result[tag] = body[start:end].strip('：: \n')
    return result


class NumericFidelityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / '数据/城市空间名录.json').read_text(encoding='utf-8'))
        cls.registry = {entry['id']: entry for entry in data['entries']}
        cls.drafts = {}
        for path in (ROOT / '分卷/原稿').glob('*.md'):
            for eid, _, body in compiler.split_entries(path.read_text(encoding='utf-8-sig')):
                cls.drafts[eid] = body

    def issues(self, eid, body):
        return compiler.check_numeric_fidelity(eid, self.registry[eid], body, sections_of(body), self.registry)[0]

    def lit(self, eid, field, suffix=''):
        """把名录现值排成原稿里的那串字面量，负测就不钉死某一个量级的数字。"""
        value = self.registry[eid][field]
        return (('%g' % value) if isinstance(value, float) else str(value)) + suffix

    def once(self, eid, literal):
        """注入前提：该字面量在正文里恰好出现一次；名录改过而原稿没跟上时夹具先判红，不许静默空跑。"""
        self.assertEqual(self.drafts[eid].count(literal), 1, f'夹具字面量已失效：{eid} {literal}')
        return literal

    def test_all_current_entries_have_matching_labeled_parameters(self):
        self.assertEqual(len(self.drafts), 312)
        for eid, body in self.drafts.items():
            with self.subTest(eid=eid):
                self.assertEqual(self.issues(eid, body), [])

    def test_population_cannot_match_digits_inside_a_larger_number(self):
        pop = self.once('R018', self.lit('R018', 'population'))
        body = self.drafts['R018'].replace(pop, '1' + pop)
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_unrelated_correct_number_cannot_rescue_wrong_population(self):
        pop = self.once('R018', self.lit('R018', 'population'))
        body = self.drafts['R018'].replace(pop, '1' + pop) + f'\n铺装{pop}平方米。'
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_decimal_suffix_cannot_match_population(self):
        pop = self.once('R018', self.lit('R018', 'population'))
        body = self.drafts['R018'].replace(pop, pop + '.5')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_households_are_required_even_when_number_occurs_elsewhere(self):
        unit = self.once('R018', self.lit('R018', 'households', '户'))
        body = self.drafts['R018'].replace(unit, unit[:-1] + '平方米')
        self.assertTrue(any('households' in issue for issue in self.issues('R018', body)))

    def test_floor_area_requires_square_meters(self):
        area = self.once('R018', self.lit('R018', 'gross_floor_area_m2', '平方米'))
        body = self.drafts['R018'].replace(area, area[:-3] + '米')
        self.assertTrue(any('gross_floor_area_m2' in issue for issue in self.issues('R018', body)))

    def test_land_area_is_not_a_rounded_or_unrelated_number(self):
        plot = self.once('R018', self.lit('R018', 'area_km2', '平方公里'))
        body = self.drafts['R018'].replace(plot, self.lit('R018', 'area_km2', '').split('.')[0] + '.2平方公里')
        body += f'\n机位参数{self.lit("R018", "area_km2")}。'
        self.assertTrue(any('area_km2' in issue for issue in self.issues('R018', body)))

    def test_conflicting_population_claim_is_not_rescued_by_correct_claim(self):
        claim = self.once('R018', '人口' + self.lit('R018', 'population'))
        body = self.drafts['R018'].replace(claim, '人口1' + self.lit('R018', 'population'))
        body = body.replace('**人群与生活节奏**：', f'**人群与生活节奏**：{claim}人。')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_building_height_cannot_be_supplied_by_camera_height(self):
        height = self.lit('L001', 'height_m')
        pair = self.once('L001', f"{self.lit('L001', 'floors')}层{height}米")
        self.once('L001', f'高{height}米')
        body = self.drafts['L001'].replace(f'高{height}米', f'高1{height}米').replace(pair, f'{self.lit("L001", "floors")}层1{height}米')
        body += f'\n相机离地{height}米。'
        self.assertTrue(any('height_m' in issue for issue in self.issues('L001', body)))

    def test_lock_only_floor_and_height_conflicts_are_rejected(self):
        height, floors = self.lit('L001', 'height_m'), self.lit('L001', 'floors')
        for before, after, field in [(f'{floors}层{height}米', f'1{floors}层{height}米', 'floors'),
                                     (f'{floors}层{height}米', f'{floors}层1{height}米', 'height_m')]:
            with self.subTest(field=field):
                original = self.drafts['L001']
                self.assertEqual(original.count(before), 1)
                body = original.replace(before, after)
                self.assertTrue(any(field in issue for issue in self.issues('L001', body)))

    def test_lock_only_prohibited_height_conflict_is_rejected(self):
        limit = self.once('R016', f"禁止超{self.lit('R016', 'height_limit_m')}米")
        body = self.drafts['R016'].replace(limit, f"禁止超1{self.lit('R016', 'height_limit_m')}米")
        self.assertTrue(any('height_limit_m' in issue for issue in self.issues('R016', body)))

    def test_suffix_form_limit_outside_the_position_paragraph_is_still_audited(self):
        """2-B 抬的 9 条里有 3 条把限高写成「N米上限」后置式，且落在规划段而非位置段。

        这一支不在校验面的话，抬限高时改错数字会静默过闸，名录与原稿各留一个数。
        """
        for eid, suffix in (('R050', '米高度上限'), ('R051', '米上限无需用尽'), ('R054', '米上限')):
            with self.subTest(eid=eid):
                limit = self.once(eid, self.lit(eid, 'height_limit_m') + suffix)
                body = self.drafts[eid].replace(
                    limit, self.lit(eid, 'height_limit_m') + '0' + suffix)
                self.assertTrue(any('height_limit_m' in issue
                                    for issue in self.issues(eid, body)))

    def test_population_with_explicit_wrong_unit_is_rejected(self):
        claim = self.once('R018', f"人口{self.lit('R018', 'population')}、")
        body = self.drafts['R018'].replace(claim, f"人口{self.lit('R018', 'population')}平方米、")
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_distance_sign_and_grouped_digits_are_not_discarded(self):
        original = self.drafts['R018']
        self.once('R018', '1.58千米')
        for wrong in ('-1.58千米', '1,001.58千米'):
            with self.subTest(wrong=wrong):
                body = original.replace('1.58千米', wrong)
                self.assertTrue(any('geometry gives' in issue for issue in self.issues('R018', body)))

    def test_person_visits_are_not_resident_population(self):
        claim = self.once('R018', f"人口{self.lit('R018', 'population')}、")
        body = self.drafts['R018'].replace(claim, f"人口{self.lit('R018', 'population')}人次、")
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_grouped_thousands_remain_valid(self):
        original = self.drafts['R018']
        body = original
        for field in ('population', 'gross_floor_area_m2', 'households'):
            plain = self.once('R018', self.lit('R018', field))
            body = body.replace(plain, f'{self.registry["R018"][field]:,}')
        self.assertEqual(self.issues('R018', body), [])

    def test_audit_command_returns_failure_when_population_is_wrong(self):
        population = self.registry['R018']['population']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '工具').mkdir()
            (root / '数据').mkdir()
            shutil.copy2(ROOT / '工具/compile_book.py', root / '工具/compile_book.py')
            shutil.copy2(ROOT / '数据/城市空间名录.json', root / '数据/城市空间名录.json')
            shutil.copytree(ROOT / '分卷/原稿', root / '分卷/原稿')
            draft = root / '分卷/原稿/08-R011-R020.md'
            draft.write_text(draft.read_text(encoding='utf-8-sig').replace(
                f'人口{population}', f'人口1{population}'), encoding='utf-8')
            result = subprocess.run([sys.executable, str(root / '工具/compile_book.py'), '--audit-only'], capture_output=True)
            report = json.loads((root / '数据/质量核验结果.json').read_text(encoding='utf-8'))
            self.assertTrue(any('R018: population' in error for error in report['errors']))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / '钛湖城城市设定集-完整合订本.md').exists())


class CoverCountTests(unittest.TestCase):
    """封面那行计数是读者唯一会当成全书面包络的数字：四档必须把名录分完，加总等于条目总数。

    来由：2026-11-03 的 Word 渲染目视发现原串写「24 个外围聚落 / 148 项城市空间 / 120 个著名居民区」，
    而 148 只是功能区＋地标，20 个城市片区没进封面；24+148+120=292 与全书 312 条对不上。
    """

    @staticmethod
    def numbers(line):
        return [int(n) for n in re.findall(r'·\s*(\d+)(?:个|项)', line)]

    def setUp(self):
        data = json.loads((ROOT / '数据/城市空间名录.json').read_text(encoding='utf-8'))['entries']
        self.counts = collections.Counter(entry['type'] for entry in data)
        self.total = len(data)
        head = (ROOT / '钛湖城城市设定集-完整合订本.md').read_text(encoding='utf-8').splitlines()[:6]
        self.cover = next(line for line in head if '原创虚构城市正典' in line)

    def test_cover_buckets_partition_the_registry(self):
        expected = [self.counts['产业小镇'] + self.counts['特色村落'], self.counts['城市片区'],
                    self.counts['功能区'] + self.counts['标志性建筑'], self.counts['居民区']]
        got = self.numbers(self.cover)
        self.assertEqual(len(got), 4, self.cover)
        self.assertEqual(got, expected, self.cover)
        self.assertEqual(sum(got), self.total, '封面四档没把名录分完')
        for label in ('村镇', '片区', '功能区与地标', '著名居民区'):
            self.assertIn(label, self.cover)

    def test_docx_cover_enumerates_the_same_four_buckets(self):
        cjs = (ROOT / '工具/export_docx.cjs').read_text(encoding='utf-8')
        line = next(l for l in cjs.splitlines() if '个外围聚落' in l)
        self.assertEqual(line.count('  /  '), 3, line)
        for key in ('产业小镇', '特色村落', '城市片区', '功能区', '标志性建筑', '居民区'):
            self.assertIn("countBy['%s']" % key, cjs, 'docx 封面少了这一类的取数')

    def test_dropping_a_bucket_is_caught(self):
        """违例负测：把片区那一档删回旧写法，加总判据必须落空。"""
        stale = self.cover.replace(' · %d个片区' % self.counts['城市片区'], '')
        self.assertNotEqual(sum(self.numbers(stale)), self.total)
        self.assertEqual(self.numbers(stale), self.numbers(self.cover)[:1] + self.numbers(self.cover)[2:])


if __name__ == '__main__':
    unittest.main()
