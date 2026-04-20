# flash-longxia module

这是 `video-workflow` 的内部模块，不再作为独立 skill 暴露。

用途：

- 图生视频生成
- 查询可用模型
- 查询行业模板
- 查询任务状态
- 下载成片

常用命令：

```bash
python3 skills/flash-longxia/scripts/generate_video.py --list-models
python3 skills/flash-longxia/scripts/generate_video.py --list-templates --mediaType=1 --menuType=1
python3 skills/flash-longxia/scripts/generate_video.py --list-templates --mediaType=1 --menuType=1 --tabType=<行业码>
python3 skills/flash-longxia/scripts/generate_video.py <image-path> [--model=...] [--duration=10] [--aspectRatio=16:9] [--variants=1]
python3 skills/flash-longxia/scripts/download_video.py <task-id>
python3 skills/flash-longxia/scripts/download_video.py <task-id> --check-only
```

## 行业模板查询（2026-04-20 更新）

- 第一步先跑不带 `--tabType` 的 `--list-templates`，拿到行业分类列表
- 第二步从输出里选一个 `tabType`，再带 `--tabType=<行业码>` 查询该行业下的模板
- `mediaType`、`menuType` 常用值都是 `1`
