"""
在 GitHub Actions runner 中运行：视频去水印/去字幕处理

全帧 inpaint 处理，用户指定水印/字幕区域。
"""
import argparse
import sys
import os
import shutil
import cv2
import numpy as np


def parse_region(region_str: str) -> tuple:
    parts = [int(x.strip()) for x in region_str.split(",")]
    x, y, w, h = parts[0], parts[1], parts[2], parts[3]
    return (x, y, x + w, y + h)


def create_mask(width: int, height: int, region: tuple) -> np.ndarray:
    x1, y1, x2, y2 = region
    mask = np.zeros((height, width), dtype=np.uint8)
    x1c = max(0, min(x1, width - 1))
    y1c = max(0, min(y1, height - 1))
    x2c = max(x1c + 1, min(x2, width))
    y2c = max(y1c + 1, min(y2, height))
    mask[y1c:y2c, x1c:x2c] = 255
    return mask


def process_video(input_path: str, output_path: str, mask: np.ndarray, algorithm: str, label: str = "") -> None:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"错误: 无法打开视频 {input_path}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[{label}] {width}x{height}, {fps:.1f}fps, {total_frames}帧")

    flag = cv2.INPAINT_NS if algorithm == "ns" else cv2.INPAINT_TELEA
    radius = 3 if algorithm == "ns" else 5

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break
        result = cv2.inpaint(frame, mask, inpaintRadius=radius, flags=flag)
        out.write(result)
        if (idx + 1) % 100 == 0:
            print(f"[{label}] {idx+1}/{total_frames} ({100*(idx+1)//total_frames}%)")

    cap.release()
    out.release()
    print(f"[{label}] 完成 → {output_path}")


def merge_audio(video_path: str, audio_source: str, output_path: str) -> None:
    import subprocess
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", audio_source,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
           "-map", "0:v:0", "-map", "1:a:0", "-shortest", output_path]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"[音频] 完成")


def main():
    parser = argparse.ArgumentParser(description="视频去水印/去字幕处理")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cleanup_type", required=True, choices=["watermark", "subtitle", "both"])
    parser.add_argument("--watermark_region", default="")
    parser.add_argument("--subtitle_region", default="")
    parser.add_argument("--algorithm", default="telea", choices=["telea", "ns"])
    args = parser.parse_args()

    print(f"清理类型: {args.cleanup_type}")
    print(f"修复算法: {args.algorithm}")
    print(f"水印区域: {args.watermark_region or '(无)'}")
    print(f"字幕区域: {args.subtitle_region or '(无)'}")

    current_input = args.input

    if args.cleanup_type in ("watermark", "both"):
        if not args.watermark_region:
            print("错误: 去水印时必须提供 --watermark_region")
            sys.exit(1)
        cap = cv2.VideoCapture(current_input)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        process_video(current_input, "wm_removed.mp4", create_mask(w, h, parse_region(args.watermark_region)),
                     args.algorithm, label="去水印")
        current_input = "wm_removed.mp4"

    if args.cleanup_type in ("subtitle", "both"):
        if not args.subtitle_region:
            print("错误: 去字幕时必须提供 --subtitle_region")
            sys.exit(1)
        cap = cv2.VideoCapture(current_input)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        process_video(current_input, args.output, create_mask(w, h, parse_region(args.subtitle_region)),
                     args.algorithm, label="去字幕")
    else:
        shutil.move(current_input, args.output)

    # 合并音频
    if args.input != args.output:
        temp = args.output + ".temp.mp4"
        merge_audio(args.output, args.input, temp)
        os.replace(temp, args.output)

    print(f"✅ 全部处理完成: {args.output}")


if __name__ == "__main__":
    main()
