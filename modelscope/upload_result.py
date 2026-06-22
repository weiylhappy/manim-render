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

# Manim 输出目录
VIDEO_DIR = "media/videos"

OUTPUT_FILE = None

# 优先：ffmpeg 合成后的文件（带旁白）
if os.path.exists("combined.mp4"):
    OUTPUT_FILE = "combined.mp4"
else:
    all_mp4 = []
    for root, dirs, files in os.walk(VIDEO_DIR):
        for f in files:
            if f.endswith(".mp4") and "partial_movie_files" not in root:
                all_mp4.append(os.path.join(root, f))

    if all_mp4:
        OUTPUT_FILE = max(all_mp4, key=os.path.getsize)

if OUTPUT_FILE is None:
    print("错误: 未找到渲染输出的 mp4 文件")
    sys.exit(1)

print(f"找到输出文件: {OUTPUT_FILE}")

config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
client = CosS3Client(config)

cos_key = f"manim_render/{TASK_ID}.mp4"

file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
print(f"文件大小: {file_size_mb:.1f} MB")

# 大文件使用分片上传（PartSize=10MB 最大，减少分片数提高成功率）
client.upload_file(
    Bucket=BUCKET,
    LocalFilePath=OUTPUT_FILE,
    Key=cos_key,
    PartSize=10,       # 分片大小 10MB（最大值，减少分片数）
    MAXThread=5,       # 并发线程
    EnableMD5=False,   # 关闭 MD5 校验加速上传
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
