import copy
import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "数据" / "视觉控制资产"
SQRT_HALF = math.sqrt(0.5)

SCENES = {
    "L007": {
        "id": "L007",
        "name": "钛湖之脊",
        "center_km": (3.324, 1.842),
        "canonical": {"area_m2": 62000, "gross_floor_area_m2": 236000, "height_m": 368, "floors": 78},
        "site": {"width_m": 200, "depth_m": 310, "status": "等面积美术工作轮廓，非宗地测绘"},
        "camera": {
            "start_m": (-30.0, -120.0, 1.6),
            "end_m": (-24.0, -120.0, 1.6),
            "yaw_deg": 0.0,
            "pitch_deg": 35.0,
            "lens_mm": 24.0,
            "sensor_fit": "vertical",
        },
        "duration_s": 8,
        "key_times_s": (0, 2, 4, 6, 8),
        "control_size": (512, 768),
        "art_lock": {
            "tower_footprint_m": (48, 60),
            "shaft_top_m": 320,
            "crown_high_m": 344,
            "antenna_top_m": 368,
            "note": "塔身、冠部和天线分解为本次白模美术锁定候选；368米总高与78层为正典硬参数。",
        },
    },
    "R043": {
        "id": "R043",
        "name": "白石老街坊",
        "center_km": (-3.717, -2.06),
        "canonical": {
            "area_m2": 294000,
            "gross_floor_area_m2": 39800,
            "population": 900,
            "households": 375,
            "height_limit_m": 12,
        },
        "site": {"width_m": 600, "depth_m": 490, "status": "等面积美术工作轮廓，非宗地测绘；院落数量为示意"},
        "camera": {
            "start_m": (-240.0, -190.0, 1.4),
            "end_m": (-240.0 + 4.0 * SQRT_HALF, -190.0 + 4.0 * SQRT_HALF, 1.4),
            "yaw_deg": 45.0,
            "pitch_deg": 0.0,
            "lens_mm": 35.0,
            "sensor_fit": "horizontal",
        },
        "duration_s": 8,
        "key_times_s": (0, 2, 4, 6, 8),
        "control_size": (640, 512),
        "art_lock": {
            "camera_travel_m": 4.0,
            "closed_gate_forward_m": 8.0,
            "roof_range_m": (4, 9),
            "note": "镜头移动4米、院门位于起点前方8米为本次试点镜头锁定；终点保留4米净空，院落位置与数量是局部白模示意，不新增正典。",
        },
    },
}


def camera_at(scene, time_s):
    if not 0 <= time_s <= scene["duration_s"]:
        raise ValueError("镜头时间超出范围")
    ratio = time_s / scene["duration_s"]
    start = scene["camera"]["start_m"]
    end = scene["camera"]["end_m"]
    return tuple(start[i] + (end[i] - start[i]) * ratio for i in range(3))


def site_bounds(scene):
    half_w = scene["site"]["width_m"] / 2
    half_d = scene["site"]["depth_m"] / 2
    return -half_w, half_w, -half_d, half_d


def validate_scene(scene):
    errors = []
    site = scene["site"]
    if site["width_m"] * site["depth_m"] != scene["canonical"]["area_m2"]:
        errors.append("工作轮廓面积与正典不符")
    if scene["duration_s"] != 8 or scene["key_times_s"] != (0, 2, 4, 6, 8):
        errors.append("镜头时长或关键帧时间点不符")
    min_x, max_x, min_y, max_y = site_bounds(scene)
    heights = []
    for step in range(81):
        x, y, z = camera_at(scene, scene["duration_s"] * step / 80)
        heights.append(z)
        if not min_x <= x <= max_x or not min_y <= y <= max_y:
            errors.append("路径越界")
            break
    if len(set(heights)) != 1:
        errors.append("机位高度发生变化")
    if errors:
        raise ValueError("；".join(errors))
    return []


def camera_for(scene, time_s):
    camera = dict(scene["camera"])
    camera["position"] = camera_at(scene, time_s)
    return camera


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def project_point(point, camera, size):
    yaw = math.radians(camera["yaw_deg"])
    pitch = math.radians(camera["pitch_deg"])
    forward = (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
    right = (math.cos(yaw), -math.sin(yaw), 0.0)
    up = (0.0, -math.sin(pitch), math.cos(pitch)) if abs(yaw) < 1e-9 else (
        -math.sin(yaw) * math.sin(pitch),
        -math.cos(yaw) * math.sin(pitch),
        math.cos(pitch),
    )
    relative = tuple(point[i] - camera["position"][i] for i in range(3))
    depth = dot(relative, forward)
    if depth <= 0.05:
        raise ValueError("点位于相机后方")
    focal = (size[0] if camera["sensor_fit"] == "horizontal" else size[1]) * camera["lens_mm"] / 36.0
    x = size[0] / 2 + focal * dot(relative, right) / depth
    y = size[1] / 2 - focal * dot(relative, up) / depth
    return x, y, depth


def box_faces(cx, cy, width, depth, height, color=(190, 196, 198), origin=(0, 0), angle=0.0):
    ux, uy = math.cos(angle), math.sin(angle)
    vx, vy = -uy, ux
    points = []
    for z in (0, height):
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            points.append((cx + origin[0] + a * width / 2 * ux + b * depth / 2 * vx,
                           cy + origin[1] + a * width / 2 * uy + b * depth / 2 * vy, z))
    return [
        (points[:4], tuple(max(0, c - 25) for c in color)),
        (points[4:], tuple(min(255, c + 15) for c in color)),
        ([points[i] for i in (0, 1, 5, 4)], color),
        ([points[i] for i in (1, 2, 6, 5)], tuple(max(0, c - 12) for c in color)),
        ([points[i] for i in (2, 3, 7, 6)], tuple(max(0, c - 20) for c in color)),
        ([points[i] for i in (3, 0, 4, 7)], tuple(min(255, c + 5) for c in color)),
    ]


def lane_point(scene, forward, side=0.0, z=0.0):
    start = scene["camera"]["start_m"]
    return (start[0] + forward * SQRT_HALF + side * SQRT_HALF,
            start[1] + forward * SQRT_HALF - side * SQRT_HALF, z)


def shifted_faces(faces, delta):
    return [([(x + delta[0], y + delta[1], z + delta[2]) for x, y, z in vertices], color)
            for vertices, color in faces]


def scene_geometry(scene):
    faces = []
    lines = []
    if scene["id"] == "L007":
        faces += box_faces(0, 20, 130, 90, 24, (102, 108, 112))
        faces += box_faces(0, 30, 48, 60, 320, (165, 183, 192))
        lower = [(-24, 0, 320), (24, 0, 320), (24, 60, 320), (-24, 60, 320)]
        upper = [(-24, 0, 344), (24, 0, 320), (24, 60, 320), (-24, 60, 344)]
        faces += [(upper, (188, 199, 204))]
        for i in range(4):
            j = (i + 1) % 4
            faces.append(([lower[i], lower[j], upper[j], upper[i]], (154 + i * 5, 174 + i * 4, 184 + i * 3)))
        for floor in range(1, 78):
            z = 320 * floor / 78
            lines.append(((-24, 0, z), (24, 0, z), (107, 132, 143), 1))
            lines.append(((-24, 0, z), (-24, 60, z), (107, 132, 143), 1))
        lines.append(((-24, 0, 344), (-24, 0, 368), (75, 82, 87), 2))
        for x in range(-16, 25, 8):
            lines.append(((x, 0, 24), (x, 0, 320), (211, 220, 222), 1))
    else:
        for forward in (8, 16, 24):
            for side in (-5.5, 5.5):
                center = lane_point(scene, forward, side)
                height = 4 + ((forward + int(side)) % 6)
                faces += box_faces(center[0], center[1], 6, 8, height, (210, 207, 194), angle=math.pi / 4)
                ridge_a = lane_point(scene, forward - 3, side, height + 1.4)
                ridge_b = lane_point(scene, forward + 3, side, height + 1.4)
                left_a = lane_point(scene, forward - 3, side - 4, height)
                left_b = lane_point(scene, forward + 3, side - 4, height)
                right_a = lane_point(scene, forward - 3, side + 4, height)
                right_b = lane_point(scene, forward + 3, side + 4, height)
                faces.append(([left_a, left_b, ridge_b, ridge_a], (112, 119, 119)))
                faces.append(([ridge_a, ridge_b, right_b, right_a], (88, 97, 100)))
        gate_forward = scene["art_lock"]["closed_gate_forward_m"]
        gate = [lane_point(scene, gate_forward, -1.2, 0), lane_point(scene, gate_forward, 1.2, 0),
                lane_point(scene, gate_forward, 1.2, 2.4), lane_point(scene, gate_forward, -1.2, 2.4)]
        faces.append((gate, (115, 82, 53)))
        rail = lane_point(scene, 2, -1.7)
        faces += box_faces(rail[0], rail[1], 1.8, 0.35, 0.8, (201, 200, 190), angle=math.pi / 4)
        person_base = lane_point(scene, 6.4, 1.5)
        lines.append((person_base, (person_base[0], person_base[1], 1.55), (62, 65, 61), 4))
        lines.append(((person_base[0], person_base[1], 1.55), (person_base[0], person_base[1], 1.72), (62, 65, 61), 5))
    return faces, lines


def render_frame(scene, time_s, size=None):
    size = size or scene["control_size"]
    camera = camera_for(scene, time_s)
    image = Image.new("RGB", size, (218, 228, 232))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, size[1] * 0.58, size[0], size[1]), fill=(195, 193, 180))
    faces, lines = scene_geometry(scene)
    projected = []
    for vertices, color in faces:
        try:
            points = [project_point(p, camera, size) for p in vertices]
        except ValueError:
            continue
        projected.append((sum(p[2] for p in points) / len(points), [(p[0], p[1]) for p in points], color))
    for _, points, color in sorted(projected, key=lambda item: item[0], reverse=True):
        draw.polygon(points, fill=color, outline=(77, 86, 89))
    for start, end, color, width in lines:
        try:
            a = project_point(start, camera, size)
            b = project_point(end, camera, size)
        except ValueError:
            continue
        draw.line((a[0], a[1], b[0], b[1]), fill=color, width=width)
    return image


def font(size):
    try:
        return ImageFont.truetype("msyh.ttc", size)
    except OSError:
        return ImageFont.load_default()


def draw_l007_elevation(draw, box, scene, west_view=False):
    x, y, w, h = box
    base = y + h - 24
    scale = (h - 50) / 368
    tower_w = w * 0.28
    cx = x + w / 2
    draw.rectangle((cx - w * 0.38, base - 24 * scale, cx + w * 0.38, base), fill=(105, 110, 113), outline=(60, 65, 68))
    top_left = base - (344 if west_view else 320) * scale
    top_right = base - (320 if west_view else 344) * scale
    draw.polygon([(cx - tower_w / 2, base), (cx + tower_w / 2, base),
                  (cx + tower_w / 2, top_right), (cx - tower_w / 2, top_left)], fill=(171, 187, 195), outline=(60, 65, 68))
    for floor in range(1, 78):
        yy = base - 320 * scale * floor / 78
        draw.line((cx - tower_w / 2, yy, cx + tower_w / 2, yy), fill=(121, 140, 148))
    antenna_x = cx - tower_w / 2 if west_view else cx + tower_w / 2
    antenna_base = top_left if west_view else top_right
    draw.line((antenna_x, antenna_base, antenna_x, base - 368 * scale), fill=(55, 62, 65), width=2)
    draw.text((x + 8, y + h - 20), "368m总高｜78层｜直线斜削", font=font(14), fill=(35, 46, 50))


def draw_r043_elevation(draw, box, scene, variant=0):
    x, y, w, h = box
    base = y + h - 28
    for index, offset in enumerate((0.12, 0.42, 0.70)):
        bx = x + w * offset
        bw = w * 0.24
        wall_h = 28 + ((index + variant) % 2) * 18
        roof_h = 14 + ((index + variant) % 3) * 4
        draw.rectangle((bx, base - wall_h, bx + bw, base), fill=(220, 216, 201), outline=(78, 80, 75))
        draw.polygon([(bx - 4, base - wall_h), (bx + bw / 2, base - wall_h - roof_h),
                      (bx + bw + 4, base - wall_h)], fill=(103, 111, 111), outline=(65, 70, 70))
    draw.line((x + 8, base - 12 * (h - 50) / 12, x + w - 8, base - 12 * (h - 50) / 12), fill=(180, 70, 60))
    draw.text((x + 8, y + h - 20), "1—2层｜屋脊4—9m｜限高12m", font=font(14), fill=(35, 46, 50))


def make_control_sheet(scene):
    sheet = Image.new("RGB", (1600, 1100), (246, 244, 237))
    draw = ImageDraw.Draw(sheet)
    draw.text((40, 24), f'{scene["id"]} {scene["name"]}｜几何控制板', font=font(32), fill=(28, 43, 48))
    draw.text((40, 70), scene["site"]["status"], font=font(18), fill=(85, 88, 82))
    draw.rectangle((35, 110, 510, 570), outline=(92, 103, 103), width=2)
    min_x, max_x, min_y, max_y = site_bounds(scene)
    sx = 420 / (max_x - min_x)
    sy = 400 / (max_y - min_y)
    scale = min(sx, sy)
    def map_point(p):
        return (275 + p[0] * scale, 340 - p[1] * scale)
    boundary = [map_point(p) for p in ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))]
    draw.polygon(boundary, fill=(226, 231, 220), outline=(66, 83, 79))
    start = map_point(scene["camera"]["start_m"])
    end = map_point(scene["camera"]["end_m"])
    draw.line((*start, *end), fill=(193, 81, 56), width=5)
    draw.ellipse((start[0] - 6, start[1] - 6, start[0] + 6, start[1] + 6), fill=(193, 81, 56))
    draw.ellipse((end[0] - 6, end[1] - 6, end[0] + 6, end[1] + 6), fill=(230, 147, 64))
    draw.text((55, 125), "场地工作轮廓与连续机位路径", font=font(20), fill=(35, 49, 50))
    draw.text((55, 535), f'{scene["site"]["width_m"]}m × {scene["site"]["depth_m"]}m｜北向↑', font=font(17), fill=(55, 65, 62))
    views = [(535, 110, 785, 340), (805, 110, 1055, 340), (1075, 110, 1325, 340), (1345, 110, 1595, 340)]
    for index, box in enumerate(views):
        x1, y1, x2, y2 = box
        draw.rectangle(box, outline=(150, 154, 148))
        draw.text((x1 + 8, y1 + 6), ("北向", "东向", "南向", "西向")[index], font=font(18), fill=(40, 50, 52))
        inner = (x1 + 5, y1 + 28, x2 - x1 - 10, y2 - y1 - 33)
        if scene["id"] == "L007":
            draw_l007_elevation(draw, inner, scene, index % 2 == 0)
        else:
            draw_r043_elevation(draw, inner, scene, index)
    draw.text((40, 595), "0 / 2 / 4 / 6 / 8秒关键帧｜同一静态场景，仅机位沿锁定路径变化", font=font(22), fill=(35, 49, 50))
    for index, time_s in enumerate(scene["key_times_s"]):
        thumb = render_frame(scene, time_s, (280, 340))
        x = 40 + index * 310
        sheet.paste(thumb, (x, 640))
        draw.text((x + 8, 990), f"{time_s}s", font=font(18), fill=(35, 45, 47))
    return sheet


def save_scene_assets(scene):
    validate_scene(scene)
    target = OUT / scene["id"]
    target.mkdir(parents=True, exist_ok=True)
    make_control_sheet(scene).save(target / "平面四向与关键帧.png")
    for time_s in scene["key_times_s"]:
        render_frame(scene, time_s).save(target / f"关键帧-{time_s:02d}s.png")
    card = copy.deepcopy(scene)
    card["validation"] = {"passed": True, "checks": ["面积匹配", "路径不越界", "机高恒定", "关键帧完整"]}
    (target / "镜头卡.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix=f'{scene["id"]}-frames-') as temp:
        temp_path = Path(temp)
        for index in range(scene["duration_s"] * 24):
            render_frame(scene, index / 24).save(temp_path / f"{index:04d}.png")
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", "24",
            "-i", str(temp_path / "%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(target / "白模预演-8s.mp4"),
        ], check=True)
    return target


def main():
    for scene in SCENES.values():
        target = save_scene_assets(scene)
        print(f'{scene["id"]}: {target}')


if __name__ == "__main__":
    main()
