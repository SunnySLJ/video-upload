---
name: flash-longxia
description: Generate one video from 1 to 4 local images and query or download completed videos for the zhenlongxia or flash_longxia workflow in this project. Supports optional industry-template selection before generation. Use when the user asks to run this repo's image-to-video pipeline, inspect available models or industry templates, submit a generation task with up to 4 images, query a task by ID, download a finished video by task ID, or troubleshoot flash-longxia generation and download issues. Do not use this skill as the public entrypoint; public routing goes through video-workflow.
---

# flash-longxia

使用此 skill 时，优先复用 skill 自带脚本，不要重新实现上传、图生文、模型查询、行业模板查询、生成和下载 API。

## 定位仓库

- 先定位包含 `flash_longxia/zhenlongxia_workflow.py` 的仓库根目录。
- 封装脚本会优先尝试当前目录、环境变量 `OPENCLAW_UPLOAD_ROOT`、`~/Desktop/openclaw_upload` 和 `~/.openclaw/workspace/openclaw_upload`。
- 若自动定位失败，显式设置 `OPENCLAW_UPLOAD_ROOT=/path/to/openclaw_upload` 再运行命令。
- 若工作区目录不是默认值，同时设置 `OPENCLAW_WORKSPACE_ROOT=/path/to/workspace`。

## 前置条件

- 使用 `python3.11`；Hermes 下优先使用 `OPENCLAW_PYTHON` 或仓库根目录 uv `.venv/bin/python`。
- 确保 `flash_longxia/config.yaml` 已准备好。
- 确保 `flash_longxia/token.txt` 存在，或在命令中传 `--token=...`。
- 视频完成通知只保留飞书，提前配置 `FEISHU_NOTIFY_TARGET` 或 `FLASH_LONGXIA_FEISHU_TARGET`。
- 生成任务支持传 1 到 4 张本地图片路径，并生成 1 个视频；查询/下载任务需要 `generateVideo` 返回的任务 ID。

## 常用命令

```bash
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/generate_video.py --list-models [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/generate_video.py --list-templates [--mediaType=1] [--tabType=...] [--pageNum=1] [--pageSize=10] [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/generate_video.py <image-path> [--model=...] [--duration=10] [--aspectRatio=16:9] [--variants=1] [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/generate_video.py <image1> <image2> [image3] [image4] [--model=...] [--duration=10] [--aspectRatio=16:9] [--variants=1] [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/generate_video.py <image-path> --yes [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/download_video.py <task-id> [--token=...]
${OPENCLAW_PYTHON:-./.venv/bin/python} scripts/download_video.py <task-id> --check-only [--token=...]
```

## 执行规则

- 先用 `--list-models` 获取可用 `model`、`duration` 和 `aspectRatio`。
- 需要行业模板时，先调用模板分类接口 `api/v1/aiTemplateCategory/getList`，传 `mediaType=1`；优先选择 `tabName=行业模板` 对应的 `tabType`，再调用 `api/v1/aiTemplate/pageList`，传 `pageNum=1`、`pageSize=10` 和该 `tabType`。
- 交互式生成时，如果用户选择使用行业模板，先把模板列表展示给用户，再根据用户选择的模板把 `tmpplateId` 和模板 `title` 一起传给 `generateVideo`；如果用户跳过模板，则不要传模板参数。
- 只传后端模型接口支持的 `model`、`duration`、`aspectRatio` 组合。
- 保持参数名 `aspectRatio` 为驼峰写法。
- 不要向请求体加入 `style` 或 `quality`。
- 图生文失败或提示词校验失败时，立即停止，不要继续发起生成。
- 默认保留人工确认；只有明确需要无人值守时才传 `--yes`。
- 生成成功后返回任务 ID；查询或补下载时调用 `scripts/download_video.py`，不要重写查询逻辑。
- 多图模式下，最多传 4 张本地图片。脚本会逐张上传，然后将这 1 到 4 个远程图片 URL 一起传给 `generateVideo`，最终仍只生成 1 个视频；图生文默认只使用第 1 张图片。
- 如果传入超过 4 张图片，应主动报错，不要继续提交任务。
- 发起生成前，必须在日志中打印本次实际提交的图片 URL 列表，便于核对多图输入是否完整。
- 查询 `getById` 时，不要只看顶层 `status`。如果顶层 `mediaUrl` 已存在，或 `repMsg.data.status=2` / `repMsg.data.result` 已返回成片链接，也应视为已完成。
- 任务查询、补下载和轮询统一复用仓库里的 `flash_longxia/zhenlongxia_workflow.py`。

## ⚠️ 超时处理硬性规定

- **单个视频任务最多等待 30 分钟（从提交任务开始计时）**
- **超时后必须放弃任务，停止轮询**
- **超时后必须通知用户任务失败，说明原因**
- 通知内容需包含：任务 ID、开始时间、超时时间、最终状态、失败原因
- 询问用户是否需要重新生成该任务

## 排错

- 模型参数报错时，先重新执行 `--list-models`。
- 找不到仓库时，检查 `OPENCLAW_UPLOAD_ROOT` 是否指向包含 `flash_longxia/` 的目录。
- Token 报错时，检查 `flash_longxia/token.txt` 或显式传 `--token=...`。
- 下载失败时，确认传入的是生成接口返回的任务 ID，而不是其他业务字段。
- 如果 `getById` 返回顶层 `status=1`，但已有 `mediaUrl` 或 `repMsg.data.status=2`，这是后端状态未同步，不是下载脚本故障。
