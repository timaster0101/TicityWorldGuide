"""阶段 2-B 高度阶梯的机器不变量。

分档读数、抬升名单、体量守恒与山外低限钉在这里。两张表从 工具/build_registry.py 的源码
用 ast 取，不能用 import——那个脚本在被守护的名录已存在时会直接 SystemExit。
"""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GFA = (68000, 41000, 39000)
DEFAULT_PLOT = (.042, .036, .018)


def source_table(name):
    tree = ast.parse((ROOT / '工具/build_registry.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('build_registry.py 里找不到常量 ' + name)


def registry():
    data = json.loads((ROOT / '数据/城市空间名录.json').read_text(encoding='utf-8'))
    entries = data['entries'] if isinstance(data, dict) and 'entries' in data else data
    return {entry['id']: entry for entry in entries}


def tier(height):
    for floor, name in ((400, '400+'), (300, '300-399'), (200, '200-299'),
                        (150, '150-199'), (100, '100-149'), (60, '60-99')):
        if height >= floor:
            return name
    return '<60'


class HeightLadderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = registry()
        cls.landmarks = {k: v for k, v in cls.entries.items() if k.startswith('L')}
        cls.residences = {k: v for k, v in cls.entries.items() if k.startswith('R')}
        cls.raise_table = source_table('MID_RISE_BY_ID')
        cls.limit_table = source_table('RES_RISE_BY_ID')
        cls.tiers = {}
        for entry in cls.landmarks.values():
            cls.tiers[tier(entry['height_m'])] = cls.tiers.get(tier(entry['height_m']), 0) + 1

    def test_height_bands_after_the_retiering(self):
        self.assertEqual(
            self.tiers,
            {'400+': 1, '300-399': 3, '200-299': 16, '150-199': 12,
             '100-149': 18, '60-99': 40, '<60': 18})
        self.assertEqual(sum(self.tiers.values()), len(self.landmarks))

    def test_sixty_to_ninety_band_is_the_table_plus_the_one_special_it_cannot_touch(self):
        band = {k for k, v in self.landmarks.items() if 60 <= v['height_m'] < 100}
        self.assertEqual(band - set(self.raise_table), {'L013'},
                         '60—99 档里出现了表外条目：要么有人手改了原稿或名录，要么特例链被抬升表盖掉')
        self.assertEqual(self.landmarks['L013']['name'], '青湾中央医院')
        self.assertEqual((self.landmarks['L013']['height_m'], self.landmarks['L013']['floors']), (78, 18))

    def test_raise_table_moves_only_height_and_floors(self):
        for eid, (height, floors) in self.raise_table.items():
            entry = self.landmarks[eid]
            with self.subTest(eid=eid):
                self.assertEqual((entry['height_m'], entry['floors']), (height, floors))
                self.assertIn(entry['area_km2'], DEFAULT_PLOT, '用地被连带改动，FAR 会漂')
                self.assertIn(entry['gross_floor_area_m2'], DEFAULT_GFA, '总建面被连带改动，成熟度会漂')
                self.assertTrue(4.0 <= entry['height_m'] / entry['floors'] <= 4.8)

    def test_the_top_of_the_skyline_is_untouched_by_the_band(self):
        self.assertNotIn('L007', self.raise_table)
        self.assertEqual((self.landmarks['L007']['height_m'], self.landmarks['L007']['floors']), (368, 78))
        self.assertEqual(self.landmarks['L066']['height_m'], 458)
        self.assertGreater(self.landmarks['L066']['height_m'] - self.landmarks['L007']['height_m'], 60)

    def test_tall_residential_limits_are_nine_raised_plus_two_that_already_were(self):
        tall = {k for k, v in self.residences.items() if v['height_limit_m'] >= 90}
        self.assertEqual(tall - set(self.limit_table), {'R093', 'R096'})
        self.assertEqual({self.residences[k]['parent'] for k in self.limit_table},
                         {'D03', 'D04', 'D05', 'D09'})
        for eid, limit in self.limit_table.items():
            self.assertEqual(self.residences[eid]['height_limit_m'], limit)
            self.assertLessEqual(limit, 180, '居民区限高不得超过 2-C 定档的 180 米')

    def test_low_band_stays_the_majority(self):
        self.assertGreaterEqual(sum(1 for v in self.residences.values()
                                    if v['height_limit_m'] < 60), 85)
        self.assertLessEqual(max(v['height_limit_m'] for k, v in self.residences.items()
                                 if k not in self.limit_table), 90)

    def test_towns_and_villages_keep_their_low_limits(self):
        limits = {}
        for entry in self.entries.values():
            if entry['type'] in ('产业小镇', '特色村落'):
                limits.setdefault(entry['type'], set()).add(entry['height_limit_m'])
        self.assertEqual(limits, {'产业小镇': {36}, '特色村落': {15}})


if __name__ == '__main__':
    unittest.main()
