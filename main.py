"""VisiStat - AstrBot 服务器状态可视化插件（重制版）。

指令 /状态 /status /info 触发后，采集系统状态并渲染成一张图片卡片返回。

结构说明：
- config.py   配置解析与默认值
- monitor.py  系统监控数据采集（psutil / wmi）
- renderer.py 图片卡片渲染（纯 Pillow）
- utils.py    路径、字体、颜色、头像、临时目录工具
- main.py     插件入口与指令处理（本文件）

设计要点：
- 渲染是 CPU 密集型操作，放到线程池执行，避免阻塞事件循环。
- 临时图片写入插件目录下 cache/temp，使用唯一文件名，并定期清理。
- 异常详情记入日志，用户侧只返回简洁中文提示。
"""

from __future__ import annotations

import asyncio
import uuid

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .config import load_config
from .monitor import collect
from .renderer import CardRenderer
from .utils import cleanup_temp_dir, ensure_temp_dir


@register(
    "astrbot_plugin_VisiStat",
    "Rentz",
    "可视化的系统硬件监控，支持自定义美化，适配 Windows/Linux 双端",
    "v2.0.0",
    "https://github.com/Rentz412/astrbot_plugin_VisiStat",
)
class VisiStatPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.cfg = load_config(config)
        # 渲染器在初始化时预处理背景图与字体，构造失败也不应让插件加载崩溃。
        try:
            self.renderer: CardRenderer | None = CardRenderer(self.cfg)
        except Exception as e:  # noqa: BLE001
            self.renderer = None
            logger.error(f"[VisiStat] 渲染器初始化失败: {e}", exc_info=True)
        logger.info("[VisiStat] 插件已加载")

    @filter.command("状态", alias={"status", "info"})
    async def server_status(self, event: AstrMessageEvent):
        """获取并发送服务器状态卡片。"""
        if self.renderer is None:
            # 尝试再次构造，仍失败则提示用户。
            try:
                self.renderer = CardRenderer(self.cfg)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[VisiStat] 渲染器不可用: {e}", exc_info=True)
                yield event.plain_result("⚠️ 状态卡片渲染器初始化失败，请检查日志。")
                return

        try:
            # 采集 + 渲染都在线程池中执行，避免阻塞事件循环。
            image = await asyncio.to_thread(self._build_image)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[VisiStat] 生成状态卡片失败: {e}", exc_info=True)
            yield event.plain_result("⚠️ 获取服务器状态失败，请稍后重试或查看日志。")
            return

        try:
            temp_dir = ensure_temp_dir()
            out_path = temp_dir / f"visistat_{uuid.uuid4().hex}.png"
            image.save(str(out_path))
        except Exception as e:  # noqa: BLE001
            logger.error(f"[VisiStat] 状态卡片保存失败: {e}", exc_info=True)
            yield event.plain_result("⚠️ 状态卡片保存失败，请查看日志。")
            return

        yield event.image_result(str(out_path))

        # 发送后清理旧的临时文件，避免无限堆积。
        cleanup_temp_dir()

    def _build_image(self):
        """同步采集数据并渲染卡片，供线程池调用。"""
        stats = collect(self.cfg)
        assert self.renderer is not None
        return self.renderer.render(stats)

    async def terminate(self):
        """插件卸载 / 停用时调用。"""
        logger.info("[VisiStat] 插件已卸载")
