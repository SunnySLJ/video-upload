---
name: video-workflow
description: 统一视频工作流入口。处理图生视频生成、模型与模板查询、任务查询和视频下载。内部模块保持独立，但不要把 flash-longxia 当作独立 skill 调用。
---

# video-workflow

这是当前对 OpenClaw 暴露的唯一技能入口。

当前仓库里的内部模块：

- `skills/flash-longxia/`：图生视频生成、模型查询、模板查询、任务查询、视频下载
- `scripts/platform_login.py`：视频号登录检查/补登录
- `upload.py`：视频号发布统一入口

## 路由规则

### 图生视频

用户提到以下意图时，路由到 `flash-longxia` 内部模块：

- 生成视频
- 图生视频
- 图片转视频
- 查询模型
- 查询行业模板
- 查询任务
- 下载视频
- 排查生成失败

### 视频号登录/发布

用户提到以下意图时，先路由到 `scripts/platform_login.py` 做登录检查，再路由到 `upload.py` 做发布：

- 登录视频号
- 视频号扫码登录
- 视频号登录失效
- 检查视频号登录状态
- 发布视频号
- 继续发布

优先命令：

```bash
python3 skills/flash-longxia/scripts/generate_video.py --list-models
python3 skills/flash-longxia/scripts/generate_video.py --list-templates [--mediaType=1] [--pageNum=1] [--pageSize=10]
python3 skills/flash-longxia/scripts/generate_video.py <image-path> [--model=...] [--duration=10] [--aspectRatio=16:9] [--variants=1]
python3 scripts/platform_login.py --project-root <repo-root> --platform shipinhao --check-only
python3 upload.py --platform shipinhao <video-path> <title> <description> <tags>
```

## 总体规则

1. 对外只暴露 `video-workflow` 这一个 skill。
2. `flash-longxia` 目录继续保留，但仅作为内部模块使用。
3. 不要再把 `flash-longxia` 当作独立 skill 名称对外引用。
4. 视频号登录检查由 `scripts/platform_login.py` 统一处理，二维码发送由外层调用飞书消息工具。
5. 所有图生视频与发布相关能力统一通过本 skill 进入，再路由到内部模块。


## 登录收口

- 登录脚本检查通过后，视为发布前置条件已满足。
- 若本地缓存被清空而外部 connect 会话仍可复用，不要再强制重新扫码。
- 二维码仅在登录检查失败且确实需要重新拉起会话时才发。


## 成品回传

- 视频生成成功后，应优先把成片 MP4 回传到飞书 DM；如果回传失败，至少发送本地路径。
- 发布成功后，再补一条“已发布成功”的通知。
- 生成与发布是两条不同链路，不能只完成其中一条。
