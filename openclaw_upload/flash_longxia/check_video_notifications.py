#!/usr/bin/env python3
"""
视频完成通知检查脚本
由心跳调用，读取 completed_notification.json 并写入飞书通知载荷
"""
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flash_longxia.notify_utils import load_processed_ids, save_processed_ids, send_feishu_notification

NOTIFY_FILE = SCRIPT_DIR / "completed_notification.json"
PROCESSED_FILE = SCRIPT_DIR / ".processed_notifications.json"

def load_processed():
    return load_processed_ids(PROCESSED_FILE)

def save_processed(processed):
    save_processed_ids(PROCESSED_FILE, processed)

def main():
    if not NOTIFY_FILE.exists():
        print("[INFO] 没有待处理的通知")
        return 0
    
    try:
        data = json.loads(NOTIFY_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        print("[错误] 通知文件格式错误")
        return 1
    
    # 兼容两种格式：单个对象或数组队列
    if isinstance(data, dict):
        notifications = [data]
    elif isinstance(data, list):
        notifications = data
    else:
        print(f"[错误] 通知格式错误：{type(data)}")
        return 1
    
    if not notifications:
        print("[INFO] 通知队列为空")
        return 0
    
    processed = load_processed()
    remaining = []
    sent_count = 0
    
    for notification in notifications:
        task_id = str(notification.get("task_id") or "").strip()
        video_path = notification.get("video_path")
        
        if not task_id or not video_path:
            print(f"[错误] 通知信息不完整，跳过：{notification}")
            continue
        
        # 检查是否已处理
        if task_id in processed:
            print(f"[INFO] 任务 {task_id} 已通知过，跳过")
            continue
        
        print(f"[通知] 发现待通知任务：{task_id}")
        print(f"[通知] 视频路径：{video_path}")
        
        # 生成飞书通知载荷
        success = send_feishu_notification(
            task_id,
            video_path=video_path,
            message=notification.get("message", "视频生成完成！"),
            follow_up='请说"**可以发布**"或"**确认发布**"，我会上传到视频号！',
        )
        
        if success:
            processed.add(task_id)
            sent_count += 1
        else:
            remaining.append(notification)
    
    # 保存已处理记录
    save_processed(processed)
    
    # 更新通知文件（保留未发送的）
    if remaining:
        NOTIFY_FILE.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"[INFO] 剩余 {len(remaining)} 个待发送通知")
    else:
        NOTIFY_FILE.unlink()
        print(f"[完成] 所有通知已处理，文件已清理")
    
    print(f"[汇总] 本次发送 {sent_count} 个通知")
    return 0

if __name__ == "__main__":
    sys.exit(main())
