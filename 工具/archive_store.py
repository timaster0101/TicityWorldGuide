# -*- coding: utf-8 -*-
"""仓内归档区（`backup/`、`vibe_images/`）的统一解析器。

动机（2026-11-27 项目结构整理 §55.76）：`backup/数据`（558MB）、`backup/vibe_images`（173MB）、
`backup/同级vibe_images`（16MB）与仓内 `vibe_images/`（848MB）合计约 1.59GB，全部不被 git 跟踪
（`git ls-files backup` 只有 10 件顶层明细 json／md／py），却仍被闸门与生成器读取：母图池、卡面
文案底稿、`verify_pre_e1_archive` 的逐张 sha 对拍、`test_image_assets` 的归档面计数。把它们整体
移出仓外后，读取方必须走同一个解析口径，否则会出现两种坏形态：

  ① 判据直接报「文件不在盘」——那不是数据坏了，是路径口径分叉；
  ② 更糟的：判据把「移走了」当成「验过了」，空扫描面打印通过（本仓库明令禁止的假绿）。

所以这里的立场是：**解析器只负责找到文件，找不到就说找不到**。闸门拿到的仍是具体路径，
盘上缺件照样逐条判红，不做任何「归档了就算过」的降级。

口径：
  * `resolve(rel)` 先在仓内找（仓内优先，保证未被外置的件行为不变），找不到再到归档根找；
    两处都没有时返回仓内路径，让调用方在自己那句「文件不在盘」上判红，而不是这里抛异常。
  * **只在 `root` 就是本仓库根时才回落到归档根**：闸门的负测夹具把 `root` 指到临时目录，
    夹具里故意缺的文件不许被真实归档件「补上」，否则违例负测会静默失效。
  * 归档根可由环境变量 `TIHU_ARCHIVE_ROOT` 覆盖（换机器／换盘时不用改代码）。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV = 'TIHU_ARCHIVE_ROOT'
#: 归档根与仓库同级（用户 2026-11-27 指定：挪到 `..\钛湖城卡面备份` 下面）。相对路径原样保留，
#: 于是那边就是一棵 `backup/`、一棵 `vibe_images/`，与本文件 `EXTERNALISED` 一一对应。
#: 换机器／换盘用环境变量 `TIHU_ARCHIVE_ROOT` 覆盖，不鼓励改这一行。
DEFAULT_ARCHIVE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '钛湖城卡面备份')

#: 已外置的子树（相对仓库根）。列在这里是为了让 `describe()` 能自证「哪些树不在仓内了」，
#: 以及让测试能断言解析器认的正是这几棵，不是随手一个前缀。
EXTERNALISED = (
    'backup/数据',
    'backup/vibe_images',
    'backup/同级vibe_images',
    'vibe_images',
)


def _norm(rel):
    return str(rel).replace('\\', '/')


def archive_root():
    return os.environ.get(ENV) or DEFAULT_ARCHIVE


def repo_root():
    return ROOT


def _same_root(root):
    try:
        return os.path.realpath(root) == os.path.realpath(ROOT)
    except OSError:
        return False


def candidates(rel, root=None):
    """返回候选路径列表：仓内那条永远第一，归档根那条只在 root 是本仓库根时补上。"""
    base = root if root is not None else ROOT
    rel = _norm(rel)
    out = [os.path.join(base, rel.replace('/', os.sep))]
    if _same_root(base):
        out.append(os.path.join(archive_root(), rel.replace('/', os.sep)))
    return out


def resolve(rel, root=None):
    """找到就返回那条真实路径；两处都没有时返回仓内路径（调用方据此判红）。"""
    cands = candidates(rel, root)
    for p in cands:
        if os.path.isfile(p):
            return p
    return cands[0]


def exists(rel, root=None):
    return os.path.isfile(resolve(rel, root))


def resolve_dir(rel, root=None):
    """目录版 `resolve()`：找**目录**，两处都没有时返回仓内路径。

    `resolve()` 只认文件，整棵树外置后拿 `resolve('backup/数据/图集')` 会一直返回仓内那条
    不存在的老路径（首版就是这样，`oss_gallery.archive_files()` 读到 0 件）。
    """
    cands = candidates(rel, root)
    for p in cands:
        if os.path.isdir(p):
            return p
    return cands[0]


def exists_dir(rel, root=None):
    return os.path.isdir(resolve_dir(rel, root))


def is_externalised(rel):
    """这条相对路径是否落在已外置的子树下（只判前缀，不看盘面）。"""
    rel = _norm(rel)
    return any(rel == t or rel.startswith(t + '/') for t in EXTERNALISED)


def where(rel, root=None):
    """`repo` / `archive` / `missing`——给报告与排障用。"""
    cands = candidates(rel, root)
    if os.path.isfile(cands[0]):
        return 'repo'
    if len(cands) > 1 and os.path.isfile(cands[1]):
        return 'archive'
    return 'missing'


def describe():
    """自检读数：归档根在不在、各棵外置树在归档根里还剩多少件。"""
    aroot = archive_root()
    trees = {}
    for rel in EXTERNALISED:
        here = os.path.join(ROOT, rel.replace('/', os.sep))
        there = os.path.join(aroot, rel.replace('/', os.sep))
        trees[rel] = {
            '仓内件数': _count(here),
            '归档件数': _count(there),
        }
    return {
        '仓库根': ROOT,
        '归档根': aroot,
        '归档根存在': os.path.isdir(aroot),
        '外置树': trees,
    }


def _count(path):
    if not os.path.isdir(path):
        return 0
    n = 0
    for _dirpath, _dirnames, filenames in os.walk(path):
        n += len(filenames)
    return n


if __name__ == '__main__':
    import json
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
