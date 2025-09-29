#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import numpy as np
from PIL import Image
import pytesseract
import cv2  # 需要安装 opencv-python


def _to_gray(arr: np.ndarray) -> np.ndarray:
    """RGB/BGR->灰度，或已是灰度则原样返回"""
    if arr.ndim == 2:
        return arr
    # PIL读取通常是RGB；直接按加权求灰度
    return (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32)

def detect_middle_black_border(
    image_array: np.ndarray,
    dark_threshold: int = 60,       # 针对纯黑边的阈值
    min_width: int = 10,
    smooth_window: int = 9,
    dark_ratio_thresh: float = 0.80,# 针对纯黑边的占比要求
     edge_margin_ratio: float = 0.03,

    # 新增参数用于辅助检测浅色粗边
    avg_gray_threshold: int = 150,  # 新增：判断深色区域的平均灰度上限
):
    """
    检测“中间的”粗竖黑边。融合了两种策略：
    1. 基于“黑像素占比”（适用于纯黑边）
    2. 基于“列平均灰度”（适用于深灰边/浅色粗边）
    
    两种策略的结果取并集，然后进行后续筛选。
    """
    gray = _to_gray(image_array)
    h, w = gray.shape

    # --- 策略 1: 基于黑像素占比 (原逻辑) ---
    black_ratio = (gray < dark_threshold).mean(axis=0)
    
    # --- 策略 2: 基于列平均灰度 (新逻辑) ---
    column_mean = gray.mean(axis=0)
    
    # 1D 平滑：对两种统计结果都进行平滑
    k = max(1, int(smooth_window))
    kernel = np.ones(k, dtype=np.float32) / k
    smooth_ratio = np.convolve(black_ratio, kernel, mode="same")
    smooth_mean = np.convolve(column_mean, kernel, mode="same")
    
    # 二值化：分别生成两种策略的掩码
    # 掩码 A: 黑像素占比达标 OR 平均灰度达标
    mask_ratio = smooth_ratio >= dark_ratio_thresh
    mask_mean = smooth_mean <= avg_gray_threshold 
    
    # 融合两种策略：只要满足其中任一条件，即认为是“深色列”
    mask = np.logical_or(mask_ratio, mask_mean)

    # ---------------------------------------------
    # 接下来是寻找连续段、过滤宽度和边缘约束的逻辑 (与您原代码相同)
    # ---------------------------------------------
    
    idx = np.where(mask)[0]
    if idx.size == 0:
        return None, None

    segments = []
    s = idx[0]
    for i in range(1, len(idx)):
        if idx[i] != idx[i - 1] + 1:
            e = idx[i - 1]
            segments.append((s, e))
            s = idx[i]
    segments.append((s, idx[-1]))

    # 过滤：宽度与边缘约束
    edge_margin = int(w * edge_margin_ratio)
    candidates = [(a, b) for (a, b) in segments
                  if (b - a + 1) >= min_width and a > edge_margin and b < (w - 1 - edge_margin)]
    if not candidates:
        return None, None

    # 选距离中线最近的一段
    mid = w / 2.0
    
    # 如果您之前采纳了“优先最宽”的逻辑，这里需要修改为：
    # seg = min(candidates, key=lambda ab: abs((ab[0] + ab[1]) / 2.0 - mid)) # 距离中线最近
    
    # 如果使用您原始的“距离中线最近”逻辑：
    seg = min(candidates, key=lambda ab: abs((ab[0] + ab[1]) / 2.0 - mid))
    
    return seg

def move_after_border_to_left(
    image_array: np.ndarray,
    dark_threshold: int = 60,
    min_width: int = 10,
    smooth_window: int = 9,
    dark_ratio_thresh: float = 0.80,
    edge_margin_ratio: float = 0.03,
):
    """
    找到“中间那条粗黑边”的左右边界 (start, end)，
    将 **右边界之后的整幅内容** 移到最左侧： new = right_part + left_part。
    找不到则原样返回。

    新增：在执行前增加一个简单的判断，如果最宽的黑边段宽度不是特别大，
    或者其位置不在中心附近，则认为不需要拼接。
    """
    start, end = detect_middle_black_border(
        image_array,
        dark_threshold=dark_threshold,
        min_width=min_width,
        smooth_window=smooth_window,
        dark_ratio_thresh=dark_ratio_thresh,
        edge_margin_ratio=edge_margin_ratio,
    )
    if start is None:
        print("未检测到中间粗黑边（或在边缘，跳过拼接）。")
        return image_array

    # 简单的启发式判断：如果检测到的“黑边”太细，可能不是拼接线
    detected_width = end - start + 1
    if detected_width < 30:  # 假设物理拼接线通常比10像素宽
        print(f"检测到黑边宽度过窄（{detected_width}px），可能不是拼接线，跳过。")
        return image_array

    # 简单的启发式判断：如果检测到的“黑边”离中心太远
    w = image_array.shape[1]
    mid = w / 2.0
    center_dist = abs((start + end) / 2.0 - mid)
    if center_dist > w * 0.2:  # 假设拼接线在图像中心20%范围内
        print(f"检测到黑边位置({(start+end)/2.0})离中心({mid})太远，可能不是拼接线，--跳过。")
        #return image_array

    print(f"检测到中间黑边：start={start}, end={end}（宽度={end - start + 1}）")
    right_part = image_array[:, end + 1:]
    left_part = image_array[:, : end + 1]
    # 右边移动到最左
    corrected = np.hstack((right_part, left_part))
    return corrected


def detect_text_orientation(image_array: np.ndarray) -> int:
    """
    用 Tesseract OSD 检测文字方向。返回 0/90/180/270。
    失败则返回 0。
    """
    try:
        pil_img = Image.fromarray(image_array)
        osd = pytesseract.image_to_osd(pil_img, lang="eng")
        # 解析 "Rotate: 90" 这样的行
        for line in osd.splitlines():
            if "Rotate:" in line:
                angle = int(line.split("Rotate:")[1].strip())
                print(f"OCR 检测旋转角度：{angle}°")
                return angle
    except Exception as e:
        print(f"OCR 方向检测失败：{e}")
    return 0


def rotate_by_osd_angle(image_array: np.ndarray, angle: int) -> np.ndarray:
    """
    按 OSD 给出的角度旋正：Tesseract 的含义是“需要旋转 angle° 才正”。
    我们用 PIL 逆向旋转：angle=90 => 旋转 -90。
    """
    if angle % 360 == 0:
        return image_array
    pil = Image.fromarray(image_array)
    # 逆向旋转
    if angle == 90:
        rot = pil.rotate(-90, expand=True)
    elif angle == 180:
        rot = pil.rotate(180, expand=True)
    elif angle == 270:
        rot = pil.rotate(90, expand=True)
    else:
        # 其它角度也支持
        rot = pil.rotate(-angle, expand=True)
    return np.array(rot)


def denoise_image(image_array: np.ndarray) -> np.ndarray:
    """
    专门为传真类气象图设计的去噪函数。
    """
    if image_array.ndim == 3:
        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = image_array

    # 1. 计算背景的平均亮度（为了判断是否需要去噪）
    mean_brightness = np.mean(gray)

    # 2. 如果背景太亮且方差很小，可能不需要去噪
    is_clean = False
    # 灰度值在180-255的像素占比
    white_pixel_ratio = np.mean(gray > 180) 
    # 计算白色背景区域的方差
    white_region_variance = np.var(gray[gray > 180]) if white_pixel_ratio > 0.5 else 9999

    # 简单的启发式判断：
    # 如果白色像素占比高且方差低，则认为图片干净
    if white_pixel_ratio > 0.8 and white_region_variance < 500:
        is_clean = True
    
    if is_clean:
        print("图片背景干净，跳过去噪步骤。")
        # 可以直接返回一个二值化结果，但保留细节
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, blockSize=15, C=2
        )
        return binary

    # ------------------
    # 以下是原有的去噪逻辑，只在图片有噪声时执行
    # ------------------
    print("图片背景有噪声，执行去噪处理。")
    # 自适应阈值二值化 (针对噪声背景)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY, blockSize=35, C=15
    )

    # 去水平条纹噪声：形态学开运算
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    no_stripe = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    # 小连通域去除：只保留大于一定面积的对象
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(no_stripe, connectivity=8)
    min_area = 50 
    mask = np.zeros_like(labels, dtype=np.uint8)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            mask[labels == i] = 255

    return mask


def process_image(
    input_path: str,
    do_move: bool = True,
    do_rotate: bool = True,
    do_denoise: bool = False,
    dark_threshold: int = 60,
    min_width: int = 10,
    smooth_window: int = 9,
    dark_ratio_thresh: float = 0.80,
    edge_margin_ratio: float = 0.03,
):
    """
    先执行“黑边右侧移到左侧”，再做 OCR 旋转，然后尝试去噪声；最后覆盖原文件。
    """
    img = Image.open(input_path)
    arr = np.array(img)

    if do_move:
        print("== 步骤1：中间黑边纠偏拼接 ==")
        arr = move_after_border_to_left(
            arr,
            dark_threshold=dark_threshold,
            min_width=min_width,
            smooth_window=smooth_window,
            dark_ratio_thresh=dark_ratio_thresh,
            edge_margin_ratio=edge_margin_ratio,
        )

    if do_denoise:
        print("== 步骤2：去噪 ==")
        arr = denoise_image(arr)

    if do_rotate:
        print("== 步骤3：OCR 方向识别并旋正 ==")
        angle = detect_text_orientation(arr)
        arr = rotate_by_osd_angle(arr, angle)

    Image.fromarray(arr).save(input_path)
    print(f"已覆盖保存：{input_path}")


def main():
    parser = argparse.ArgumentParser(
        description="先纠偏（将中间粗黑边右侧移到左侧），再用OCR自动转正（覆盖原图）。"
    )
    parser.add_argument("input_path", help="要处理的图片路径")
    parser.add_argument("--no-move", action="store_true", help="跳过黑边纠偏拼接")
    parser.add_argument("--no-rotate", action="store_true", help="跳过OCR方向识别与旋转")
    parser.add_argument("--denoise", action="store_true", help="跳过去噪")
    # 可调参数（一般默认即可）
    parser.add_argument("--dark-th", type=int, default=60, help="判定黑像素的灰度阈值，默认60")
    parser.add_argument("--min-width", type=int, default=10, help="黑边最小宽度(像素列)，默认10")
    parser.add_argument("--smooth", type=int, default=9, help="列黑度的一维平滑窗口大小，默认9")
    parser.add_argument("--ratio", type=float, default=0.80, help="列黑像素占比阈值，默认0.80")
    parser.add_argument("--edge-margin", type=float, default=0.03, help="忽略靠边段的边距比例，默认0.03")

    args = parser.parse_args()

    process_image(
        args.input_path,
        do_move=not args.no_move,
        do_rotate=not args.no_rotate,
        do_denoise=args.denoise,
        dark_threshold=args.dark_th,
        min_width=args.min_width,
        smooth_window=args.smooth,
        dark_ratio_thresh=args.ratio,
        edge_margin_ratio=args.edge_margin,
    )


if __name__ == "__main__":
    main()
