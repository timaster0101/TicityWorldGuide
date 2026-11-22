"""Verify ordered Markdown/DOCX content and XML structure, not rendering or XSD validity.

渲染一栏不在本脚本的判定权内：它只回显人工维护的 `数据/Word渲染目视.json`，并核对该记录绑定的
DOCX 摘要是否就是当前这份。docx 重导后摘要变化，目视结论自动失效，须重看——与图片的
`image_prompt_sha256` 同一口径。脚本不得把 `rendering_verified` 自行置真。
"""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
BOOK = '钛湖城城市设定集-完整合订本'
REPORT = Path('数据') / 'Word核验结果.json'
RECORD = Path('数据') / 'Word渲染目视.json'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BT = '`'  # Markdown 内联码标记；导出到 Word 正文后必须已被剥掉，留在这里就是渲染缺陷
# 目视记录必须自带的字段与必须覆盖的范围：缺任何一项都不算看过，脚本只核对不补写。
RECORD_FIELDS = ('docx_sha256', '渲染方式', '目视范围', '结论', '核验人', '日期')
RECORD_SCOPE = ('封面计数', '目录页码', '分卷首页', '表格页', '末页截断')


def rendering_state(root, docx_sha256):
    """Return (verified, note) from the human record only; never infer a verdict from structure."""
    if not docx_sha256:
        return False, 'DOCX 未能读取，无摘要可绑定'
    try:
        record = json.loads((Path(root) / RECORD).read_text(encoding='utf-8'))['目视记录']
    except FileNotFoundError:
        return False, '缺少人工目视记录 %s，未做渲染级目视' % RECORD.as_posix()
    except (OSError, ValueError, KeyError, TypeError) as error:
        return False, '人工目视记录读取失败：%s' % error
    missing = [name for name in RECORD_FIELDS if not str(record.get(name) or '').strip()]
    if missing:
        return False, '人工目视记录缺字段：%s' % '、'.join(missing)
    scope = record['目视范围'] if isinstance(record['目视范围'], list) else [record['目视范围']]
    gaps = [name for name in RECORD_SCOPE if name not in scope]
    if gaps:
        return False, '目视范围未覆盖：%s' % '、'.join(gaps)
    if record['docx_sha256'] != docx_sha256:
        return False, ('目视记录绑定的是另一份 DOCX（记录 %s…，当前 %s…）：重导即失效，须重看'
                       % (record['docx_sha256'][:8], docx_sha256[:8]))
    if record['结论'].strip() != '通过':
        return False, '人工结论为「%s」，不是通过' % record['结论'].strip()
    if record.get('问题'):
        return False, '仍有未收口问题：%s' % '；'.join(str(item) for item in record['问题'][:3])
    return True, '结论来自 %s：由「%s」按「%s」目视，绑定当前 DOCX 摘要' % (
        RECORD.as_posix(), record['核验人'], record['渲染方式'])


def _inline(text):
    # Match export_docx.cjs runs(): code/link markers are stripped BEFORE the bold split, so a
    # code span nested inside bold no longer leaves literal backticks in the rendered document.
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', re.sub(r'`([^`]+)`', r'\1', text))
    return ''.join(part[2:-2] if part.startswith('**') else part
                   for part in re.split(r'(\*\*[^*]+\*\*)', text) if part)


def _markdown_blocks(source):
    # Deliberately not a general Markdown parser: these are the exporter rules.
    lines = re.split(r'\r?\n', source)
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].strip().strip('\ufeff').strip()
        source_line = i + 1
        i += 1
        if not line or line == '---':
            continue
        if line.startswith('|'):
            table_lines = [lines[i - 1]]
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            # The exporter tests separators against the raw line, not its trim.
            # Cells go through the same _inline as prose since 2026-11-16: export_docx.cjs strips
            # markers inside table cells too, so the source side must be normalised or every
            # marker-bearing cell turns into a fake difference.
            rows = [[_inline(cell.strip()) for cell in raw.strip()[1:-1].split('|')]
                    for raw in table_lines if not re.fullmatch(r'\|[\s:|\-]+\|', raw)]
            blocks.append({'kind': 'table', 'rows': rows, 'source_line': source_line})
            continue
        heading = re.match(r'^(#{1,3})\s+(.+)$', line)
        if heading:
            if source_line == 1:
                continue
            kind, text = 'heading' + str(len(heading[1])), heading[2]
        elif line.startswith('- '):
            kind, text = 'bullet', line[2:]
        else:
            kind, text = 'paragraph', re.sub(r'^>\s?', '', line)
        text = _inline(text)
        if text.strip():
            blocks.append({'kind': kind, 'text': text, 'source_line': source_line})
    return blocks


def _on(element):
    return element is not None and element.get(W + 'val', 'true').lower() in ('true', '1', 'on')


def _text(paragraph):
    # Keep every character, including ASCII, digits, minus signs and whitespace.
    chunks = []
    for element in paragraph.iter():
        if element.tag == W + 't':
            chunks.append(element.text or '')
        elif element.tag == W + 'tab':
            chunks.append('\t')
        elif element.tag == W + 'cr' or (element.tag == W + 'br' and element.get(W + 'type', 'textWrapping') == 'textWrapping'):
            chunks.append('\n')
        elif element.tag == W + 'noBreakHyphen':
            chunks.append('\u2011')
        elif element.tag == W + 'softHyphen':
            chunks.append('\u00ad')
    return ''.join(chunks)


def _toc_info(body):
    """Count fields (not instrText fragments); mark TOC paragraphs for anchoring."""
    toc_paragraphs = set()
    instructions = []
    stack = []

    def is_toc(instruction):
        return re.match(r'^\s*TOC(?:\s|$)', instruction, re.I) is not None

    def visit(element, paragraph=None):
        if element.tag == W + 'p':
            paragraph = element
            style = element.find(W + 'pPr/' + W + 'pStyle')
            if style is not None and style.get(W + 'val', '').lower().startswith('toc'):
                toc_paragraphs.add(paragraph)
        for frame in stack:
            if paragraph is not None:
                frame['paragraphs'].add(paragraph)
        if element.tag == W + 'sdt':
            gallery = element.find(W + 'sdtPr/' + W + 'docPartObj/' + W + 'docPartGallery')
            if gallery is not None and gallery.get(W + 'val', '').lower() == 'table of contents':
                toc_paragraphs.update(element.iter(W + 'p'))
        if element.tag == W + 'fldSimple':
            instruction = element.get(W + 'instr', '')
            if is_toc(instruction):
                instructions.append(instruction)
                toc_paragraphs.update(element.iter(W + 'p'))
                if paragraph is not None:
                    toc_paragraphs.add(paragraph)
        elif element.tag == W + 'fldChar':
            field_type = element.get(W + 'fldCharType')
            if field_type == 'begin':
                stack.append({'text': '', 'paragraphs': {paragraph} if paragraph is not None else set()})
            elif field_type == 'end' and stack:
                frame = stack.pop()
                if is_toc(frame['text']):
                    instructions.append(frame['text'])
                    toc_paragraphs.update(frame['paragraphs'])
        elif element.tag == W + 'instrText' and stack:
            stack[-1]['text'] += element.text or ''
        for child in element:
            visit(child, paragraph)

    visit(body)
    for frame in stack:
        if is_toc(frame['text']):
            instructions.append(frame['text'])
            toc_paragraphs.update(frame['paragraphs'])
    return toc_paragraphs, instructions


def _word_blocks(body, toc_paragraphs):
    blocks = []

    def visit(container, location):
        for index, child in enumerate(container, 1):
            child_location = '%s/%s[%d]' % (location, child.tag.rsplit('}', 1)[-1], index)
            if child.tag == W + 'p':
                text = _text(child)
                if not text.strip():
                    continue
                style = child.find(W + 'pPr/' + W + 'pStyle')
                style_name = style.get(W + 'val', '') if style is not None else ''
                if style_name in ('Heading1', 'Heading2', 'Heading3'):
                    kind = style_name.lower()
                elif child.find(W + 'pPr/' + W + 'numPr') is not None:
                    kind = 'bullet'
                else:
                    kind = 'paragraph'
                blocks.append({'kind': kind, 'text': text, 'docx_location': child_location,
                               'in_toc': child in toc_paragraphs})
            elif child.tag == W + 'tbl':
                rows = []
                merged_cell_count = 0
                for row in child.findall(W + 'tr'):
                    cells = []
                    for cell in row.findall(W + 'tc'):
                        texts = [_text(p) for p in cell.iter(W + 'p')]
                        cells.append('\n'.join(text for text in texts if text.strip()))
                        merged_cell_count += any(
                            prop.tag in (W + 'vMerge', W + 'hMerge') or
                            (prop.tag == W + 'gridSpan' and prop.get(W + 'val') != '1')
                            for prop in cell.findall(W + 'tcPr/*')
                        )
                    rows.append(cells)
                blocks.append({'kind': 'table', 'rows': rows, 'docx_location': child_location,
                               'in_toc': any(p in toc_paragraphs for p in child.iter(W + 'p')),
                               'merged_cell_count': merged_cell_count,
                               'nested_table_count': len(child.findall('.//' + W + 'tbl'))})
            elif child.tag not in (W + 'sectPr', W + 'sdtPr', W + 'sdtEndPr'):
                visit(child, child_location)

    visit(body, 'word/document.xml/body')
    return blocks


def _key(block):
    if block['kind'] == 'table':
        # The exporter never merges or nests cells, even when their text is identical.
        return ('table', tuple(tuple(row) for row in block['rows']),
                block.get('nested_table_count', 0), block.get('merged_cell_count', 0))
    return block['kind'], block['text']


def _differences(source, actual):
    # Disable the popularity heuristic: repeated labels/cells must not hide edits.
    matcher = SequenceMatcher(None, [_key(b) for b in source], [_key(b) for b in actual], autojunk=False)
    return [
        {'operation': tag, 'source_range': [i, j], 'docx_range': [a, b],
         'source_blocks': source[i:j], 'docx_blocks': actual[a:b]}
        for tag, i, j, a, b in matcher.get_opcodes() if tag != 'equal'
    ]


def _parse_xml(name, data, errors):
    try:
        return ET.fromstring(data)
    except (ET.ParseError, ValueError, LookupError) as error:
        errors.append('XML %s: %s' % (name, error))
        return None


_XSD_TOOL = None


def _xsd_module():
    """按文件路径加载同目录的 validate_docx_xsd.py 并缓存：不能靠 sys.path——本脚本在单测里是
    用 importlib 从路径加载的，工作目录与 sys.path 都不保证含「工具/」，裸 import 会 ModuleNotFoundError。"""
    global _XSD_TOOL
    if _XSD_TOOL is None:
        path = Path(__file__).with_name('validate_docx_xsd.py')
        spec = importlib.util.spec_from_file_location('validate_docx_xsd_sibling', str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _XSD_TOOL = module
    return _XSD_TOOL


def verify(root=DEFAULT_ROOT):
    """Return fresh, JSON-serializable evidence without writing or reusing reports."""
    root = Path(root)
    result = {
        'passed': False, 'errors': [], 'source_sha256': None, 'docx_sha256': None,
        'paragraph_count': 0, 'table_count': 0, 'cell_count': 0, 'h1_count': 0,
        'page_break_count': 0, 'page_break_before_count': 0, 'explicit_page_break_count': 0,
        'toc_field_count': 0, 'xml_parts': 0, 'xml_part_names': [],
        'crc_verified': False, 'update_fields': False, 'rendering_verified': False,
        'rendering_note': '未执行渲染级目视',
        'source_block_count': 0, 'docx_body_block_count': 0,
        'body_anchor': None, 'differences': [],
    }
    source_blocks = None
    try:
        source_bytes = (root / (BOOK + '.md')).read_bytes()
        result['source_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        source_blocks = _markdown_blocks(source_bytes.decode('utf-8'))
        result['source_block_count'] = len(source_blocks)
        if not source_blocks:
            result['errors'].append('Markdown 没有可比对的正文块')
    except (OSError, UnicodeError) as error:
        result['errors'].append('Markdown 读取失败: %s' % error)

    roots = {}
    try:
        docx_bytes = (root / (BOOK + '.docx')).read_bytes()
        result['docx_sha256'] = hashlib.sha256(docx_bytes).hexdigest()
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            for name, count in Counter(names).items():
                if count > 1:
                    result['errors'].append('ZIP 重复部件: ' + name)
            for required in ('[Content_Types].xml', '_rels/.rels', 'word/document.xml', 'word/settings.xml'):
                if required not in names:
                    result['errors'].append('ZIP 缺少部件: ' + required)
            result['crc_verified'] = True
            payloads = {}
            for member in members:
                if member.is_dir():
                    continue
                is_xml = member.filename.lower().endswith(('.xml', '.rels', '.svg', '.vml'))
                if is_xml:
                    result['xml_part_names'].append(member.filename)
                try:
                    data = archive.read(member)  # Reading to EOF validates each member's CRC, including binary assets.
                except (OSError, RuntimeError, zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as error:
                    result['crc_verified'] = False
                    result['errors'].append('ZIP/CRC %s: %s' % (member.filename, error))
                    continue
                payloads[member.filename] = data
                if is_xml:
                    roots[member.filename] = _parse_xml(member.filename, data, result['errors'])
            # Content types can declare XML under non-.xml extensions as well.
            types = roots.get('[Content_Types].xml')
            if types is not None:
                defaults = {e.get('Extension', '').lower(): e.get('ContentType', '')
                            for e in types if e.tag.rsplit('}', 1)[-1] == 'Default'}
                overrides = {e.get('PartName', '').lstrip('/'): e.get('ContentType', '')
                             for e in types if e.tag.rsplit('}', 1)[-1] == 'Override'}
                known = set(result['xml_part_names'])
                for name in names:
                    content_type = overrides.get(name, defaults.get(name.rsplit('.', 1)[-1].lower(), '')).lower()
                    content_type = content_type.split(';', 1)[0].strip()
                    if name not in known and (content_type.endswith('+xml') or content_type in ('application/xml', 'text/xml')):
                        result['xml_part_names'].append(name)
                        known.add(name)
                        if name in payloads:
                            roots[name] = _parse_xml(name, payloads[name], result['errors'])
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, ValueError) as error:
        result['crc_verified'] = False
        result['errors'].append('DOCX 读取失败: %s' % error)
    result['xml_parts'] = len(result['xml_part_names'])

    settings = roots.get('word/settings.xml')
    if settings is not None:
        result['update_fields'] = settings.tag == W + 'settings' and _on(settings.find(W + 'updateFields'))
    if not result['update_fields']:
        result['errors'].append('settings.xml 未启用 updateFields')

    document = roots.get('word/document.xml')
    body = document.find(W + 'body') if document is not None and document.tag == W + 'document' else None
    if body is None:
        result['errors'].append('缺少合法的 Word document/body')
    else:
        paragraphs = list(body.iter(W + 'p'))
        result['paragraph_count'] = len(paragraphs)
        result['table_count'] = sum(1 for _ in body.iter(W + 'tbl'))
        result['cell_count'] = sum(1 for _ in body.iter(W + 'tc'))
        result['h1_count'] = sum(
            1 for p in paragraphs for style in p.findall(W + 'pPr/' + W + 'pStyle')
            if style.get(W + 'val') == 'Heading1'
        )
        result['page_break_before_count'] = sum(_on(p.find(W + 'pPr/' + W + 'pageBreakBefore')) for p in paragraphs)
        result['explicit_page_break_count'] = sum(b.get(W + 'type') == 'page' for b in body.iter(W + 'br'))
        result['page_break_count'] = result['page_break_before_count'] + result['explicit_page_break_count']
        toc_paragraphs, instructions = _toc_info(body)
        result['toc_field_count'] = len(instructions)
        actual = [block for block in _word_blocks(body, toc_paragraphs) if not block.get('in_toc')]
        if source_blocks:
            first = source_blocks[0]
            # Never anchor on an arbitrary later heading or choose a best-matching suffix.
            anchor = next((i for i, block in enumerate(actual)
                           if block['kind'] != 'table' and not block.get('in_toc')
                           and first['kind'] != 'table' and block['text'] == first['text']), None)
            if anchor is None:
                result['errors'].append('未找到首个 Markdown 正文段锚点（排除目录）')
                # Still retain full differences, including a deleted/changed first paragraph.
            else:
                result['body_anchor'] = {'source_line': first['source_line'],
                                         'docx_location': actual[anchor]['docx_location'],
                                         'text': first['text'], 'prefix_block_count': anchor}
                actual = actual[anchor:]
            result['docx_body_block_count'] = len(actual)
            result['differences'] = _differences(source_blocks, actual)
            if result['differences']:
                result['errors'].append('正文有序块不一致: %d 处差异（完整内容见 differences）' % len(result['differences']))
        # 字面反引号体检：正文里的内联码标记必须在导出时剥掉，漏出来就是书面渲染缺陷。
        # 2026-11-16 起表格单元与段落同判（导出器改成走 runs()，豁免通道随之关闭）；仍豁免的只有
        # 围栏代码块的 ``` 分隔行——那是围栏本身而不是内联码没配对，去掉反引号后为空即可判别。
        def leak_texts(block):
            candidates = [cell for row in block['rows'] for cell in row] \
                if block['kind'] == 'table' else [block['text']]
            return [text for text in candidates
                    if BT in text and text.replace(BT, '').strip()]
        leaks = ['%s：%s' % (block['docx_location'], text[:40])
                 for block in actual for text in leak_texts(block)]
        result['prose_marker_leaks'] = len(leaks)
        result['prose_fence_paragraphs'] = sum(1 for block in actual
                                               if block['kind'] != 'table' and BT in block['text']
                                               and not block['text'].replace(BT, '').strip())
        result['prose_marker_leak_locations'] = leaks[:10]
        if leaks:
            result['errors'].append('正文（段落或表格单元）漏出未转换的内联码标记: %d 处（%s）'
                                    % (len(leaks), '、'.join(leaks)))
    # 官方 XSD 模式校验并入本链（2026-11-22 用户点单「把 XSD 校验接进 verify_docx 日常链」）：
    # 以前它是独立脚本，跑不跑靠人记得；并进来之后「docx 重导 → verify_docx」这一条日常动作就自带模式判定。
    # 口径说明：判定认 Part 3 Ignorable 消费视图那一档（件内 mc:Ignorable 点名的扩展命名空间按不存在处理），
    # 「原样校验违例数」照实记录不隐藏——Part 1 模式不声明 mc: 属性，那条非空是规范事实，不参与判红。
    try:
        xsd = _xsd_module().validate(str(root / (BOOK + '.docx')))
        result['xsd'] = {
            '件面': xsd['统计']['XML件面'], '通过': xsd['统计']['通过'], '违例': xsd['统计']['违例'],
            '未覆盖命名空间': xsd['统计']['未覆盖命名空间'],
            '原样校验违例合计': xsd['统计']['原样校验违例合计'],
            'Part3结构元素合计': xsd['统计']['Part3结构元素合计'],
            '模式套件摘要前12位': xsd['模式套件']['套件摘要前12位'],
            '口径': xsd['口径'],
        }
        if xsd['统计']['违例'] or xsd['统计']['未覆盖命名空间']:
            result['errors'].append('官方 XSD 模式校验未过：违例 %d 件面、未覆盖命名空间 %d（逐件见 数据/Word模式校验.json）'
                                    % (xsd['统计']['违例'], xsd['统计']['未覆盖命名空间']))
    except Exception as exc:
        result['xsd'] = {'跳过原因': str(exc)[:200]}
        result['errors'].append('官方 XSD 模式校验未能执行：%s' % str(exc)[:120])
    result['rendering_verified'], result['rendering_note'] = rendering_state(root, result['docx_sha256'])
    result['passed'] = not result['errors']
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='项目根目录，默认工具所在项目')
    args = parser.parse_args(argv)
    result = verify(args.root)
    output = args.root / REPORT
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError as error:
        result['passed'] = False
        result['errors'].append('核验 JSON 写入失败: %s' % error)
    # JSON stdout is UTF-8 even on Windows; the caller need not parse log prose.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
