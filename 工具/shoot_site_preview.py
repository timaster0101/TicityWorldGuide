# -*- coding: utf-8 -*-
"""把网站截成 README 用的预览图（网站/预览/*.jpg）。

自起一个静态服务器（只读 网站/ 目录，端口随机），用 playwright 无头 Chromium 截图：
按 2× 设备像素比采，落盘前缩到 1440 宽（手机图 780），JPEG q84，整组控制在 1 MB 上下。

用法：
    python -X utf8 工具/shoot_site_preview.py            # 全量重截
    python -X utf8 工具/shoot_site_preview.py --only maps
    python -X utf8 工具/shoot_site_preview.py --list

依赖 Python 包 playwright（pip install playwright && playwright install chromium），
它只用来出预览图，跑单测不需要。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "网站"
OUT = SITE / "预览"
TMP = Path(os.environ.get("TEMP", ".")) / "tihu_site_preview"

# (名字, 页面, 选择器或 None, 视口, 设备像素比, 附加动作)
SHOTS = [
    ("cover", "/index.html", None, (1440, 820), 2, None),
    ("places", "/index.html", "#places", (1440, 900), 2, None),
    ("run", "/index.html", "#run", (1440, 900), 2, None),
    ("gallery", "/index.html", "#gallery", (1440, 900), 2, None),
    ("locations", "/locations.html", None, (1440, 860), 2, "search"),
    ("maps", "/map.html", None, (1440, 860), 2, None),
    ("atlas", "/atlas.html", None, (1440, 820), 2, None),
    ("lightbox", "/atlas.html", None, (1440, 820), 2, "lightbox"),
    ("mobile", "/index.html", None, (390, 844), 3, None),
]

JPEG_WIDTH = {"mobile": 780}


def serve():
    """起一个只读 网站/ 的本地服务器，返回 (base_url, httpd)。

    注意：Windows 上 mimetypes 会把 .svg 认成 image/svg（少了 +xml），Chromium 不认，
    图会显示成坏图。这里显式覆盖成 image/svg+xml。
    """
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = dict(
            http.server.SimpleHTTPRequestHandler.extensions_map,
            **{
                ".svg": "image/svg+xml",
                ".css": "text/css",
                ".js": "text/javascript",
                ".json": "application/json",
            }
        )

        def log_message(self, *args):  # 静音访问日志
            pass

    handler = functools.partial(Handler, directory=str(SITE))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % httpd.server_address[1], httpd


def to_jpg(src, dst, width):
    from PIL import Image

    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w > width:
            im = im.resize((width, round(h * width / w)), Image.LANCZOS)
        im.save(dst, "JPEG", quality=84, optimize=True, progressive=True)
    return dst.stat().st_size


def shoot(base, names=None):
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    rows = [s for s in SHOTS if not names or s[0] in names]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, path, sel, (vw, vh), dsf, action in rows:
            ctx = browser.new_context(
                viewport={"width": vw, "height": vh},
                device_scale_factor=dsf,
                color_scheme="dark",
            )
            page = ctx.new_page()
            page.goto(base + path, wait_until="networkidle", timeout=120000)
            page.wait_for_timeout(1500)
            png = TMP / (name + ".png")
            if action == "lightbox":
                page.locator("button.tile[data-full]").nth(2).click()
                page.wait_for_timeout(1800)
                page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": vw, "height": vh})
            elif action == "search":
                page.fill("#q", "D08")
                page.wait_for_timeout(400)
                page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": vw, "height": vh})
            elif sel:
                page.locator(sel).screenshot(path=str(png))
            else:
                page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": vw, "height": vh})
            ctx.close()
            jpg = OUT / (name + ".jpg")
            size = to_jpg(png, jpg, JPEG_WIDTH.get(name, 1440))
            print("%-10s %-12s %7.1f KB" % (name, "%dx%d" % (vw, vh), size / 1024))
        browser.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="截网站预览图到 网站/预览/")
    ap.add_argument("--only", help="只截某几张，逗号分隔，如 cover,atlas")
    ap.add_argument("--list", action="store_true", help="列出可截的图名")
    args = ap.parse_args(argv)

    if args.list:
        for name, path, sel, view, _dsf, action in SHOTS:
            print("%-10s %-18s %-12s %s" % (name, path, "%dx%d" % view, action or sel or ""))
        return 0

    names = {n.strip() for n in args.only.split(",") if n.strip()} if args.only else None
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("缺 playwright：pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    base, httpd = serve()
    try:
        print("本地预览服务器 %s（根目录 网站/）" % base)
        shoot(base, names)
    finally:
        httpd.shutdown()

    total = sum(f.stat().st_size for f in OUT.glob("*.jpg"))
    print("合计 %.2f MB / %d 张 → %s" % (total / 1024 ** 2, len(list(OUT.glob("*.jpg"))), OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
