"""
在 GitHub Actions runner 中运行：上传处理后的视频到腾讯云 COS
先上传到美国 bucket（同区域，速度快），COS 自动跨地域复制到北京
带重试机制，网络慢时自动重试 10 次
"""
import os
import sys
import time
from qcloud_cos import CosConfig, CosS3Client

# 美国 bucket（GitHub Actions 同区域，上传快）
US_SECRET_ID = os.environ["US_COS_SECRET_ID"]
US_SECRET_KEY = os.environ["US_COS_SECRET_KEY"]
US_REGION = os.environ["US_COS_REGION"]
US_BUCKET = os.environ["US_COS_BUCKET"]

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

us_config = CosConfig(Region=US_REGION, SecretId=US_SECRET_ID, SecretKey=US_SECRET_KEY)
us_client = CosS3Client(us_config)

cos_key = f"video_cleanup/{TASK_ID}.mp4"
file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
print(f"文件大小: {file_size_mb:.1f} MB")
print(f"目标: {US_BUCKET} ({US_REGION})")

MAX_RETRIES = 10
uploaded = False

for attempt in range(1, MAX_RETRIES + 1):
    try:
        if file_size_mb < 20:
            print(f"[{attempt}/{MAX_RETRIES}] 使用 put_object 上传...")
            with open(OUTPUT_FILE, "rb") as fp:
                us_client.put_object(Bucket=US_BUCKET, Body=fp, Key=cos_key)
        else:
            print(f"[{attempt}/{MAX_RETRIES}] 使用分片上传...")
            us_client.upload_file(Bucket=US_BUCKET, LocalFilePath=OUTPUT_FILE, Key=cos_key, PartSize=5, MAXThread=3, EnableMD5=False)
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

# 生成预签名 URL（美国 bucket，COS 跨地域复制后北京 bucket 也可以访问同一 key）
result_url = us_client.get_presigned_url(Method="GET", Bucket=US_BUCKET, Key=cos_key, Expired=86400)

with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
    f.write(f"RESULT_URL={result_url}\n")
    f.write(f"COS_KEY={cos_key}\n")
    f.write(f"COS_BUCKET={US_BUCKET}\n")
    f.write(f"COS_REGION={US_REGION}\n")

print(f"上传成功: {result_url}")
print("COS 将自动跨地域复制到北京 bucket")
