# -*- coding: utf-8 -*-
"""共享日志工厂 - 供各平台 utils/log.py 使用"""
import sys
from pathlib import Path
from typing import Union

from loguru import logger
from common.console import ensure_console_ready

_stdout_initialized = False


def _log_formatter(record: dict) -> str:
    colors = {
        "TRACE": "#cfe2f3",
        "INFO": "#9cbfdd",
        "DEBUG": "#8598ea",
        "WARNING": "#dcad5a",
        "SUCCESS": "#3dd08d",
        "ERROR": "#ae2c2c",
    }
    color = colors.get(record["level"].name, "#b3cfe7")
    return f"<fg #70acde>{{time:YYYY-MM-DD HH:mm:ss}}</fg #70acde> | <fg {color}>{{level}}</fg {color}>: <light-white>{{message}}</light-white>\n"


def create_logger(log_name: str, log_path: str, base_dir: Union[Path, str]):
    """
    创建平台专用 logger，输出到控制台和文件
    :param log_name: 业务名称，用于 filter
    :param log_path: 日志文件相对路径，如 "logs/douyin.log"
    :param base_dir: 项目根目录
    """
    def filter_record(record):
        return record["extra"].get("business_name") == log_name

    file_path = Path(base_dir) / log_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(file_path),
        filter=filter_record,
        level="INFO",
        rotation="10 MB",
        retention="10 days",
    )
    return logger.bind(business_name=log_name)


def setup_stdout():
    """配置控制台输出（仅执行一次，避免多次调用清除已有 file sink）"""
    global _stdout_initialized
    if _stdout_initialized:
        return
    _stdout_initialized = True
    ensure_console_ready()
    logger.remove()
    logger.add(sys.stdout, colorize=True, format=_log_formatter)
