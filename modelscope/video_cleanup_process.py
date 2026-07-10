"""
在 GitHub Actions runner 中运行：视频去水印/去字幕处理

流程：下载视频 → 创建 mask → 逐帧 inpaint → 合并音频 → 上传 COS → 回调
"""
import os
import sys
import time
import tempfile
import shutil
import subprocess
import numpy as np

# 依赖通过 apt 安装：python3-opencv python3-numpy python3-requests
import cv2
import requests

# ===================== 配置 =====================

COS_VIDEO_URL = os.environ.get("COS_VIDEO_URL", "")
WATERMARK_REGION = os.environ.get("WATERMARK_REGION", "")
SUBTITLE_REGION = os.environ.get("SUBTITLE_REGION", "")
CLEANUP_TYPE = os.environ.get("CLEANUP_TYPE", "both")
TASK_ID = os.environ.get("TASK_ID", "")

COS_SECRET_ID = os.environ.get("COS_SECRET_ID", "")
COS_SECRET_KEY = os.environ.get("COS_SECRET_KEY", "")
COS_REGION = os.environ.get("COS_REGION", "ap-beijing")
COS_BUCKET = os.environ.get("COS_BUCKET", "")

CALLBACK_URL = os.environ.get("CALLBACK_URL", "")

INPAINT_RADIUS = 5
INPAINT_FLAGS = cv2.INPAINT_TELEA

# ===================== 辅助函数 =====================


def log(msg):
    print(f"[video-cleanup] {msg}", flush=True)


def create_mask(width, height, region_str):
    """根据 x,y,w,h 创建掩码"""
    parts = region_str.split(",")
    x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    if x + w > width or y + h > height:
        raise ValueError(f"区域 ({x},{y},{w},{h}) 超出视频边界 ({width}x{height})")
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y:y+h, x:x+w] = 255
    log(f"创建掩码: ({x},{y},{w},{h})")
    return mask


def download_video(url, local_path):
    """下载视频"""
    log(f"下载视频: {url[:80]}...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    size_mb = os.path.getsize(local_path) / 1024 / 1024
    log(f"下载完成: {size_mb:.1f} MB")


def probe_video(video_path):
    """FFmpeg 探测视频信息"""
    result = subprocess.run(
        ["ffmpeg", "-i", video_path],
        capture_output=True, text=True, timeout=30
    )
    info = result.stderr

    import re
    size_match = re.search(r"(\d{2,5})x(\d{2,5})", info)
    if not size_match:
        raise RuntimeError(f"无法解析分辨率: {info[:200]}")
    width, height = int(size_match.group(1)), int(size_match.group(2))

    fps_match = re.search(r"([\d.]+)\s*fps", info)
    fps = float(fps_match.group(1)) if fps_match else 25.0

    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", info)
    if duration_match:
        h, m, s = duration_match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)
    else:
        duration = 0

    total_frames = int(duration * fps) if duration > 0 else 0
    has_audio = "Audio:" in info

    return {
        "width": width, "height": height, "fps": fps,
        "total_frames": total_frames, "has_audio": has_audio,
        "duration": duration,
    }


def extract_audio(video_path, audio_path):
    cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "aac", "-b:a", "128k", audio_path]
    log("提取音频...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        log(f"音频提取失败(将处理为无声视频): {result.stderr[:200]}")
    else:
        log("音频提取完成")


def process_frames(input_path, output_path, mask, fps, width, height, total_frames):
    """OpenCV 逐帧 inpaint"""
    log(f"开始逐帧处理: {total_frames} 帧, {fps}fps")

    # 优先使用 H.264
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not out.isOpened():
        log("avc1 不可用，使用 mp4v")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    cap = cv2.VideoCapture(input_path)
    processed = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            result = cv2.inpaint(frame, mask, inpaintRadius=INPAINT_RADIUS, flags=INPAINT_FLAGS)
            out.write(result)
            processed += 1
            if processed % 60 == 0:
                elapsed = time.time() - start_time
                log(f"进度: {processed}/{total_frames} 帧 ({processed/max(total_frames,1)*100:.1f}%) 用时 {elapsed:.0f}s")
    finally:
        cap.release()
        out.release()

    elapsed = time.time() - start_time
    log(f"帧处理完成: {processed}/{total_frames} 帧, 用时 {elapsed:.0f}s")


def merge_audio(video_path, audio_path, output_path):
    """合并视频+音频 + H.264 重编码"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path, "-i", audio_path,
        "-c:v", "libx264", "-crf", "23", "-preset", "medium", "-threads", "1",
        "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-pix_fmt", "yuv420p", "-shortest",
        output_path
    ]
    log("合并音视频 (H.264 CRF 18)...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"合并失败: {result.stderr[:300]}")
    log("合并完成")


def reencode_h264(input_path, output_path):
    """无音频时重编码为 H.264"""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264", "-crf", "23", "-preset", "medium", "-threads", "1",
        "-pix_fmt", "yuv420p", "-an",
        output_path
    ]
    log("重编码为 H.264...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"重编码失败: {result.stderr[:300]}")
    log("重编码完成")


def upload_to_cos(local_path, task_id):
    """上传结果到 COS，小文件直接上传，大文件分片上传带重试"""
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
    client = CosS3Client(config)

    cos_key = f"video_cleanup/{task_id}.mp4"
    file_size = os.path.getsize(local_path)
    log(f"上传到 COS: {file_size/1024/1024:.1f} MB, key={cos_key}")

    # 小于 20MB 直接上传，避免分片上传在 GitHub Actions 网络下不稳定
    if file_size < 20 * 1024 * 1024:
        log("文件较小，使用 put_object 直接上传")
        with open(local_path, 'rb') as f:
            client.put_object(Bucket=COS_BUCKET, Body=f.read(), Key=cos_key)
    else:
        # 大文件分片上传，减小分片 + 减少并发线程数提高稳定性
        max_retries = 3
        for attempt in range(max_retries):
            try:
                log(f"分片上传 (第 {attempt+1}/{max_retries} 次尝试)...")
                client.upload_file(
                    Bucket=COS_BUCKET,
                    LocalFilePath=local_path,
                    Key=cos_key,
                    PartSize=5,
                    MAXThread=2,
                    EnableMD5=False,
                )
                break
            except Exception as e:
                log(f"上传失败: {e}")
                if attempt == max_retries - 1:
                    raise
                import time
                time.sleep(5)

    result_url = f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{cos_key}"
    log(f"上传完成: {result_url}")
    return result_url, cos_key


def notify_callback(status, result_url="", cos_key=""):
    """回调通知服务器"""
    if not CALLBACK_URL:
        log("未设置 callback_url，跳过回调")
        return

    payload = {
        "task_id": TASK_ID,
        "result_url": result_url,
        "cos_key": cos_key,
        "status": status,
    }
    try:
        resp = requests.post(CALLBACK_URL, json=payload, timeout=30)
        log(f"回调成功: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        log(f"回调失败: {e}")


# ===================== 主流程 =====================

def main():
    start_time = time.time()

    if not COS_VIDEO_URL:
        log("错误: 未设置 COS_VIDEO_URL")
        notify_callback("failed")
        sys.exit(1)

    tempdir = tempfile.mkdtemp(prefix="video_cleanup_")
    try:
        # 1. 下载视频
        input_path = os.path.join(tempdir, "input.mp4")
        download_video(COS_VIDEO_URL, input_path)

        # 2. 探测视频信息
        info = probe_video(input_path)
        log(f"视频信息: {info['width']}x{info['height']}, {info['fps']}fps, {info['total_frames']}帧, 音频: {info['has_audio']}")

        # 3. 创建 mask
        masks = []
        if CLEANUP_TYPE in ("watermark", "both") and WATERMARK_REGION:
            masks.append(create_mask(info["width"], info["height"], WATERMARK_REGION))
        if CLEANUP_TYPE in ("subtitle", "both") and SUBTITLE_REGION:
            masks.append(create_mask(info["width"], info["height"], SUBTITLE_REGION))

        if not masks:
            raise ValueError(f"cleanup_type={CLEANUP_TYPE} 但未提供有效的区域坐标")

        combined_mask = np.maximum.reduce(masks)

        # 4. 提取音频
        audio_file = None
        if info["has_audio"]:
            audio_file = os.path.join(tempdir, "temp_audio.aac")
            extract_audio(input_path, audio_file)

        # 5. 逐帧 inpaint
        processed_path = os.path.join(tempdir, "processed.mp4")
        process_frames(
            input_path, processed_path, combined_mask,
            info["fps"], info["width"], info["height"], info["total_frames"]
        )

        # 6. 合并 + 重编码
        final_path = os.path.join(tempdir, "final.mp4")
        if audio_file and os.path.exists(audio_file):
            merge_audio(processed_path, audio_file, final_path)
        else:
            reencode_h264(processed_path, final_path)

        # 7. 上传 COS
        result_url, cos_key = upload_to_cos(final_path, TASK_ID)

        # 8. 回调
        elapsed = time.time() - start_time
        log(f"全部完成, 总用时 {elapsed:.0f}s")
        notify_callback("completed", result_url, cos_key)

    except Exception as e:
        log(f"处理失败: {e}")
        notify_callback("failed")
        sys.exit(1)
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


if __name__ == "__main__":
    main()
