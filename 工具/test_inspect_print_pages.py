# -*- coding: utf-8 -*-
"""inspect_print_pages 的闸门：像素体征与标记口径必须能判红，汇总与报告必须自洽。

不跑 LibreOffice（那要一分钟以上且依赖本机安装），只测纯函数：page_metrics／flags_for／
summarize／write_report；渲染链路由 `python 工具/inspect_print_pages.py --limit 3` 手工验。
"""
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import inspect_print_pages as I

PAGE_MM = (210.0, 297.0)


def blank(w=827, h=1169):
    return Image.new('RGB', (w, h), 'white')


def inked(box=(100, 200, 700, 1000)):
    """正文页样张：在 box 里画一列细横线（像行文），既够密又不会把整页压暗。"""
    im = blank()
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = box
    for y in range(y0, y1, 20):
        d.rectangle((x0, y, x1, y + 8), fill=(60, 60, 60))
    return im


class MetricsFace(unittest.TestCase):
    def test_blank_page_has_no_ink_and_no_bbox(self):
        m = I.page_metrics(blank())
        self.assertEqual(m['ink_ratio'], 0.0)
        self.assertIsNone(m['bbox'])

    def test_blank_page_flags_blank(self):
        m = I.page_metrics(blank())
        self.assertEqual(I.flags_for(m, 100, PAGE_MM), ['空白页'])

    def test_full_text_page_is_not_flagged(self):
        m = I.page_metrics(inked())
        flags = I.flags_for(m, 100, PAGE_MM)
        self.assertNotIn('空白页', flags)
        self.assertNotIn('内容压边', flags)

    def test_content_touching_edge_flags_it(self):
        im = blank()
        ImageDraw.Draw(im).rectangle((0, 500, 8, 900), fill='black')   # 贴左页边 8px≈2mm
        flags = I.flags_for(I.page_metrics(im), 100, PAGE_MM)
        self.assertIn('内容压边', flags)

    def test_dark_page_flags_dark(self):
        im = Image.new('RGB', (827, 1169), (40, 40, 40))
        flags = I.flags_for(I.page_metrics(im), 100, PAGE_MM)
        self.assertIn('整页发暗', flags)

    def test_sparse_page_flags_sparse_not_blank(self):
        im = blank()
        ImageDraw.Draw(im).rectangle((120, 120, 400, 150), fill='black')  # 一条短标题
        m = I.page_metrics(im)
        self.assertGreater(m['ink_ratio'], I.BLANK_INK)
        self.assertLess(m['ink_ratio'], I.SPARSE_INK)
        self.assertEqual(I.flags_for(m, 100, PAGE_MM), ['稀疏页'])

    def test_metrics_carry_margins_in_mm(self):
        m = I.page_metrics(inked())
        I.flags_for(m, 100, PAGE_MM)
        self.assertIn('margins_mm', m)
        self.assertGreater(m['margins_mm']['left'], 20)


class SummarizeFace(unittest.TestCase):
    def _rows(self):
        rows = []
        for name, img in (('p001.png', blank()), ('p002.png', inked()), ('p003.png', inked((0, 500, 8, 900)))):
            m = I.page_metrics(img)
            m['file'] = name
            m['flags'] = I.flags_for(m, 100, PAGE_MM)
            rows.append(m)
        return rows

    def test_counts_match_flagged_rows(self):
        rep = I.summarize(self._rows(), pages_in_word=424)
        self.assertEqual(rep['统计']['页数'], 3)
        self.assertEqual(rep['统计']['被标记页数'], 2)
        self.assertEqual(rep['统计']['空白页'], 1)
        self.assertEqual(rep['统计']['内容压边'], 1)
        self.assertEqual(rep['按标记归组']['空白页'], ['p001.png'])

    def test_limited_by_word_page_count_in_caveat(self):
        rep = I.summarize(self._rows(), pages_in_word=424)
        self.assertIn('424', rep['局限'])
        self.assertIn('不替代 Word 渲染目视', rep['局限'])

    def test_flagged_pages_are_a_subset_of_rows(self):
        rep = I.summarize(self._rows())
        listed = {f for files in rep['按标记归组'].values() for f in files}
        self.assertTrue(listed <= {r['file'] for r in rep['逐页']})


class WriteReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='inspect_'))
        self.jp = self.tmp / 'r.json'
        self.mp = self.tmp / 'r.md'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_json_and_markdown_with_counts(self):
        rows = []
        im = blank()
        m = I.page_metrics(im)
        m['file'] = 'p001.png'
        m['flags'] = I.flags_for(m, 100, PAGE_MM)
        rows.append(m)
        I.write_report(I.summarize(rows), json_path=self.jp, md_path=self.mp)
        data = json.loads(self.jp.read_text(encoding='utf-8'))
        self.assertEqual(data['统计']['空白页'], 1)
        md = self.mp.read_text(encoding='utf-8')
        self.assertIn('逐页版面体检', md)
        self.assertIn('p001', md)
        self.assertIn('Word 渲染目视', md)


class NegativeGate(unittest.TestCase):
    def test_swallowing_blank_flag_changes_counts(self):
        # 负测：把空白页硬说成正常页，统计必须随之变，证明判据不是装饰
        im = blank()
        m = I.page_metrics(im)
        m['file'] = 'p001.png'
        m['flags'] = []
        rep = I.summarize([m])
        self.assertEqual(rep['统计']['空白页'], 0)
        self.assertEqual(rep['统计']['被标记页数'], 0)
        # 同一页给回真实标记，计数必须回到 1
        m['flags'] = I.flags_for(m, 100, PAGE_MM)
        rep2 = I.summarize([m])
        self.assertEqual(rep2['统计']['空白页'], 1)


if __name__ == '__main__':
    unittest.main()

class ChromeAndStructure(unittest.TestCase):
    def test_header_lines_are_chrome(self):
        for line in ('钛湖城/ 城市空间与生活设定', '原创虚构设定· 12', '卷三 地标建筑', '424', '  '):
            self.assertTrue(I._is_chrome(line), line)

    def test_content_lines_are_not_chrome(self):
        for line in ('地标建筑上卷', 'D01 北湖政务片区', 'L007 天际线主塔'):
            self.assertFalse(I._is_chrome(line), line)

    def test_first_content_line_skips_header(self):
        text = '钛湖城/ 城市空间与生活设定\n原创虚构设定· 108\n地标建筑上卷\n正文第一段'
        self.assertEqual(I.first_content_line(text), '地标建筑上卷')

    def test_structure_pages_finds_cover_and_last(self):
        rows = [
            {'file': 'p001.png', '首行': '城市设定集· 完整合订本', '字符数': 210},
            {'file': 'p002.png', '首行': '卷目导航', '字符数': 3273},
            {'file': 'p108.png', '首行': '地标建筑上卷', '字符数': 500},
            {'file': 'p424.png', '首行': '正典末条', '字符数': 1409},
        ]
        sp = I.structure_pages(rows)
        self.assertEqual(sp['封面'], [1])
        self.assertEqual(sp['末页'], [424])
        self.assertIn(108, sp['分卷首页'])

    def test_wps_renderer_caveat_does_not_disclaim_page_numbers(self):
        rows = [{'file': 'p001.png', 'flags': [], '首行': 'x', '字符数': 10}]
        rep = I.summarize(rows, pages_in_word=424, renderer='WPS')
        self.assertIn('页号即 Word 页号', rep['局限'])
        self.assertNotIn('不作为 Word 页号依据', rep['局限'])

