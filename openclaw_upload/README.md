# 帧龙虾（zhenlongxia）图生视频工具

核心流程：上传图片 -> 可选行业模板 -> 图生文 -> 按模型配置生成视频 -> 后台轮询 getById -> 下载视频。

## 关键文件
- `flash_longxia/zhenlongxia_workflow.py`：主流程（生产用）
- `flash_longxia/debug_apis.py`：分步调试接口
- `flash_longxia/download_latest_video.py`：按任务 ID 补下载
- `flash_longxia/device_verify.py`：设备 MAC 鉴权预留
- `config.example.yaml`：配置模板

## 使用
1) 准备 token：放到 `flash_longxia/token.txt`
2) 运行主流程：
   `./.venv/bin/python flash_longxia/zhenlongxia_workflow.py <图片路径>`
   如需查看可用模型：
   `./.venv/bin/python flash_longxia/zhenlongxia_workflow.py --list-models`
   如需查看行业模板：
   `./.venv/bin/python flash_longxia/zhenlongxia_workflow.py --list-templates`
3) 若外部已拿到生成任务 ID，可直接补下载：
   `./.venv/bin/python flash_longxia/zhenlongxia_workflow.py --id=<任务ID>`
   `./.venv/bin/python flash_longxia/download_latest_video.py <任务ID>`

默认交互模式下，图片上传完成后会继续询问两件事：
- 是否改用别的视频模型配置（model / duration / aspectRatio）
- 是否为本次视频附加行业模板

默认不要传行业模板；只有这次明确需要时，才去查询模板并把选中的 `tmpplateId/title` 传给生成接口。

如果你传了 `--yes`，或已显式传入 `--model` / `--duration` / `--aspectRatio` / `--tmpplateId`，对应交互会跳过。

## 行业模板
- 交互式使用：直接运行主流程且不要带 `--yes`，上传完成后会提示是否选择行业模板。
- 查询模板：`./.venv/bin/python flash_longxia/zhenlongxia_workflow.py --list-templates --mediaType=1`
- 严禁直接裸请求 `api/v1/aiTemplate/pageList`。若未带正确 `token`、POST 请求体和参数，接口常会返回 `code=1003, msg=服务器开小差了，请稍后再试`，这是错误调用，不是模板服务真实故障。
- 指定模板生成：`./.venv/bin/python flash_longxia/zhenlongxia_workflow.py <图片路径> --tmpplateId=<模板ID> --title=<模板标题或产品名> --yes`
- `--templateId` 是 `--tmpplateId` 的兼容别名，最终都会透传给 `generateVideo` 的 `tmpplateId` 字段。
- 模板分类默认使用 `mediaType=1`；首轮先返回分类列表，选定分类后再用对应 `tabType` 和 `menuType=1` 查询模板。

## 说明
- 本项目强制使用 Python 3.11；若版本不符，入口脚本会直接退出。
- OpenClaw 当前统一使用 uv 创建的 `.venv`；如需外部调用，设置 `OPENCLAW_PYTHON=~/.openclaw/workspace/openclaw_upload/.venv/bin/python`。
- 模型、时长、比例来自 `GET /api/v1/globalConfig/getModel?modelType=1`，生成前会按接口返回值校验。
- 行业模板通过 `api/v1/aiTemplateCategory/getList` 和 `api/v1/aiTemplate/pageList` 获取，生成时只传 `tmpplateId` 与 `title`，不额外传 `style` 或 `quality`。
- 轮询间隔、超时、下载重试可在 `config.yaml` 配置。
- 当后端状态字段滞后时，主流程会尝试解析 `repMsg` 中的 `result` 链接并直接下载。

## 迁移
- 不要直接复制旧机器的 `.venv` 或 `venv`；在新机器用 uv 重新创建并安装依赖：

  `uv venv --python 3.11 .venv`

  `uv pip install --python .venv/bin/python -r requirements.txt`
- 仓库内脚本现在默认按“脚本所在目录”定位 `flash_longxia/output` 等路径，不再依赖固定绝对路径或当前工作目录。
- 若你的 OpenClaw 工作区不在默认位置，设置 `OPENCLAW_UPLOAD_ROOT` 指向仓库根目录，设置 `OPENCLAW_WORKSPACE_ROOT` 指向工作区根目录。
- OpenClaw 当前只保留飞书通知，设置 `FEISHU_NOTIFY_TARGET` 或 `FLASH_LONGXIA_FEISHU_TARGET`。
