"""
在 GitHub Actions runner 中运行：将处理后的视频上传到腾讯云 COS
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

# 查找输出文件
OUTPUT_FILE = None

# 优先查找 cleaned_output.mp4（我们指定的输出文件名）
candidates = [
    "cleaned_output.mp4",
    "output.mp4",
    "combined_output.mp4",
]

for fname in candidates:
    if os.path.exists(fname):
        OUTPUT_FILE = fname
        break

# 兜底：搜索所有 mp4 文件
if OUTPUT_FILE is None:
    import glob
    all_mp4 = glob.glob("*.mp4")
    # 排除原始输入文件
    exclude = {"input_video.mp4", "original.mp4"}
    all_mp4 = [f for f in all_mp4 if os.path.basename(f) not in exclude]
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

client.upload_file(
    Bucket=BUCKET,
    LocalFilePath=OUTPUT_FILE,
    Key=cos_key,
    PartSize=10,
    MAXThread=5,
    EnableMD5=False,
)

result_url = client.get_presigned_url(
    Method="GET",
    Bucket=BUCKET,
    Key=cos_key,
    Expired=86400,  # 24 小时有效
)

# 导出环境变量供后续步骤使用
with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
    f.write(f"RESULT_URL={result_url}\n")
    f.write(f"COS_KEY={cos_key}\n")

print(f"上传成功: {result_url}")
