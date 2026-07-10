"""
在 GitHub Actions runner 中运行：上传处理后的视频到腾讯云 COS
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

config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
client = CosS3Client(config)

cos_key = f"video_cleanup/{TASK_ID}.mp4"
file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
print(f"文件大小: {file_size_mb:.1f} MB")

if file_size_mb < 20:
    with open(OUTPUT_FILE, "rb") as fp:
        client.put_object(Bucket=BUCKET, Body=fp, Key=cos_key)
else:
    client.upload_file(Bucket=BUCKET, LocalFilePath=OUTPUT_FILE, Key=cos_key, PartSize=5, MAXThread=3, EnableMD5=False)

result_url = client.get_presigned_url(Method="GET", Bucket=BUCKET, Key=cos_key, Expired=86400)

with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
    f.write(f"RESULT_URL={result_url}\n")
    f.write(f"COS_KEY={cos_key}\n")

print(f"上传成功: {result_url}")
