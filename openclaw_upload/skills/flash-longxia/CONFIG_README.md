# flash-longxia 配置说明

`flash-longxia` 现在是 OpenClaw `video-workflow` 的内部模块，运行时以
`~/.openclaw/workspace/openclaw_upload/flash_longxia/config.yaml` 为准。

当前版本已经切到最新的 `openclaw_upload` 实现，通知链路只保留飞书。

## 关键配置文件

- 主配置：`flash_longxia/config.yaml`
- Token：`flash_longxia/token.txt`
- 输出目录：`flash_longxia/output/`
- 通知载荷：`flash_longxia/notify_<task_id>.json`

## 常改字段

```yaml
base_url: "http://123.56.58.223:8081"

video:
  model: "auto"
  duration: 10
  aspectRatio: "9:16"
  variants: 1
  poll_interval: 30
  max_wait_minutes: 30
  output_dir: "./output"
  confirm_before_generate: true

notify:
  channel: "feishu"
  feishu_target: "ou_xxx"
```

## 字段说明

| 字段 | 作用 |
|------|------|
| `video.model` | 默认视频模型 |
| `video.duration` | 默认时长（秒） |
| `video.aspectRatio` | 默认画幅比例 |
| `video.variants` | 默认变体数 |
| `video.poll_interval` | 轮询间隔（秒） |
| `video.max_wait_minutes` | 单任务最大等待时间 |
| `video.output_dir` | 成片输出目录 |
| `video.confirm_before_generate` | 是否保留人工确认 |
| `notify.channel` | 通知通道，OpenClaw 当前固定为 `feishu` |
| `notify.feishu_target` | 飞书接收人 open_id / receive_id |

## 迁移到其他机器

1. 复制仓库代码，但不要直接复用旧机器的 `.venv`。
2. 新机器统一用 uv 重建 Python 3.11 环境：

   `uv venv --python 3.11 .venv`

   `uv pip install --python .venv/bin/python -r requirements.txt`

3. 设置 `OPENCLAW_UPLOAD_ROOT` 指向仓库根目录。
4. 设置 `OPENCLAW_PYTHON` 指向新的 Python 3.11 解释器。
5. 在 `.env` 或 `config.yaml` 里填 `FEISHU_NOTIFY_TARGET` / `notify.feishu_target`。
6. 准备好 `flash_longxia/token.txt`。

## 说明

- 历史 `wechat.*` 配置不再生效。
- 模型和模板查询直接走脚本，不再经微信中转。
- 发布链路目前只对接视频号。
