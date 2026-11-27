# -*- coding: utf-8 -*-
"""图集上 OSS：把 `数据/图集/`（808 件）与母图池 `数据/视觉控制资产/`（184 件）传到
`timaster` 桶的 `taihucheng/` 前缀下，并在仓内生成「本地路径 ↔ 公网 URL」对照表。

桶保持私有，只用 Bucket Policy 放开 `acs:oss:*:*:timaster/taihucheng/*` 的匿名 GetObject，
所以这里的 URL 是永久直链，可以直接给拿到基版的人用。

用法：
  python -X utf8 工具/oss_gallery.py --plan                  # 只算要传什么，不联网
  python -X utf8 工具/oss_gallery.py --upload --limit 3      # 试传 3 件
  python -X utf8 工具/oss_gallery.py --upload --workers 8    # 全量传（已传过的跳过）
  python -X utf8 工具/oss_gallery.py --verify                # HEAD 逐个核对远端
  python -X utf8 工具/oss_gallery.py --links                 # 只重写 数据/图集OSS.json
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "数据", "图集清单.json")
LEDGER = os.path.join(ROOT, "数据", "OSS上传台账.json")
LINKS = os.path.join(ROOT, "数据", "图集OSS.json")
META_DIR = os.path.join(ROOT, "数据", "视觉控制资产")

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


def remote_key(rel):
    """仓内相对路径 → 桶内 key。图集进 gallery/，母图池进 mothers/。"""
    rel = rel.replace("\\", "/")
    if rel.startswith("数据/图集/"):
        tail = rel[len("数据/图集/"):]
        return PREFIX + "gallery/" + tail
    if rel.startswith("数据/视觉控制资产/"):
        tail = rel[len("数据/视觉控制资产/"):]
        return PREFIX + "mothers/" + tail
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

def plan(limit=None):
    items = []
    for full, rel, sha, size in gallery_files() + mother_files():
        if not os.path.isfile(full):
            print("  ✗ 本地缺件：", rel)
            continue
        items.append({"local": full, "rel": rel, "key": remote_key(rel),
                      "sha256": sha, "bytes": size, "url": url_of(remote_key(rel))})
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
    for it in items:
        files[it["rel"]] = {"key": it["key"], "url": it["url"], "bytes": it["bytes"]}
        rel = it["rel"]
        if rel.startswith("数据/图集/"):
            tail = rel[len("数据/图集/"):]
            eid = tail.split("/")[0]
            per_id.setdefault(eid, []).append({"文件": tail.split("/")[-1], "url": it["url"],
                                               "bytes": it["bytes"]})
    doc = {
        "说明": "钛湖城图集/母图池的 OSS 直链对照表。桶私有，仅 taihucheng/ 前缀按 Bucket Policy 匿名可读，链接永久有效。",
        "口径": "url 由 工具/oss_gallery.py 生成；本地路径→key 的映射规则见该脚本 remote_key()。",
        "bucket": BUCKET, "region": REGION, "prefix": PREFIX, "base_url": BASE,
        "统计": {"地点数": len(per_id), "件数": len(files),
                 "合计字节": sum(v["bytes"] for v in files.values())},
        "按地点": dict(sorted(per_id.items())),
        "逐件": dict(sorted(files.items())),
    }
    with io.open(LINKS, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(doc, fp, ensure_ascii=False, indent=1)
        fp.write("\n")
    print("已写 %s：地点 %d／件数 %d" % (os.path.relpath(LINKS, ROOT), len(per_id), len(files)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="图集上 OSS 与直链对照表")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--links", action="store_true")
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
        if upload(items, workers=args.workers, force=args.force):
            rc = 1
    if args.verify:
        if verify(items, workers=args.workers):
            rc = 1
    if args.links or args.upload:
        write_links(plan())
    return rc


if __name__ == "__main__":
    sys.exit(main())
