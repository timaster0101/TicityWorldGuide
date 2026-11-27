# 数据字段字典（SCHEMA）

`数据/` 下有 93 个 JSON。这份文件说清每类文件的**用途**与**关键字段**，够你写脚本读写，不要求你读完全部正典。

全部 JSON 都是 UTF-8、对象或数组、可直接 `json.load`。用 Python 读：

```python
import json, io
with io.open("数据/城市空间名录.json", encoding="utf-8") as fp:
    canon = json.load(fp)
print(canon["region_area_km2"], len(canon["entries"]))
```

---

## 1. 通用约定

带正典性质的 JSON 顶层都有这几项：

| 键 | 类型 | 含义 |
| --- | --- | --- |
| `version` | str | 该文件的版本，如 `"1.0"` |
| `fictional` | bool | 恒 `true`：明确虚构 |
| `setting_year` | int | 恒 `2013`：基准年 |
| `currency` / `currency_name` | str | 币种代码与显示名（经济类文件才有） |
| `declaration` | str | 该文件的一句话权威声明 |

账本类文件（开图清单、图集清单、裁定记录、投送台账）**没有** `setting_year`，用时别假设。

---

## 2. 文件分工（按用途分六组）

| 组 | 文件 | 用途 |
| --- | --- | --- |
| **正典** | `城市空间名录.json`、`物价与生活正典.json`、`空间通行正典.json`、`产业就业正典.json`、`岗位准入正典.json`、`流程制度正典.json`、`运行参数正典.json` | 城市事实，改它等于改世界 |
| **源表** | `*源表.json`（物价生活、空间通行、产业就业、岗位准入、流程制度、运行参数、职业条目、卡牌实例） | 生成正典的手写输入，**不要直接改正典** |
| **分卷成稿** | `01-外围村镇.json` … `11-居民区第4卷.json` | 由原稿展开的 11 卷结构化稿 |
| **开图账** | `开图清单.json`、`开图提示词/`、`开图验收备注.json`、`提示词基准冻结.json` | 312 个地点的出图状态与提示词 |
| **图集账** | `图集清单.json`、`图集AIGC声明.json`、`图片资产核验.json`、`图集迁移明细_20261107.json`、`下一轮重投候选.json` | 808 件图的清单、授权声明、逐格核验 |
| **核验读数** | `质量核验结果.json`、`Word核验结果.json`、`Word渲染目视.json`、`取景几何核验.json`、`天际线落位核验.json`、`片区重复构图复验.json` 等 | 各闸门的机读结论，**只读** |

`*源表.json` → `*正典.json` 的关系是**单向**：改源表后由生成器重算正典。手改正典会在下一次 rebuild 被覆盖。

---

## 3. `城市空间名录.json`（最重要的一份）

312 个地点的唯一权威表。

顶层：

| 键 | 类型 | 含义 |
| --- | --- | --- |
| `version` | str | `"1.0"` |
| `fictional` | bool | `true` |
| `setting_year` | int | `2013` |
| `coordinate_system` | str | `"THC-LOCAL-2013：千米；湖心(0,0)；x东正、y北正；方位角北0度顺时针；高程米"` |
| `region_area_km2` | number | `4608` |
| `urban_radius_km` | number | `10.2` |
| `population` | object | 见下 |
| `entries` | array | 312 条地点 |

`population` 子字段：`city_core` 3200000、`satellite_settlements` 332200、`dispersed_rural` 42000、`regional_total` 3574200、`featured_residences` 1358300。

`entries[i]` 字段：

| 字段 | 类型 | 含义 | 可改 |
| --- | --- | --- | --- |
| `id` | str | 地点编号（`S01`…`R120`） | 否 |
| `name` | str | 官方名称 | 否 |
| `type` | str | 城市片区／功能区／标志性建筑／居民区／产业小镇／特色村落 | 否 |
| `parent` | str | 上级 ID，顶层为 `CITY` | 否 |
| `center_km` | `[x, y]` | 中心坐标（千米） | 否 |
| `area_km2` | number | 占地（平方公里） | 否 |
| `population` | int | 该地点在册人口 | 否 |
| `focus` | str | 功能定位 | 是（软区） |
| `visual` | str | 视觉形态一句话 | 是（软区） |
| `sector` | object | `angle_center_deg`、`angle_half_width_deg`、`inner_radius_km`、`outer_radius_km`、`exclude_lake` | 否 |
| `ring` | str | 内湖环／外城环／产业小镇／特色村落 | 否 |
| `distance_to_lake_center_km` | number | 到湖心直线距离 | 否（派生） |
| `bearing_from_lake_center_deg` | number | 相对湖心方位角（北 0° 顺时针） | 否（派生） |

---

## 4. `开图清单.json`（出图账）

顶层：`version`、`fictional`、`setting_year`、`declaration`、`prompt_count`（312）、`pending`、`generated`、`accepted`、`needs_review`、`batch_order`、`items`。

`items[i]` 字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` / `name` / `type` / `parent` / `parent_name` / `ring` | str | 与名录一致 |
| `center_km` | `[x, y]` | 机位所在坐标 |
| `distance_to_lake_center_km` | number | 到湖心距离 |
| `size` | str | 出图尺寸，如 `1792x1024`、`1024x1536` |
| `aspect` | str | 画幅，如 `7:4` |
| `camera_facing_deg` | number | 相机朝向（北 0° 顺时针） |
| `sun_relative_deg` | number | 太阳相对机位的方位差 |
| `sun_side` | str | 顺光／侧光／逆光 |
| `lighting_baseline` | str | 光照基准说明 |
| `pricing_reference` | str | 该图定价参照（出图计价用） |
| `prompt_file` | str | 提示词文件路径（相对仓根） |
| `image_file` | array | 该地点所有已生成图的路径（**在册格 = `image_file[0]`**） |
| `batch` | str | 出图批次标签 |
| `status` | str | `待开图`／`待复验`／`已验收` |
| `acceptance` | str | 验收说明（机械判据／目视／代签） |
| `prompt_sha256` | str | 提示词全文摘要（与 `提示词基准冻结.json` 对拍） |
| `image_prompt_sha256` | str \| null | 该图绑定的提示词摘要；未绑为 `null` |
| `review_note` | str | 最近一条复验备注（多行文本） |
| `review_note_history` | array[str] | 备注全史（只追加） |

**不要手改这个文件**。它是 `build_prompts.py --rebuild` 与 `sync_manifest_counts.py` 的产物，手改会被覆盖。

---

## 5. `图集清单.json` 与 `图集AIGC声明.json`

`图集清单.json`：顶层 `说明`／`口径`／`接线`／`统计`／`逐件`。

- `逐件[i]` 四键：`路径`（`数据/图集/<ID>/<文件名>`）、`字节`、`sha256`、`url`（OSS 直链，由 `工具/oss_gallery.py --backfill` 回写；`build_gallery_manifest.py` 重写清单时原样带回）
- 用途：`mirror_gallery.py` 做仓外镜像时按 `sha256` 逐件对拍

`图集AIGC声明.json`：顶层 `说明`／`口径`／`接线`／`统计`／`逐件`。

- `逐件[i]`：`ID`／`名称`／`类型`／`路径`／`字节`／`sha256`／`来源通道`／`模型`／`生成日期`／`水印`／`元数据`／`提示词摘要12`
- **这是图集唯一的授权标识载体**：图不在仓，声明在仓；转载图必须随附

---

## 6. `设定裁定记录.json` 与 `在册裁定收口.json`

`设定裁定记录.json` 是**数组**（不是对象），156 条：

| 键 | 类型 | 含义 |
| --- | --- | --- |
| `编号` | str | `C1` … `C155`、`C157` |
| `裁定` | str | 结论原文（可长，含①②③分项） |
| `原因` | str | 依据 |
| `影响` | str | 影响到哪些文件／判据 |

`在册裁定收口.json`：顶层 `口径`／`委托来源`／`统计`／`逐条`，7 条（D06 D09 D10 D11 D12 D15 D20），记录「在册那张图仍是换档前的串所出、不可签」的处理结果。

---

## 7. 出图投送台账（`R10/R11/R12方舟投送记录.json`）

每枚一次调用一行，字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 地点 ID |
| `file` | 落盘文件名（`vibe_images/<发名>_<13位毫秒>_<sha8>.png`） |
| `bytes` / `sha256` / `sha256_jpeg` | 字节数与两种摘要（URL 回的是 JPEG，转 PNG 后两者不同） |
| `size` | 请求尺寸 |
| `seconds` | 耗时 |
| `cost` | 本次花费（元） |
| `model` | 模型 id |
| `input_images` | 服务端确认收到的母图数（必须 `1`） |
| `note` | 备注（如 `conv` 表示做过格式转换） |

同目录另有 `round_readings_*.json`（逐条核验结果）与 `ledger_*.json`（回填台账）。

---

## 8. `图片资产核验.json`（闸门读数）

| 键 | 含义 |
| --- | --- |
| `文件格数` | 参与核验的图片格总数（1125） |
| `通过格数` / `失败格数` / `提示格数` | 结果计数 |
| `C2PA在位格数` | 带 `caBX` 容器的格数（162） |
| `iTXt标识在位格数` | 带 `iTXt` 元数据的格数（310） |
| `容器计数` | `XMP·TC260`／`C2PA(caBX)`／`iTXt·TC260` 三类的件数 |
| `失败明细` | 数组，空表示全绿 |

---

## 9. 稳定性承诺

| 变化等级 | 说明 |
| --- | --- |
| 稳定 | `城市空间名录.json` 的硬正典字段、`设定裁定记录.json` 的既有条目、ID 编号 |
| 可能增补 | `开图清单.json` 的 `items`（新增地点时）、`图集清单.json` 的 `逐件` |
| 随判据动 | 各种 `*核验.json` 的键名与计数（机器读数，别当接口用） |

要长期依赖某字段，请以 `城市空间名录.json` 为准，并在自己的派生项目里做一层适配。

## 8. 图集直链表（`数据/图集OSS.json`）

图集不在仓，这份表是唯一的取图入口。生成器：`工具/oss_gallery.py --links`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `bucket` / `region` / `prefix` | str | `timaster` / `oss-cn-shenzhen` / `taihucheng/` |
| `base_url` | str | 直链前缀 |
| `统计` | object | `地点数`(312)／`件数`(967)／`合计字节` |
| `按地点` | object | `ID → [{文件, url, bytes}]`，给「这个地点有哪几张图」用 |
| `逐件` | object | `仓内相对路径 → {key, url, bytes}`，与 `数据/图集清单.json` 的 `逐件` 一一对应 |

不变量（`工具/test_oss_gallery.py` 守着）：

1. 图集清单里每一件，在 `逐件` 里都要有对应行；
2. `key` 必须落在 `taihucheng/` 前缀内（Bucket Policy 只放开这个前缀）；
3. `url` 必须由 `base_url` + `key` 拼成，不带签名参数。

桶是私有的，`taihucheng/` 之外的键（`meixi/`、`pics/`、`software/`、`video/`）匿名读不到，别把它们的地址写进文档。

### 8.1 回写：`开图清单.json` 的 `image_url`

`items[i].image_url` 是与 `items[i].image_file` **逐格对齐**的列表（第 k 个 URL 对第 k 张图），
由 `工具/oss_gallery.py --backfill` 从 `数据/图集OSS.json` 回写。1,125 格全部有链（2026-11-28 实测）。

- 长度必须等于 `image_file`；缺链写 `null` 并让 `--backfill` 以退出码 1 报出来，不许静默留白；
- 不参与 `prompt_sha256` / `image_prompt_sha256` 的任何绑定计算——绑定认的是提示词串，URL 只是取图位置；
- 人工读版本在 `数据/图集直链.md`（一地点一行，图名即可点的链接）。
