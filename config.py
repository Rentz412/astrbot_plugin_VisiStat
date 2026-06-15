"""VisiStat 配置读取与默认值。

负责把 AstrBot 传入的 _conf_schema.json 配置（一个 dict）解析成一个结构化、
带默认值、做过基本校验的 PluginConfig 对象。即使某些配置项缺失或类型错误，
也保证返回可用的默认值，绝不抛异常导致插件加载失败。

保持与旧版本配置完全兼容，所有旧的嵌套结构（user_config / background_config /
font_config / color_config / sensor_config / layout_config）都被保留。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


# 所有默认值集中在这里，便于维护，也作为校验失败时的兜底。
DEFAULTS: dict[str, Any] = {
    "main_title": "服务器运行状态",
    "custom_name": "default",
    "user_config": {
        "fixed_user_name": "AstrBot 用户",
        "fixed_avatar_path": "resources/avatar.png",
    },
    "background_config": {
        "image_path": "resources/bg1.png",
        "blur_radius": 10,
    },
    "font_config": {
        "content_font_path": "fonts/content.ttf",
    },
    "color_config": {
        "background": "#ffffff",
        "bing_dark": "#4c51bf",
        "bing_light": "#a8a8a8",
        "font_color": "#1a202c",
        "title_font_color": "#1a202c",
    },
    "sensor_config": {
        "monitor_cpu_temp": True,
        "monitor_gpu_temp": False,
        "monitor_bat_temp": False,
        "monitor_battery_status": True,
        "temp_unit": "C",
        "show_temp_abbr": True,
    },
    "layout_config": {
        "vertical_scale": 1.1,
        "horizontal_scale": 1.3,
    },
}


def _as_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "是")
    return default


def _as_int(value: Any, default: int, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and result < minimum:
        return minimum
    return result


def _as_float(value: Any, default: float, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and result < minimum:
        return minimum
    return result


def _norm_color(value: Any, default: str) -> str:
    """规范化十六进制颜色，非法时回退默认值。"""
    text = _as_str(value, default).strip()
    if not text:
        return default
    if not text.startswith("#"):
        text = "#" + text
    body = text[1:]
    if len(body) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in body):
        return text
    return default


@dataclass
class PluginConfig:
    """结构化的插件配置。"""

    main_title: str = DEFAULTS["main_title"]
    custom_name: str = DEFAULTS["custom_name"]

    fixed_user_name: str = DEFAULTS["user_config"]["fixed_user_name"]
    fixed_avatar_path: str = DEFAULTS["user_config"]["fixed_avatar_path"]

    background_image_path: str = DEFAULTS["background_config"]["image_path"]
    blur_radius: int = DEFAULTS["background_config"]["blur_radius"]

    content_font_path: str = DEFAULTS["font_config"]["content_font_path"]

    color_background: str = DEFAULTS["color_config"]["background"]
    color_bing_dark: str = DEFAULTS["color_config"]["bing_dark"]
    color_bing_light: str = DEFAULTS["color_config"]["bing_light"]
    color_font: str = DEFAULTS["color_config"]["font_color"]
    color_title_font: str = DEFAULTS["color_config"]["title_font_color"]

    monitor_cpu_temp: bool = DEFAULTS["sensor_config"]["monitor_cpu_temp"]
    monitor_gpu_temp: bool = DEFAULTS["sensor_config"]["monitor_gpu_temp"]
    monitor_bat_temp: bool = DEFAULTS["sensor_config"]["monitor_bat_temp"]
    monitor_battery_status: bool = DEFAULTS["sensor_config"]["monitor_battery_status"]
    temp_unit: str = DEFAULTS["sensor_config"]["temp_unit"]
    show_temp_abbr: bool = DEFAULTS["sensor_config"]["show_temp_abbr"]

    vertical_scale: float = DEFAULTS["layout_config"]["vertical_scale"]
    horizontal_scale: float = DEFAULTS["layout_config"]["horizontal_scale"]

    @property
    def temp_unit_upper(self) -> str:
        return "F" if self.temp_unit.upper() == "F" else "C"


def load_config(raw: Mapping[str, Any] | None) -> PluginConfig:
    """从 AstrBot 传入的原始配置 dict 构造 PluginConfig。

    raw 可能为 None、缺字段、或字段类型不对，本函数对所有情况做兜底。
    """
    raw = raw or {}

    def section(name: str) -> Mapping[str, Any]:
        value = raw.get(name)
        return value if isinstance(value, Mapping) else {}

    user = section("user_config")
    bg = section("background_config")
    font = section("font_config")
    color = section("color_config")
    sensor = section("sensor_config")
    layout = section("layout_config")

    d = DEFAULTS
    temp_unit = _as_str(sensor.get("temp_unit"), d["sensor_config"]["temp_unit"]).strip().upper()
    if temp_unit not in ("C", "F"):
        temp_unit = "C"

    return PluginConfig(
        main_title=_as_str(raw.get("main_title"), d["main_title"]),
        custom_name=_as_str(raw.get("custom_name"), d["custom_name"]),
        fixed_user_name=_as_str(
            user.get("fixed_user_name"), d["user_config"]["fixed_user_name"]
        ),
        fixed_avatar_path=_as_str(
            user.get("fixed_avatar_path"), d["user_config"]["fixed_avatar_path"]
        ),
        background_image_path=_as_str(
            bg.get("image_path"), d["background_config"]["image_path"]
        ),
        blur_radius=_as_int(
            bg.get("blur_radius"), d["background_config"]["blur_radius"], minimum=0
        ),
        content_font_path=_as_str(
            font.get("content_font_path"), d["font_config"]["content_font_path"]
        ),
        color_background=_norm_color(
            color.get("background"), d["color_config"]["background"]
        ),
        color_bing_dark=_norm_color(
            color.get("bing_dark"), d["color_config"]["bing_dark"]
        ),
        color_bing_light=_norm_color(
            color.get("bing_light"), d["color_config"]["bing_light"]
        ),
        color_font=_norm_color(color.get("font_color"), d["color_config"]["font_color"]),
        color_title_font=_norm_color(
            color.get("title_font_color"), d["color_config"]["title_font_color"]
        ),
        monitor_cpu_temp=_as_bool(
            sensor.get("monitor_cpu_temp"), d["sensor_config"]["monitor_cpu_temp"]
        ),
        monitor_gpu_temp=_as_bool(
            sensor.get("monitor_gpu_temp"), d["sensor_config"]["monitor_gpu_temp"]
        ),
        monitor_bat_temp=_as_bool(
            sensor.get("monitor_bat_temp"), d["sensor_config"]["monitor_bat_temp"]
        ),
        monitor_battery_status=_as_bool(
            sensor.get("monitor_battery_status"),
            d["sensor_config"]["monitor_battery_status"],
        ),
        temp_unit=temp_unit,
        show_temp_abbr=_as_bool(
            sensor.get("show_temp_abbr"), d["sensor_config"]["show_temp_abbr"]
        ),
        vertical_scale=_as_float(
            layout.get("vertical_scale"),
            d["layout_config"]["vertical_scale"],
            minimum=0.1,
        ),
        horizontal_scale=_as_float(
            layout.get("horizontal_scale"),
            d["layout_config"]["horizontal_scale"],
            minimum=0.1,
        ),
    )
