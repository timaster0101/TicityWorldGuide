# -*- coding: utf-8 -*-
"""B 裁定迁移：老图归档到 backup
1. dry-run 只统计不移动；2. 传 --exec 真正执行
归档 = move（原位置移除，backup 镜像原相对路径）
"""
import json, io, sys, os, shutil, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
base = r"C:\Users\TIMASTER\Documents\Qoder\2026-10-29\c8c10ff8\钛湖城城市设定集"
data = os.path.join(base, "数据")
tuji = os.path.join(data, "图集")
backup = os.path.join(base, "backup")
vi = os.path.join(base, "vibe_images")

ap = argparse.ArgumentParser()
ap.add_argument("--exec", action="store_true")
args = ap.parse_args()

# 迁移前快照
snap = {"数据图集": {}, "vibe引用": {}}
def snap_files(root, prefix):
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for f in sorted(files):
            src = os.path.join(dirpath, f)
            out.append({"rel": os.path.join(prefix, rel, f) if rel!="." else os.path.join(prefix,f),
                        "bytes": os.path.getsize(src), "src": src})
    return out

plan = []  # (src, dst)
# 1. 数据/图集 全部（四向 + 根散图 + 全城鸟瞰）
if os.path.exists(tuji):
    for dirpath, dirs, files in os.walk(tuji):
        rel = os.path.relpath(dirpath, tuji)
        for f in sorted(files):
            src = os.path.join(dirpath, f)
            dst_rel = os.path.join("数据/图集" if rel=="." else os.path.join("数据/图集", rel), f)
            dst = os.path.join(backup, dst_rel.replace("/", os.sep))
            plan.append((src, dst, dst_rel))
            snap["数据图集"][dst_rel] = os.path.getsize(src)

# 2. vibe_images 被开图清单引用的那 60 个
with open(os.path.join(data, "开图清单.json"), encoding="utf-8") as f:
    kl = json.load(f)
vibe_refs = set()
for it in kl.get("items", []):
    im = it.get("image_file")
    if isinstance(im, list):
        for p in im:
            if isinstance(p, str) and p.startswith("vibe_images"):
                vibe_refs.add(os.path.basename(p))
vibe_plan = []
for dirpath, dirs, files in os.walk(vi):
    for f in sorted(files):
        if f in vibe_refs:
            src = os.path.join(dirpath, f)
            dst_rel = os.path.join("vibe_images", f)
            dst = os.path.join(backup, dst_rel.replace("/", os.sep))
            vibe_plan.append((src, dst, dst_rel))
            snap["vibe引用"][dst_rel] = os.path.getsize(src)
plan = plan + vibe_plan

print(f"待迁移文件总数: {len(plan)}")
print(f"  数据/图集: {len(snap['数据图集'])} 文件, {sum(snap['数据图集'].values())/1024/1024:.1f}MB")
print(f"  vibe引用:  {len(snap['vibe引用'])} 文件, {sum(snap['vibe引用'].values())/1024/1024:.1f}MB")
total_bytes = sum(v for d in snap.values() for v in d.values())
print(f"  合计字节: {total_bytes/1024/1024:.1f}MB")

# 保存快照（无论 dry-run 还是 exec 都存，便于回溯）
snap_path = os.path.join(backup, "归档明细_20261106.json")
with open(snap_path, "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, indent=2)
print(f"迁移前快照已存: {snap_path}")

if not args.exec:
    print("\n[DRY-RUN] 未移动任何文件。查看前10条计划：")
    for src, dst, rel in plan[:10]:
        print(f"  {rel}  ({os.path.getsize(src)/1024:.0f}KB)")
    print(f"\n确认无误后执行: python 迁移_归档.py --exec")
    sys.exit(0)

# 执行 move
moved=0; failed=[]
for src, dst, rel in plan:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        if os.path.exists(dst):
            os.remove(dst)  # 目标已存在则覆盖去重（不应发生，防御）
        shutil.move(src, dst)
        moved += 1
    except Exception as e:
        failed.append((rel, str(e)))
print(f"\n实际迁移完成: {moved}/{len(plan)}")
if failed:
    print("失败项:")
    for rel, e in failed:
        print(f"  {rel}: {e}")

# 更新开图清单 image_file 指向 backup
def rehang(p):
    if not isinstance(p, str):
        return p
    if p.startswith("数据/图集"):
        return "backup/" + p
    if p.startswith("vibe_images"):
        return "backup/" + p
    return p
changed=0
for it in kl.get("items", []):
    im = it.get("image_file")
    if isinstance(im, list):
        new = [rehang(p) for p in im]
        if new != im:
            it["image_file"] = new; changed += 1
with open(os.path.join(data, "开图清单.json"), "w", encoding="utf-8") as f:
    json.dump(kl, f, ensure_ascii=False, indent=2)
print(f"开图清单 image_file 已更新: {changed} 条指向 backup 归档路径")

# 后检查：原位置残留
leftover = 0
for dirpath, dirs, files in os.walk(tuji):
    leftover += len(files)
print(f"数据/图集 残留文件: {leftover}（应为 0，空目录保留待新图落位）")