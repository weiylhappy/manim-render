"""
在 GitHub Actions runner 中运行：处理失败时回调服务器更新状态
"""
import os
import json
import urllib.request

CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
TASK_ID = os.environ.get("TASK_ID", "")

if not CALLBACK_URL:
    print("未设置 callback_url，跳过回调")
    exit(0)

payload = json.dumps({
    "task_id": TASK_ID,
    "result_url": "",
    "cos_key": "",
    "status": "failed",
}).encode("utf-8")

req = urllib.request.Request(
    CALLBACK_URL,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"失败回调成功: {resp.status} - {resp.read().decode()}")
except Exception as e:
    print(f"失败回调异常: {e}")
