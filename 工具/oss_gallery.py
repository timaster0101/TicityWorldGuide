# -*- coding: utf-8 -*-
"""图集上 OSS：把 `数据/图集/`（808 件）、母图池 `数据/视觉控制资产/` 的图片，以及
已外置到归档根的 `backup/数据/图集/`（四向基准照等，1093 件）传到 `timaster` 桶的
`taihucheng/` 前缀下，并在仓内生成「本地路径 ↔ 公网 URL」对照表与回写。

回写（`--backfill`）把 URL 落进两个账本：
  · `数据/开图清单.json` 每条 item 的 `image_url`（与 `image_file` 逐格对齐的列表）；
  · `数据/图集清单.json` 每件 `逐件` 行的 `url`。
这样「项目里只存链接」在账本层面成立，本地图片只是生成侧的可用副本。

桶保持私有，只用 Bucket Policy 放开 `acs:oss:*:*:timaster/taihucheng/*` 的匿名 GetObject，
所以这里的 URL 是永久直链，可以直接给拿到基版的人用。

用法：
  python -X utf8 工具/oss_gallery.py --plan                  # 只算要传什么，不联网
  python -X utf8 工具/oss_gallery.py --upload --limit 3      # 试传 3 件
  python -X utf8 工具/oss_gallery.py --upload --workers 8    # 全量传（已传过的跳过）
  python -X utf8 工具/oss_gallery.py --verify                # HEAD 逐个核对远端
  python -X utf8 工具/oss_gallery.py --links                 # 只重写 数据/图集OSS.json
  python -X utf8 工具/oss_gallery.py --backfill              # 把 URL 回写进开图清单与图集清单
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import sys
import time

import oss2

import archive_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "数据", "图集清单.json")
LEDGER = os.path.join(ROOT, "数据", "OSS上传台账.json")
LINKS = os.path.join(ROOT, "数据", "图集OSS.json")
PROMPTS = os.path.join(ROOT, "数据", "开图清单.json")
META_DIR = os.path.join(ROOT, "数据", "视觉控制资产")
ARCHIVE_REL = "backup/数据/图集"

BUCKET = "timaster"
REGION = "oss-cn-shenzhen"
PREFIX = "taihucheng/"
BASE = "https://%s.%s.aliyuncs.com/%s" % (BUCKET, REGION, PREFIX)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")

SECRET_FILE = os.path.join(os.path.expanduser("~"), ".dsh", "secrets", "oss-ak.txt")


def _auth():
    kv = {}
    with io.open(SECRET_FILE, encoding="utf-8") as fp:
        for line in fp:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                kv[k] = v
    return oss2.Auth(kv["access_key_id"], kv["access_key_secret"])


def bucket():
    return oss2.Bucket(_auth(), "https://%s.aliyuncs.com" % REGION, BUCKET)


# ---------- 本地清单 ----------

def gallery_files():
    """仓内图集：[(本地绝对路径, 仓内相对路径)]，按清单 808 件现读盘面。"""
    with io.open(MANIFEST, encoding="utf-8") as fp:
        man = json.load(fp)
    out = []
    for row in man["逐件"]:
        rel = row["路径"].replace("\\", "/")
        out.append((os.path.join(ROOT, rel.replace("/", os.sep)), rel, row["sha256"], row["字节"]))
    return out


def mother_files():
    """母图池：`数据/视觉控制资产/` 下的图片，按盘面递归现扫。"""
    out = []
    for dirpath, _dirs, files in os.walk(META_DIR):
        for f in sorted(files):
            if not f.lower().endswith(IMAGE_EXT):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            out.append((full, rel, None, os.path.getsize(full)))
    return out


def archive_files():
    """已外置的归档图集：`backup/数据/图集/` 整棵（四向基准照等，1093 件）。

    这些路径仍被 `数据/开图清单.json` 的 `image_file` 指着（653 格历史格），所以也要有直链，
    否则「账本里只存链接」对那批格不成立。
    """
    out = []
    base = archive_store.resolve_dir(ARCHIVE_REL, ROOT)
    if not os.path.isdir(base):
        return out
    for dirpath, _dirs, files in os.walk(base):
        for f in sorted(files):
            if not f.lower().endswith(IMAGE_EXT):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, base).replace("\\", "/")
            out.append((full, ARCHIVE_REL + "/" + rel, None, os.path.getsize(full)))
    return out


def referenced_archive_files(covered):
    """账本里被指着、但不属于图集/母图/归档图集三棵的格子（实测只有 2 格：S02、S18 的 B3 样本）。

    这类格散在别处归档树里（`backup/vibe_images/`），只为它们整棵上传不值得（另有 848MB），
    所以按「被引用才传」处理——回写要的是「这一格有链」，不是「那棵树全上云」。
    """
    out = []
    prompts_path = os.path.join(ROOT, "数据", "开图清单.json")
    if not os.path.isfile(prompts_path):
        return out
    with io.open(prompts_path, encoding="utf-8") as fp:
        items = json.load(fp)["items"]
    seen = set()
    for item in items:
        for rel in item.get("image_file") or []:
            rel = rel.replace("\\", "/")
            if rel in covered or rel in seen:
                continue
            seen.add(rel)
            if not archive_store.is_externalised(rel):
                continue
            full = archive_store.resolve(rel, ROOT)
            if os.path.isfile(full):
                out.append((full, rel, None, os.path.getsize(full)))
            else:
                print("  ✗ 归档树里也找不到：", rel)
    return out


def remote_key(rel):
    """仓内相对路径 → 桶内 key。图集进 gallery/，母图进 mothers/，外置归档图集进 archive/。"""
    rel = rel.replace("\\", "/")
    if rel.startswith("数据/图集/"):
        tail = rel[len("数据/图集/"):]
        return PREFIX + "gallery/" + tail
    if rel.startswith("数据/视觉控制资产/"):
        tail = rel[len("数据/视觉控制资产/"):]
        return PREFIX + "mothers/" + tail
    if rel.startswith(ARCHIVE_REL + "/"):
        tail = rel[len(ARCHIVE_REL) + 1:]
        return PREFIX + "archive/gallery/" + tail
    if archive_store.is_externalised(rel):
        return PREFIX + "archive/" + rel
    return PREFIX + "other/" + rel


def url_of(key):
    return "https://%s.%s.aliyuncs.com/%s" % (BUCKET, REGION, key)


# ---------- 台账 ----------

def load_ledger():
    if not os.path.exists(LEDGER):
        return {"说明": "OSS 上传台账：key → 本地 sha256/字节/远端 etag。仓内只记事实，不含密钥。",
                "bucket": BUCKET, "region": REGION, "prefix": PREFIX, "逐件": {}}
    with io.open(LEDGER, encoding="utf-8") as fp:
        return json.load(fp)


def save_ledger(doc):
    with io.open(LEDGER, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(doc, fp, ensure_ascii=False, indent=1)
        fp.write("\n")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- 动作 ----------

META_FILES = (
    ("数据/图集清单.json", PREFIX + "meta/图集清单.json"),
    ("数据/图集AIGC声明.json", PREFIX + "meta/图集AIGC声明.json"),
    ("数据/图集AIGC声明.md", PREFIX + "meta/图集AIGC声明.md"),
    ("数据/图集OSS.json", PREFIX + "meta/图集OSS.json"),
    ("数据/图集直链.md", PREFIX + "meta/图集直链.md"),
)


def meta_files():
    """随图一起放的元数据（清单／AIGC 声明／直链表本身）。

    进计划而不是手工补传：`--prune` 按「计划外即孤儿」删除，元数据不在计划里就会被一起删掉
    （首版就是这么把 `taihucheng/meta/` 四件删掉的，已复传）。
    """
    out = []
    for rel, key in META_FILES:
        full = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(full):
            out.append({"local": full, "rel": rel, "key": key, "sha256": None,
                        "bytes": os.path.getsize(full), "url": url_of(key)})
    return out


def plan(limit=None):
    items = []
    core = gallery_files() + mother_files() + archive_files()
    extra = referenced_archive_files({rel for _f, rel, _s, _b in core})
    seen = set()
    for full, rel, sha, size in core + extra:
        if rel in seen:
            continue
        seen.add(rel)
        if not os.path.isfile(full):
            print("  ✗ 本地缺件：", rel)
            continue
        items.append({"local": full, "rel": rel, "key": remote_key(rel),
                      "sha256": sha, "bytes": size, "url": url_of(remote_key(rel))})
    for it in meta_files():
        if it["key"] not in {x["key"] for x in items}:
            items.append(it)
    if limit:
        items = items[:limit]
    return items


def upload(items, workers=8, force=False):
    bk = bucket()
    led = load_ledger()
    done = [0]
    failed = []
    skipped = [0]
    lock_total = len(items)

    def one(it):
        key = it["key"]
        prev = led["逐件"].get(key)
        cur_sha = it["sha256"] or sha256_of(it["local"])
        if prev and not force and prev.get("sha256") == cur_sha and prev.get("bytes") == it["bytes"]:
            skipped[0] += 1
            return ("skip", key, None)
        with open(it["local"], "rb") as fp:
            data = fp.read()
        res = bk.put_object(key, data)
        etag = (res.etag or "").strip('"')
        rec = {"本地路径": it["rel"], "sha256": cur_sha, "bytes": it["bytes"],
               "etag": etag, "url": it["url"], "上传时间": time.strftime("%Y-%m-%d %H:%M:%S")}
        done[0] += 1
        if done[0] % 40 == 0 or done[0] == lock_total:
            print("  进度 %d/%d" % (done[0], lock_total), flush=True)
        return ("ok", key, rec)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, it): it for it in items}
        for fut in concurrent.futures.as_completed(futs):
            it = futs[fut]
            try:
                kind, key, rec = fut.result()
            except Exception as e:  # noqa: BLE001
                failed.append((it["key"], str(e)[:160]))
                continue
            if rec:
                led["逐件"][key] = rec
    save_ledger(led)
    print("\n上传完成：成功 %d／跳过 %d／失败 %d" % (done[0], skipped[0], len(failed)))
    for k, e in failed[:10]:
        print("  ✗", k, e)
    return failed


def verify(items, workers=8):
    bk = bucket()
    ok, bad = 0, []

    def head(it):
        try:
            meta = bk.head_object(it["key"])
            if int(meta.content_length) != int(it["bytes"]):
                return (it["key"], "字节 %s != %s" % (meta.content_length, it["bytes"]))
            return (it["key"], None)
        except Exception as e:  # noqa: BLE001
            return (it["key"], str(e)[:100])

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for key, err in ex.map(head, items):
            if err:
                bad.append((key, err))
            else:
                ok += 1
    print("远端核对：相符 %d／异常 %d" % (ok, len(bad)))
    for k, e in bad[:10]:
        print("  ✗", k, e)
    return bad


def write_links(items):
    """生成 数据/图集OSS.json：按地点 ID 分组，另附逐件 key→url。"""
    per_id = {}
    files = {}
    meta = {}
    for it in items:
        if it["key"].startswith(PREFIX + "meta/"):
            meta[it["rel"]] = {"key": it["key"], "url": it["url"], "bytes": it["bytes"]}
            continue
        files[it["rel"]] = {"key": it["key"], "url": it["url"], "bytes": it["bytes"]}
        rel = it["rel"]
        if rel.startswith("数据/图集/"):
            tail = rel[len("数据/图集/"):]
            eid = tail.split("/")[0]
            per_id.setdefault(eid, []).append({"文件": tail.split("/")[-1], "url": it["url"],
                                               "bytes": it["bytes"]})
    doc = {
        "说明": "钛湖城图集/母图池/历史归档图的 OSS 直链对照表。桶私有，仅 taihucheng/ 前缀按 Bucket Policy 匿名可读，链接永久有效。",
        "口径": "url 由 工具/oss_gallery.py 生成；本地路径→key 的映射规则见该脚本 remote_key()；"
                "开图清单的 image_url 与图集清单的逐件 url 由 --backfill 从本表回写，不要手改。",
        "bucket": BUCKET, "region": REGION, "prefix": PREFIX, "base_url": BASE,
        "统计": {"地点数": len(per_id), "件数": len(files),
                 "图集": sum(1 for r in files if r.startswith("数据/图集/")),
                 "母图池": sum(1 for r in files if r.startswith("数据/视觉控制资产/")),
                 "历史归档": sum(1 for r in files if archive_store.is_externalised(r)),
                 "元数据": len(meta),
                 "合计字节": sum(v["bytes"] for v in files.values())},
        "按地点": dict(sorted(per_id.items())),
        "逐件": dict(sorted(files.items())),
        "元数据": dict(sorted(meta.items())),
    }
    with io.open(LINKS, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(doc, fp, ensure_ascii=False, indent=1)
        fp.write("\n")
    write_links_md(doc)
    print("已写 %s：地点 %d／件数 %d" % (os.path.relpath(LINKS, ROOT), len(per_id), len(files)))


LINKS_MD = os.path.join(ROOT, "数据", "图集直链.md")


def write_links_md(doc=None):
    """人读版直链表 `数据/图集直链.md`：一地点一行，图名即链接。

    JSON 那份是机器读的；这份是给拿到基版的人「点开就能看」的入口。名字取自
    `数据/开图清单.json`，没取到就写 ID。
    """
    if doc is None:
        with io.open(LINKS, encoding="utf-8") as fp:
            doc = json.load(fp)
    names = {}
    if os.path.isfile(PROMPTS):
        with io.open(PROMPTS, encoding="utf-8") as fp:
            for item in json.load(fp)["items"]:
                names[item["id"]] = (item["name"], item.get("type", ""))
    out = ["# 钛湖城图集直链（%d 个地点／%d 件）\n" % (
        doc["统计"]["地点数"], doc["统计"]["件数"]),
        "图不在仓内，全部放在阿里云 OSS `%s` 桶（%s）`%s` 前缀下；桶私有，"
        "只对这个前缀放开了匿名读取，链接永久有效、不需要签名。\n" % (
            doc["bucket"], doc["region"], doc["prefix"]),
        "机器读的对照表是同目录的 `图集OSS.json`（含 `逐件` 的 key／字节／URL 全量）。"
        "本地路径→URL 的回写由 `工具/oss_gallery.py --backfill` 负责："
        "`数据/开图清单.json` 的 `image_url` 与 `数据/图集清单.json` 的 `url`。\n",
        "| ID | 名称 | 类型 | 图（%d 件中的 %s） |" % (doc["统计"]["件数"], "该地点"),
        "|---|---|---|---|"]
    for eid in sorted(doc["按地点"]):
        items = doc["按地点"][eid]
        name, typ = names.get(eid, (eid, ""))
        links = "、".join("[%s](%s)" % (it["文件"], it["url"]) for it in items)
        out.append("| %s | %s | %s | %s |" % (eid, name, typ or "—", links))
    out.append("")
    with io.open(LINKS_MD, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(out))
    print("已写 %s（%d 行）" % (os.path.relpath(LINKS_MD, ROOT), len(out)))


def backfill(items=None):
    """把直链回写进两个账本：开图清单的 `image_url`（与 image_file 逐格对齐）、图集清单的 `url`。

    幂等：算出来跟盘上一样就不写；缺链的格子写 None 并在退出码上报 1（不静默留白）。
    """
    items = plan() if items is None else items
    link = {it["rel"]: it["url"] for it in items}

    with io.open(PROMPTS, encoding="utf-8") as fp:
        prompts = json.load(fp)
    missing = []
    cells = 0
    for item in prompts["items"]:
        urls = []
        for rel in item.get("image_file") or []:
            rel = rel.replace("\\", "/")
            url = link.get(rel)
            if url is None:
                missing.append((item["id"], rel))
            urls.append(url)
            cells += 1
        item["image_url"] = urls
    with io.open(PROMPTS, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(prompts, fp, ensure_ascii=False, indent=1)
        fp.write("\n")

    with io.open(MANIFEST, encoding="utf-8") as fp:
        man = json.load(fp)
    rows = 0
    for row in man["逐件"]:
        rel = row["路径"].replace("\\", "/")
        row["url"] = link.get(rel)
        rows += 1
    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(man, fp, ensure_ascii=False, indent=1)
        fp.write("\n")

    linked = sum(1 for i in prompts["items"] for u in i["image_url"] if u)
    print("回写完成：开图清单 %d 格（有链 %d／缺链 %d）｜图集清单 %d 件（有链 %d）" % (
        cells, linked, len(missing), rows, sum(1 for r in man["逐件"] if r.get("url"))))
    for eid, rel in missing[:10]:
        print("  ✗ 无链格：", eid, rel)
    return missing


def prune(items, apply=False):
    """删掉前缀下**不在计划里**的对象（换过 key 规则会留下孤儿件，白付存储费）。

    默认只列出，加 `apply=True` 才真删；只动 `taihucheng/` 前缀，桶里别的前缀不碰。
    """
    bk = bucket()
    keep = {it["key"] for it in items}
    orphans = []
    for obj in oss2.ObjectIterator(bk, prefix=PREFIX):
        if obj.key not in keep:
            orphans.append(obj.key)
    total = 0
    for key in orphans[:5]:
        print("  孤儿件：", key)
    print("孤儿件 %d 个（前缀 %s 下计划外对象）" % (len(orphans), PREFIX))
    if not apply:
        print("（只列出；加 --prune-apply 才删）")
        return orphans
    for key in orphans:
        bk.delete_object(key)
        total += 1
    print("已删除 %d 个孤儿件" % total)
    return orphans


def main(argv=None):
    ap = argparse.ArgumentParser(description="图集上 OSS 与直链对照表")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--prune-apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    items = plan(args.limit or None)
    total = sum(i["bytes"] for i in items)
    print("待处理 %d 件 / %.1f MB" % (len(items), total / 1048576.0))
    if args.plan:
        for it in items[:8]:
            print("  ", it["rel"], "→", it["key"])
        print("   …（共 %d 件）" % len(items))
        return 0
    rc = 0
    if args.upload:
        write_links(plan())          # 先刷新直链表，再连同它一起传（meta 里也放一份）
        if upload(plan(), workers=args.workers, force=args.force):
            rc = 1
    if args.verify:
        if verify(items, workers=args.workers):
            rc = 1
    if args.links:
        write_links(plan())
    if args.backfill:
        if backfill(plan()):
            rc = 1
    if args.prune or args.prune_apply:
        prune(plan(), apply=args.prune_apply)
    return rc


if __name__ == "__main__":
    sys.exit(main())
