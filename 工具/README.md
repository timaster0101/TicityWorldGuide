# 工具/ 目录说明

仓库里所有可执行的生成器、核验器与闸门都在这里。真源是 `分卷/原稿/*.md` 与 `数据/*源表.json`，
本目录只做「展开、核验、记账」，**任何产物都不在这里手改**。

## 一、日常只用这五条

```powershell
# 从真源重建全书（正典／总表／分卷成稿／合订本 md＋docx／名录／知识库）
python -X utf8 工具/build_prompts.py --rebuild

# 核验：图片资产（1125 格逐格）／合订本 docx／清单 Markdown
python -X utf8 工具/verify_image_assets.py
python -X utf8 工具/verify_docx.py
python -X utf8 工具/render_manifest_md.py --check

# 全量单测（788 例，约 7.5 分钟）
python -X utf8 -m unittest discover -s 工具 -p "test_*.py"
```

## 二、按角色分工

| 角色 | 脚本 | 说明 |
|---|---|---|
| 书稿展开 | `build_prompts.py` | 唯一入口；产物含 `钛湖城城市设定集-完整合订本.md/.docx`、`阅读入口.md`、`质量核验报告.md` |
| 清单渲染 | `manifest_md.py`（库）／`render_manifest_md.py`（命令） | `数据/开图清单.md` 的唯一渲染方；`--check` 只核对 |
| 清单计数 | `sync_manifest_counts.py` | 只写 prompt_count／pending／generated／accepted／needs_review 五个计数 |
| 图片核验 | `verify_image_assets.py` | 逐格核 1125 格，写 `数据/图片资产核验.json`＋`数据/图片复验清单.md` |
| 图集账 | `build_gallery_manifest.py`／`mirror_gallery.py` | 前者出 `数据/图集清单.json`，后者做仓外镜像与 `--verify` 对拍 |
| AIGC 声明 | `build_aigc_declaration.py` | 逐件声明（含 C2PA／iTXt 实测），`--check` 只核对 |
| docx 核验 | `verify_docx.py` | 结构＋官方 XSD（`工具/官方模式/`）；`rendering_verified` 只读 `数据/Word渲染目视.json` |
| 版面体检 | `inspect_print_pages.py` | LibreOffice／WPS 出 PDF 后逐页像素体检；页图是可再生的中间产物 |
| 代签 | `sign_acceptance.py` | 受用户逐字委托时按 `--ids` 收窄面代签；`check_sign_declaration` 是判据 |
| 裁定 | `append_ruling_c155.py`、`ruling_closeout.py` | 前者追加裁定条（155 条末条 C155），后者做 C155 在册裁定收口 |
| 单测 | `test_*.py` | 788 例；判据改动必须配违例负测 |

## 三、分批与轮次

`reshoot_campaign_2026_11_06/` 是出图轮次的完整链路，同一套骨架按轮次参数化：

- 建台账：`build_send_bodies_r10.py`／`_r11`／`_r12`（成员面现算＋冻名单 `frozen(ids)`／`build(ids)`）
- 投送：`send_r10_ark.py`／`send_r11_ark.py --round {R11,R12}`（火山方舟标准域，`image` 单数传母图，硬断言 `input_images==1`）
- 核验：`verify_round.py`（ImageGen 通道，读会话 jsonl）／`verify_round_ark.py --round {R10,R11,R12}`（方舟通道，读投送台账）
- 回填：`backfill_round.py {R4,R7,R8,R10,R11,R12}`（逐字节对拍后请进 `数据/图集/<ID>/`）
- 参考件：`r4_style_ref.py`（前导句、母图池、`send_body()` 唯一拼接处）、`current_cells.py`（现读在册格）

历史批次目录（`batch9b…9h`、`reinject_2026_11_05`、`parallel_batch_2026_11_03`、`measure_sun_2026_11_06`）
只保留脚本与机读读数；它们的过程图（crops／放大件）已于 2026-11-27 移到项目外归档
（`D:\bak\钛湖城-项目归档-2026-11-27\工具-过程图\`），需要复看时按同目录脚本重切。

## 四、两条不许破的规矩

1. **生成物永不手改**——改 `分卷/原稿/*.md` 或 `数据/*源表.json`，再 `--rebuild` 重跑全链。
2. **新判据必须配违例负测**——临时目录造夹具、断言必须判红、复核残留 0。
