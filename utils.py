"""VisiStat 工具函数：路径、字体、颜色、头像、缓存目录。

所有路径都基于插件目录解析，不依赖当前工作目录。
字体 / 头像加载都带有兜底逻辑，保证在资源缺失时也不崩溃。
"""

from __future__ import annotations

import platform
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger


# 插件根目录（utils.py 所在目录）。
PLUGIN_DIR = Path(__file__).resolve().parent

# 临时图片输出目录。使用插件目录下的 cache/temp，避免写到当前工作目录。
CACHE_DIR = PLUGIN_DIR / "cache"
TEMP_DIR = CACHE_DIR / "temp"

# 系统字体候选，用于配置字体不可用时的兜底。
_SYSTEM_FONT_CANDIDATES = {
    "Windows": [
        "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",  # 黑体
        "msyh.ttc",
        "simhei.ttf",
    ],
    "Linux": [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "Darwin": [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ],
}


def resolve_path(relative: str) -> Path | None:
    """把相对插件目录的路径解析为绝对路径。

    relative 为空返回 None。绝对路径直接返回。
    """
    if not relative:
        return None
    p = Path(relative)
    if p.is_absolute():
        return p
    return PLUGIN_DIR / p


def ensure_temp_dir() -> Path:
    """确保临时目录存在并返回它。"""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def cleanup_temp_dir(max_files: int = 20, max_age_seconds: int = 3600) -> None:
    """清理临时图片，避免无限堆积。

    删除超过 max_age_seconds 的旧文件；若文件数仍超过 max_files，
    则按修改时间从旧到新删除多余文件。任何异常只记录日志，不抛出。
    """
    try:
        if not TEMP_DIR.exists():
            return
        files = [p for p in TEMP_DIR.glob("visistat_*.png") if p.is_file()]
        now = time.time()

        # 先按年龄清理。
        for p in list(files):
            try:
                if now - p.stat().st_mtime > max_age_seconds:
                    p.unlink(missing_ok=True)
                    files.remove(p)
            except OSError:
                pass

        # 再按数量清理。
        if len(files) > max_files:
            files.sort(key=lambda p: p.stat().st_mtime)
            for p in files[: len(files) - max_files]:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception as e:  # noqa: BLE001 - 清理失败不应影响主流程
        logger.debug(f"[VisiStat] 清理临时目录失败: {e}")


def hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """把 #rgb / #rrggbb / #rrggbbaa 转换为 RGBA 元组。失败回退白色。"""
    try:
        text = color.lstrip("#")
        if len(text) == 3:
            r, g, b = (int(c * 2, 16) for c in text)
            return (r, g, b, alpha)
        if len(text) == 6:
            r = int(text[0:2], 16)
            g = int(text[2:4], 16)
            b = int(text[4:6], 16)
            return (r, g, b, alpha)
        if len(text) == 8:
            r = int(text[0:2], 16)
            g = int(text[2:4], 16)
            b = int(text[4:6], 16)
            a = int(text[6:8], 16)
            return (r, g, b, a)
    except (ValueError, TypeError):
        pass
    return (255, 255, 255, alpha)


class FontCache:
    """字体缓存与加载，带兜底。

    优先用户配置字体 -> 系统中文字体 -> Pillow 默认字体。
    一旦确定了可用字体文件路径，就缓存下来，按 size 缓存字体对象。
    """

    def __init__(self, configured_font_path: str = ""):
        self._configured = resolve_path(configured_font_path)
        self._resolved_font_file: Path | None = None
        self._use_default = False
        self._cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._resolve_font_file()

    def _resolve_font_file(self) -> None:
        # 1. 用户配置字体
        if self._configured and self._configured.is_file():
            try:
                ImageFont.truetype(str(self._configured), 16)
                self._resolved_font_file = self._configured
                logger.info(f"[VisiStat] 使用配置字体: {self._configured}")
                return
            except OSError:
                logger.warning(
                    f"[VisiStat] 配置字体无法加载，回退系统字体: {self._configured}"
                )

        # 2. 系统中文字体
        for candidate in _SYSTEM_FONT_CANDIDATES.get(platform.system(), []):
            try:
                ImageFont.truetype(candidate, 16)
                self._resolved_font_file = Path(candidate)
                logger.info(f"[VisiStat] 使用系统字体: {candidate}")
                return
            except OSError:
                continue

        # 3. Pillow 默认字体（不支持中文，但保证不崩溃）
        self._use_default = True
        logger.warning("[VisiStat] 未找到可用 TTF 字体，使用 Pillow 默认字体（中文可能无法显示）")

    def get(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        size = max(1, int(size))
        cached = self._cache.get(size)
        if cached is not None:
            return cached

        font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        if not self._use_default and self._resolved_font_file is not None:
            try:
                font = ImageFont.truetype(str(self._resolved_font_file), size)
            except OSError:
                font = ImageFont.load_default()
        else:
            font = ImageFont.load_default()

        self._cache[size] = font
        return font


def make_default_avatar(size: int, font_cache: FontCache | None = None) -> Image.Image:
    """生成一个默认占位头像（圆形渐变底 + 字母 A）。"""
    size = max(16, int(size))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 圆形纯色底
    draw.ellipse((0, 0, size - 1, size - 1), fill=(99, 102, 241, 255))

    text = "A"
    if font_cache is not None:
        font = font_cache.get(int(size * 0.5))
    else:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((size - text_w) / 2 - bbox[0], (size - text_h) / 2 - bbox[1]),
            text,
            font=font,
            fill=(255, 255, 255, 255),
        )
    except Exception:  # noqa: BLE001 - 文本绘制失败时返回纯色圆
        pass
    return img


def load_avatar(avatar_path: str, size: int, font_cache: FontCache | None = None) -> Image.Image:
    """加载头像，失败时返回默认占位头像。"""
    p = resolve_path(avatar_path)
    if p is not None and p.is_file():
        try:
            return Image.open(str(p)).convert("RGBA")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[VisiStat] 头像加载失败，使用默认头像: {p} ({e})")
    return make_default_avatar(size, font_cache)


def make_circular(img: Image.Image) -> Image.Image:
    """把图片裁切成圆形（先居中正方形裁切，再套圆形蒙版）。"""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, side, side), fill=255)

    result = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result
