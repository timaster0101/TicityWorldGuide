# -*- coding: utf-8 -*-
"""四向图集扩展名归一：JPEG 字节配 .jpg，真 PNG 保持 .png。

只改文件名，一个字节都不动；不生成、不重抽、不裁剪任何图片。
逐文件 sha256 改名前后比对，不一致立即中止并报告（宁可停在半路，也不要"看起来改完了"）。

跑法：python 工具/rename_gallery_ext.py（工作目录＝设定集根）
重复跑安全：已合规的格子跳过，真 PNG 不动。
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / '数据' / '开图清单.json'
JPEG_MAGIC = b'\xff\xd8\xff'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
OK_EXT = ('.jpg', '.jpeg')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head8(path):
    with path.open('rb') as fh:
        return fh.read(8)


def plan_renames(items):
    """返回 (待改列表, 已合规数, 真PNG保留列表)。待改项＝(Path, Path)。"""
    todo, compliant, real_png = [], 0, []
    seen = set()
    for item in items:
        for rel in item.get('image_file') or []:
            path = ROOT / rel
            if rel in seen:
                continue
            seen.add(rel)
            if not path.is_file():
                sys.exit('判红：%s（%s）在清单里但磁盘上没有，先修清单再改名。' % (rel, item['id']))
            head = head8(path)
            if head == PNG_MAGIC:
                real_png.append(rel)
                continue
            if head[:3] != JPEG_MAGIC:
                sys.exit('判红：%s 既不是 JPEG 也不是 PNG 字节头（%s），拒绝改名。' % (rel, head[:3].hex()))
            if path.suffix.lower() in OK_EXT:
                compliant += 1
                continue
            target = path.with_suffix('.jpg')
            if target.exists():
                sys.exit('判红：%s 的目标 %s 已存在，可能是重名，中止以免覆盖。' % (rel, target.relative_to(ROOT)))
            todo.append((path, target))
    return todo, compliant, real_png


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    todo, compliant, real_png = plan_renames(manifest['items'])
    print('待改名 %d｜已合规 %d｜真 PNG 保留 %d' % (len(todo), compliant, len(real_png)))

    moved = 0
    for src, dst in todo:
        before = digest(src)
        src.rename(dst)
        rel = dst.relative_to(ROOT).as_posix()
        if not dst.is_file():
            sys.exit('判红：%s 改名后文件不在位。' % rel)
        after = digest(dst)
        if before != after:
            sys.exit('判红：%s 改名后字节摘要变了（%s → %s），立即停止。' % (rel, before[:12], after[:12]))
        moved += 1

    mapping = {src.relative_to(ROOT).as_posix(): dst.relative_to(ROOT).as_posix() for src, dst in todo}
    changed = 0
    for item in manifest['items']:
        files = item.get('image_file') or []
        new = [mapping.get(p, p) for p in files]
        if new != files:
            item['image_file'] = new
            changed += 1
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    remaining = [p for i in manifest['items'] for p in (i.get('image_file') or [])
                 if Path(p).suffix.lower() not in OK_EXT]
    print('改名 %d 个文件，清单改写 %d 条，清单内非 jpg 扩展名剩 %d 条，真 PNG 保留 %d 个' % (
        moved, changed, len(remaining), len(real_png)))
    if moved + compliant != 1056 or changed != 264 or remaining:
        sys.exit('判红：规模不符（应为 1056 格、264 条、零残留），请核对后再跑。')


if __name__ == '__main__':
    main()
