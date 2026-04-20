---
name: video-workflow
description: 统一视频工作流入口。处理图生视频生成、视频号登录和视频号发布。内部模块继续保留，但不要把 auth、flash-longxia、openclaw_upload/upload.py 当作独立入口对外调用。
---

# video-workflow

这是当前对 OpenClaw 暴露的统一视频工作流入口。

内部模块仍然分目录维护，但它们只是实现模块：

- `skills/flash-longxia/`：图生视频生成、任务查询、视频下载
- `skills/auth/`：视频号登录检查、补登录、二维码登录
- 登录二维码若过期，auth 会自动关闭旧 connect Chrome，重新取码并重新发飞书
- `openclaw_upload/upload.py`：视频号发布

## 路由规则

### 1. 图生视频

用户提到以下意图时，走 `flash-longxia` 模块：

- 生成视频
- 图生视频
- 图片转视频
- 查询模型
- 查询行业模板
- 查询任务
- 下载视频

优先命令：

```bash
cd ~/.openclaw/workspace && ${OPENCLAW_PYTHON:-./openclaw_upload/.venv/bin/python} skills/flash-longxia/scripts/preflight.py
cd ~/.openclaw/workspace && ${OPENCLAW_PYTHON:-./openclaw_upload/.venv/bin/python} skills/flash-longxia/scripts/generate_video.py --list-models
cd ~/.openclaw/workspace && ${OPENCLAW_PYTHON:-./openclaw_upload/.venv/bin/python} skills/flash-longxia/scripts/generate_video.py <image-path> [--model=...] [--duration=10] [--aspectRatio=16:9]
cd ~/.openclaw/workspace && ${OPENCLAW_PYTHON:-./openclaw_upload/.venv/bin/python} skills/flash-longxia/scripts/download_video.py <task-id>
```

### 2. 视频号登录

用户提到以下意图时，走 `auth` 模块：

- 登录视频号
- 重新登录视频号
- 视频号扫码登录
- 视频号会话过期
- 先登录再发布

优先命令：

```bash
${OPENCLAW_PYTHON:-~/.openclaw/workspace/openclaw_upload/.venv/bin/python} ~/.openclaw/workspace/skills/auth/scripts/platform_login.py --platform shipinhao --check-only
${OPENCLAW_PYTHON:-~/.openclaw/workspace/openclaw_upload/.venv/bin/python} ~/.openclaw/workspace/skills/auth/scripts/platform_login.py --platform shipinhao
```

### 3. 视频号发布

用户提到以下意图时，走 `openclaw_upload/upload.py`：

- 上传到视频号
- 发布视频号
- 继续发布
- 重传视频号

优先命令：

```bash
cd "${OPENCLAW_UPLOAD_ROOT:-~/.openclaw/workspace/openclaw_upload}" && ${OPENCLAW_PYTHON:-./.venv/bin/python} upload.py --platform shipinhao "<视频路径>" "<标题>" "<文案>" "<标签1,标签2,...>"
cd "${OPENCLAW_UPLOAD_ROOT:-~/.openclaw/workspace/openclaw_upload}" && ${OPENCLAW_PYTHON:-./.venv/bin/python} upload.py --platform shipinhao "<视频路径>" --login-only
```

## 总体规则

1. 对外只暴露 `video-workflow` 这一个 skill。
2. 内部模块目录继续保留，各自脚本路径不变。
3. 不要再把 `auth`、`flash-longxia`、`openclaw_upload/upload.py` 当作独立入口对外引用。
4. 需要登录、生成、发布时，统一通过本 skill 根据用户意图路由到对应模块。
5. 当前通知链路只保留飞书，不走微信。
