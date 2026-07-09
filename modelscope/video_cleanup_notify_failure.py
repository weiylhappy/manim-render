"""
在 GitHub Actions runner 中运行：处理失败时回调服务器更新状态
"""
import os
import requests

CALLBACK_URL = os.environ["CALLBACK_URL"]
TASK_ID = os.environ["TASK_ID"]

try:
    resp = requests.post(
        CALLBACK_URL,
        json={
            "task_id": TASK_ID,
            "result_url": "",
            "cos_key": "",
            "status": "failed",
        },
        timeout=30,
    )
    print(f"失败回调完成: {resp.status_code} - {resp.text[:200]}")
except Exception as e:
    print(f"失败回调异常: {e}")
