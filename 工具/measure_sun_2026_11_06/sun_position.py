# -*- coding: utf-8 -*-
"""极亮簇（日面）定位：在既有 measure_images.sun_blob 口径上补质心与包围盒。

复用口径申报（与已交付批次证据链对齐，不修改历史脚本本体）：
- 判据口径完全沿用 工具/reinject_2026_11_05/measure_images.py 的
  sun_blob(gray)（该文件 :79-108）：
  ① 灰度阈值 >=250；
  ② 只扫上半区 a[: a.shape[0] // 2, :]（下半区一律不计）；
  ③ 4x 降采样聚合（4x4 块内任一像素过阈即该降采样格为真，残行/残列丢弃）；
  ④ 降采样网格上做 4-邻接洪水填充取最大连通块；
  ⑤ 面积按 *16 还原回原分辨率像素数。
- 本文件不改动、不复制改写那台历史脚本，而是用
  importlib.util.spec_from_file_location 把它作为参照实现加载进来，
  每枚图都把它算出的 sun_blob(gray) 与本文件自算的最大连通块面积逐枚对拍，
  不相等即抛错（判据漂移必须炸，不许静默）。注意：直接 import 该历史脚本
  没有副作用风险——它只在 main() 里写文件，模块级只读 数据/开图清单.json。

质心算法申报（两种候选取哪一种、为什么）：
- 本文件取「该最大连通块所辖降采样格覆盖到的全部原始极亮像素
  （>=250、在上半区内）的均值」，不是「降采样格中心坐标的均值」。
  原因：格中心均值带 4px 网格量化（每格都代表其左上角中心），
  会把质心最多拉偏 ±2px 且带系统性方格吸附；台账旧读数
  （如 00格 x=484/960、簇 2745 像素）是像素级目视手算，
  用原始像素均值才和那种读数在同一精度上对话。
- 面积 area_px 仍按 ③⑤ 的格口径 *16 还原（不是组件内真实过阈像素计数）——
  这是与 sun_blob 对拍的量，口径必须原样，不许为了「更准」而改。
- bbox 为还原回原分辨率的包围盒 [x0, y0, x1, y1]（x1/y1 为开区间右/下缘，
  即 max+1），由组件内原始极亮像素的 min/max 求得，不是降采样网格坐标。

哨兵分支申报：
- 上半区找不到任何 >=250 像素时返回
  {cx_px: None, cy_px: None, cx_ratio: None, cy_ratio: None,
   area_px: 0, bbox: None, w: 实际宽, h: 实际高}，
  位置字段全部 None。绝不再返回 (0, 0)——(0,0) 是合法的左上角坐标，
  静默返回会被误读成「日面在左上」的假结论（这正是本判据要防的错）。

用法：
  python sun_position.py 图1.png [图2.jpg ...]   # 逐枚打印 JSON（ensure_ascii=False）
临时文件约定：本工具只读图，不落盘；测试夹具一律走 tempfile。
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

THRESHOLD = 250          # 与 sun_blob ①一致
DOWN = 4                 # 与 sun_blob ③一致（4x 降采样）
AREA_RESTORE = DOWN * DOWN  # 与 sun_blob ⑤一致（*16 还原）

_REF_PATH = Path(__file__).resolve().parents[1] / "reinject_2026_11_05" / "measure_images.py"


def _load_reference():
    """按文件路径加载历史脚本，只借它的 sun_blob 作对拍参照。"""
    spec = importlib.util.spec_from_file_location("measure_images_ref", _REF_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sentinel(gray=None):
    """无极亮像素的明确哨兵：位置字段全 None、area_px=0，不冒充 (0,0)。"""
    w, h = (gray.size if gray is not None else (None, None))
    return {"cx_px": None, "cy_px": None, "cx_ratio": None, "cy_ratio": None,
            "area_px": 0, "bbox": None, "w": w, "h": h}


def sun_position(gray):
    """对 PIL「L」图求上半区最大极亮连通块的位置。

    返回 {cx_px, cy_px, cx_ratio, cy_ratio, area_px, bbox, w, h}；
    无过阈像素时走 sentinel()。area_px 与参照实现 sun_blob() 对拍，
    不一致即抛 RuntimeError（判据漂移不许静默）。
    """
    a = np.asarray(gray, dtype=np.uint8)
    H, W = a.shape
    top = a[: H // 2, :]                       # 口径②：只扫上半区
    mask = top >= THRESHOLD                    # 口径①：>=250
    if not mask.any():
        return sentinel(gray)

    # 口径③：4x 降采样 any 聚合，与 sun_blob :88-90 同式（残行残列丢弃）
    h_res, w_res = mask.shape
    bh, bw = h_res // DOWN, w_res // DOWN
    small = mask[: bh * DOWN, : bw * DOWN].reshape(bh, DOWN, bw, DOWN).sum(axis=(1, 3)) > 0

    # 口径④：4-邻接洪水填充，逐块记账（sun_blob :91-107 只求最大块面积）
    seen = np.zeros_like(small, dtype=bool)
    best_cells = None
    best_size = 0
    for sy in range(bh):
        for sx in range(bw):
            if not small[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            cells = []
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < bh and 0 <= nx < bw and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(cells) > best_size:          # 平手保留先见块，与 sun_blob 的 max 同语义
                best_size = len(cells)
                best_cells = cells

    if best_cells is None:
        # 过阈像素全落在被丢弃的残行/残列里（口径③不计）——等同于无日面，走哨兵
        return sentinel(gray)

    area_px = int(best_size * AREA_RESTORE)     # 口径⑤：*16 还原

    # 与历史脚本参照实现对拍；不等说明两边口径漂了，必须炸不许静默
    ref = _load_reference()
    ref_area = ref.sun_blob(gray)
    if area_px != ref_area:
        raise RuntimeError("判据漂移：本实现 area_px=%d != 参照 sun_blob=%d" % (area_px, ref_area))

    # 组件所辖降采样格展开回原分辨率，取其中真实过阈像素
    comp_grid = np.zeros((bh, bw), dtype=bool)
    for (y, x) in best_cells:
        comp_grid[y, x] = True
    expanded = np.repeat(np.repeat(comp_grid, DOWN, axis=0), DOWN, axis=1)
    pix = mask[: bh * DOWN, : bw * DOWN] & expanded
    ys, xs = np.nonzero(pix)                    # 原始像素坐标（上半区内）
    cx = float(xs.mean())                       # 质心＝组件内全部原始极亮像素均值
    cy = float(ys.mean())
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]

    w, h = gray.size
    return {
        "cx_px": int(round(cx)),
        "cy_px": int(round(cy)),
        "cx_ratio": round(cx / w, 2),
        "cy_ratio": round(cy / h, 2),
        "area_px": area_px,
        "bbox": bbox,
        "w": w,
        "h": h,
    }


def sun_position_file(path):
    """读一枚 PNG/JPG，转「L」后求日面位置（与 measure() 同样的 convert 口径）。"""
    img = Image.open(path)
    img.load()
    try:
        return sun_position(img.convert("L"))
    finally:
        img.close()


def main(argv=None):
    paths = list(sys.argv[1:] if argv is None else argv)
    if not paths:
        print(__doc__)
        return 1
    for p in paths:
        print(json.dumps({"file": str(p), **sun_position_file(p)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
