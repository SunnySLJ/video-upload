# auth module

这是 OpenClaw `video-workflow` 的内部模块。

用途：

- 检查视频号登录状态
- 拉起视频号扫码登录
- 把二维码发送到飞书
- 若二维码过期，自动关闭旧登录浏览器并重新获取、重新发送二维码

常用命令：

```bash
~/.openclaw/workspace/openclaw_upload/.venv/bin/python \
~/.openclaw/workspace/skills/auth/scripts/platform_login.py \
--platform shipinhao --check-only

~/.openclaw/workspace/openclaw_upload/.venv/bin/python \
~/.openclaw/workspace/skills/auth/scripts/platform_login.py \
--platform shipinhao
```
