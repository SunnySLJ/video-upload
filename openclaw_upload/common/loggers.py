# -*- coding: utf-8 -*-
"""
统一导出各平台 logger，日志写入项目根 logs/ 目录
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from common.log import setup_stdout, create_logger

setup_stdout()
douyin_logger = create_logger("douyin", "logs/douyin.log", _ROOT)
kuaishou_logger = create_logger("kuaishou", "logs/kuaishou.log", _ROOT)
shipinhao_logger = create_logger("shipinhao", "logs/shipinhao.log", _ROOT)
xiaohongshu_logger = create_logger("xiaohongshu", "logs/xiaohongshu.log", _ROOT)
