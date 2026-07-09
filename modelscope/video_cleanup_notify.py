"""
在 GitHub Actions runner 中运行：回调通知 FastAPI 服务器任务完成
"""
import os
import json
import urllib.request

CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
TASK_ID = os.environ.get("TASK_ID", "")
RESULT_URL = os.environ.get("RESULT_URL", "")
COS_KEY = os.environ.get("COS_KEY", "")

if not CALLBACK_URL:
    print("未设置 callback_url，跳过回调")
    exit(0)

payload = json.dumps({
    "task_id": TASK_ID,
    "result_url": RESULT_URL,
    "cos_key": COS_KEY,
    "status": "completed",
}).encode("utf-8")

req = urllib.request.Request(
    CALLBACK_URL,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"回调成功: {resp.status} - {resp.read().decode()}")
except Exception as e:
    print(f"回调失败: {e}")
