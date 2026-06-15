"""VisiStat 图片卡片渲染。

使用 Pillow 直接绘制环形图（替代 matplotlib），生成服务器状态卡片。
支持横屏 / 竖屏背景自适应，支持纯色背景兜底。所有字体加载经过 FontCache 兜底。

设计目标：
- 不依赖 matplotlib，纯 Pillow 实现，规避 matplotlib 全局状态在异步环境下的线程安全问题。
- 背景图缺失时使用纯色背景；字体缺失时使用兜底字体；头像缺失时使用默认头像。
- 横屏 / 竖屏根据背景图宽高比自动选择。
"""

from __future__ import annotations

import re

from PIL import Image, ImageDraw, ImageFilter

from astrbot.api import logger
from .config import PluginConfig
from .monitor import SystemStats
from .utils import (
    FontCache,
    hex_to_rgba,
    load_avatar,
    make_circular,
    resolve_path,
)

# 4x 超采样绘制环形图，再缩小，得到平滑边缘（Pillow 没有内置抗锯齿）。
_SUPERSAMPLE = 4

# 默认卡片尺寸（无背景图时）。
_DEFAULT_CARD_W = 900
_DEFAULT_CARD_H = 350

# 宽高比大于该值视为横屏。
_HORIZONTAL_RATIO = 1.2


class CardRenderer:
    """状态卡片渲染器。

    在 __init__ 阶段完成背景图加载、模糊预处理与字体缓存初始化，
    使得每次渲染只需绘制文字和图表，开销较小。
    """

    def __init__(self, cfg: PluginConfig):
        self.cfg = cfg
        self.fonts = FontCache(cfg.content_font_path)

        self._dark = hex_to_rgba(cfg.color_bing_dark)
        self._light = hex_to_rgba(cfg.color_bing_light)
        self._font_color = hex_to_rgba(cfg.color_font)
        self._title_color = hex_to_rgba(cfg.color_title_font)
        self._bg_color = hex_to_rgba(cfg.color_background)

        self._base_canvas: Image.Image | None = None
        self._is_horizontal = False
        self._prepare_background()

    # ---- 背景准备 ----------------------------------------------------------

    def _prepare_background(self) -> None:
        """加载并（可选）模糊背景图，缓存为基础画布。失败回退纯色。"""
        bg_path = resolve_path(self.cfg.background_image_path)
        if bg_path is not None and bg_path.is_file():
            try:
                bg = Image.open(str(bg_path)).convert("RGBA")
                if self.cfg.blur_radius > 0:
                    bg = (
                        bg.convert("RGB")
                        .filter(ImageFilter.GaussianBlur(self.cfg.blur_radius))
                        .convert("RGBA")
                    )
                self._base_canvas = bg
                w, h = bg.size
                self._is_horizontal = (w / h) > _HORIZONTAL_RATIO if h else False
                logger.info(
                    f"[VisiStat] 背景图已加载 {w}x{h}，"
                    f"{'横屏' if self._is_horizontal else '竖屏'}模式"
                )
                return
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[VisiStat] 背景图加载失败，使用纯色背景: {bg_path} ({e})")

        # 纯色背景兜底
        self._base_canvas = None
        self._is_horizontal = (_DEFAULT_CARD_W / _DEFAULT_CARD_H) > _HORIZONTAL_RATIO
        logger.info("[VisiStat] 使用纯色背景")

    def _new_canvas(self) -> Image.Image:
        if self._base_canvas is not None:
            return self._base_canvas.copy()
        return Image.new("RGBA", (_DEFAULT_CARD_W, _DEFAULT_CARD_H), self._bg_color)

    # ---- 环形图 ------------------------------------------------------------

    def _ring_chart(self, value: float, size: int) -> Image.Image:
        """绘制一个环形进度图，中心显示百分比。纯 Pillow 实现。"""
        value = max(0.0, min(100.0, float(value)))
        ss = size * _SUPERSAMPLE
        img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        thickness = max(2, int(ss * 0.16))
        pad = thickness // 2 + 1
        box = (pad, pad, ss - pad, ss - pad)

        # 底环（未占用色）
        draw.ellipse(box, outline=self._light, width=thickness)

        # 进度弧（已占用色），从 12 点钟方向顺时针。
        if value > 0:
            start = -90
            end = start + 360 * (value / 100.0)
            draw.arc(box, start, end, fill=self._dark, width=thickness)

        img = img.resize((size, size), Image.Resampling.LANCZOS)

        # 中心百分比文字（在缩小后的图上绘制，保证清晰）。
        draw = ImageDraw.Draw(img)
        text = f"{value:.0f}%"
        font = self.fonts.get(max(10, int(size * 0.22)))
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
            text,
            font=font,
            fill=self._font_color,
        )
        return img

    # ---- 文本换行 ----------------------------------------------------------

    @staticmethod
    def _wrap_text(text: str, font, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
        if not text:
            return [""]
        segments = re.findall(r"[\S一-鿿]+|\s+", text)
        lines: list[str] = []
        current = ""
        for seg in segments:
            test = current + seg
            width = draw.textbbox((0, 0), test.strip(), font=font)[2]
            if width <= max_width or not current.strip():
                current = test
            else:
                lines.append(current.rstrip())
                current = seg.lstrip()
        if current.strip():
            lines.append(current.rstrip())
        return lines or [""]

    # ---- 温度文本 ----------------------------------------------------------

    def _temp_items(self, stats: SystemStats) -> list[str]:
        """构造温度显示文本列表，每项形如 'CPU: 45°C' 或 '45°C'。"""
        unit = self.cfg.temp_unit_upper
        items: list[str] = []
        mapping = [
            ("CPU", self.cfg.monitor_cpu_temp, stats.cpu_temp),
            ("GPU", self.cfg.monitor_gpu_temp, stats.gpu_temp),
            ("BAT", self.cfg.monitor_bat_temp, stats.bat_temp),
        ]
        for abbr, enabled, value in mapping:
            if not enabled:
                continue
            prefix = f"{abbr}: " if self.cfg.show_temp_abbr else ""
            if value is not None and value > 0.1:
                items.append(f"{prefix}{value:.1f}°{unit}")
            else:
                items.append(f"{prefix}N/A")
        return items

    # ---- 顶层渲染入口 ------------------------------------------------------

    def render(self, stats: SystemStats) -> Image.Image:
        canvas = self._new_canvas()
        avatar = load_avatar(
            self.cfg.fixed_avatar_path, 300, self.fonts
        )
        if self._is_horizontal:
            return self._draw_horizontal(canvas, stats, avatar)
        return self._draw_vertical(canvas, stats, avatar)

    # ---- 竖屏布局 ----------------------------------------------------------

    def _draw_vertical(
        self, canvas: Image.Image, stats: SystemStats, avatar: Image.Image
    ) -> Image.Image:
        w, h = canvas.size
        base = min(w, h)
        scale = self.cfg.vertical_scale

        margin = int(base * 0.05 * scale)
        title_size = int(base * 0.08 * scale)
        name_size = int(base * 0.06 * scale)
        content_size = int(base * 0.045 * scale)
        line_h = int(base * 0.06 * scale)
        avatar_size = int(base * 0.15 * scale)

        title_font = self.fonts.get(title_size)
        name_font = self.fonts.get(name_size)
        content_font = self.fonts.get(content_size)

        draw = ImageDraw.Draw(canvas)
        x = margin
        fg = self._font_color

        # 头部：头像 + 昵称 + 主标题
        av = make_circular(avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS))
        name = self.cfg.fixed_user_name
        title = self.cfg.main_title
        name_h = draw.textbbox((0, 0), name, font=name_font)[3]
        small_gap = int(base * 0.01 * scale)

        header_text_h = name_h + small_gap + draw.textbbox((0, 0), title, font=title_font)[3]
        header_h = max(avatar_size, header_text_h)

        header_y = margin
        canvas.paste(av, (x, header_y + (header_h - avatar_size) // 2), av)
        text_x = x + avatar_size + margin
        text_y = header_y + (header_h - header_text_h) // 2
        draw.text((text_x, text_y), name, font=name_font, fill=self._title_color)
        draw.text(
            (text_x, text_y + name_h + small_gap), title, font=title_font, fill=self._title_color
        )

        cur_y = header_y + header_h + margin

        # 系统信息（自动换行）
        info_max_w = w - 2 * margin
        sys_prefix = "系统信息: "
        prefix_w = draw.textbbox((0, 0), sys_prefix, font=content_font)[2]
        sys_lines = self._wrap_text(stats.system_info, content_font, draw, info_max_w - prefix_w)
        draw.text((x, cur_y), sys_prefix + sys_lines[0], font=content_font, fill=fg)
        cur_y += line_h
        for line in sys_lines[1:]:
            draw.text((x + prefix_w, cur_y), line, font=content_font, fill=fg)
            cur_y += line_h

        # 温度
        temp_items = self._temp_items(stats)
        temp_prefix = "系统温度: "
        if not temp_items:
            draw.text((x, cur_y), f"{temp_prefix}N/A", font=content_font, fill=fg)
            cur_y += line_h
        else:
            tp_w = draw.textbbox((0, 0), temp_prefix, font=content_font)[2]
            draw.text((x, cur_y), temp_prefix + temp_items[0], font=content_font, fill=fg)
            cur_y += line_h
            for item in temp_items[1:]:
                draw.text((x + tp_w, cur_y), item, font=content_font, fill=fg)
                cur_y += line_h

        # 电池
        if stats.battery_text and stats.battery_percent is not None:
            draw.text((x, cur_y), stats.battery_text, font=content_font, fill=fg)
            cur_y += line_h

        # 运行时间 / 当前时间
        draw.text((x, cur_y), f"运行时间: {stats.uptime_text}", font=content_font, fill=fg)
        cur_y += line_h
        draw.text((x, cur_y), f"当前时间: {stats.current_time}", font=content_font, fill=fg)
        cur_y += line_h

        # 分隔线
        cur_y += margin // 2
        draw.line([(margin, cur_y), (w - margin, cur_y)], fill=fg, width=2)
        cur_y += margin // 2

        # 网络流量（居中）
        net_title = "网络流量:"
        net_data = f"↑{stats.net_sent_mb:.2f}MB ↓{stats.net_recv_mb:.2f}MB"
        for line in (net_title, net_data):
            lw = draw.textbbox((0, 0), line, font=content_font)[2]
            draw.text(((w - lw) // 2, cur_y), line, font=content_font, fill=fg)
            cur_y += line_h

        cur_y += margin // 2

        # 三个环形图
        gap = margin // 2
        chart_size = (w - 2 * margin - 2 * gap) // 3
        # 防止图表超出画布底部
        max_chart = max(40, h - cur_y - margin - line_h)
        chart_size = max(40, min(chart_size, max_chart))

        charts = [
            ("CPU", stats.cpu_percent),
            ("MEM", stats.mem_percent),
            ("DISK", stats.disk_percent),
        ]
        total_w = 3 * chart_size + 2 * gap
        start_x = (w - total_w) // 2
        label_h = draw.textbbox((0, 0), "CPU", font=content_font)[3]
        label_y = cur_y
        chart_y = cur_y + label_h + margin // 4

        for i, (label, value) in enumerate(charts):
            cx = start_x + i * (chart_size + gap)
            lw = draw.textbbox((0, 0), label, font=content_font)[2]
            draw.text((cx + (chart_size - lw) // 2, label_y), label, font=content_font, fill=fg)
            ring = self._ring_chart(value, chart_size)
            canvas.paste(ring, (cx, chart_y), ring)

        return canvas

    # ---- 横屏布局 ----------------------------------------------------------

    def _draw_horizontal(
        self, canvas: Image.Image, stats: SystemStats, avatar: Image.Image
    ) -> Image.Image:
        w, h = canvas.size
        base = h
        scale = self.cfg.horizontal_scale

        margin = int(base * 0.05 * scale)
        title_size = int(base * 0.07 * scale)
        name_size = int(base * 0.055 * scale)
        content_size = int(base * 0.042 * scale)
        line_h = int(base * 0.058 * scale)
        avatar_size = int(base * 0.14 * scale)

        title_font = self.fonts.get(title_size)
        name_font = self.fonts.get(name_size)
        content_font = self.fonts.get(content_size)

        draw = ImageDraw.Draw(canvas)
        fg = self._font_color

        # 右侧图表区域宽度
        num_charts = 3
        chart_gap = max(8, int(base * 0.03 * scale))
        label_h = draw.textbbox((0, 0), "MEM", font=content_font)[3]
        label_gap = margin // 4
        avail_h = h - 2 * margin
        per_overhead = label_h + label_gap
        chart_size = (avail_h - num_charts * per_overhead - (num_charts - 1) * chart_gap) // num_charts
        chart_size = max(60, chart_size)

        chart_block_w = chart_size + margin // 2
        chart_area_x = w - margin - chart_block_w
        chart_center_x = chart_area_x + chart_size // 2

        # 左侧信息区域
        x = margin
        info_max_w = chart_area_x - margin - x

        # 头部
        av = make_circular(avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS))
        name = self.cfg.fixed_user_name
        title = self.cfg.main_title
        name_h = draw.textbbox((0, 0), name, font=name_font)[3]
        small_gap = int(base * 0.01 * scale)
        header_text_h = name_h + small_gap + draw.textbbox((0, 0), title, font=title_font)[3]
        header_h = max(avatar_size, header_text_h)

        cur_y = margin
        canvas.paste(av, (x, cur_y + (header_h - avatar_size) // 2), av)
        text_x = x + avatar_size + margin // 2
        text_y = cur_y + (header_h - header_text_h) // 2
        draw.text((text_x, text_y), name, font=name_font, fill=self._title_color)
        draw.text(
            (text_x, text_y + name_h + small_gap), title, font=title_font, fill=self._title_color
        )

        cur_y += header_h + margin // 2

        # 系统信息
        sys_prefix = "系统信息: "
        prefix_w = draw.textbbox((0, 0), sys_prefix, font=content_font)[2]
        sys_lines = self._wrap_text(stats.system_info, content_font, draw, info_max_w - prefix_w)
        draw.text((x, cur_y), sys_prefix + sys_lines[0], font=content_font, fill=fg)
        cur_y += line_h
        for line in sys_lines[1:]:
            draw.text((x + prefix_w, cur_y), line, font=content_font, fill=fg)
            cur_y += line_h

        # 温度
        temp_items = self._temp_items(stats)
        temp_prefix = "系统温度: "
        if not temp_items:
            draw.text((x, cur_y), f"{temp_prefix}N/A", font=content_font, fill=fg)
            cur_y += line_h
        else:
            tp_w = draw.textbbox((0, 0), temp_prefix, font=content_font)[2]
            draw.text((x, cur_y), temp_prefix + temp_items[0], font=content_font, fill=fg)
            cur_y += line_h
            for item in temp_items[1:]:
                draw.text((x + tp_w, cur_y), item, font=content_font, fill=fg)
                cur_y += line_h

        # 电池
        if stats.battery_text and stats.battery_percent is not None:
            draw.text((x, cur_y), stats.battery_text, font=content_font, fill=fg)
            cur_y += line_h

        # 运行时间 / 当前时间 / 网络流量
        draw.text((x, cur_y), f"运行时间: {stats.uptime_text}", font=content_font, fill=fg)
        cur_y += line_h
        draw.text((x, cur_y), f"当前时间: {stats.current_time}", font=content_font, fill=fg)
        cur_y += line_h
        net = f"网络流量: ↑{stats.net_sent_mb:.2f}MB ↓{stats.net_recv_mb:.2f}MB"
        draw.text((x, cur_y), net, font=content_font, fill=fg)
        cur_y += line_h

        # 右侧三个环形图，垂直居中排布
        charts = [
            ("CPU", stats.cpu_percent),
            ("MEM", stats.mem_percent),
            ("DISK", stats.disk_percent),
        ]
        block_h = num_charts * chart_size + num_charts * per_overhead + (num_charts - 1) * chart_gap
        chart_y = margin + max(0, (avail_h - block_h) // 2)

        for label, value in charts:
            lw = draw.textbbox((0, 0), label, font=content_font)[2]
            draw.text((chart_center_x - lw // 2, chart_y), label, font=content_font, fill=fg)
            ring_y = chart_y + label_h + label_gap
            ring = self._ring_chart(value, chart_size)
            canvas.paste(ring, (chart_center_x - chart_size // 2, ring_y), ring)
            chart_y = ring_y + chart_size + chart_gap

        return canvas
