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
    target_fps: float = None,
) -> None:
    """逐帧对视频进行 inpainting 处理"""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"错误: 无法打开视频 {input_path}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 如果指定了目标帧率，降低帧率处理
    if target_fps and target_fps < fps:
        frame_skip = int(fps / target_fps)
        print(f"[{label}] 降帧处理: {fps:.1f}fps → {target_fps:.1f}fps (每{frame_skip}帧处理1帧)")
    else:
        frame_skip = 1
        target_fps = fps
        print(f"[{label}] 原始帧率处理: {fps:.1f}fps")

    print(f"[{label}] 视频信息: {width}x{height}, 总帧数: {total_frames}")

    flag = get_inpaint_flag(algorithm)
    radius = 3 if algorithm == "ns" else 5

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, target_fps, (width, height))

    frame_idx = 0
    processed_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # 按帧率跳帧
        if frame_idx % frame_skip == 0:
            result = cv2.inpaint(frame, mask, inpaintRadius=radius, flags=flag)
            out.write(result)
            processed_count += 1

            if processed_count % 50 == 0:
                pct = int(processed_count * frame_skip * 100 / max(total_frames, 1))
                print(f"[{label}] 进度: {processed_count} 帧 ({min(pct, 100)}%)")

        frame_idx += 1

    cap.release()
    out.release()
    print(f"[{label}] 完成: 处理 {processed_count} 帧 → {output_path}")


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
    parser.add_argument("--target_fps", type=float, default=None,
                        help="目标帧率(如15)，降低可加速处理")
    args = parser.parse_args()

    print("═══════════════════════════════════════")
    print(f"清理类型: {args.cleanup_type}")
    print(f"修复算法: {args.algorithm}")
    print(f"水印区域: {args.watermark_region or '(无)'}")
    print(f"字幕区域: {args.subtitle_region or '(无)'}")
    print(f"目标帧率: {args.target_fps or '保持原帧率'}")
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
        process_video(current_input, wm_output, wm_mask, args.algorithm,
                     label="去水印", target_fps=args.target_fps)
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
        process_video(current_input, args.output, sub_mask, args.algorithm,
                     label="去字幕", target_fps=args.target_fps)
    else:
        # 仅去水印时，最终输出就是水印处理后的文件
        import shutil
        shutil.move(current_input, args.output)

    print(f"✅ 全部处理完成: {args.output}")


if __name__ == "__main__":
    main()
