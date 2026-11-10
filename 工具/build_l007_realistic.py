# -*- coding: utf-8 -*-
"""用显式78层几何渲染L007写实建筑首图；不依赖文本生图抽卡。"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from build_visual_controls import SCENES, project_point

ROOT = Path(__file__).resolve().parents[1]
# v05 原件已按 B 前置裁定整体归档进 backup/ 镜像路径（移交清单 §50.2），此处只读不改。
V05_SOURCE = ROOT / "backup" / "数据" / "图集" / "L007-钛湖之脊-v05.jpg"
SCENE = SCENES["L007"]
SHAFT_BOTTOM = 24
SHAFT_TOP = 320
FLOORS = 78


def floor_bands():
    """裙房屋顶以上恰好78个等高使用楼层，不含冠部和天线。"""
    return [(SHAFT_BOTTOM + (SHAFT_TOP - SHAFT_BOTTOM) * i / FLOORS,
             SHAFT_BOTTOM + (SHAFT_TOP - SHAFT_BOTTOM) * (i + 1) / FLOORS)
            for i in range(FLOORS)]


def realistic_camera(time_s):
    """24毫米竖幅机位，8秒向东平移6米，机高始终1.6米。"""
    return {
        "position": (-30 + 6 * time_s / 8, -180, 1.6),
        "yaw_deg": 0,
        "pitch_deg": 30,
        "lens_mm": 24,
        "sensor_fit": "vertical",
    }


@lru_cache(maxsize=4)
def background(size):
    """生成固定的晚秋天空、远景和石板广场，避免视频背景闪烁。"""
    w, h = size
    rng = np.random.default_rng(7)
    horizon = int(h * 0.885)
    yy = np.arange(h)[:, None]
    sky_t = np.clip(yy / max(horizon, 1), 0, 1)
    sky_top = np.array([143, 180, 208], dtype=float)
    sky_bottom = np.array([220, 228, 229], dtype=float)
    pixels = np.empty((h, w, 3), dtype=float)
    pixels[:] = sky_top * (1 - sky_t[..., None]) + sky_bottom * sky_t[..., None]
    cloud = rng.normal(0, 1, (12, 8))
    cloud = np.asarray(Image.fromarray(((cloud - cloud.min()) / np.ptp(cloud) * 255).astype("uint8")).resize((w, h), Image.Resampling.BICUBIC), dtype=float)
    cloud = (cloud - 128) / 128
    pixels += cloud[..., None] * 4.5
    ground_t = np.clip((yy - horizon) / max(h - horizon, 1), 0, 1)
    ground_top = np.array([164, 165, 159], dtype=float)
    ground_bottom = np.array([105, 110, 110], dtype=float)
    ground = ground_top * (1 - ground_t[..., None]) + ground_bottom * ground_t[..., None]
    mask = (yy >= horizon)[..., None]
    pixels = pixels * (1 - mask) + ground * mask
    pixels += rng.normal(0, 1.5, (h, w, 1))
    image = Image.fromarray(np.clip(pixels, 0, 255).astype("uint8"), "RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    for i in range(24):
        x = int(i * w / 23)
        bw = max(3, int(w * (0.012 + (i % 4) * 0.004)))
        bh = int(h * (0.018 + (i % 5) * 0.009))
        draw.rectangle((x - bw // 2, horizon - bh, x + bw // 2, horizon), fill=(105, 119, 126, 150))
        draw.line((x - bw // 2, horizon - bh, x + bw // 2, horizon - bh), fill=(188, 194, 194, 150))
    return image


def render_realistic_frame(time_s, size=(1024, 1536)):
    """渲染一帧；78个楼层带和77条内部横缝均由floor_bands显式控制。"""
    w, h = size
    camera = realistic_camera(time_s)
    image = background(size).copy()
    draw = ImageDraw.Draw(image, "RGBA")

    def project(point):
        return project_point(point, camera, size)[:2]

    def polygon(points, fill, outline=None, width=1):
        draw.polygon([project(p) for p in points], fill=fill)
        if outline:
            draw.line([project(p) for p in points + [points[0]]], fill=outline, width=width)

    def line(points, fill, width=1):
        draw.line([project(p) for p in points], fill=fill, width=width)

    # 广场石板分缝使用同一世界坐标投影，镜头移动时不会滑动或闪烁。
    for x in range(-120, 121, 10):
        line([(x, -170, 0), (x, 100, 0)], (54, 61, 62, 80), max(1, w // 1024))
    for y in range(-160, 101, 12):
        line([(-130, y, 0), (130, y, 0)], (55, 61, 61, 90), max(1, w // 1024))

    bands = floor_bands()
    front_panels = 12
    side_panels = 15
    for floor, (z0, z1) in enumerate(bands):
        for panel in range(front_panels):
            x0 = -24 + 48 * panel / front_panels
            x1 = -24 + 48 * (panel + 1) / front_panels
            variation = ((floor * 17 + panel * 31) % 23) - 11
            top_lift = int(10 * floor / FLOORS)
            color = (43 + variation // 3 + top_lift, 72 + variation // 2 + top_lift,
                     96 + variation + top_lift, 255)
            if (floor * 7 + panel * 13) % 31 == 0:
                color = (92, 119, 137, 255)
            polygon([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)], color)
        for panel in range(side_panels):
            y0 = 60 * panel / side_panels
            y1 = 60 * (panel + 1) / side_panels
            variation = ((floor * 19 + panel * 11) % 21) - 10
            color = (78 + variation // 2, 103 + variation // 2, 119 + variation, 255)
            polygon([(-24, y0, z0), (-24, y1, z0), (-24, y1, z1), (-24, y0, z1)], color)

    joint_width = max(1, round(w / 1024))
    for z0, _ in bands:
        line([(-24, 0, z0), (24, 0, z0)], (20, 37, 51, 255), joint_width)
        line([(-24, 0, z0), (-24, 60, z0)], (48, 65, 74, 255), joint_width)
    for panel in range(front_panels + 1):
        x = -24 + 48 * panel / front_panels
        line([(x, 0, SHAFT_BOTTOM), (x, 0, SHAFT_TOP)], (164, 183, 193, 175),
             2 if panel % 3 == 0 else 1)
    for panel in range(side_panels + 1):
        y = 60 * panel / side_panels
        line([(-24, y, SHAFT_BOTTOM), (-24, y, SHAFT_TOP)], (184, 194, 197, 170), 1)

    # 冠部只占屋顶，不新增使用楼层；左高右低，始终为一条单向斜线。
    polygon([(-24, 0, 320), (24, 0, 320), (-24, 0, 344)], (66, 99, 121, 255), (25, 45, 58, 255), 2)
    polygon([(-24, 0, 320), (-24, 60, 320), (-24, 60, 344), (-24, 0, 344)],
            (91, 117, 131, 255), (42, 57, 65, 255), 2)
    for panel in range(1, front_panels):
        x = -24 + 48 * panel / front_panels
        top = 344 - (x + 24) * 0.5
        line([(x, 0, 320), (x, 0, top)], (173, 192, 201, 190), 1)
    line([(-24, 0, 344), (24, 0, 320)], (27, 45, 56, 255), 2)
    line([(-24, 0, 344), (-24, 0, 368)], (60, 69, 74, 255), max(2, w // 512))
    line([(-23.7, 0, 344), (-23.7, 0, 368)], (205, 211, 211, 220), 1)

    # 深灰石材裙房压住塔楼基部，中央门厅保持通透。
    for row in range(3):
        z0, z1 = row * 8, (row + 1) * 8
        for panel in range(13):
            x0, x1 = -65 + panel * 10, -65 + (panel + 1) * 10
            shade = 69 + ((row * 7 + panel * 5) % 12)
            polygon([(x0, -25, z0), (x1, -25, z0), (x1, -25, z1), (x0, -25, z1)],
                    (shade, shade + 5, shade + 7, 255), (45, 50, 53, 255), 1)
    polygon([(-65, -25, 0), (-65, 65, 0), (-65, 65, 24), (-65, -25, 24)],
            (91, 94, 94, 255), (48, 53, 55, 255), 1)
    polygon([(-20, -25.1, 0), (20, -25.1, 0), (20, -25.1, 8), (-20, -25.1, 8)],
            (76, 93, 98, 255), (32, 42, 46, 255), 2)
    for x in range(-20, 21, 5):
        line([(x, -25.2, 0), (x, -25.2, 8)], (177, 164, 128, 220), 1)
    line([(-20, -25.2, 7.7), (20, -25.2, 7.7)], (209, 181, 124, 180), 2)

    def tree(x, y, height, seed):
        rng = np.random.default_rng(seed)
        base = project((x, y, 0))
        top = project((x, y, height))
        radius = abs(base[1] - top[1]) * 0.55
        if radius < 2:
            return
        draw.line((base, top), fill=(69, 61, 46, 255), width=max(1, int(radius / 12)))
        for _ in range(60):
            dx, dy = rng.normal(0, radius * 0.42, 2)
            r = radius * rng.uniform(0.10, 0.25)
            color = [(67, 83, 48, 235), (93, 103, 54, 235), (135, 105, 49, 225), (157, 91, 43, 220)][seed % 4]
            draw.ellipse((top[0] + dx - r, top[1] + dy - r, top[0] + dx + r, top[1] + dy + r), fill=color)

    for args in ((-78, -12, 8, 1), (77, -8, 9, 2), (-52, -55, 7, 3), (56, -48, 7, 4)):
        tree(*args)

    for index, (x, y) in enumerate(((-12, -66), (8, -72), (28, -54))):
        px = x + 0.35 * time_s / 8 * (1 if index % 2 == 0 else -1)
        base = project((px, y, 0))
        head = project((px, y, 1.68))
        body = project((px, y, 0.85))
        radius = max(1.2, abs(base[1] - head[1]) * 0.10)
        draw.ellipse((head[0] - radius, head[1] - radius, head[0] + radius, head[1] + radius), fill=(177, 153, 128, 255))
        draw.line((head, base), fill=[(40, 46, 52, 255), (67, 62, 54, 255), (38, 57, 65, 255)][index], width=max(2, int(radius)))
        draw.line((body[0], body[1], base[0] - radius, base[1]), fill=(37, 41, 44, 255), width=1)
        draw.line((body[0], body[1], base[0] + radius, base[1]), fill=(37, 41, 44, 255), width=1)

    return image


def composite_realistic_still(size=(1024, 1536)):
    """沿用v05照片材质，仅在塔身立面重绘恰好78个等高楼层。"""
    source = V05_SOURCE
    with Image.open(source) as source_image:
        pixels = np.asarray(source_image.convert("RGB")).copy()
    facades = (
        ([(608, 338), (1036, 635), (1058, 1948), (596, 1912)], 480, 12),
        ([(482, 487), (608, 338), (596, 1912), (463, 1892)], 180, 5),
    )
    for quad, width, panels in facades:
        height = 1560
        rectangle = np.float32([(0, 0), (width - 1, 0),
                                (width - 1, height - 1), (0, height - 1)])
        to_rectangle = cv2.getPerspectiveTransform(np.float32(quad), rectangle)
        to_photo = cv2.getPerspectiveTransform(rectangle, np.float32(quad))
        facade = cv2.warpPerspective(pixels, to_rectangle, (width, height),
                                     flags=cv2.INTER_CUBIC)

        # 纵向柔化旧分缝，保留原照片的竖肋、玻璃反射和明暗变化。
        softened = cv2.GaussianBlur(facade, (1, 45), 0)
        facade = cv2.addWeighted(facade, 0.18, softened, 0.82, 0)
        overlay = facade.copy()
        for floor in range(FLOORS):
            y0 = round(floor * height / FLOORS)
            y1 = round((floor + 1) * height / FLOORS)
            variation = ((floor * 17) % 9) - 4
            color = (int(variation * 0.65), int(variation * 0.85), variation)
            overlay[y0:y1] = np.clip(overlay[y0:y1].astype(np.int16) + color, 0, 255)
            if floor:
                cv2.line(overlay, (0, y0), (width - 1, y0), (25, 39, 51), 2, cv2.LINE_AA)
                cv2.line(overlay, (0, y0 + 2), (width - 1, y0 + 2), (117, 143, 158), 1, cv2.LINE_AA)
        for panel in range(1, panels):
            x = round(panel * width / panels)
            cv2.line(overlay, (x, 0), (x, height - 1), (157, 178, 188), 1, cv2.LINE_AA)
        cv2.rectangle(overlay, (0, 0), (width - 1, height - 1), (39, 55, 65), 2)

        warped = cv2.warpPerspective(overlay, to_photo, (pixels.shape[1], pixels.shape[0]),
                                     flags=cv2.INTER_CUBIC)
        mask = cv2.warpPerspective(np.full((height, width), 255, dtype=np.uint8),
                                   to_photo, (pixels.shape[1], pixels.shape[0]))
        mask = cv2.GaussianBlur(mask, (5, 5), 0).astype(np.float32)[..., None] / 255
        pixels = np.clip(pixels * (1 - mask) + warped * mask, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, "RGB").resize(size, Image.Resampling.LANCZOS)


@lru_cache(maxsize=2)
def _composite_pixels(size):
    """缓存同一照片母版，视频帧只做连续镜头变换。"""
    return np.asarray(composite_realistic_still(size)).copy()


def composite_realistic_frame(time_s, size=(1024, 1536)):
    """按24毫米机位的向东位移生成连续帧，首帧与v07完全一致。"""
    pixels = _composite_pixels(size)
    if time_s == 0:
        return Image.fromarray(pixels.copy(), "RGB")
    reference = (0, 0, 160)
    start = project_point(reference, realistic_camera(0), size)
    current = project_point(reference, realistic_camera(time_s), size)
    transform = np.float32([[1, 0, current[0] - start[0]],
                            [0, 1, current[1] - start[1]]])
    moved = cv2.warpAffine(pixels, transform, size, flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REFLECT_101)
    return Image.fromarray(moved, "RGB")


def save_still():
    """只生成首图；视频须在首图人工复验通过后另行封装。"""
    target = ROOT / "数据" / "图集" / "L007-钛湖之脊-v07-1024x1536.jpg"
    source = V05_SOURCE
    image = composite_realistic_still()
    with Image.open(source) as src:
        xmp = src.info.get("xmp", b"")
    image.save(target, quality=95, subsampling=0, xmp=xmp)
    print(target)


if __name__ == "__main__":
    save_still()
