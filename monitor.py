"""VisiStat 系统监控数据采集。

封装所有 psutil / wmi 相关的读取逻辑，向上层提供一个干净的数据结构 SystemStats。
所有硬件相关读取都做了异常保护：取不到的值返回 None，由渲染层显示为 N/A 或隐藏，
绝不向上抛异常。
"""

from __future__ import annotations

import datetime
import platform
from dataclasses import dataclass
from typing import Any

import psutil

from astrbot.api import logger
from .config import PluginConfig

# wmi 是 Windows 下的可选依赖，导入失败不影响插件整体可用。
_wmi: Any = None
if platform.system() == "Windows":
    try:
        import wmi as _wmi_module

        _wmi = _wmi_module
    except Exception as e:  # noqa: BLE001 - 任何导入问题都视为不可用
        _wmi = None
        logger.info(f"[VisiStat] 未启用 wmi（Windows 温度可能无法获取）: {e}")


@dataclass
class SystemStats:
    """一次采集得到的系统状态快照。"""

    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    disk_percent: float = 0.0
    net_sent_mb: float = 0.0
    net_recv_mb: float = 0.0
    uptime_text: str = "N/A"
    current_time: str = ""
    system_info: str = ""

    # 温度（单位由配置决定），不可用为 None
    cpu_temp: float | None = None
    gpu_temp: float | None = None
    bat_temp: float | None = None

    # 电池
    battery_percent: float | None = None
    battery_text: str | None = None  # 已格式化好的电池状态文本；None 表示不显示


def _uptime_text() -> str:
    try:
        boot = psutil.boot_time()
        seconds = int(datetime.datetime.now().timestamp() - boot)
        if seconds < 0:
            return "N/A"
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        parts.append(f"{minutes}分")
        return " ".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] 运行时间获取失败: {e}")
        return "N/A"


def _disk_percent() -> float:
    """取系统盘使用率，跨平台兼容。"""
    path = "C:\\" if platform.system() == "Windows" else "/"
    try:
        return psutil.disk_usage(path).percent
    except Exception:
        # 兜底：尝试当前盘 / 第一个分区
        try:
            return psutil.disk_usage(".").percent
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[VisiStat] 磁盘使用率获取失败: {e}")
            return 0.0


def _temps_linux(cfg: PluginConfig) -> dict[str, float | None]:
    result: dict[str, float | None] = {"cpu": None, "gpu": None, "bat": None}
    if not hasattr(psutil, "sensors_temperatures"):
        return result
    try:
        fahrenheit = cfg.temp_unit_upper == "F"
        temps = psutil.sensors_temperatures(fahrenheit=fahrenheit)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] Linux 温度读取失败: {e}")
        return result
    if not temps:
        return result

    def max_current(entries) -> float | None:
        vals = [e.current for e in entries if e.current is not None]
        return max(vals) if vals else None

    if cfg.monitor_cpu_temp:
        cpu_entries = temps.get("coretemp") or temps.get("cpu_thermal") or temps.get("k10temp")
        if not cpu_entries:
            for name, entries in temps.items():
                if "cpu" in name.lower() or "package" in name.lower():
                    cpu_entries = entries
                    break
        if cpu_entries:
            result["cpu"] = max_current(cpu_entries)

    if cfg.monitor_gpu_temp:
        for name, entries in temps.items():
            lname = name.lower()
            if any(k in lname for k in ("gpu", "amdgpu", "nouveau", "nvidia")):
                result["gpu"] = max_current(entries)
                break

    if cfg.monitor_bat_temp:
        for name, entries in temps.items():
            if "bat" in name.lower():
                result["bat"] = max_current(entries)
                break

    return result


def _temps_windows(cfg: PluginConfig) -> dict[str, float | None]:
    result: dict[str, float | None] = {"cpu": None, "gpu": None, "bat": None}
    if _wmi is None:
        return result
    if not cfg.monitor_cpu_temp:
        return result
    try:
        c = _wmi.WMI(namespace="root\\wmi")
        data = c.MSAcpi_ThermalZoneTemperature()
        if data:
            # CurrentTemperature 单位是 0.1 开尔文
            temp_c = (data[0].CurrentTemperature - 2732) / 10.0
            if cfg.temp_unit_upper == "F":
                result["cpu"] = temp_c * 9 / 5 + 32
            else:
                result["cpu"] = temp_c
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] Windows WMI 温度读取失败: {e}")
    return result


def _temps_generic(cfg: PluginConfig) -> dict[str, float | None]:
    result: dict[str, float | None] = {"cpu": None, "gpu": None, "bat": None}
    if cfg.monitor_cpu_temp and hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures(fahrenheit=cfg.temp_unit_upper == "F")
            entries = temps.get("coretemp", [])
            vals = [e.current for e in entries if e.current is not None]
            if vals:
                result["cpu"] = max(vals)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[VisiStat] 通用温度读取失败: {e}")
    return result


def _collect_temps(cfg: PluginConfig) -> dict[str, float | None]:
    system = platform.system()
    if system == "Linux":
        return _temps_linux(cfg)
    if system == "Windows":
        return _temps_windows(cfg)
    return _temps_generic(cfg)


def _collect_battery(cfg: PluginConfig) -> tuple[float | None, str | None]:
    if not cfg.monitor_battery_status:
        return None, None
    try:
        bat = psutil.sensors_battery()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] 电池信息读取失败: {e}")
        return None, None
    if bat is None:
        return None, None

    percent = bat.percent
    if bat.power_plugged:
        return percent, f"电池状态: 充电中 ({percent:.0f}%)"

    secs = bat.secsleft
    if secs == psutil.POWER_TIME_UNLIMITED:
        left = "无限"
    elif secs == psutil.POWER_TIME_UNKNOWN or secs is None or secs < 0:
        left = "未知"
    else:
        minutes, _ = divmod(int(secs), 60)
        hours, minutes = divmod(minutes, 60)
        left = f"{hours}时{minutes}分"
    return percent, f"电池状态: 剩余 {percent:.0f}% ({left})"


def collect(cfg: PluginConfig) -> SystemStats:
    """采集一次完整的系统状态。任何子项失败都会被兜底，不会抛异常。"""
    stats = SystemStats()

    try:
        stats.cpu_percent = float(psutil.cpu_percent(interval=0.3))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] CPU 使用率获取失败: {e}")

    try:
        stats.mem_percent = float(psutil.virtual_memory().percent)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] 内存使用率获取失败: {e}")

    stats.disk_percent = _disk_percent()

    try:
        net = psutil.net_io_counters()
        stats.net_sent_mb = net.bytes_sent / (1024 * 1024)
        stats.net_recv_mb = net.bytes_recv / (1024 * 1024)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[VisiStat] 网络流量获取失败: {e}")

    stats.uptime_text = _uptime_text()
    stats.current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if cfg.custom_name and cfg.custom_name.strip().lower() != "default":
        stats.system_info = cfg.custom_name
    else:
        try:
            stats.system_info = (
                f"{platform.system()} {platform.release()} ({platform.machine()})"
            )
        except Exception:  # noqa: BLE001
            stats.system_info = "未知系统"

    temps = _collect_temps(cfg)
    stats.cpu_temp = temps.get("cpu")
    stats.gpu_temp = temps.get("gpu")
    stats.bat_temp = temps.get("bat")

    stats.battery_percent, stats.battery_text = _collect_battery(cfg)

    return stats
