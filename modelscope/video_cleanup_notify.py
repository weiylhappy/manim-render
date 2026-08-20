"""
在 GitHub Actions runner 中运行：回调通知 API 服务器任务完成
带 X-Cleanup-Secret 鉴权 Header + 内部 3 次重试
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error

CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
TASK_ID = os.environ.get("TASK_ID", "")
RESULT_URL = os.environ.get("RESULT_URL", "")
COS_KEY = os.environ.get("COS_KEY", "")
CALLBACK_SECRET = os.environ.get("CALLBACK_SECRET", "")

if not CALLBACK_URL:
    print("未设置 CALLBACK_URL，跳过回调")
    sys.exit(0)

payload = json.dumps({
    "task_id": TASK_ID, "result_url": RESULT_URL, "cos_key": COS_KEY, "status": "completed"
}).encode("utf-8")

headers = {"Content-Type": "application/json"}
if CALLBACK_SECRET:
    headers["X-Cleanup-Secret"] = CALLBACK_SECRET

MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        req = urllib.request.Request(CALLBACK_URL, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            print(f"[{attempt}/{MAX_RETRIES}] 回调成功: {resp.status} - {body}")
            sys.exit(0)
    except urllib.error.HTTPError as e:
        # 4xx 不重试（鉴权/参数错误，重试无意义）
        if 400 <= e.code < 500:
            print(f"[{attempt}/{MAX_RETRIES}] 客户端错误 {e.code}，不重试: {e.read().decode()[:200]}")
            sys.exit(0)
        print(f"[{attempt}/{MAX_RETRIES}] 服务端错误 {e.code}")
    except Exception as e:
        print(f"[{attempt}/{MAX_RETRIES}] 回调异常: {e}")

    if attempt < MAX_RETRIES:
        wait = 30 * attempt
        print(f"等待 {wait} 秒后重试...")
        time.sleep(wait)

print(f"回调失败，已达最大重试次数 {MAX_RETRIES}")
# 返回非零退出码，让 step 标记为失败，触发「回调通知（失败）」step
sys.exit(1)
