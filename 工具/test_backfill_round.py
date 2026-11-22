# -*- coding: utf-8 -*-
"""`backfill_round.py` 的单测：机械回填的六条禁则与两处停手，全部在临时根里跑，不碰真源。

为什么这一支必须有单测（§55.60 待办⑥）：这个脚本写两份真源（清单与备注），而它的禁则全是
「不许把未经复验的图洗成已验收」这一类。判据面（`test_image_assets`）只查回填之后的形态，
查不到「回填这一步本身越权」；越权一旦发生在真源上，代价要下一轮才看得见。

夹具口径：分组、档串、来源句都用 `RX`／`C999未来重投` 这种与历轮无关的名字，
用例只依赖 `ROUNDS`／`PROVENANCE` 的**结构**，不依赖任何一轮的历史事实——将来加轮次不必来改这里。
"""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN = os.path.join(HERE, 'reshoot_campaign_2026_11_06')
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location('backfill_round_under_test',
                                               os.path.join(CAMPAIGN, 'backfill_round.py'))
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)

PREFIX = 'C999未来重投'
SUFFIX = 'C999未来重投-v01'


def png_bytes(tag):
    return b'\x89PNG\r\n\x1a\n' + tag.encode('utf-8')


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as fp:
        return fp.read()


class Base(unittest.TestCase):
    """搭一个最小仓库根：仓外出图目录、仓内图集目录、清单、备注、读数件各就各位。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = os.path.join(self.temp.name, 'repo')
        self.ws = os.path.join(self.temp.name, 'ws')
        os.makedirs(os.path.join(self.root, '数据'))
        os.makedirs(os.path.join(self.ws, 'vibe_images'))
        self.here_bak, self.root_bak = br.HERE, br.ROOT
        self.ws_bak = br.WORKSPACE
        self.man_bak, self.notes_bak, self.gal_bak = br.MANIFEST, br.NOTES, br.GALLERY
        self.rounds_bak, self.prov_bak = dict(br.ROUNDS), dict(br.PROVENANCE)
        self.fix = os.path.join(self.temp.name, 'fixture')
        os.makedirs(self.fix)
        br.HERE = self.fix
        br.ROOT = self.root
        br.WORKSPACE = self.ws
        br.MANIFEST = os.path.join(self.root, '数据', '开图清单.json')
        br.NOTES = os.path.join(self.root, '数据', '开图验收备注.json')
        br.GALLERY = os.path.join(self.root, '数据', '图集')
        br.ROUNDS = dict(br.ROUNDS)
        self.readings_name = 'round_readings_rx_test.json'
        br.ROUNDS['RX'] = {'readings': self.readings_name,
                           'suffix': SUFFIX, 'prefix': PREFIX, 'head': PREFIX + '%s（v01）',
                           'occupy_all': False, 'statuses': ('待复验', '待开图', '已验收')}
        br.PROVENANCE = dict(br.PROVENANCE)
        br.PROVENANCE['RX'] = '执行人：单测夹具；委托来源：本用例；人工目视未执行。'
        self.addCleanup(self.restore)

    def restore(self):
        br.HERE, br.ROOT, br.WORKSPACE = self.here_bak, self.root_bak, self.ws_bak
        br.MANIFEST, br.NOTES, br.GALLERY = self.man_bak, self.notes_bak, self.gal_bak
        br.ROUNDS, br.PROVENANCE = self.rounds_bak, self.prov_bak

    # ---- 夹具构造 -----------------------------------------------------------
    def out_file(self, eid, tag='new', content=None):
        name = '%s-样本一-%s_1799999999999_deadbeef.png' % (eid, PREFIX)
        data = png_bytes(tag) if content is None else content
        with io.open(os.path.join(self.ws, 'vibe_images', name), 'wb') as fp:
            fp.write(data)
        return name, data

    def row(self, eid, name, data, replaced_cell, **over):
        r = {'id': eid, 'file': name, 'sha256_12': hashlib.sha256(data).hexdigest()[:12],
             'dims': '1280x1024', 'bytes': len(data), 'ts_text': '2026-11-22 12:00:00',
             'container': {'cabx': 0, 'itxt': 1}, '逐字相等': True, 'size_match': True,
             '母图相符': True, '投次': 1, '逐字发起数': 1, '非逐字发起数': 0, '登记作废发起数': 0,
             'replaced_cell': replaced_cell}
        r.update(over)
        return r

    def item(self, eid, files, status='待复验', bound=None, prompt_sha=None, typ='片区'):
        return {'id': eid, 'name': '样本一', 'type': typ, 'status': status, 'image_file': files,
                'image_prompt_sha256': bound, 'prompt_sha256': prompt_sha or 'a' * 64,
                'batch': '%s-%s-旧批次' % (typ, eid)}

    def write_face(self, items, notes, rows, only=None, catchup=None):
        with io.open(br.MANIFEST, 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'items': items}, ensure_ascii=False))
        with io.open(br.NOTES, 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'备注': notes}, ensure_ascii=False))
        with io.open(os.path.join(self.fix, self.readings_name), 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'rows': rows}, ensure_ascii=False))
        if only:
            with io.open(os.path.join(self.fix, only[0]), 'w', encoding='utf-8') as fp:
                fp.write(json.dumps(only[1]))
        if catchup:
            with io.open(os.path.join(self.fix, catchup[0]), 'w', encoding='utf-8') as fp:
                fp.write(json.dumps(catchup[1]))
        self.addCleanup(lambda: os.path.exists(os.path.join(self.fix, self.readings_name)) and
                        os.remove(os.path.join(self.fix, self.readings_name)))

    def read(self):
        man = json.loads(_read(br.MANIFEST))
        notes = json.loads(_read(br.NOTES))['备注']
        return {i['id']: i for i in man['items']}, notes

    def gallery(self, name):
        return os.path.join(br.GALLERY, name.split('-')[0], name)


class GreenPath(Base):
    def test_a_replaces_only_the_declared_cell_and_lands_the_file(self):
        name, data = self.out_file('D001')
        old = '数据/图集/D001/D001-样本一-历轮枚_1.png'
        keep = '数据/图集/D001/D001-样本一-另一格_2.png'
        self.write_face([self.item('D001', [old, keep])], {}, [self.row('D001', name, data, old)])
        br.main('RX')
        items, notes = self.read()
        self.assertEqual(items['D001']['image_file'],
                         ['数据/图集/D001/' + name, keep], '占格口径只能动被点名那一格')
        self.assertTrue(os.path.isfile(self.gallery(name)), '判绿枚没请进仓内交付落点＝清单那一格是死链')
        self.assertEqual(len(notes['D001']), 1)
        self.assertIn('替换第1格', notes['D001'][0])
        self.assertIn('人工目视未执行', notes['D001'][0])
        self.assertEqual(items['D001']['batch'], '片区-D001' + SUFFIX)

    def test_b_red_rows_never_take_a_slot_or_write_a_note(self):
        name, data = self.out_file('D002')
        old = '数据/图集/D002/D002-样本一-历轮枚_1.png'
        rows = [self.row('D002', name, data, old, 逐字相等=False),
                self.row('D003', name, data, old, size_match=False),
                self.row('D004', name, data, old, 母图相符=False),
                self.row('D005', name, data, old, container={'cabx': 0, 'itxt': 0})]
        self.write_face([self.item(e, [old]) for e in ('D002', 'D003', 'D004', 'D005')], {}, rows)
        br.main('RX')
        items, notes = self.read()
        for eid in ('D002', 'D003', 'D004', 'D005'):
            self.assertEqual(items[eid]['image_file'], [old], eid + ' 判红却占了格')
            self.assertEqual(notes.get(eid, []), [], eid + ' 判红却写了备注')
            self.assertFalse(os.path.isfile(self.gallery(name)), eid + ' 判红却被请进仓内')

    def test_c_script_never_signs_or_rebinds(self):
        """绑定摘要与状态是人工验收面：脚本一律不写、不撤、不改（唯一例外是零图条目的挪记）。"""
        name, data = self.out_file('D006')
        old = '数据/图集/D006/D006-样本一-历轮枚_1.png'
        self.write_face([self.item('D006', [old], status='待复验', bound=None)], {},
                        [self.row('D006', name, data, old)])
        br.main('RX')
        items, _n = self.read()
        self.assertIsNone(items['D006']['image_prompt_sha256'], '脚本代写了绑定摘要')
        self.assertEqual(items['D006']['status'], '待复验', '非零图条目的状态被动过')


class ZeroCellAndBindings(Base):
    def test_d_first_slot_moves_pending_shoot_into_review_without_signing(self):
        name, data = self.out_file('D007')
        self.write_face([self.item('D007', [], status='待开图')], {},
                        [self.row('D007', name, data, None)])
        br.main('RX')
        items, notes = self.read()
        self.assertEqual(items['D007']['image_file'], ['数据/图集/D007/' + name])
        self.assertEqual(items['D007']['status'], '待复验', '零图条目拿到本轮枚还留在待开图＝状态面没跟上')
        self.assertIn('本条此前无格为首占第1格', notes['D007'][0])
        self.assertIn('挪状态只是把它送进复验队列，不是验收', notes['D007'][0])
        self.assertIn('新增首格', notes['D007'][0])

    def test_e_binding_buckets_are_spelled_out_separately(self):
        """绑的是串不是格：串没变就写「未过期」，变了就写「已过期、重绑归人工」，两档不许混成一句。"""
        same, data1 = self.out_file('D008', tag='a')
        stale, data2 = self.out_file('D009', tag='b')
        sha = 'b' * 64
        self.write_face([self.item('D008', ['x/旧8'], status='待复验', bound=sha, prompt_sha=sha),
                         self.item('D009', ['y/旧9'], status='待复验', bound=sha, prompt_sha='c' * 64)],
                        {}, [self.row('D008', same, data1, 'x/旧8'), self.row('D009', stale, data2, 'y/旧9')])
        br.ROUNDS['RX'] = dict(br.ROUNDS['RX'], occupy_all=True)
        br.main('RX')
        _items, notes = self.read()
        self.assertIn('串未变则摘要未过期', notes['D008'][0])
        self.assertNotIn('摘要已过期', notes['D008'][0])
        self.assertIn('已过期', notes['D009'][0])
        self.assertNotIn('未过期', notes['D009'][0])
        self.assertIn('重绑或撤销归人工', notes['D009'][0])

    def test_f_occupy_all_false_stops_when_a_binding_exists(self):
        name, data = self.out_file('D010')
        sha = 'd' * 64
        self.write_face([self.item('D010', ['z/旧10'], bound=sha, prompt_sha='e' * 64)], {},
                        [self.row('D010', name, data, 'z/旧10')])
        with self.assertRaises(AssertionError) as ctx:
            br.main('RX')
        self.assertIn('全部占格', str(ctx.exception))
        _items, notes = self.read()
        self.assertEqual(notes.get('D010', []), [], '停手那一条不该已经写过备注')


class StopConditions(Base):
    def test_g_manifest_touched_elsewhere_stops(self):
        """replaced_cell 与本轮新格恰有其一才继续：同在或同不在都说明清单被别处动过。"""
        name, data = self.out_file('D011')
        old = '数据/图集/D011/D011-样本一-历轮枚_1.png'
        both = [old, '数据/图集/D011/' + name]
        self.write_face([self.item('D011', both)], {}, [self.row('D011', name, data, old)])
        with self.assertRaises(AssertionError) as ctx:
            br.main('RX')
        self.assertIn('清单被别处动过', str(ctx.exception))

    def test_h_changed_head_stops(self):
        name, data = self.out_file('D012')
        old = '数据/图集/D012/D012-样本一-历轮枚_1.png'
        prev = PREFIX + 'D012（v01）投后机械对账读数（数据/图集/D012/别的形态，替换第2格 旧格，1280x1024，1字节；x）：旧正文'
        self.write_face([self.item('D012', [old])], {'D012': [prev]},
                        [self.row('D012', name, data, old)])
        with self.assertRaises(AssertionError) as ctx:
            br.main('RX')
        self.assertIn('抬头变了', str(ctx.exception))

    def test_i_status_outside_the_round_scope_stops(self):
        name, data = self.out_file('D013')
        br.ROUNDS['RX'] = dict(br.ROUNDS['RX'], statuses=('待复验',))
        self.write_face([self.item('D013', ['q/旧13'], status='已验收')], {},
                        [self.row('D013', name, data, 'q/旧13')])
        with self.assertRaises(AssertionError) as ctx:
            br.main('RX')
        self.assertIn('不在本组回填口径', str(ctx.exception))

    def test_j_byte_mismatch_with_an_existing_in_repo_copy_stops(self):
        """仓内同名件与仓外原件字节不同＝盘面被动过，停手而不是覆盖。"""
        name, _data = self.out_file('D014')
        os.makedirs(os.path.join(br.GALLERY, 'D014'))
        with io.open(self.gallery(name), 'wb') as fp:
            fp.write(png_bytes('different'))
        old = '数据/图集/D014/D014-样本一-历轮枚_1.png'
        self.write_face([self.item('D014', [old])], {},
                        [self.row('D014', name, png_bytes('different'), old)])
        with self.assertRaises(AssertionError) as ctx:
            br.main('RX')
        self.assertIn('字节不同', str(ctx.exception))

    def test_k_reuses_the_previous_landing_instead_of_double_claiming_disk(self):
        """上一档落点（仓内 vibe_images/）已有同名原件时：校验后挪进图集目录，不重复占盘。"""
        name, data = self.out_file('D015')
        legacy_dir = os.path.join(self.root, 'vibe_images')
        os.makedirs(legacy_dir)
        with io.open(os.path.join(legacy_dir, name), 'wb') as fp:
            fp.write(data)
        old = '数据/图集/D015/D015-样本一-历轮枚_1.png'
        self.write_face([self.item('D015', [old])], {}, [self.row('D015', name, data, old)])
        br.main('RX')
        self.assertTrue(os.path.isfile(self.gallery(name)), '旧落点的件没被挪进交付落点')
        self.assertFalse(os.path.exists(os.path.join(legacy_dir, name)), '挪家后旧落点还留着＝同一枚占两份盘')


class Idempotency(Base):
    def test_l_second_run_rewrites_the_same_head(self):
        name, data = self.out_file('D016')
        old = '数据/图集/D016/D016-样本一-历轮枚_1.png'
        items = [self.item('D016', [old])]
        rows = [self.row('D016', name, data, old)]
        self.write_face(items, {}, rows)
        br.main('RX')
        first_items, first_notes = self.read()
        br.main('RX')
        _items, notes = self.read()
        self.assertEqual(len(notes['D016']), 1, '同抬头再跑一次必须改写而不是追加')
        self.assertEqual(notes['D016'], first_notes['D016'])
        self.assertEqual(_items['D016']['image_file'], first_items['D016']['image_file'],
                         '重跑把已回填那一格又顶了一次＝格数或格位漂了')

    def test_m_only_restricts_the_scope(self):
        """--only 把范围收到一份台账的键面：读数里的另一条不该被本轮的委托原句顶掉历史正文。"""
        n1, d1 = self.out_file('D017', tag='1')
        n2, d2 = self.out_file('D018', tag='2')
        old = '数据/图集/D017/D017-样本一-历轮枚_1.png'
        rows = [self.row('D017', n1, d1, old), self.row('D018', n2, d2, '数据/图集/D018/旧18')]
        self.write_face([self.item('D017', [old]), self.item('D018', ['数据/图集/D018/旧18'])], {}, rows,
                        only=('only_rx_test.json', ['D017']))
        br.main('RX', 'only_rx_test.json')
        _items, notes = self.read()
        self.assertIn('D017', notes)
        self.assertEqual(notes.get('D018', []), [], '范围外的条目被本轮重打了')
        self.assertTrue(os.path.isfile(self.gallery(n1)))
        self.assertFalse(os.path.isfile(self.gallery(n2)))


if __name__ == '__main__':
    unittest.main()
