import json
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

    def test_all_current_entries_have_matching_labeled_parameters(self):
        self.assertEqual(len(self.drafts), 264)
        for eid, body in self.drafts.items():
            with self.subTest(eid=eid):
                self.assertEqual(self.issues(eid, body), [])

    def test_population_cannot_match_digits_inside_a_larger_number(self):
        body = self.drafts['R018'].replace('4400', '14400')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_unrelated_correct_number_cannot_rescue_wrong_population(self):
        body = self.drafts['R018'].replace('4400', '14400') + '\n铺装4400平方米。'
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_decimal_suffix_cannot_match_population(self):
        body = self.drafts['R018'].replace('4400', '4400.5')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_households_are_required_even_when_number_occurs_elsewhere(self):
        body = self.drafts['R018'].replace('1796户', '1796平方米')
        self.assertTrue(any('households' in issue for issue in self.issues('R018', body)))

    def test_floor_area_requires_square_meters(self):
        body = self.drafts['R018'].replace('224600平方米', '224600米')
        self.assertTrue(any('gross_floor_area_m2' in issue for issue in self.issues('R018', body)))

    def test_land_area_is_not_a_rounded_or_unrelated_number(self):
        body = self.drafts['R018'].replace('0.21平方公里', '0.2平方公里') + '\n机位参数0.21。'
        self.assertTrue(any('area_km2' in issue for issue in self.issues('R018', body)))

    def test_conflicting_population_claim_is_not_rescued_by_correct_claim(self):
        body = self.drafts['R018'].replace('人口4400', '人口14400')
        body = body.replace('**人群与生活节奏**：', '**人群与生活节奏**：常住4400人。')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_building_height_cannot_be_supplied_by_camera_height(self):
        body = self.drafts['L001'].replace('高32米', '高132米').replace('6层32米', '6层132米')
        body += '\n相机离地32米。'
        self.assertTrue(any('height_m' in issue for issue in self.issues('L001', body)))

    def test_lock_only_floor_and_height_conflicts_are_rejected(self):
        for before, after, field in [('6层32米', '16层32米', 'floors'), ('6层32米', '6层132米', 'height_m')]:
            with self.subTest(field=field):
                original = self.drafts['L001']
                self.assertEqual(original.count(before), 1)
                body = original.replace(before, after)
                self.assertTrue(any(field in issue for issue in self.issues('L001', body)))

    def test_lock_only_prohibited_height_conflict_is_rejected(self):
        original = self.drafts['R016']
        self.assertEqual(original.count('禁止超33米'), 1)
        body = original.replace('禁止超33米', '禁止超133米')
        self.assertTrue(any('height_limit_m' in issue for issue in self.issues('R016', body)))

    def test_population_with_explicit_wrong_unit_is_rejected(self):
        original = self.drafts['R018']
        self.assertEqual(original.count('人口4400、'), 1)
        body = original.replace('人口4400、', '人口4400平方米、')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_distance_sign_and_grouped_digits_are_not_discarded(self):
        original = self.drafts['R018']
        self.assertEqual(original.count('1.58千米'), 1)
        for wrong in ('-1.58千米', '1,001.58千米'):
            with self.subTest(wrong=wrong):
                body = original.replace('1.58千米', wrong)
                self.assertTrue(any('geometry gives' in issue for issue in self.issues('R018', body)))

    def test_person_visits_are_not_resident_population(self):
        original = self.drafts['R018']
        self.assertEqual(original.count('人口4400、'), 1)
        body = original.replace('人口4400、', '人口4400人次、')
        self.assertTrue(any('population' in issue for issue in self.issues('R018', body)))

    def test_grouped_thousands_remain_valid(self):
        body = self.drafts['R018'].replace('4400', '4,400').replace('224600', '224,600').replace('1796', '1,796')
        self.assertEqual(self.issues('R018', body), [])

    def test_audit_command_returns_failure_when_population_is_wrong(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '工具').mkdir()
            (root / '数据').mkdir()
            shutil.copy2(ROOT / '工具/compile_book.py', root / '工具/compile_book.py')
            shutil.copy2(ROOT / '数据/城市空间名录.json', root / '数据/城市空间名录.json')
            shutil.copytree(ROOT / '分卷/原稿', root / '分卷/原稿')
            draft = root / '分卷/原稿/06-R011-R020.md'
            draft.write_text(draft.read_text(encoding='utf-8-sig').replace('人口4400', '人口14400'), encoding='utf-8')
            result = subprocess.run([sys.executable, str(root / '工具/compile_book.py'), '--audit-only'], capture_output=True)
            report = json.loads((root / '数据/质量核验结果.json').read_text(encoding='utf-8'))
            self.assertTrue(any('R018: population' in error for error in report['errors']))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / '钛湖城城市设定集-完整合订本.md').exists())


if __name__ == '__main__':
    unittest.main()
