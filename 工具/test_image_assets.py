# -*- coding: utf-8 -*-
"""开图图片资产核验回归。只读已落盘产物与真实图集，不生成、不修改任何图片。

跑法：python 工具/test_image_assets.py（工作目录＝设定集根）
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))


class ReviewNoteHistory(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.items = {i['id']: i for i in self.manifest['items']}
        self.notes = json.loads((ROOT / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))['备注']

    # 第3期从 git 809ed08 找回的 4 条长文本；C97 后追加 4 条回填备注（D03／D08／S02／S18）；
    # C105／C106 换档后子批①②的 7 张重出各记一条打表（L066／L083／F012／F039／R009，S02／S18 是第二条）。
    RECOVERED = ('D01', 'L007', 'L008', 'R043')
    BACKFILLED = ('D03', 'D08', 'S02', 'S18')
    RESHOT = ('L066', 'L083', 'F012', 'F039', 'R009')
    # 子批③夜光批四条：R038 用真源串出图并回填，R053／R086 的达标图出自串外试投、只记打表，
    # S23 旧串两赌用尽判废（C109／C110 新串 v03 达标后回填第 5 格，见待办清单 §18）。
    VARIANT = ('S23', 'R038', 'R053', 'R086')
    # 子批③清晨批四条：全部出在 C107 换串之后，输入即当前真源串，故四张都允许回填第 5 格。
    # 夜光批只有 R038 一张回填（另三条串外或判废），清晨批四条一起进——这正是 C107 落进生成器的兑现。
    MORNING = ('L033', 'R076', 'R090', 'R098')
    # 子批③雨后批七条：R006／R063／R066／R116 四张在真源串上达标并回填；R015 的 v02 达标但串外
    # （tail 多了一句），R034 与 R054 旧串两赌用尽（右下角地面字母形签名、日面不可纳）。
    # C109／C110 新串重出后 R015／R034 达标回填，R054 仍因日面入画判废、不占格。
    RAIN = ('R006', 'R015', 'R034', 'R054', 'R063', 'R066', 'R116')
    # 子批③晴日批一条：v01 因投放时把「人群段」误写成「人群档」属串外，达标不回填；
    # v02 按当前真源串逐字重出后达标回填。同一条ID的两版只有一版能占格，这是串绑定的本意。
    SUNNY = ('R092',)
    # 只有目视十项达标的才允许追加图格；判废与待复验的只记打表，不占 image_file。
    APPENDED = {'D03': 5, 'D08': 5, 'S02': 6, 'S18': 6, 'R009': 5, 'R038': 5,
                'L033': 5, 'R076': 5, 'R090': 5, 'R098': 5,
                'R006': 5, 'R063': 5, 'R066': 5, 'R116': 5, 'R092': 5,
                'R015': 5, 'R034': 5, 'S23': 5}

    def test_four_long_notes_recovered(self):
        self.assertEqual(sorted(self.notes),
                         sorted(self.RECOVERED + self.BACKFILLED + self.RESHOT + self.VARIANT
                                + self.MORNING + self.RAIN + self.SUNNY))
        # 本轮实测：809ed08 的原始长度 518/226/231/151，各带一条同文派生原因，剥净后如下
        self.assertEqual({k: len(v[0]) for k, v in self.notes.items() if k in self.RECOVERED},
                         {'D01': 204, 'L007': 491, 'L008': 199, 'R043': 124})
        for eid, rows in self.notes.items():
            self.assertTrue(all(r.strip() for r in rows), eid)
            self.assertNotIn('图片对应的基准提示词已变化', rows[-1], f'{eid} 手工源里混入了派生原因')

    def test_backfill_notes_name_the_appended_cell_and_refuse_to_sign(self):
        """回填批次必须自带出处：文件名、容器口径、目视判读与「不代签」四要素缺一，
        下一轮就查不到这格图是哪一批、按哪条裁定计进来的。"""
        for eid, cells in self.APPENDED.items():
            with self.subTest(eid=eid):
                row = self.notes[eid][-1]
                self.assertIn('vibe_images/', row)
                self.assertIn('C97', row)
                self.assertIn('待复验', row)
                self.assertIn('不代签验收', row)
                item = self.items[eid]
                self.assertEqual(len(item['image_file']), cells, eid)
                self.assertTrue(item['image_file'][-1].startswith('vibe_images/'), eid)
                self.assertIn(item['image_file'][-1], row, eid)
                self.assertEqual(item['status'], '待复验', eid)
                self.assertFalse(item.get('image_prompt_sha256'), '%s 已绑定摘要，不该再追加格' % eid)

    def test_rejected_and_borderline_rereads_name_the_file_but_take_no_cell(self):
        """子批①里判废与待复验的四条只留打表、不占 image_file；子批③的 R053／R086 同口径——
        图是串外试投出的，回填等于把未经当前真源串复验的图洗成该串产物。
        C109／C110 新串重出的 R054 也进这一组：判达标与否只看人工读数，判废就不占格，换串不改变这条。
        一旦让这类图也追加格，「有图＝生成过」的口径就会把废图混进交付面。"""
        expect = {'L066': ('待开图', 0), 'L083': ('待开图', 0), 'F012': ('待复验', 4), 'F039': ('待复验', 4),
                  'R053': ('待复验', 4), 'R086': ('待复验', 4), 'R054': ('待复验', 4)}
        for eid, (status, cells) in expect.items():
            with self.subTest(eid=eid):
                row = self.notes[eid][-1]
                self.assertIn('vibe_images/', row)
                self.assertIn('不回填', row)
                item = self.items[eid]
                self.assertNotIn('vibe_images/', json.dumps(item['image_file'], ensure_ascii=False), eid)
                self.assertEqual(item['status'], status, eid)
                got = item['image_file']
                self.assertEqual(len(got) if isinstance(got, list) else (1 if got else 0), cells, eid)

    def test_history_survives_and_note_still_derives(self):
        # 308 条没有人工长文本，历史是空数组：判"键在不在"而不是"值真不真"；键随名录扩到312条
        self.assertEqual(sum(1 for i in self.items.values() if 'review_note_history' in i), 312)
        self.assertEqual(sum(1 for i in self.items.values() if i['review_note_history']), 29)
        for eid in self.RECOVERED + self.BACKFILLED + self.RESHOT + self.VARIANT + self.MORNING \
                + self.RAIN + self.SUNNY:
            hist = self.items[eid]['review_note_history']
            self.assertEqual(hist, self.notes[eid], eid)
            self.assertIn(self.notes[eid][-1], self.items[eid]['review_note'])
        self.assertEqual(self.manifest['needs_review'], 264)
        self.assertEqual(self.manifest['accepted'], 0)
        self.assertEqual(self.manifest['generated'], 264)
        # 阶段2 名录扩容的48条地标只进队列不出图：generated/needs_review 仍按有图的264条计，pending 单独承担新增。
        self.assertEqual(self.manifest['pending'], 48)


def jpeg(segments):
    """按 marker＋body 拼一段合法 JPEG：size 字段＝2＋body 长度，含 size 自身。
    夹具里的段长必须由这个函数算出来，不能手写常数——手写 40／56 会让核验器在长度不符时
    提前 break，把「XMP 缺 TC260」误判成「缺XMP段」，测的就不是那条判据了。"""
    body = b'\xff\xd8'
    for marker, payload in segments:
        body += marker + (len(payload) + 2).to_bytes(2, 'big') + payload
    return body + b'\xff\xd9'


def write_jpeg(name, segments):
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / name).write_bytes(jpeg(segments))
    return tmp


XMP_NS = b'http://ns.adobe.com/xap/1.0/\x00'


def png(caBX_payload=None, ihdr=True):
    """拼一个真 PNG 外壳：IHDR＋可选 caBX＋IEND。块长度字段必须实算，
    写死常数会让核验器在长度不符时提前退出，测的就不是 caBX 那条判据了。"""
    out = b'\x89PNG\r\n\x1a\n'
    if ihdr:
        out += _chunk(b'IHDR', bytes(13))
    if caBX_payload is not None:
        out += _chunk(b'caBX', caBX_payload)
    return out + _chunk(b'IEND', b'')


def _chunk(kind, payload):
    body = kind + payload
    import zlib
    return len(payload).to_bytes(4, 'big') + body + \
        zlib.crc32(body).to_bytes(4, 'big')


def write_png(name, caBX_payload=None):
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / name).write_bytes(png(caBX_payload))
    return tmp


class AssetGate(unittest.TestCase):
    def setUp(self):
        import verify_image_assets as va
        self.va = va
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.report = json.loads((ROOT / '数据' / '图片资产核验.json').read_text(encoding='utf-8'))

    def test_paths_are_authoritative_and_unique(self):
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']]
        self.assertEqual(len(paths), 1076)
        self.assertEqual(len(set(paths)), 1076)
        self.assertEqual(sum(1 for i in self.manifest['items'] if i.get('image_file')), 264)

    def test_report_all_green_and_disclaims(self):
        self.assertEqual(self.report['文件格数'], 1076)
        self.assertEqual(self.report['失败格数'], 0)
        self.assertEqual(self.report['通过格数'], 1076)
        # 回填的 E1 批次格必须真按 C2PA 容器计入，否则「认容器是识别」只写在裁定里、查不到证据。
        # 20 格 = 阶段6首批 4 格（D03／D08／S02／S18）＋子批①②的 R009＋夜光批 R038＋清晨批四条＋雨后批 R006／R063／R066／R116
        # ＋晴日批 R092＋C109／C110 新串重出的 R015／R034／S23。
        self.assertEqual(self.report['C2PA在位格数'], 20)
        self.assertNotIn('已验收', json.dumps(self.report, ensure_ascii=False))
        self.assertIn('结构合规不等于视觉验收', self.report['声明'])

    def test_c2pa_absent_on_gallery_is_expected_not_failure(self):
        # 图集那批只写 XMP·TC260，C2PA 缺位不判红也不催办；容器计数要与逐格结论对得上，不能各报各的。
        self.assertEqual(self.report['C2PA在位格数'], self.report['容器计数']['C2PA(caBX)'])
        self.assertEqual(self.report['容器计数']['XMP·TC260'] + self.report['容器计数']['C2PA(caBX)'],
                         self.report['通过格数'])

    def test_two_containers_are_the_delivery_criterion(self):
        # C97 口径：JPEG 走 XMP·TC260，PNG 走 caBX·C2PA；C83 的「不属交付判据」只对 JPEG 侧成立，
        # 这句必须在核验产物里写清，否则下一轮又会把 PNG 判成不合规或把 JPEG 放松。
        for token in ('两条被接受的标识容器（C97）', '不放松原 JPEG 路径'):
            self.assertIn(token, self.report['判据'])
        for token in ('C83', 'C97', '不得由脚本给图片补写元数据过闸'):
            self.assertIn(token, self.report['C2PA口径'])
        self.assertIn('只记提示、不判红', self.report['提示口径'])
        self.assertNotIn('本期不改名', self.report['提示口径'])
        self.assertIn('rename_gallery_ext', self.report['提示口径'])

    def test_extension_mismatch_is_advisory(self):
        # 判据行为本身：字节对、元数据全，只扩展名不符 → 通过但记提示，绝不判红
        tmp = write_jpeg('真JPEG假扩展名.png', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260 AIGC</x:xmpmeta>')])
        got = self.va.check([{'id': 'X007', 'image_file': ['真JPEG假扩展名.png']}], root=tmp)
        self.assertEqual((got['通过格数'], got['失败格数'], got['提示格数']), (1, 0, 1))
        self.assertIn('扩展名', self.report['提示口径'])

    def test_gallery_extension_is_normalised(self):
        self.assertEqual(self.report['提示格数'], 0)
        self.assertEqual(self.report['失败格数'], 0)
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']]
        self.assertEqual(len(paths), 1076)
        # C82 的归一只管 数据/图集/ 那批；E1 放量批次与 C105／C106 重出批次（C97 起认 caBX·C2PA 容器）
        # 是真 PNG，按字节与容器引用，不改名也不要求它变成 .jpg。图集外 20 格全部是 caBX·C2PA 容器。
        gallery = [p for p in paths if p.startswith('数据/图集/')]
        out_of_gallery = [p for p in paths if not p.startswith('数据/图集/')]
        self.assertEqual(len(gallery), 1056)
        self.assertEqual(len(out_of_gallery), 20)
        for p in gallery:
            self.assertTrue(p.lower().endswith(('.jpg', '.jpeg')), p)
            self.assertTrue((ROOT / p).is_file(), p)
        for p in out_of_gallery:
            self.assertTrue(p.lower().endswith('.png'), p)
            self.assertTrue((ROOT / p).is_file(), p)

    def test_out_of_gallery_extension_sweep_is_advisory(self):
        # 图集外还有一批 .png 装 JPEG 字节，但被视频工程 JSON 与文档按文件名引用，改名会打断既有工程；
        # 「看不见」不等于「不用核验」，所以扫一遍只提示、只写口径，绝不判红。
        sweep = self.report['图集外扩展名体检']
        self.assertGreater(sweep['不一致数'], 0)
        self.assertEqual(sweep['判红数'], 0)
        refs = {p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']}
        self.assertFalse(set(sweep['明细']) & refs)
        for token in ('影像作品', '视觉控制资产'):
            self.assertIn(token, json.dumps(sweep['按目录'], ensure_ascii=False))
        self.assertIn('按文件名引用', sweep['不改名口径'])

    def test_missing_file_fixture_red(self):
        import tempfile
        items = [{'id': 'X001', 'image_file': ['数据/图集/不存在-甲.png']}]
        bad = self.va.check(items, root=Path(tempfile.mkdtemp()))
        self.assertEqual(bad['失败明细'][0]['原因'], '文件缺失')

    def test_stripped_metadata_fixture_red(self):
        tmp = write_jpeg('无元数据.jpg', [(b'\xff\xe0', b'JFIF\x00' + bytes(10))])
        bad = self.va.check([{'id': 'X002', 'image_file': ['无元数据.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], '缺XMP段')

    def test_xmp_without_tc260_fixture_red(self):
        tmp = write_jpeg('有XMP无TC260.jpg', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta><a>TCAAA</a></x:xmpmeta>')])
        bad = self.va.check([{'id': 'X003', 'image_file': ['有XMP无TC260.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'XMP缺TC260标识')

    def test_xmp_without_aigc_fixture_red(self):
        tmp = write_jpeg('有TC260无AIGC.jpg', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260</x:xmpmeta>')])
        bad = self.va.check([{'id': 'X004', 'image_file': ['有TC260无AIGC.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'XMP缺AIGC标识')

    def test_bare_png_without_caBX_fixture_red(self):
        # C97 后 PNG 是被接受的容器，所以「PNG 但没标识块」必须从「非JPEG字节头」改判为容器缺位，
        # 而不是被旧口径误当成 JPEG 缺 XMP——两种原因对应的修法完全不同。
        tmp = write_png('无标识块.png')
        bad = self.va.check([{'id': 'X005', 'image_file': ['无标识块.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'PNG缺caBX标识块')

    def test_neither_jpeg_nor_png_magic_fixture_red(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        (tmp / '假图.jpg').write_bytes(b'GIF89a' + bytes(24))
        bad = self.va.check([{'id': 'X011', 'image_file': ['假图.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], '字节头既非JPEG亦非PNG')

    def test_png_caBX_with_c2pa_declaration_passes(self):
        tmp = write_png('带C2PA.png', b'urn:c2pa:abcd jumb '
                        b'http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia')
        ok = self.va.check([{'id': 'X012', 'image_file': ['带C2PA.png']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['失败格数'], ok['提示格数'], ok['C2PA在位格数']), (1, 0, 0, 1))
        self.assertEqual(ok['逐格'][0]['标识容器'], 'C2PA(caBX)')

    def test_png_caBX_missing_generative_declaration_fixture_red(self):
        # 有 C2PA 清单但没有生成式来源声明＝容器在、标识不在，必须判红；
        # 这条就是「不得由脚本补写元数据过闸」的反面：判据认的是平台写进去的声明。
        tmp = write_png('有清单无声明.png', b'urn:c2pa:abcd jumb c2pa.actions.v2')
        bad = self.va.check([{'id': 'X013', 'image_file': ['有清单无声明.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'caBX缺生成式AI标识')

    def test_png_caBX_without_c2pa_manifest_fixture_red(self):
        tmp = write_png('有块无清单.png', b'trainedAlgorithmicMedia Generated with AI')
        bad = self.va.check([{'id': 'X014', 'image_file': ['有块无清单.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'caBX缺C2PA清单')

    def test_archived_e1_pngs_carry_the_accepted_container(self):
        # 真实夹具：归档的 E1 定档与重出图必须被新判据认下，不能只靠合成字节自证。
        import glob
        paths = sorted(glob.glob(str(ROOT / '数据' / '视觉控制资产' / 'E1定档-20261103' / '*.png')))
        self.assertEqual(len(paths), 12)
        for p in paths:
            with self.subTest(path=os.path.relpath(p, ROOT)):
                info = self.va.sniff(Path(p))
                self.assertEqual((info['PNG'], info['caBX'], info['C2PA'], info['AIGC声明']),
                                 (True, True, True, True))
                self.assertEqual(info['标识容器'], 'C2PA(caBX)')
                self.assertIsNone(self.va.verdict(info))

    def test_c2pa_box_fixture_does_not_turn_xmp_green(self):
        tmp = write_jpeg('带jumb.jpg', [(b'\xff\xeb', b'jumb' + bytes(20)),
                                        (b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260 AIGC</x:xmpmeta>')])
        ok = self.va.check([{'id': 'X006', 'image_file': ['带jumb.jpg']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['C2PA在位格数']), (1, 1))

    def test_recheck_worksheet_lists_every_id(self):
        md = (ROOT / '数据' / '图片复验清单.md').read_text(encoding='utf-8')
        items = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))['items']
        rows = len(re.findall(r'^\| [DFLRS]\d+ \|', md, re.M))
        # 工作单由 verify_image_assets 逐条遍历清单派生，所以行数必须等于清单条目数（含「无图」占位行）。
        # 2026-11-02 实测教训：2-A 扩到 312 条后没重跑这张下游表，它还停在 264 行旧禁则上，硬编码行数的旧断言反而看不见。
        self.assertEqual(rows, len(items), '图片复验清单未随开图清单重跑，属过期生成物')
        self.assertEqual(md.count('| 无图 |'), sum(1 for item in items if not item.get('image_file')))
        self.assertNotIn('第二座超两百米', md)
        for token in ('结构合规不等于视觉验收', '待人工复验', '不得由脚本代签', '图集外扩展名体检', '只报不办、不改名'):
            self.assertIn(token, md)

    def test_worksheet_missing_the_new_rows_would_fail_that_gate(self):
        # 负测：2-A 那轮的故障是清单已扩到 312 条而工作单还是扩容前的行数。
        # 用真渲染函数造一张 264 行的过期单，上面的行数判据必须判红，否则该闸门是假绿。
        stale = self.manifest['items'][:264]
        md = self.va.render_worksheet(self.va.check(stale), stale)
        rows = len(re.findall(r'^\| [DFLRS]\d+ \|', md, re.M))
        self.assertEqual(rows, 264)
        self.assertNotEqual(rows, len(self.manifest['items']))


class AssetRulings(unittest.TestCase):
    IDS = ['C82', 'C83', 'C84']

    def test_three_asset_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 111)
        self.assertEqual(rows[-1]['编号'], 'C111')
        self.assertIn('rename_gallery_ext', by_id['C82']['裁定'])
        self.assertIn('不是交付判据', by_id['C83']['裁定'])
        self.assertIn('不判红、不改名', by_id['C84']['裁定'])
        self.assertIn('按文件名引用', by_id['C84']['原因'])

    def test_c97_records_the_two_accepted_containers(self):
        """C97 是双容器交付判据的唯一出处：裁定措辞一旦被回退，核验脚本的判据文本与裁定记录就各说各话，
        所以把容器名单、判红边界与「补写即伪造」一起钉在这里。"""
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertEqual(set(by_id['C97']), {'编号', '裁定', '原因', '影响'})
        for token in ('caBX', 'trainedAlgorithmicMedia', '字节头既非 JPEG 也非 PNG 直接判红', '补写是伪造'):
            self.assertIn(token, by_id['C97']['裁定'])
        self.assertIn('通过 1056/1056', by_id['C97']['影响'])


if __name__ == '__main__':
    unittest.main()
