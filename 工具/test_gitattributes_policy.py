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
  4) 违例注入负测全部走合成输入（含伪造的扩展名→文件映射），不碰被守护仓库；
  5) 换行口径自洽：被文档引用的那几个件必须满足「工作区字节 − 索引 blob 字节 == CRLF 数」且行尾二态，
     三份设计文档必须仍是 `w/lf`。这条管的是读数会不会被机器误读，不是内容本身——
     `core.autocrlf=true` 的机器上重新检出会把 w/lf 的文本翻成 CRLF，下一轮用 `wc -c` 直接重取就会把
     「行数」当成「内容漂移」误报，所以此处当场把两个口径的关系钉死，翻转一发生就判红而不是静默。

跑法：python 工具/test_gitattributes_policy.py（工作目录＝设定集根）
"""
import io
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITATTR = os.path.join(ROOT, '.gitattributes')
HEAD_BYTES = 8192

# 文档里被当作「本轮读数」引用的件：三份设计文档（工作区 LF）＋手册（LF）＋质量核验报告（CRLF）＋裁定 JSON（CRLF）。
# 这四态混在一起正是本条判据要管的：同一仓里工作区行尾本就两套并存，只有「差值==CRLF 数」这条关系是全仓不变的。
READOUT_FILES = [
    '设计/2026-11-03-待办移交清单.md',
    '设计/2026-10-31-分期路线图.md',
    '设计/2026-10-31-卡面标准样式规范.md',
    'AI创作使用手册.md',
    '质量核验报告.md',
    '数据/设定裁定记录.json',
]
# 记为 LF 口径的三件设计文档：工作区一旦翻成 CRLF，本节下面那些字节数就不再是 `wc -c` 能直接重取的数。
LF_READOUT_DOCS = READOUT_FILES[:4]


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


def eol_table():
    """`git ls-files --eol` 的行 → {路径: (索引口径, 工作区口径, 属性)}；行格式＝`i/x w/y attr<TAB>path`。"""
    out = {}
    for ln in git('ls-files', '--eol').split('\n'):
        if not ln.strip():
            continue
        idx, work, attr, path = ln.split(None, 3)
        out[path.split('\t', 1)[-1].strip()] = (idx, work, attr)
    return out


def staged_blobs():
    """路径 → 索引 blob 的 sha。先 `ls-files -s` 拿哈希、再单独 `cat-file -s` 问大小，
    不走 `<rev>:<path>` 那种参数——它在 MSYS 下会被打碎成假读数（本仓记过一次）。"""
    out = {}
    for ln in git('ls-files', '-s').split('\n'):
        if not ln.strip():
            continue
        meta, path = ln.split('\t', 1)
        mode, sha, stage = meta.split()
        if stage == '0':
            out[path.strip()] = sha
    return out


def blob_size(sha):
    return int(git('cat-file', '-s', sha).strip())


def flipped_docs(table, docs):
    """纯函数：从 `eol_table()` 的形态里挑出工作区不再是 LF 的那些（不在表里也算，＝该件已被移出跟踪）。"""
    return [rel for rel in docs if table.get(rel, ('', 'w/missing'))[1] != 'w/lf']


def readout_state(work_bytes, blob_bytes, crlf, lf_only):
    """纯函数判据：工作区与索引两个口径必须只差在 CRLF 上，且行尾必须二态。

    work_bytes − blob_bytes == crlf 是「blob 全 LF、工作区把每个换行多写一个 CR」这条唯一可能的关系；
    不等只有三种解释——内容真漂移、工作区有裸 LF 与 CRLF 混排、或该文件本就不该被当文本引用。
    """
    out = []
    if work_bytes - blob_bytes != crlf:
        out.append('工作区 %d − blob %d ＝ %d 不等于 CRLF 数 %d（内容漂移或行尾非二态）'
                   % (work_bytes, blob_bytes, work_bytes - blob_bytes, crlf))
    if crlf and lf_only:
        out.append('行尾混排：CRLF %d 且裸 LF %d，两个口径都无法互推' % (crlf, lf_only))
    return out


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

    def test_工作区与索引两个口径只差在CRLF上(self):
        # 统计面：扫描对象＝READOUT_FILES 这 6 个被文档引用字节的件。
        # 两层判据分开：行尾二态永远判（与内容无关，改文档的那一轮照样有效）；
        # 「工作区字节 − blob 字节 == CRLF 数」只在件相对索引干净时判——文档刚改完未提交时盘上本就领先 blob，
        # 那时它必然不等，把它算成违例就是假红，所以脏件逐个点名、不静默跳过。
        blobs = staged_blobs()
        dirty = []
        for rel in READOUT_FILES:
            with self.subTest(f=rel):
                self.assertIn(rel, blobs, '%s 不在索引里，本条判据无法自证' % rel)
                with io.open(os.path.join(ROOT, rel), 'rb') as f:
                    raw = f.read()
                crlf = raw.count(b'\r\n')
                lf_only = raw.count(b'\n') - crlf
                self.assertFalse(crlf and lf_only, '%s 行尾混排：CRLF %d 且裸 LF %d，两个口径无法互推'
                                 % (rel, crlf, lf_only))
                if git('status', '--porcelain', '--', rel).strip():
                    dirty.append(rel)
                    continue
                v = readout_state(len(raw), blob_size(blobs[rel]), crlf, lf_only)
                self.assertEqual(v, [], '%s 的两个口径不再自洽：%r（工作区 %d／blob %d／CRLF %d／裸LF %d）'
                                 % (rel, v, len(raw), blob_size(blobs[rel]), crlf, lf_only))
        if dirty:
            # 措辞按内容分档：这是编辑态说明，不是违例，判据本身仍以绿收。
            print('\n  [口径对拍跳过（盘上领先索引，属正常编辑态）]：%r' % dirty)

    def test_记为LF口径的设计文档翻成CRLF即判红(self):
        """本机 `core.autocrlf=true`，重新检出会把 w/lf 的文本写成 CRLF；那时 `wc -c` 重取得到的数比本节记的多出「行数」，
        会被误读成内容漂移。本条不防翻转（防它要动 eol，而 eol 一写就是几百个文件集体翻转，见判据面 1），
        只保证翻转一旦发生当场报红并给出修法。"""
        table = eol_table()
        flipped = flipped_docs(table, LF_READOUT_DOCS)
        self.assertEqual(
            flipped, [],
            '这些文档的工作区已不再是 LF：%r。修法二选一并同步本节：`git -c core.autocrlf=false checkout -- <file>` '
            '把盘改回 LF（推荐，不改口径），或按 blob 口径重取全部字节读数并在节首写明口径已换。')

    def test_口径判据自身的违例注入(self):
        # 纯函数夹具，不碰仓库：三种错法必须各自判红，两种正常态必须判绿
        self.assertEqual(readout_state(100, 100, 0, 10), [], 'LF 工作区＝blob 的干净态被误判')
        self.assertEqual(readout_state(110, 100, 10, 0), [], 'CRLF 工作区差值恰等 CRLF 数的干净态被误判')
        self.assertTrue(readout_state(104, 100, 2, 8), '差值 4 而 CRLF 只有 2（＝内容漂移）竟然不判红')
        self.assertTrue(readout_state(110, 100, 10, 3), 'CRLF 与裸 LF 混排竟然不判红')
        self.assertTrue(readout_state(99, 100, 0, 9), '工作区比 blob 还小（截断）竟然不判红')
        # 翻转判据的同一注入：合成表里把一个 LF 文档写成 w/crlf、一个写成缺项，两个都必须被抓到
        fake = {'a.md': ('i/lf', 'w/lf', 'attr/text=auto'), 'b.md': ('i/lf', 'w/crlf', 'attr/text=auto')}
        self.assertEqual(flipped_docs(fake, ['a.md']), [], '干净态被误判为翻转')
        self.assertEqual(flipped_docs(fake, ['a.md', 'b.md', 'c.md']), ['b.md', 'c.md'],
                         'w/crlf 与不在 eol 表里的件竟然没被抓到')


if __name__ == '__main__':
    unittest.main(verbosity=2)
