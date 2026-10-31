# -*- coding: utf-8 -*-
"""开图图片资产核验回归。只读已落盘产物与真实图集，不生成、不修改任何图片。

跑法：python 工具/test_image_assets.py（工作目录＝设定集根）
"""
import json
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

    def test_four_long_notes_recovered(self):
        self.assertEqual(sorted(self.notes), ['D01', 'L007', 'L008', 'R043'])
        # 本轮实测：809ed08 的原始长度 518/226/231/151，各带一条同文派生原因，剥净后如下
        self.assertEqual({k: len(v[0]) for k, v in self.notes.items()},
                         {'D01': 204, 'L007': 491, 'L008': 199, 'R043': 124})
        for eid, rows in self.notes.items():
            self.assertTrue(all(r.strip() for r in rows), eid)
            self.assertNotIn('图片对应的基准提示词已变化', rows[-1], f'{eid} 手工源里混入了派生原因')

    def test_history_survives_and_note_still_derives(self):
        # 260 条没有人工长文本，历史是空数组：判"键在不在"而不是"值真不真"
        self.assertEqual(sum(1 for i in self.items.values() if 'review_note_history' in i), 264)
        self.assertEqual(sum(1 for i in self.items.values() if i['review_note_history']), 4)
        for eid in ('L007', 'L008', 'R043', 'D01'):
            hist = self.items[eid]['review_note_history']
            self.assertEqual(hist, self.notes[eid], eid)
            self.assertIn(self.notes[eid][-1], self.items[eid]['review_note'])
        self.assertEqual(self.manifest['needs_review'], 264)
        self.assertEqual(self.manifest['accepted'], 0)
        self.assertEqual(self.manifest['generated'], 264)
        self.assertEqual(self.manifest['pending'], 0)


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


class AssetGate(unittest.TestCase):
    def setUp(self):
        import verify_image_assets as va
        self.va = va
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.report = json.loads((ROOT / '数据' / '图片资产核验.json').read_text(encoding='utf-8'))

    def test_paths_are_authoritative_and_unique(self):
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']]
        self.assertEqual(len(paths), 1056)
        self.assertEqual(len(set(paths)), 1056)
        self.assertEqual(sum(1 for i in self.manifest['items'] if i.get('image_file')), 264)

    def test_report_all_green_and_disclaims(self):
        self.assertEqual(self.report['文件格数'], 1056)
        self.assertEqual(self.report['失败格数'], 0)
        self.assertEqual(self.report['通过格数'], 1056)
        self.assertNotIn('已验收', json.dumps(self.report, ensure_ascii=False))
        self.assertIn('结构合规不等于视觉验收', self.report['声明'])

    def test_c2pa_absent_is_expected_not_failure(self):
        self.assertEqual(self.report['C2PA在位格数'], 0)
        self.assertIn('C2PA', self.report['判据'])

    def test_c2pa_is_recorded_not_a_delivery_criterion(self):
        # 缺位既不是判红也不是待办，口径要写死，否则每轮都要有人重新问一遍
        for token in ('不是交付判据', '不列待办'):
            self.assertIn(token, self.report['判据'])
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
        self.assertEqual(len(paths), 1056)
        for p in paths:
            self.assertTrue(p.lower().endswith(('.jpg', '.jpeg')), p)
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

    def test_non_jpeg_magic_fixture_red(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        (tmp / '假png.png').write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(24))
        bad = self.va.check([{'id': 'X005', 'image_file': ['假png.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], '非JPEG字节头')

    def test_c2pa_box_fixture_does_not_turn_xmp_green(self):
        tmp = write_jpeg('带jumb.jpg', [(b'\xff\xeb', b'jumb' + bytes(20)),
                                        (b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260 AIGC</x:xmpmeta>')])
        ok = self.va.check([{'id': 'X006', 'image_file': ['带jumb.jpg']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['C2PA在位格数']), (1, 1))

    def test_recheck_worksheet_lists_every_id(self):
        md = (ROOT / '数据' / '图片复验清单.md').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'^\| [DFLRS]\d+ \|', md, re.M)), 264)
        for token in ('结构合规不等于视觉验收', '待人工复验', '不得由脚本代签', '图集外扩展名体检', '只报不办、不改名'):
            self.assertIn(token, md)


class AssetRulings(unittest.TestCase):
    IDS = ['C82', 'C83', 'C84']

    def test_three_asset_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 84)
        self.assertEqual(rows[-1]['编号'], 'C84')
        self.assertIn('rename_gallery_ext', by_id['C82']['裁定'])
        self.assertIn('不是交付判据', by_id['C83']['裁定'])
        self.assertIn('不判红、不改名', by_id['C84']['裁定'])
        self.assertIn('按文件名引用', by_id['C84']['原因'])


if __name__ == '__main__':
    unittest.main()
