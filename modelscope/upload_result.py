"""
在 GitHub Actions runner 中运行：将渲染结果上传到腾讯云 COS
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

VIDEO_DIR = "media/videos/scene"
OUTPUT_FILE = None
for root, dirs, files in os.walk(VIDEO_DIR):
    for f in files:
        if f.endswith(".mp4"):
            OUTPUT_FILE = os.path.join(root, f)
            break

if OUTPUT_FILE is None:
    print("错误: 未找到渲染输出的 mp4 文件")
    sys.exit(1)

print(f"找到输出文件: {OUTPUT_FILE}")

config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
client = CosS3Client(config)

cos_key = f"manim_render/{TASK_ID}.mp4"
client.upload_file(
    Bucket=BUCKET,
    LocalFilePath=OUTPUT_FILE,
    Key=cos_key,
    PartSize=1,
    MAXThread=4,
)

result_url = client.get_presigned_url(
    Method="GET",
    Bucket=BUCKET,
    Key=cos_key,
    Expired=3600,
)

with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
    f.write(f"RESULT_URL={result_url}\n")
    f.write(f"COS_KEY={cos_key}\n")

print(f"上传成功: {result_url}")
