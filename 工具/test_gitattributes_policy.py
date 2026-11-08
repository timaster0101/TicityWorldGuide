# -*- coding: utf-8 -*-
"""`.gitattributes` 策略闸门：`* text=auto` 在位、二进制声明只落在真二进制上、SVG 必须留在文本侧。

C151 入库前复核实测：`*.svg binary` 让三张空间图的 `git check-attr diff` 变 unset，每次 compile_book 重导后
`git diff` 只剩「Binary files differ」，提交评审读不出改动。这条回归没有别的判据看得见，故在此钉住。

判据面（统计面一并给出：扫描对象＝`.gitattributes` 全文＋`git ls-files` 现算）：
  1) `* text=auto` 恰有一行；全文件不得出现 `eol=`——写了 eol 会让几百个工作区文件下次 checkout 集体翻转，
     而本仓文档里的字节数全是工作区口径；
  2) 每个 `*.ext binary` 声明，若该扩展名有跟踪文件，则逐个必须真是二进制（前 8KiB 含 NUL 或 UTF-8 解不开）；
     无跟踪文件的按「预防性声明」放行，但处数必须报出来，防止日后往里塞文本扩展名而无人对账；
  3) SVG 是纯文本 XML，必须留在文本侧；三张空间图的 `git check-attr` 不得出现 `diff: unset`；
  4) 违例注入负测全部走合成输入（含伪造的扩展名→文件映射），不碰被守护仓库。
"""
import io
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITATTR = os.path.join(ROOT, '.gitattributes')
HEAD_BYTES = 8192


def git(*args):
    return subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8').stdout


def ls(*pattern):
    return [p for p in git('ls-files', *pattern).split('\n') if p.strip()]


def parse(text):
    """把 `.gitattributes` 拆成四份读数：text=auto 行数、eol 行、{扩展名: 声明行}、svg 声明行。"""
    lines = [ln.strip() for ln in text.split('\n') if ln.strip() and not ln.strip().startswith('#')]
    binary = {}
    for ln in lines:
        if ln.endswith(' binary') and ln.startswith('*.'):
            binary[ln[2:].split()[0].lower()] = ln
    return {
        'text_auto': sum(1 for ln in lines if ln == '* text=auto'),
        'eol': [ln for ln in lines if 'eol=' in ln],
        'binary': binary,
        'svg_declared': [ln for ln in lines if ln.lower().startswith('*.svg')],
    }


def looks_binary(head):
    if b'\x00' in head:
        return True
    trimmed = head
    for _ in range(4):
        try:
            trimmed.decode('utf-8')
            return False
        except UnicodeDecodeError:
            # 定长切片可能正好切在中文字符中间，先剥掉尾部残缺字节再判
            trimmed = trimmed[:-1]
    return True


def is_binary_file(rel):
    with io.open(os.path.join(ROOT, rel), 'rb') as f:
        return looks_binary(f.read(HEAD_BYTES))


def violations(parsed, tracked):
    """纯函数判据：输入解析结果与 {扩展名: [仓内相对路径]}，输出违例清单（空＝通过）。"""
    out = []
    if parsed['text_auto'] != 1:
        out.append('`* text=auto` 行数=%d（应为 1）' % parsed['text_auto'])
    if parsed['eol']:
        out.append('出现了 eol 声明：%r（本仓文档字节数全是工作区口径，写 eol 会让 checkout 集体翻转）' % parsed['eol'])
    if parsed['svg_declared']:
        out.append('SVG 被声明为二进制：%r（三张空间图是纯文本 XML，diff 会退化成「Binary files differ」）'
                   % parsed['svg_declared'])
    for ext, line in sorted(parsed['binary'].items()):
        for rel in tracked.get(ext, []):
            with io.open(os.path.join(ROOT, rel), 'rb') as f:
                if not looks_binary(f.read(HEAD_BYTES)):
                    out.append('%s 把 %s 当二进制，但它前 %d 字节无 NUL 且 UTF-8 可解' % (line, rel, HEAD_BYTES))
    return out


def preview_extensions(parsed, tracked):
    return sorted(ext for ext in parsed['binary'] if not tracked.get(ext))


class GitAttributesPolicy(unittest.TestCase):
    def setUp(self):
        with io.open(GITATTR, encoding='utf-8', newline='') as f:
            self.text = f.read()
        self.parsed = parse(self.text)
        self.tracked = {ext: ls('*.%s' % ext) for ext in sorted(self.parsed['binary'])}

    def test_现值合规(self):
        v = violations(self.parsed, self.tracked)
        self.assertEqual(v, [], '策略判据不通过：%r' % v)

    def test_svg_在文本侧且可_diff(self):
        self.assertEqual(self.parsed['svg_declared'], [])
        svg = ls('*.svg')
        self.assertEqual(len(svg), 3, '空间图应为三张，取到 %r' % svg)
        out = git('check-attr', 'diff', 'text', '--', *svg)
        self.assertNotIn('diff: unset', out, 'SVG 的 diff 被关掉＝binary 宏仍在位：%s' % out)
        self.assertIn('text: auto', out)

    def test_声明覆盖与统计面(self):
        used = {ext: len(f) for ext, f in self.tracked.items() if f}
        prev = preview_extensions(self.parsed, self.tracked)
        self.assertEqual(sorted(used), ['docx', 'png'], '本轮实际生效的二进制声明应只有 png／docx：%r' % used)
        self.assertEqual(sum(used.values()), 7, 'png 6 枚＋docx 1 枚：%r' % used)
        self.assertEqual(len(prev), 17, '预防性（无跟踪文件）声明处数变了要重取读数：%r' % prev)
        self.assertEqual(len(self.parsed['binary']), 19)
        for ext in used:
            for rel in self.tracked[ext]:
                self.assertTrue(is_binary_file(rel), '%s 其实不是二进制' % rel)

    def test_违例注入必须判红(self):
        clean = parse('* text=auto\n*.png binary\n')
        png_map = {'png': ls('*.png')}
        self.assertEqual(violations(clean, png_map), [], '干净夹具应判绿，否则后面的注入没有意义')
        self.assertTrue(any('SVG 被声明为二进制' in v
                            for v in violations(parse('* text=auto\n*.png binary\n*.svg binary\n'),
                                                dict(png_map, svg=ls('*.svg')))))
        self.assertTrue(any('text=auto' in v for v in violations(parse('*.png binary\n'), png_map)))
        self.assertTrue(any('eol=' in v for v in violations(parse('* text=auto eol=lf\n*.png binary\n'), png_map)))
        # 文本被声明成二进制：把真文本文件挂到声明下的扩展名上（合成映射，不碰仓库）
        self.assertTrue(any('UTF-8 可解' in v
                            for v in violations(parse('* text=auto\n*.md binary\n'), {'md': ['AI创作使用手册.md']})))
        # 统计面：无跟踪文件的声明计入预防性，不算违例但必须报数
        self.assertEqual(preview_extensions(parse('* text=auto\n*.png binary\n*.tif binary\n'), png_map), ['tif'])

    def test_跟踪集里若混进文本扩展名声明会当场判红(self):
        # 用仓内真实文本文件构造映射（txt 在仓内有 474 个跟踪文件，绝不该声明 binary）
        txt = ls('*.txt')
        self.assertTrue(txt, '取不到 txt 跟踪文件，夹具失效')
        v = violations(parse('* text=auto\n*.txt binary\n'), {'txt': txt[:3]})
        self.assertTrue(v, '把 474 个 .txt 声明成 binary 竟然不判红')


if __name__ == '__main__':
    unittest.main(verbosity=2)
