"""
在 GitHub Actions runner 中运行：上传处理后的视频到腾讯云 COS
使用全球加速域名上传，解决跨国网络慢问题
带重试机制，网络慢时自动重试 10 次
"""
import os
import sys
import time
from qcloud_cos import CosConfig, CosS3Client

SECRET_ID = os.environ["COS_SECRET_ID"]
SECRET_KEY = os.environ["COS_SECRET_KEY"]
REGION = os.environ["COS_REGION"]
BUCKET = os.environ["COS_BUCKET"]
TASK_ID = os.environ.get("TASK_ID", f"task_{int(time.time())}")

OUTPUT_FILE = None
for fname in ["cleaned_output.mp4", "output.mp4"]:
    if os.path.exists(fname):
        OUTPUT_FILE = fname
        break

if OUTPUT_FILE is None:
    import glob
    all_mp4 = [f for f in glob.glob("*.mp4") if f not in {"input_video.mp4", "original.mp4"}]
    if all_mp4:
        OUTPUT_FILE = max(all_mp4, key=os.path.getsize)

if OUTPUT_FILE is None:
    print("错误: 未找到处理后的 mp4 文件")
    sys.exit(1)

print(f"找到输出文件: {OUTPUT_FILE}")

# 使用全球加速域名上传
config = CosConfig(
    Region=REGION,
    SecretId=SECRET_ID,
    SecretKey=SECRET_KEY,
    Scheme="https",
    Domain=f"{BUCKET}.cos.accelerate.myqcloud.com",
)
client = CosS3Client(config)

cos_key = f"video_cleanup/{TASK_ID}.mp4"
file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
print(f"文件大小: {file_size_mb:.1f} MB")
print(f"目标: {BUCKET} ({REGION}) 全球加速")

MAX_RETRIES = 10
uploaded = False

for attempt in range(1, MAX_RETRIES + 1):
    try:
        if file_size_mb < 20:
            print(f"[{attempt}/{MAX_RETRIES}] 使用 put_object 上传...")
            with open(OUTPUT_FILE, "rb") as fp:
                client.put_object(Bucket=BUCKET, Body=fp, Key=cos_key)
        else:
            print(f"[{attempt}/{MAX_RETRIES}] 使用分片上传...")
            client.upload_file(Bucket=BUCKET, LocalFilePath=OUTPUT_FILE, Key=cos_key, PartSize=5, MAXThread=3, EnableMD5=False)
        uploaded = True
        break
    except Exception as e:
        err_msg = str(e)
        print(f"[{attempt}/{MAX_RETRIES}] 上传失败: {err_msg[:200]}")
        if attempt < MAX_RETRIES:
            wait = min(5 * attempt, 30)
            print(f"   等待 {wait} 秒后重试...")
            time.sleep(wait)

if not uploaded:
    print("错误: 上传失败，已达到最大重试次数")
    sys.exit(1)

result_url = client.get_presigned_url(Method="GET", Bucket=BUCKET, Key=cos_key, Expired=86400)

with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
    f.write(f"RESULT_URL={result_url}\n")
    f.write(f"COS_KEY={cos_key}\n")

print(f"上传成功: {result_url}")
