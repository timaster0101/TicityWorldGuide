"""Real ZIP/XML fixtures; no exports, dependencies, or writes to the real project."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
import zipfile

sys.dont_write_bytecode = True
VERIFY_PATH = Path(__file__).with_name('verify_docx.py')
BOOK = '钛湖城城市设定集-完整合订本'
REPORT = Path('数据') / 'Word核验结果.json'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
SOURCE = '''# 合订本

首段 2013 / ABC-01

# 第一卷
## 第二级
### 第三级
正文 **粗体** `x=-12.5` [显示文本](https://example.test) **`保持`**。
- 列表 -36 与 36
1. 编号 007
> 引用 -0.888
#### 四级保留井号

| 字段 | 参数 |
| :--- | ---: |
| 坐标 | **原样** `-17` [原文](https://example.test) |

结尾 -25 km²
'''


def paragraph(text='', style=None, properties='', raw=None):
    if style:
        properties = '<w:pStyle w:val="%s"/>' % style + properties
    props = '<w:pPr>%s</w:pPr>' % properties if properties else ''
    runs = raw if raw is not None else '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % escape(text)
    return '<w:p>%s%s</w:p>' % (props, runs)


def table(rows):
    return '<w:tbl>' + ''.join('<w:tr>' + ''.join('<w:tc>' + paragraph(cell) + '</w:tc>' for cell in row) + '</w:tr>' for row in rows) + '</w:tbl>'


BODY = [
    paragraph('首段 2013 / ABC-01'),
    paragraph('第一卷', 'Heading1', '<w:pageBreakBefore/>'),
    paragraph('第二级', 'Heading2'),
    paragraph('第三级', 'Heading3'),
    paragraph(raw='<w:r><w:t>正文 </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>粗体</w:t></w:r><w:r><w:t> x=-12.5 </w:t></w:r><w:hyperlink><w:r><w:t>显示文本</w:t></w:r></w:hyperlink><w:r><w:t> `保持`。</w:t></w:r>'),
    paragraph('列表 -36 与 36', properties='<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'),
    paragraph('1. 编号 007'),
    paragraph('引用 -0.888'),
    paragraph('#### 四级保留井号'),
    table([['字段', '参数'], ['坐标', '**原样** `-17` [原文](https://example.test)']]),
    paragraph(''),
    paragraph('结尾 -25 km²'),
]
TOC_START = paragraph(raw='<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> TO</w:instrText></w:r><w:r><w:instrText>C \\o "1-1" </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>')
TOC_END = paragraph(raw='<w:r><w:fldChar w:fldCharType="end"/></w:r>')
PREFIX = paragraph('封面') + paragraph('卷目导航', 'Heading1', '<w:pageBreakBefore/>') + TOC_START + paragraph('第一卷', 'TOC1') + TOC_END


class DocxVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docx = self.root / (BOOK + '.docx')
        self.source = self.root / (BOOK + '.md')
        self.source.write_text(SOURCE, encoding='utf-8')
        self.write_docx()

    def write_docx(self, body=None, prefix=PREFIX, overrides=None, omit=()):
        content = ''.join(BODY if body is None else body)
        parts = {
            '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            'word/document.xml': '<w:document xmlns:w="%s"><w:body>%s%s<w:sectPr/></w:body></w:document>' % (W, prefix, content),
            'word/settings.xml': '<w:settings xmlns:w="%s"><w:updateFields w:val="true"/></w:settings>' % W,
            'word/_rels/document.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
            'word/header1.xml': '<w:hdr xmlns:w="%s">%s</w:hdr>' % (W, paragraph('页眉不属于主正文')),
            'word/media/asset.bin': b'CRC sentinel binary',
        }
        parts.update(overrides or {})
        with zipfile.ZipFile(self.docx, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, text in parts.items():
                if name not in omit:
                    archive.writestr(name, text)

    def verify(self):
        self.assertTrue(VERIFY_PATH.is_file(), '缺少只读 Word 核验实现 verify_docx.py')
        spec = importlib.util.spec_from_file_location('verify_docx_under_test', VERIFY_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify(self.root)

    def assert_failed(self, result):
        self.assertIs(result['passed'], False)
        self.assertTrue(result['errors'])
        self.assertIs(result['rendering_verified'], False)

    def test_matching_content_and_actual_metrics(self):
        result = self.verify()
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['differences'], [])
        self.assertEqual(result['paragraph_count'], 20)  # 5 prefix, 10 text, 4 cells, 1 empty
        self.assertEqual(result['table_count'], 1)
        self.assertEqual(result['cell_count'], 4)
        self.assertEqual(result['h1_count'], 2)
        self.assertEqual(result['page_break_count'], 2)
        self.assertEqual(result['toc_field_count'], 1)  # split instruction is one field
        self.assertEqual(result['xml_parts'], 6)
        self.assertTrue(result['crc_verified'])
        self.assertTrue(result['update_fields'])
        self.assertIs(result['rendering_verified'], False)
        self.assertFalse((self.root / REPORT).exists())

    def test_numeric_ascii_and_minus_changes_are_not_discarded(self):
        for before, after in [('-25', '25'), ('-25', '-26'), ('007', '008'), ('km²', 'm²')]:
            with self.subTest(change=(before, after)):
                self.write_docx(body=[part.replace(before, after) for part in BODY])
                result = self.verify()
                self.assert_failed(result)
                self.assertTrue(result['differences'])
                details = json.dumps(result['differences'], ensure_ascii=False)
                self.assertIn(before, details)
                self.assertIn(after, details)

    def test_missing_reordered_and_extra_paragraphs_fail(self):
        variants = [BODY[:4] + BODY[5:], BODY[:4] + [BODY[5], BODY[4]] + BODY[6:], BODY + [paragraph('多余正文')]]
        for body in variants:
            with self.subTest(body=body):
                self.write_docx(body=body)
                result = self.verify()
                self.assert_failed(result)
                self.assertTrue(result['differences'])

    def test_missing_or_changed_first_anchor_fails(self):
        for body in [BODY[1:], [paragraph('首段 2036 / ABC-01')] + BODY[1:]]:
            self.write_docx(body=body)
            result = self.verify()
            self.assert_failed(result)
            self.assertTrue(result['differences'])

    def test_table_header_cell_order_structure_and_value_are_compared(self):
        variants = [
            table([['错误字段', '参数'], ['坐标', '**原样** `-17` [原文](https://example.test)']]),
            table([['字段', '参数'], ['坐标', '**原样** `17` [原文](https://example.test)']]),
            table([['参数', '字段'], ['坐标', '**原样** `-17` [原文](https://example.test)']]),
            table([['字段', '参数', '坐标', '**原样** `-17` [原文](https://example.test)']]),
            ''.join(paragraph(x) for x in ['字段', '参数', '坐标', '**原样** `-17` [原文](https://example.test)']),
        ]
        for replacement in variants:
            self.write_docx(body=BODY[:9] + [replacement] + BODY[10:])
            result = self.verify()
            self.assert_failed(result)
            self.assertTrue(result['differences'])

    def test_merged_cells_cannot_pass_with_identical_text(self):
        for properties in ('<w:vMerge w:val="restart"/>', '<w:hMerge w:val="restart"/>', '<w:gridSpan w:val="2"/>'):
            with self.subTest(properties=properties):
                merged = BODY[9].replace('<w:tc>', '<w:tc><w:tcPr>' + properties + '</w:tcPr>', 1)
                if 'vMerge' in properties:
                    merged = merged.replace('<w:tc>' + paragraph('坐标'), '<w:tc><w:tcPr><w:vMerge/></w:tcPr>' + paragraph('坐标'))
                self.write_docx(body=BODY[:9] + [merged] + BODY[10:])
                result = self.verify()
                self.assert_failed(result)
                self.assertTrue(result['differences'])

    def test_toc_results_cannot_replace_body_paragraph_or_table(self):
        for index in (9, len(BODY) - 1):
            with self.subTest(index=index):
                self.write_docx(body=BODY[:index] + [TOC_START, BODY[index], TOC_END] + BODY[index + 1:])
                result = self.verify()
                self.assert_failed(result)
                self.assertTrue(result['differences'])

    def test_trailing_toc_is_excluded_without_losing_body(self):
        self.write_docx(body=BODY + [TOC_START, paragraph('目录缓存'), TOC_END])
        result = self.verify()
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['toc_field_count'], 2)

    def test_all_differences_are_retained_without_truncation(self):
        self.source.write_text('# 标题\n\n锚点\n' + '\n'.join('第%d项 -%d' % (i, i) for i in range(40)), encoding='utf-8')
        self.write_docx(body=[paragraph('锚点')] + [paragraph('第%d项 %d' % (i, i)) for i in range(40)])
        result = self.verify()
        self.assert_failed(result)
        differences = json.dumps(result['differences'], ensure_ascii=False)
        for i in range(40):
            self.assertIn('第%d项 -%d' % (i, i), differences)
            self.assertIn('第%d项 %d' % (i, i), differences)

    def test_toc_duplicates_are_not_body_anchors(self):
        self.source.write_text('# 封面\n# 第一卷\n正文\n', encoding='utf-8')
        toc_sdt = '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/></w:docPartObj></w:sdtPr><w:sdtContent>' + paragraph('第一卷', 'Heading1') + '</w:sdtContent></w:sdt>'
        for prefix in [PREFIX, TOC_START + paragraph('第一卷', 'Heading1') + TOC_END, toc_sdt]:
            self.write_docx(body=[paragraph('第一卷', 'Heading1'), paragraph('正文')], prefix=prefix)
            result = self.verify()
            self.assertTrue(result['passed'], result['errors'])
        self.write_docx(body=[paragraph('正文')], prefix=PREFIX)
        self.assert_failed(self.verify())

    def test_hashes_are_fresh_and_verify_never_writes_or_reuses_report(self):
        first = self.verify()
        report = self.root / REPORT
        report.parent.mkdir()
        report.write_text(json.dumps(first), encoding='utf-8')
        report_bytes = report.read_bytes()
        report_time = report.stat().st_mtime_ns
        self.source.write_text(SOURCE.replace('007', '009'), encoding='utf-8')
        changed_source = self.verify()
        self.assert_failed(changed_source)
        self.assertEqual(changed_source['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertNotEqual(changed_source['source_sha256'], first['source_sha256'])
        self.assertEqual(changed_source['docx_sha256'], first['docx_sha256'])
        self.write_docx(body=[part.replace('007', '009') for part in BODY])
        changed_docx = self.verify()
        self.assertTrue(changed_docx['passed'], changed_docx['errors'])
        self.assertEqual(changed_docx['docx_sha256'], hashlib.sha256(self.docx.read_bytes()).hexdigest())
        self.assertNotEqual(changed_docx['docx_sha256'], first['docx_sha256'])
        self.assertEqual(report.read_bytes(), report_bytes)
        self.assertEqual(report.stat().st_mtime_ns, report_time)

    def test_all_xml_and_relationship_parts_are_validated(self):
        for name in ['word/header1.xml', 'word/_rels/document.xml.rels', 'customXml/extra.xml']:
            self.write_docx(overrides={name: '<invalid>'})
            result = self.verify()
            self.assert_failed(result)
            self.assertIn(name, json.dumps(result['errors']))

    def test_content_type_declared_xml_is_checked_without_xml_extension(self):
        with zipfile.ZipFile(self.docx) as archive:
            types = archive.read('[Content_Types].xml').decode('utf-8')
        types = types.replace('</Types>', '<Override PartName="/custom/extra.payload" ContentType="application/example+xml"/></Types>')
        self.write_docx(overrides={'[Content_Types].xml': types, 'custom/extra.payload': '<broken>'})
        result = self.verify()
        self.assert_failed(result)
        self.assertIn('custom/extra.payload', json.dumps(result['errors']))
        self.assertEqual(result['xml_parts'], 7)

    def test_unknown_xml_encoding_returns_failure_instead_of_raising(self):
        self.write_docx(overrides={'word/header1.xml': '<?xml version="1.0" encoding="not-a-real-encoding"?><root/>'})
        try:
            result = self.verify()
        except LookupError as error:
            self.fail('损坏 XML 编码应返回 failed JSON，不应抛出: %s' % error)
        self.assert_failed(result)
        self.assertIn('word/header1.xml', json.dumps(result['errors']))

    def test_nested_table_cannot_pass_by_flattening_identical_text(self):
        nested = BODY[9].replace('<w:tc>' + paragraph('参数') + '</w:tc>', '<w:tc>' + table([['参数']]) + paragraph('') + '</w:tc>')
        self.write_docx(body=BODY[:9] + [nested] + BODY[10:])
        result = self.verify()
        self.assert_failed(result)
        self.assertEqual(result['table_count'], 2)
        self.assertTrue(result['differences'])

    def test_explicit_page_breaks_count_but_disabled_flags_do_not(self):
        extra = paragraph('', properties='<w:pageBreakBefore w:val="false"/>', raw='<w:r><w:br w:type="page"/><w:lastRenderedPageBreak/></w:r>')
        self.write_docx(body=BODY + [extra])
        result = self.verify()
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['page_break_count'], 3)
        self.assertEqual(result['explicit_page_break_count'], 1)
        self.assertEqual(result['page_break_before_count'], 2)

    def test_crc_in_non_xml_member_is_checked(self):
        with zipfile.ZipFile(self.docx) as archive:
            member = archive.getinfo('word/media/asset.bin')
            offset = member.header_offset
        raw = bytearray(self.docx.read_bytes())
        name_len, extra_len = struct.unpack_from('<HH', raw, offset + 26)
        raw[offset + 30 + name_len + extra_len] ^= 1
        self.docx.write_bytes(raw)
        result = self.verify()
        self.assert_failed(result)
        self.assertFalse(result['crc_verified'])

    def test_update_fields_required_and_on_off_values(self):
        for value in ['false', '0', 'off']:
            self.write_docx(overrides={'word/settings.xml': '<w:settings xmlns:w="%s"><w:updateFields w:val="%s"/></w:settings>' % (W, value)})
            self.assert_failed(self.verify())
        self.write_docx(overrides={'word/settings.xml': '<w:settings xmlns:w="%s"/>' % W})
        self.assert_failed(self.verify())
        for attribute in ['', ' w:val="1"', ' w:val="on"']:
            self.write_docx(overrides={'word/settings.xml': '<w:settings xmlns:w="%s"><w:updateFields%s/></w:settings>' % (W, attribute)})
            result = self.verify()
            self.assertTrue(result['passed'], result['errors'])

    def test_missing_files_parts_invalid_zip_or_source_fail(self):
        self.source.unlink()
        self.assert_failed(self.verify())
        self.source.write_text(SOURCE, encoding='utf-8')
        self.docx.unlink()
        self.assert_failed(self.verify())
        self.docx.write_bytes(b'not a zip')
        self.assert_failed(self.verify())
        for part in ['word/document.xml', 'word/settings.xml', '[Content_Types].xml']:
            self.write_docx(omit=[part])
            self.assert_failed(self.verify())
        self.write_docx()
        self.source.write_bytes(b'\xff')
        self.assert_failed(self.verify())
        self.source.write_text('# 只有标题\n', encoding='utf-8')
        self.assert_failed(self.verify())

    def test_cli_writes_fresh_json_and_sets_exit_status(self):
        self.assertTrue(VERIFY_PATH.is_file(), '缺少 Word 核验 CLI')
        command = [sys.executable, '-B', str(VERIFY_PATH), '--root', str(self.root)]
        success = subprocess.run(command, capture_output=True, encoding='utf-8')
        self.assertEqual(success.returncode, 0, success.stderr)
        report = self.root / REPORT
        saved = json.loads(report.read_text(encoding='utf-8'))
        self.assertTrue(saved['passed'])
        self.assertEqual(json.loads(success.stdout), saved)
        self.docx.write_bytes(b'broken')
        failure = subprocess.run(command, capture_output=True, encoding='utf-8')
        self.assertNotEqual(failure.returncode, 0)
        failed = json.loads(report.read_text(encoding='utf-8'))
        self.assert_failed(failed)
        self.assertNotEqual(saved['docx_sha256'], failed['docx_sha256'])
        self.assertEqual(json.loads(failure.stdout), failed)
        self.source.unlink()
        self.docx.unlink()
        missing = subprocess.run(command, capture_output=True, encoding='utf-8')
        self.assertNotEqual(missing.returncode, 0)
        self.assert_failed(json.loads(missing.stdout))


if __name__ == '__main__':
    unittest.main()
