# -*- coding: utf-8 -*-
"""示例角色卡／时间线的自检器：确认样板里的每个数字都能在正典里对上。

用途：别人拿到基版照着 `示例/角色卡-周敏.md` 造人时，把头部字段换成自己的值，
再跑 `python -X utf8 工具/check_samples.py 示例` 即可自查，不必读完 93 个 JSON。

判据（全部只读、不写盘）：
  E1 头部缺字段／字段重复
  E2 工作锚点、居住锚点不在 `城市空间名录.json`
  E3 岗位卡不在 `产业就业正典.json`（或岗位层与卡号不符）
  E4 月薪带与该岗位卡不一致
  E5 月薪不在月薪带内
  E6 月租 ≠ `住所锚[工作锚点]`
  E7 月租超过「住所四成线」（0.4 × 月薪）
  E8 篮子 ≠ `物价正典.篮子[圈层]`
  E9 户均规模 ≠ `物价正典.参数.户均规模`
  E10 通勤 ≠ 两锚点 `center_km` 的欧氏距离（容差 0.02 千米）
  E11 通勤超过该圈层的「锚点可达半径上限」
  E12 圈层与居住锚点的父片区圈层不一致
"""
import io
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FIELDS = ("编号", "姓名", "年龄", "工作锚点", "居住锚点", "岗位卡", "月薪带_钛币",
          "月薪_钛币", "月租_钛币", "户均规模", "篮子_外城环_钛币", "通勤_km",
          "通勤上限_km", "圈层")

TOL_KM = 0.02
TOL_MONEY = 0.05


def _load(*rel):
    with io.open(os.path.join(ROOT, *rel), encoding="utf-8") as fp:
        return json.load(fp)


def is_card(text):
    """是不是一份「带头部字段的角色卡」：首个非空行必须以 `编号:` 开头。

    时间线那类文档里有 `07:20–07:32` 这种带冒号的表格行，不能靠「有没有冒号」判，
    否则表格会被当成头部字段解析（首版就是这么把时间线判成缺 14 个字段的）。
    """
    for raw in text.lstrip("\ufeff").split("\n"):
        line = raw.strip()
        if not line:
            continue
        return bool(re.match(r"^编号\s*[:：]", line))
    return False


def parse_header(text):
    """取文件开头的 `键: 值` 行（到第一个 `---` 或空行为止），返回 (dict, 问题列表)。"""
    head = {}
    problems = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if head:
                break
            continue
        if line.startswith("---"):
            break
        if ":" not in line and "：" not in line:
            problems.append("E1 头部有无法解析的行：%r" % line[:40])
            continue
        k, v = re.split(r"[:：]", line, maxsplit=1)
        k, v = k.strip().lstrip("\ufeff"), v.strip()
        if k in head:
            problems.append("E1 头部字段重复：%s" % k)
        head[k] = v
    for k in FIELDS:
        if k not in head:
            problems.append("E1 头部缺字段：%s" % k)
    return head, problems


def _num(head, key):
    try:
        return float(head[key])
    except (KeyError, ValueError):
        return None


def _band(text):
    lo, hi = text.split("-", 1)
    return float(lo), float(hi)


def audit(head, root=ROOT):
    """按 12 条判据核一遍头部，返回问题列表（空表示与正典一致）。"""
    problems = []
    if head is None:
        return ["E1 没有可解析的头部"]

    canon = _load("数据", "城市空间名录.json")
    entries = {e["id"]: e for e in canon["entries"]}
    work = entries.get(head.get("工作锚点"))
    home = entries.get(head.get("居住锚点"))
    if work is None:
        problems.append("E2 工作锚点不在名录：%s" % head.get("工作锚点"))
    if home is None:
        problems.append("E2 居住锚点不在名录：%s" % head.get("居住锚点"))

    jobs = _load("数据", "产业就业正典.json")
    post = None
    for co in jobs["公司"]:
        for card in co.get("岗位卡") or []:
            if card["id"] == head.get("岗位卡"):
                post = card
    if post is None:
        problems.append("E3 岗位卡不在产业就业正典：%s" % head.get("岗位卡"))
    else:
        lo, hi = _band(head.get("月薪带_钛币", "0-0"))
        if [lo, hi] != list(post["月薪带_钛币"]):
            problems.append("E4 月薪带与岗位卡不一致：头部 %s vs 正典 %s"
                            % ([lo, hi], post["月薪带_钛币"]))
        pay = _num(head, "月薪_钛币")
        if pay is not None and not (post["月薪带_钛币"][0] <= pay <= post["月薪带_钛币"][1]):
            problems.append("E5 月薪 %s 不在岗位带 %s 内" % (pay, post["月薪带_钛币"]))

    if work is not None:
        rent = jobs["住所锚"].get(work["id"])
        got = _num(head, "月租_钛币")
        if rent is not None and got is not None and abs(got - rent) > TOL_MONEY:
            problems.append("E6 月租 %s ≠ 住所锚[%s]=%s" % (got, work["id"], rent))
        pay = _num(head, "月薪_钛币")
        if got is not None and pay is not None and got > 0.4 * pay + TOL_MONEY:
            problems.append("E7 月租 %s 超过住所四成线 %s" % (got, round(0.4 * pay, 1)))

    prices = _load("数据", "物价与生活正典.json")
    ring = head.get("圈层")
    basket = (prices.get("篮子") or {}).get(ring)
    got = _num(head, "篮子_外城环_钛币")
    if basket is not None and got is not None and abs(got - basket) > TOL_MONEY:
        problems.append("E8 篮子 %s ≠ 物价正典.篮子[%s]=%s" % (got, ring, basket))
    per = (prices.get("参数") or {}).get("户均规模")
    got = _num(head, "户均规模")
    if per is not None and got is not None and abs(got - per) > 1e-6:
        problems.append("E9 户均规模 %s ≠ 正典 %s" % (got, per))

    if work is not None and home is not None:
        wx, wy = work["center_km"]
        hx, hy = home["center_km"]
        dist = math.hypot(wx - hx, wy - hy)
        got = _num(head, "通勤_km")
        if got is not None and abs(got - dist) > TOL_KM:
            problems.append("E10 通勤 %s ≠ 名录现算 %s 千米" % (got, round(dist, 2)))
        parent = entries.get(home.get("parent"))
        ring_of = parent.get("ring") if parent else None
        if ring_of and ring and ring_of != ring:
            problems.append("E12 圈层 %s 与居住锚点所属片区圈层 %s 不一致" % (ring, ring_of))
        tol = (_load("数据", "空间通行正典.json").get("参数") or {}).get("容差") or {}
        caps = tol.get("锚点可达半径上限千米") or tol.get("锚点可达半径上限") or {}
        cap = caps.get(ring)
        got_cap = _num(head, "通勤上限_km")
        if cap is None:
            problems.append("E11 圈层 %s 不在通行正典的可达半径上限表里" % ring)
        else:
            if got_cap is None or abs(got_cap - cap) > 1e-6:
                problems.append("E11 通勤上限 %s ≠ 正典 %s 千米" % (head.get("通勤上限_km"), cap))
            if dist > cap:
                problems.append("E11 通勤 %s 超过 %s 上限 %s 千米" % (round(dist, 2), ring, cap))
    return problems


def scan(target=None, root=ROOT):
    """扫一个目录（默认 `示例/`）下所有 .md，逐份核。返回 [(路径, 问题列表)]。"""
    base = target or os.path.join(root, "示例")
    if os.path.isfile(base):
        paths = [base]
    else:
        paths = []
        for dirpath, _dirs, files in os.walk(base):
            for f in sorted(files):
                if f.lower().endswith(".md"):
                    paths.append(os.path.join(dirpath, f))
    out = []
    for p in sorted(paths):
        with io.open(p, encoding="utf-8") as fp:
            text = fp.read()
        if not is_card(text):
            continue  # 没有头部的说明文档（时间线、README）跳过
        head, problems = parse_header(text)
        out.append((p, problems + audit(head, root)))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    target = argv[0] if argv else None
    rows = scan(target)
    bad = 0
    for path, problems in rows:
        name = os.path.relpath(path, ROOT)
        if problems:
            bad += 1
            print("✗ %s" % name)
            for pr in problems:
                print("    - %s" % pr)
        else:
            print("✓ %s" % name)
    print("\n共 %d 份带头部的示例，%d 份与正典不符" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
