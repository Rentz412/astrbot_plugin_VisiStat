# VisiStat - 服务器状态可视化插件

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/Powered%20by-AstrBot-orange.svg)](https://github.com/AstrBotDevs/AstrBot)

🚀 **VisiStat** 是一款为 **AstrBot** 设计的可视化服务器状态监控插件，以精美的图片卡片形式，直观展示服务器的 CPU、内存、磁盘、网络、温度、电池、运行时间等关键指标。

> 本版本为重制版：纯 Pillow 渲染（不再依赖 matplotlib），结构模块化，增强了跨平台稳定性与异常容错。

---

## 📸 功能特性

- **纯 Pillow 渲染：** 自行绘制环形进度图，不依赖 matplotlib，规避其在异步服务中的全局状态/线程安全问题，依赖更轻量。
- **横屏 / 竖屏自适应：** 根据背景图宽高比自动选择布局，两张内置壁纸开箱即用。
- **全面监控：** CPU、内存、磁盘使用率，网络收发流量，系统温度（CPU/GPU/电池），电池状态，运行时间，当前时间。
- **高度容错：** 字体、头像、背景图缺失均有兜底，硬件信息取不到时显示 `N/A` 或隐藏，绝不因此崩溃。
- **高度可配置：** 自定义背景、模糊、头像、昵称、主标题、配色、温度单位（°C/°F）、缩放因子等。

## 📦 安装与依赖

将本仓库克隆到 AstrBot 插件目录（例如 `/AstrBot/data/plugins`）：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/Rentz412/astrbot_plugin_VisiStat.git
cd astrbot_plugin_VisiStat
pip install -r requirements.txt
```

`requirements.txt`：

```
psutil
Pillow
wmi; platform_system == "Windows"
```

> `wmi` 仅用于 Windows 下读取 CPU 温度，是可选依赖；未安装时插件依然可用，仅温度显示为 `N/A`。

## ⌨️ 使用命令

发送以下任一命令即可获取状态卡片：

```
/状态
/status
/info
```
效果示例：
![](https://github.com/Rentz412/astrbot_plugin_VisiStat/blob/origin/ciallo!.png)
> 内置两张壁纸，默认使用 `resources/bg1.png`（竖版），可在配置中切换为 `resources/bg2.png`（横版），也可以自行在插件目录中上传自定义壁纸。

## ⚙️ 配置说明

配置位于 AstrBot WebUI 的插件配置页（由 `_conf_schema.json` 定义）。主要配置项：

| 字段 | 描述 | 默认值 |
| :--- | :--- | :--- |
| `main_title` | 卡片主标题 | `服务器运行状态` |
| `custom_name` | 自定义系统信息（留空或 `default` 显示真实系统信息） | `default` |
| `user_config.fixed_user_name` | 显示的昵称 | `AstrBot 用户` |
| `user_config.fixed_avatar_path` | 头像路径（相对插件目录） | `resources/avatar.png` |
| `background_config.image_path` | 背景图路径（相对插件目录，留空用纯色） | `resources/bg1.png` |
| `background_config.blur_radius` | 背景模糊半径（0 为不模糊） | `10` |
| `font_config.content_font_path` | 字体路径（留空尝试系统字体） | `fonts/content.ttf` |
| `color_config.background` | 纯色背景色 | `#ffffff` |
| `color_config.bing_dark` | 环形图已占用色 | `#4c51bf` |
| `color_config.bing_light` | 环形图未占用色 | `#a8a8a8` |
| `color_config.font_color` | 正文字体色 | `#1a202c` |
| `color_config.title_font_color` | 标题/昵称字体色 | `#1a202c` |
| `sensor_config.monitor_cpu_temp` | 是否监控 CPU 温度 | `true` |
| `sensor_config.monitor_gpu_temp` | 是否监控 GPU 温度 | `false` |
| `sensor_config.monitor_bat_temp` | 是否监控电池温度 | `false` |
| `sensor_config.monitor_battery_status` | 是否显示电池状态 | `true` |
| `sensor_config.temp_unit` | 温度单位 `C`/`F` | `C` |
| `sensor_config.show_temp_abbr` | 是否显示设备缩写（如 `CPU:`） | `true` |
| `layout_config.vertical_scale` | 竖屏缩放因子 | `1.1` |
| `layout_config.horizontal_scale` | 横屏缩放因子 | `1.3` |

> 旧版本的配置项全部保持兼容，升级无需修改配置。

## 🗂️ 代码结构

```
astrbot_plugin_VisiStat/
├─ main.py        # 插件入口与指令处理
├─ config.py      # 配置解析、默认值、校验
├─ monitor.py     # 系统监控数据采集（psutil / wmi）
├─ renderer.py    # 图片卡片渲染（纯 Pillow）
├─ utils.py       # 路径、字体、颜色、头像、临时目录工具
├─ metadata.yaml
├─ _conf_schema.json
├─ requirements.txt
├─ resources/     # 内置壁纸与默认头像
├─ fonts/         # 内置字体
└─ cache/temp/    # 运行时生成的临时图片（自动清理，已被 .gitignore 忽略）
```

## 📌 注意事项

- **临时图片：** 生成的卡片写入 `cache/temp/`，使用唯一文件名避免并发冲突，并按数量/时间自动清理。
- **Linux/macOS：** 确保系统装有中文字体（如 wqy-zenhei、Noto Sans CJK），否则插件会回退到 Pillow 默认字体（不支持中文）。
- **Windows 温度：** 若需 CPU 温度，请安装 `wmi`；部分平台/权限下仍可能读不到，届时显示 `N/A`。

## 🤝 鸣谢

借鉴插件：
- https://github.com/yanfd/astrbot_plugin_server
- https://github.com/BB0813/astrbot_plugin_sysinfoimg/

## 📜 开源协议

本项目采用仓库根目录 [LICENSE](LICENSE) 所述协议。
