# -*- coding: utf-8 -*-
"""图集异地镜像：把 数据/图集 逐件按 sha256 对拍到第二处，并在镜像侧留一份可自证的对拍单。

为什么要有它：`数据/图集/` 因 .gitignore 不入仓，回滚只能靠本机副本；本机只有一个物理盘（Disk 0），
`D:/bak` 与 `C:` 同盘异分区，抗不了整盘损坏。这个脚本至少把「第二处副本 + 逐件 sha 对拍单」做出来，
换盘或加盘之后一条命令就能把镜像挪到真异盘上，不必重新决定放什么。

口径：
  - 源清单是 数据/图集清单.json（661 件，逐件 sha256），不现场遍历目录猜范围；
  - 目标侧同名同 sha 就跳过，不同则覆盖并记账；源侧缺件、清单缺件都记为问题，不静默跳过；
  - 只增改，不删目标侧多余文件（`--prune` 才删，且默认关闭——镜像脚本不该顺手销毁东西）。

跑法：
    python 工具/mirror_gallery.py --to D:\\bak\\钛湖城图集-镜像            对拍并补齐
    python 工具/mirror_gallery.py --to D:\\bak\\钛湖城图集-镜像 --verify   只核对，不写
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / '数据' / '图集'
MANIFEST = ROOT / '数据' / '图集清单.json'
REPORT_NAME = '镜像对拍.json'


def jload(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


GALLERY_PREFIX = '数据/图集/'


def entries(manifest):
    """清单里的逐件面：[(相对路径, sha256, 字节)]，路径相对 数据/图集。

    清单侧键是 `逐件`，每条 `路径` 写的是仓内相对路径（`数据/图集/D01/xx.png`），这里剥掉前缀，
    免得调用方把仓根和 数据/图集 两层拼重。
    """
    out = []
    for e in manifest.get('逐件') or manifest.get('条目') or manifest.get('files') or manifest.get('items') or []:
        rel = e.get('相对路径') or e.get('路径') or e.get('path') or e.get('file')
        if not rel:
            continue
        if rel.startswith(GALLERY_PREFIX):
            rel = rel[len(GALLERY_PREFIX):]
        out.append((rel, e['sha256'], e.get('字节') or e.get('bytes')))
    return out


def plan(files, src_root, dst_root):
    """逐件定策：copy（目标没有或不同）／same（已相符）／missing_src（源缺件）。"""
    rows = []
    for rel, sha, size in files:
        sp = Path(src_root) / rel
        dp = Path(dst_root) / rel
        if not sp.exists():
            rows.append({'相对路径': rel, '动作': 'missing_src'})
            continue
        if dp.exists() and dp.stat().st_size == size:
            got = sha256(dp)
            if got == sha:
                rows.append({'相对路径': rel, '动作': 'same', 'sha256': sha})
                continue
        rows.append({'相对路径': rel, '动作': 'copy', 'sha256': sha, '字节': size})
    return rows


def run(rows, src_root, dst_root, verify):
    copied, failed = [], []
    for r in rows:
        if r['动作'] != 'copy' or verify:
            continue
        sp = Path(src_root) / r['相对路径']
        dp = Path(dst_root) / r['相对路径']
        dp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sp, dp)
        got = sha256(dp)
        if got != r['sha256']:
            failed.append('%s 拷后 sha 不符（%s != %s）' % (r['相对路径'], got[:12], r['sha256'][:12]))
        else:
            copied.append(r['相对路径'])
    return copied, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--to', required=True, help='镜像根目录（会得到与 数据/图集 同构的树）')
    ap.add_argument('--verify', action='store_true', help='只核对，不写')
    ap.add_argument('--prune', action='store_true', help='删掉目标侧清单外文件（默认不删）')
    args = ap.parse_args()

    dst = Path(args.to)
    manifest = jload(MANIFEST)
    files = entries(manifest)
    if not files:
        print('❌ 清单里读不到逐件面：%s' % MANIFEST)
        return 1
    rows = plan(files, GALLERY, dst)
    same = sum(1 for r in rows if r['动作'] == 'same')
    copy = [r for r in rows if r['动作'] == 'copy']
    missing = [r['相对路径'] for r in rows if r['动作'] == 'missing_src']
    total_bytes = sum(r.get('字节') or 0 for r in copy)
    print('清单 %d 件：已相符 %d／待拷 %d（%.1f MB）／源缺件 %d'
          % (len(rows), same, len(copy), total_bytes / 1048576.0, len(missing)))
    for m in missing[:10]:
        print('   ✗ 源缺件 %s' % m)
    if args.verify:
        print('（只核对）目标侧相符 %d／%d' % (same, len(rows)))
        return 0 if not missing else 1
    dst.mkdir(parents=True, exist_ok=True)
    copied, failed = run(rows, GALLERY, dst, False)
    for f in failed[:10]:
        print('   ✗ %s' % f)
    report = {
        '口径': '逐件 sha256 对拍；只增改不删（--prune 才删）',
        '源': str(GALLERY), '目标': str(dst),
        '统计': {'清单件数': len(rows), '本轮已相符': same, '本轮新拷或覆盖': len(copied),
                 '源缺件': len(missing), '拷后不符': len(failed)},
        '新拷或覆盖': copied,
        '源缺件': missing,
        '逐件': rows,
    }
    with io.open(dst / REPORT_NAME, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('✅ 新拷或覆盖 %d 件，失败 %d 件；对拍单 %s' % (len(copied), len(failed), dst / REPORT_NAME))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
