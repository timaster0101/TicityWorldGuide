# -*- coding: utf-8 -*-
"""`current_cells.py` 的单测：在册格取法按行种派生，不写死轮次、不靠位置取末行。

这个模块原先没有单测（§55.60 待办⑥），而它是画风读数面与覆盖面对拍的共同真源——
它一漂，两处一起漂，且漂成「少读若干枚」这种不报错的形态。下面的用例按那三条历史事故排位：
按位置取末行（人工结论行也会追加到末尾）、按档串字面量筛（回填一轮就塌一次）、
按读数里的历史路径取文件（交付落点搬过三次家）。
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location(
    'current_cells_under_test', os.path.join(HERE, 'reshoot_campaign_2026_11_06', 'current_cells.py'))
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


def fname(eid, tok='C154取景补重投', sub='new'):
    """真实交付件形态：档串在文件名里，带毫秒戳与摘要后缀，current_cells 的档串抽取靠这个形态。"""
    return '%s-样本一-%s-v01_1799999999999_%s.png' % (eid, tok, sub)


def head(eid, path, tok='C154取景补重投', v='v01'):
    """造一条占格读数行：抬头形态就是 backfill_round 写进备注的那一句。"""
    return '%s%s（%s）投后机械对账读数（%s，替换第1格 旧格，1280x1024，1字节）：机械对账项。' % (tok, eid, v, path)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        os.makedirs(os.path.join(self.root, '数据', '图集', 'A001'))
        os.makedirs(os.path.join(self.root, '数据', '图集', 'A002'))
        with io.open(os.path.join(self.root, '数据', '图集', 'A001', fname('A001')), 'wb') as fp:
            fp.write(b'x')

    def build(self, items, notes):
        with io.open(os.path.join(self.root, '数据', '开图清单.json'), 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'items': items}, ensure_ascii=False))
        with io.open(os.path.join(self.root, '数据', '开图验收备注.json'), 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'备注': notes}, ensure_ascii=False))

    def take(self):
        return cc.current_cells(self.root)


class CellIsTheLastReadingNotTheLastLine(Fixture):
    def test_a_trailing_manual_lines_do_not_move_the_cell(self):
        """复看补写与人工结论行也往末尾追加：按 rows[-1] 取会把「这格在盘」读成「最新那行是读数」。"""
        self.build([{'id': 'A001', 'name': '样本一', 'status': '待复验',
                     'image_file': ['数据/图集/A001/' + fname('A001')]}],
                   {'A001': [head('A001', '数据/图集/A001/' + fname('A001')),
                             '2026-11-22 目视结论：画风达标。',
                             '2026-11-22 复看补写：远景另记。']})
        _q, rows, excluded = self.take()
        self.assertEqual(excluded, [])
        self.assertEqual([r['id'] for r in rows], ['A001'])
        self.assertTrue(rows[0]['cell'].endswith('_new.png'))

    def test_b_the_latest_round_wins_without_a_token_list(self):
        """档串名单不写死：未来那一轮的回填行进来，取法自己跟进，不许漏改硬筛。"""
        self.build([{'id': 'A001', 'name': '样本一', 'status': '待复验',
                     'image_file': ['数据/图集/A001/' + fname('A001')]}],
                   {'A001': [head('A001', '数据/图集/A001/' + fname('A001', tok='C154母图重投', sub='old'), tok='C154母图重投'),
                             head('A001', '数据/图集/A001/' + fname('A001'), tok='C199未来重投')]})
        _q, rows, excluded = self.take()
        self.assertEqual(excluded, [])
        self.assertTrue(rows[0]['cell'].endswith('_new.png'), '取到的还是上一轮的格＝档串被写死了')

    def test_c_reading_path_and_delivered_path_are_separate_fields(self):
        """交付落点搬过家：读数里那条路径是历史事实，读取一律走清单登记的在册路径。"""
        self.build([{'id': 'A001', 'name': '样本一', 'status': '待复验',
                     'image_file': ['数据/图集/A001/' + fname('A001')]}],
                   {'A001': [head('A001', 'backup/镜像/旧落点/' + fname('A001'))]})
        _q, rows, excluded = self.take()
        self.assertEqual(excluded, [], '按历史路径取不到就该走清单路径，这一条正是那次判红的修法')
        self.assertEqual(rows[0]['读数路径'], 'backup/镜像/旧落点/' + fname('A001'))
        self.assertTrue(rows[0]['path'].endswith(os.path.join('数据', '图集', 'A001', fname('A001'))))
        self.assertTrue(rows[0]['在盘'], 'path 指向清单在册路径，件在盘就该判在盘')


class ExclusionsSayWhy(Fixture):
    def test_d_no_reading_row_is_excluded_with_reason(self):
        self.build([{'id': 'A002', 'name': '样本二', 'status': '待开图', 'image_file': []}],
                   {'A002': ['2026-11-22 目视结论：本条此前无图。']})
        _q, rows, excluded = self.take()
        self.assertEqual(rows, [])
        self.assertEqual(excluded[0]['原因'], '备注里查不到任何一条占格读数')

    def test_e_cell_named_by_the_reading_is_not_in_the_manifest(self):
        """清单被别处动过（格被删或换名）必须显式排除，不许从别处凑一枚顶上。"""
        self.build([{'id': 'A002', 'name': '样本二', 'status': '待复验',
                     'image_file': ['数据/图集/A002/' + fname('A002', sub='other')]}],
                   {'A002': [head('A002', '数据/图集/A002/' + fname('A002', sub='named'))]})
        _q, rows, excluded = self.take()
        self.assertEqual(rows, [])
        self.assertEqual(excluded[0]['原因'], '最后一条占格读数点名的格不在清单在册格里')

    def test_f_a_single_string_image_file_is_still_one_cell(self):
        self.build([{'id': 'A001', 'name': '样本一', 'status': '待复验',
                     'image_file': '数据/图集/A001/' + fname('A001')}],
                   {'A001': [head('A001', '数据/图集/A001/' + fname('A001'))]})
        _q, rows, excluded = self.take()
        self.assertEqual(excluded, [], 'image_file 写成单串就不认＝覆盖面按字段形态缩水')

    def test_g_missing_on_disk_is_reported_not_hidden(self):
        self.build([{'id': 'A002', 'name': '样本二', 'status': '待复验',
                     'image_file': ['数据/图集/A002/' + fname('A002', sub='gone')]}],
                   {'A002': [head('A002', '数据/图集/A002/' + fname('A002', sub='gone'))]})
        _q, rows, excluded = self.take()
        self.assertEqual(excluded, [], '在盘与否是读数，不是排除理由')
        self.assertIs(rows[0]['在盘'], False)


class RepoFace(unittest.TestCase):
    def test_h_real_manifest_resolves_every_item(self):
        """真源面：一条都不许落进空集，档串分布只从备注派生。"""
        _q, rows, excluded = cc.current_cells(ROOT)
        self.assertEqual(excluded, [], '有 ID 取不到在册格 %s' % excluded[:3])
        self.assertEqual(len(rows), len(_q['items']))
        self.assertTrue(all(r['档串'] for r in rows), '档串为空说明文件名形态变了')
        self.assertEqual(sum(1 for r in rows if not r['在盘']), 0, '有在册格不在盘')

    def test_i_rule_text_does_not_pin_a_round_list(self):
        import re
        self.assertNotIn('C154', cc.RULE_TEXT, '取法口径句里又抄了一份档串名单＝下一轮还要来改这里')
        self.assertIsNone(re.search(r'R\d', cc.RULE_TEXT))


if __name__ == '__main__':
    unittest.main()
