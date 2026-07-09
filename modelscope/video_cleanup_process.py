"""
在 GitHub Actions runner 中运行：对视频指定区域进行去除处理

使用 OpenCV inpaint 算法（Telea / Navier-Stokes），CPU 友好，无需 GPU。
支持去水印、去字幕，以及两者组合处理。

用法:
    python video_cleanup_process.py \
        --input input.mp4 \
        --output cleaned_output.mp4 \
        --cleanup_type both \
        --watermark_region "1500,50,380,120" \
        --subtitle_region "0,400,1920,200" \
        --algorithm telea
"""
import argparse
import sys
import cv2
import numpy as np


def parse_region(region_str: str) -> tuple:
    """解析 "x,y,w,h" 为 (x1, y1, x2, y2)"""
    parts = [int(x.strip()) for x in region_str.split(",")]
    x, y, w, h = parts[0], parts[1], parts[2], parts[3]
    return (x, y, x + w, y + h)


def create_mask(width: int, height: int, region_str: str) -> np.ndarray:
    """根据区域字符串创建二值掩码"""
    x1, y1, x2, y2 = parse_region(region_str)
    mask = np.zeros((height, width), dtype=np.uint8)
    x1c = max(0, min(x1, width - 1))
    y1c = max(0, min(y1, height - 1))
    x2c = max(x1c + 1, min(x2, width))
    y2c = max(y1c + 1, min(y2, height))
    mask[y1c:y2c, x1c:x2c] = 255
    return mask


def get_inpaint_flag(algorithm: str) -> int:
    """获取 OpenCV inpaint 算法标志"""
    if algorithm == "ns":
        return cv2.INPAINT_NS
    return cv2.INPAINT_TELEA  # 默认 Telea，速度快、效果好


def process_video(
    input_path: str,
    output_path: str,
    mask: np.ndarray,
    algorithm: str,
    label: str = "",
) -> None:
    """逐帧全帧对视频进行 inpainting 处理"""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"错误: 无法打开视频 {input_path}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[{label}] {width}x{height}, {fps:.1f}fps, {total_frames}帧")

    flag = get_inpaint_flag(algorithm)
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
    """用 ffmpeg 合并视频和音频"""
    import subprocess
    print(f"[音频合并] 从 {audio_source} 提取音频合并到 {video_path}")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,      # 无声视频
            "-i", audio_source,    # 原始视频（提取音频）
            "-c:v", "copy",        # 视频流直接复制
            "-c:a", "aac",         # 音频编码为 AAC
            "-b:a", "128k",
            "-map", "0:v:0",       # 取第一个输入的视频流
            "-map", "1:a:0",       # 取第二个输入的音频流
            "-shortest",           # 以较短的流为准
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"[音频合并] 完成 → {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"[音频合并] 失败: {e}")
        print(f"stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
        raise


def main():
    parser = argparse.ArgumentParser(description="视频去水印/去字幕处理")
    parser.add_argument("--input", required=True, help="输入视频路径")
    parser.add_argument("--output", required=True, help="输出视频路径")
    parser.add_argument("--cleanup_type", required=True,
                        choices=["watermark", "subtitle", "both"])
    parser.add_argument("--watermark_region", default="", help="水印区域 x,y,w,h")
    parser.add_argument("--subtitle_region", default="", help="字幕区域 x,y,w,h")
    parser.add_argument("--algorithm", default="telea",
                        choices=["telea", "ns"],
                        help="telea(默认,快速) / ns(Navier-Stokes,慢但更平滑)")
    args = parser.parse_args()

    print("═══════════════════════════════════════")
    print(f"清理类型: {args.cleanup_type}")
    print(f"修复算法: {args.algorithm}")
    print(f"水印区域: {args.watermark_region or '(无)'}")
    print(f"字幕区域: {args.subtitle_region or '(无)'}")
    print("═══════════════════════════════════════")

    current_input = args.input

    # ── 去水印 ──
    if args.cleanup_type in ("watermark", "both"):
        if not args.watermark_region:
            print("错误: 去水印时必须提供 --watermark_region")
            sys.exit(1)

        # 先获取视频尺寸
        cap = cv2.VideoCapture(current_input)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        wm_mask = create_mask(w, h, args.watermark_region)
        wm_output = "wm_removed.mp4"
        process_video(current_input, wm_output, wm_mask, args.algorithm, label="去水印")
        current_input = wm_output

    # ── 去字幕 ──
    if args.cleanup_type in ("subtitle", "both"):
        if not args.subtitle_region:
            print("错误: 去字幕时必须提供 --subtitle_region")
            sys.exit(1)

        cap = cv2.VideoCapture(current_input)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        sub_mask = create_mask(w, h, args.subtitle_region)
        process_video(current_input, args.output, sub_mask, args.algorithm, label="去字幕")
    else:
        # 仅去水印时，最终输出就是水印处理后的文件
        import shutil
        shutil.move(current_input, args.output)

    # 合并原始视频的音频
    if args.input != args.output:
        temp_output = args.output + ".temp.mp4"
        merge_audio(args.output, args.input, temp_output)
        import os
        os.replace(temp_output, args.output)

    print(f"✅ 全部处理完成: {args.output}")


if __name__ == "__main__":
    main()
