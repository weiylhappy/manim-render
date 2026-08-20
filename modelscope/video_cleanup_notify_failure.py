"""
在 GitHub Actions runner 中运行：处理失败时回调服务器更新状态
带 5 次重试 + X-Cleanup-Secret 鉴权 Header
"""
import os
import sys
import time
import requests

CALLBACK_URL = os.environ["CALLBACK_URL"]
TASK_ID = os.environ["TASK_ID"]
CALLBACK_SECRET = os.environ.get("CALLBACK_SECRET", "")

headers = {"Content-Type": "application/json"}
if CALLBACK_SECRET:
    headers["X-Cleanup-Secret"] = CALLBACK_SECRET

MAX_RETRIES = 5
for attempt in range(1, MAX_RETRIES + 1):
    try:
        resp = requests.post(
            CALLBACK_URL,
            json={"task_id": TASK_ID, "result_url": "", "cos_key": "", "status": "failed"},
            headers=headers,
            timeout=30,
        )
        print(f"[{attempt}/{MAX_RETRIES}] 失败回调完成: {resp.status_code} - {resp.text[:200]}")
        # 2xx 视为成功，4xx 不重试（配置/鉴权问题重试无意义），5xx 重试
        if 200 <= resp.status_code < 300:
            sys.exit(0)
        if 400 <= resp.status_code < 500:
            sys.exit(0)
    except Exception as e:
        print(f"[{attempt}/{MAX_RETRIES}] 失败回调异常: {e}")

    if attempt < MAX_RETRIES:
        wait = min(10 * attempt, 60)
        print(f"   等待 {wait} 秒后重试...")
        time.sleep(wait)

print(f"失败回调已达最大重试次数 {MAX_RETRIES}")
sys.exit(1)
