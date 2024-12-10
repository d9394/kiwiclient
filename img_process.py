import numpy as np
from PIL import Image
import pytesseract
import argparse

def detect_thick_black_border(image_array, threshold=50, min_width=5):
    """
    检测图像中的粗黑边并返回其范围。
    :param image_array: 图像的numpy数组
    :param threshold: 黑色像素阈值
    :param min_width: 黑边的最小宽度（像素列数）
    :return: 黑边起止范围 (start, end)，如果没有则返回 None, None
    """
    if image_array.ndim == 3:  # RGB 图像
        column_means = np.mean(image_array, axis=(0, 2))
    else:  # 灰度图像
        column_means = np.mean(image_array, axis=0)

    is_black_column = column_means < threshold
    black_indices = np.where(is_black_column)[0]

    if len(black_indices) == 0:
        return None, None

    segments = []
    start = black_indices[0]
    for i in range(1, len(black_indices)):
        if black_indices[i] != black_indices[i - 1] + 1:
            end = black_indices[i - 1]
            segments.append((start, end + 1))
            start = black_indices[i]
    segments.append((start, black_indices[-1] + 1))

    thick_segments = [(start, end) for start, end in segments if end - start >= min_width]
    if thick_segments:
        return thick_segments[0]
    return None, None


def move_black_border_left(image_array):
    """
    将图像右侧的黑边区域移动到左侧。
    :param image_array: 输入图像数组
    :return: 处理后的图像数组
    """
    # 检测左侧黑边
    left_start, left_end = detect_thick_black_border(image_array, threshold=50, min_width=5)
    if left_start is not None and left_end is not None:
        print(f"检测到左侧黑边，从列 {left_start} 到列 {left_end}。")
        left_part = image_array[:, left_end + 1 :] 
        right_part = image_array[:, : left_start]
        image_array = np.hstack((left_part, right_part))

    return image_array


def detect_text_orientation(image_array):
    """
    使用 pytesseract 检测图像中的文本方向。
    :param image_array: 输入图像数组
    :return: 需要旋转的角度（0, 90, 180, 270）
    """
    pil_image = Image.fromarray(image_array)
    osd_info = pytesseract.image_to_osd(pil_image, lang='eng')
    angle = int(osd_info.split("Rotate:")[1].split("\n")[0].strip())
    print(f"OCR 检测到图片旋转角度：{angle}°")
    return angle


def rotate_image(image_array, angle):
    """
    根据角度旋转图像。
    :param image_array: 输入图像数组
    :param angle: 旋转角度（90, -90, 180 等）
    :return: 旋转后的图像数组
    """
    pil_image = Image.fromarray(image_array)
    rotated_image = pil_image.rotate(angle, expand=True)
    return np.array(rotated_image)


def process_image(input_path, move_black_border=True, rotate=True):
    """
    处理图像，包括黑边移动和 OCR 方向检测与旋转，最终覆盖源图像。
    :param input_path: 输入图像文件路径
    :param move_black_border: 是否移动黑边区域
    :param rotate: 是否检测方向并旋转
    """
    # 打开图像
    image = Image.open(input_path)
    image_array = np.array(image)

    # 1. 移动黑边
    if move_black_border:
        print("执行黑边移动操作...")
        image_array = move_black_border_left(image_array)

    # 2. 检测并旋转（默认执行）
    if rotate:
        print("执行 OCR 方向检测和旋转操作...")
        angle = detect_text_orientation(image_array)
        if angle == 90:
            image_array = rotate_image(image_array, -90)
        elif angle == 180:
            image_array = rotate_image(image_array, 180)
        elif angle == 270:
            image_array = rotate_image(image_array, 90)

    # 覆盖源图像
    processed_image = Image.fromarray(image_array)
    processed_image.save(input_path)
    print(f"处理后的图像已覆盖源文件：{input_path}。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="图像处理：黑边移动和方向检测与旋转（覆盖源文件）")
    parser.add_argument("input_path", type=str, help="输入图像文件路径")
    parser.add_argument("--no-move", action="store_true", help="跳过黑边移动")
    parser.add_argument("--no-rotate", action="store_true", help="跳过 OCR 检测和旋转")
    args = parser.parse_args()

    # 默认执行黑边移动和旋转，用户可通过参数关闭
    process_image(
        args.input_path,
        move_black_border=not args.no_move,
        rotate=not args.no_rotate
    )
