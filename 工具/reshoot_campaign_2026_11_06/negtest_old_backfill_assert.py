# -*- coding: utf-8 -*-
"""C136 的复现器：改之前那版 backfill（按修订钉 `6acbbad`）的容器前置断言，拿 C133 冻结重投那 3 枚真图跑一次，看它到底崩不崩。

§55.7 原先写的是「照已提交断言推它会崩，本轮没让它真崩过一次」——本文件把那条推断换成读数。
钉修订而不是读 HEAD：C136 的修复（446214e）已经把那条断言换掉了，读 HEAD 等于拿改完的代码复现改之前的崩溃。

三个案例（缺一即判红）：
  A 真读数：容器画像取 `container_profile.json` 的现读值（3/3 都是 caBX=0／iTXt≥1），档串名用真实文件名
    → 必须停在 `caBX 不在位，不能占格`，且真源零落笔。
  B 变异对照（同钉版 6acbbad）：把同 3 行的容器画像改回旧通道（caBX=1／iTXt=0）、档串名换成含 `C123新串-v02`
    → 必须放行并落笔 added=3；同时证明它写进备注的是格式串里那个**写死的** `caBX=1、iTXt=0`，
      与磁盘上真实的 (0,1) 相反——这才是「前置断言不可沿用」的完整代价：不只是崩，不崩还会记错画像。
  C 现工作树版：真实容器读数 (0,1) ＋ 只把档串名换成该脚本自己认的 `-v02`（越过第 66 行的批次串名钉，
    那条属 9g 批次口径、不属 C136）→ 必须放行落笔，且抬头按实测打印 `caBX=0、iTXt=1`。
    这一案补的是 §55.7 那条「改后代码只被片段级 exec 自测覆盖、没跑过一次真实落笔」的读数。

被检脚本 A/B 现取 `git show HEAD:工具/batch9g_2026_11_06/backfill_batch9g.py`，C 现取工作树同一文件，都不手抄第二份。
沙箱根在仓库外（`ROOT = 脚本上三级` 自然指到临时目录），跑前跑后各取一次真源 `数据/开图清单.json` 的 sha 自证未被写过。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/negtest_old_backfill_assert.py
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
REPO_MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
PROFILE = os.path.join(HERE, 'container_profile.json')
SUB = '工具/batch9g_2026_11_06'
TARGET = SUB + '/backfill_batch9g.py'
OLD_REV = '6acbbad'          # 带旧通道断言那一版；C136 的修复在 446214e 把它换掉了
OLD_ASSERT = "'caBX 不在位，不能占格'"
PREFIX = 'old_backfill_neg_'
IDS = ['D03', 'L061', 'L066']

CLEAN = '远景无越权塔群、无塔吊入画，日面在框内右低，画风达标（本条只记人工读数，不代签验收。）'


def head_source():
    """取「带旧通道断言」那一版回填脚本——按修订钉死，不取 HEAD。

    C136 的修复本身就把 :62 那条断言换掉了，HEAD 会随修复一起前进；
    复现器若读 HEAD，等于拿改完的代码去复现改之前的崩溃，A 案会永远打不出 `caBX 不在位`。
    所以钉 6acbbad，并自证钉到的确实是带旧断言那一版（字面量不在就停，不静默放行）。
    """
    r = subprocess.run(['git', '-c', 'core.quotePath=false', 'show', OLD_REV + ':' + TARGET],
                       capture_output=True, cwd=ROOT, encoding='utf-8')
    assert r.returncode == 0, r.stderr[:200]
    assert OLD_ASSERT in r.stdout, (OLD_REV, '钉的修订里没有旧通道断言 %r，复现器的 A 案无从谈起' % OLD_ASSERT)
    return r.stdout


def build(tmp, source, rows):
    d = tmp / SUB
    d.mkdir(parents=True, exist_ok=True)
    (tmp / '数据').mkdir(parents=True, exist_ok=True)
    (d / 'backfill_batch9g.py').write_text(source, encoding='utf-8', newline='\n')
    (d / 'batch9g_measure.json').write_text(
        json.dumps({'rows': rows}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    (d / 'readings_draft.json').write_text(
        json.dumps({r['id']: CLEAN for r in rows}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    with io.open(REPO_MANIFEST, encoding='utf-8') as fp:
        man = json.loads(fp.read())
    keep = [{k: it[k] for k in ('id', 'type', 'size', 'status') if k in it}
            for it in man['items'] if it['id'] in IDS]
    (tmp / '数据' / '开图清单.json').write_text(
        json.dumps({'items': keep}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    (tmp / '数据' / '开图验收备注.json').write_text(
        json.dumps({'备注': {}}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    return keep


def run(tmp):
    return subprocess.run([sys.executable, '-X', 'utf-8', str(tmp / SUB / 'backfill_batch9g.py')],
                          capture_output=True, cwd=str(tmp), encoding='utf-8', errors='replace')


def main():
    lines, rc = [], 0
    with io.open(REPO_MANIFEST, 'rb') as fh:
        sha_before = hashlib.sha256(fh.read()).hexdigest()[:12]
    source = head_source()
    with io.open(PROFILE, encoding='utf-8') as _fh:
        prof = json.loads(_fh.read())
    real = [r for g in prof['groups'] if g['group'] == 'C133冻结重投' for r in g['rows']]
    assert sorted(r['file'].split('-')[0] for r in real) == IDS, real
    dims = {'D03': '1792x1024', 'L061': '1024x1536', 'L066': '1024x1536'}
    shas = {'D03': '3e7a92f0ffdc', 'L061': '53f73801ab47', 'L066': 'f722fa2393bc'}

    def rows_for(mode):
        out = []
        for r in real:
            eid = r['file'].split('-')[0]
            v02 = mode in ('mutated', 'real_but_v02')
            name = r['file'].replace('C133冻结重投-v01', 'C123新串-v02') if v02 else r['file']
            old_profile = mode == 'mutated'
            out.append({'id': eid, 'file': name, 'dims': dims[eid], 'bytes': r['bytes'], 'sha256_12': shas[eid],
                        'container': ({'cabx': 1, 'itxt': 0} if old_profile
                                      else {'cabx': r['cabx'], 'itxt': r['itxt']}),
                        '逐字相等': True, 'size_match': True})
        return out

    tmp = Path(tmpdir := tempfile.mkdtemp(prefix=PREFIX))
    try:
        # 案例 A —— 真读数必须崩在容器断言
        build(tmp, source, rows_for('real'))
        a = run(tmp)
        err = (a.stderr or '').strip().splitlines()
        tail = err[-1] if err else ''
        a_ok = a.returncode != 0 and 'caBX 不在位' in tail
        rc |= 0 if a_ok else 1
        lines.append('%s A 真读数（caBX=0／iTXt=1，真实档串名）→ 退出码 %d，末行：%s'
                     % ('✓' if a_ok else '✗', a.returncode, tail[:110]))
        lines.append('   A 落笔与否：stdout=%r' % ((a.stdout or '').strip()[-60:]))

        # 案例 B —— 变异对照必须放行，并写出与磁盘相反的容器画像字面量
        shutil.rmtree(tmp / '数据')
        shutil.rmtree(tmp / SUB)
        build(tmp, source, rows_for('mutated'))
        b = run(tmp)
        notes = json.loads((tmp / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))
        wrote = sum(len(v) for v in notes['备注'].values())
        lit = ['caBX=1、iTXt=0' in n for v in notes['备注'].values() for n in v]
        b_ok = b.returncode == 0 and wrote == 3 and len(lit) == 3 and all(lit)
        rc |= 0 if b_ok else 1
        lines.append('%s B 变异对照（改回 caBX=1／iTXt=0 的旧通道画像）→ 退出码 %d，备注写入 %d 条，'
                     '抬头含写死字面量「caBX=1、iTXt=0」%d/%d 条'
                     % ('✓' if b_ok else '✗', b.returncode, wrote, sum(lit), len(lit)))
        lines.append('   B stdout 末行：%s' % (b.stdout or '').strip().splitlines()[-1])

        # 案例 C —— 现工作树版 + 真实容器读数（只把批次串名换成它自己认的 -v02，为越过第 66 行的批次钉）
        # 目的：把 §55.7「改后代码只被片段级 exec 覆盖、没跑过一次真实落笔」那条换成整脚本落笔读数。
        with io.open(os.path.join(ROOT, TARGET), encoding='utf-8') as _fp:
            work = _fp.read()
        tmpc = Path(tempfile.mkdtemp(prefix=PREFIX))
        try:
            build(tmpc, work, rows_for('real_but_v02'))
            c = run(tmpc)
            cn = json.loads((tmpc / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))
            cwrote = sum(len(v) for v in cn['备注'].values())
            clit = ['caBX=0、iTXt=1' in n for v in cn['备注'].values() for n in v]
            c_ok = c.returncode == 0 and cwrote == 3 and len(clit) == 3 and all(clit)
            rc |= 0 if c_ok else 1
            lines.append('%s C 现工作树版（真实 caBX=0／iTXt=1）→ 退出码 %d，备注写入 %d 条，'
                         '抬头按实测打印「caBX=0、iTXt=1」%d/%d 条'
                         % ('✓' if c_ok else '✗', c.returncode, cwrote, sum(clit), len(clit)))
            lines.append('   C stdout 末行：%s' % (c.stdout or '').strip().splitlines()[-1])
        finally:
            shutil.rmtree(tmpc, ignore_errors=True)
            lines.append('%s 临时目录已删：%s 存在=%s' % ('C', tmpc.name, tmpc.exists()))

        with io.open(REPO_MANIFEST, 'rb') as _handle:
            sha_after = hashlib.sha256(_handle.read()).hexdigest()[:12]
        same = sha_after == sha_before
        rc |= 0 if same else 1
        lines.append('%s 真源未被写过：仓库 数据/开图清单.json sha12 跑前 %s = 跑后 %s'
                     % ('✓' if same else '✗', sha_before, sha_after))
        residue = [p.name for p in Path(ROOT).rglob('*') if PREFIX in p.name]
        rc |= 1 if residue else 0
        lines.append('%s 仓库内 %s 残留 %d' % ('✓' if not residue else '✗', PREFIX, len(residue)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        lines.append('临时目录已删：%s 存在=%s' % (os.path.basename(tmpdir), os.path.exists(tmpdir)))
    print('\n'.join(lines))
    if rc == 0:
        print('✅ C136 复现成立：已提交版断言在 3 枚真实重投格上确实当场判停；改回旧通道画像才会放行，'
              '而放行时写进备注的容器画像是格式串里写死的、与磁盘读数相反；'
              '现工作树版拿真实读数放行且抬头按实测打印。')
    else:
        print('❌ 复现不成立，上面任一 ✗ 都要先查夹具再谈裁定。')
    return rc


from pathlib import Path  # noqa: E402  (build/run 用 Path 拼接，放最后免得太长)

if __name__ == '__main__':
    sys.exit(main())
