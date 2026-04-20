# -*- coding: utf-8 -*-
"""
视频号上传统一入口 - 供外部直接调用

用法:
    from platforms.shipinhao_upload.api import upload_to_shipinhao
    success = upload_to_shipinhao(video_path="...", title="...", ...)
"""
from .upload import upload as upload_to_shipinhao

__all__ = ["upload_to_shipinhao"]
