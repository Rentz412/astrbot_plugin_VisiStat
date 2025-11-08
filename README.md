# VisiStat - 服务器状态可视化插件

[![License](https://img.shields.io/badge/License-AGPLv3-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/Powered%20by-AstrBot-orange.svg)](https://github.com/AstrBotDevs/AstrBot)

🚀 **VisiStat** 是一款专为 **AstrBot** 设计的可视化服务器状态监控插件，它以**图表优先**的精美卡片形式，提供简洁、直观的资源使用概览，帮助您实时掌握服务器运行健康状况。

此插件由Gemini AI模型编写
---

## 📸 功能特性概览

* **图表优先布局：** 核心图表（CPU/内存/磁盘）自动适应可用高度，实现最大化显示，确保资源占用一目了然。
* **优雅的横屏设计：** 采用左右分栏、视觉平衡的三等距布局，信息区块自动缩放和换行，适应各种卡片尺寸。
* **全面监控：** 实时监控 CPU、内存、磁盘使用率、网络流量、系统温度、运行时间、电池状态等关键指标。
* **高度可配置：** 支持自定义背景、头像、名称、缩放因子和温度单位（°C/°F）等。

## 📦 安装与依赖

### 1. 克隆插件

请将本仓库克隆到您的 AstrBot 插件目录（例如 `/AstrBot/data/plugins`）：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/Rentz412/astrbot_plugin_VisiStat.git
```


### 2. 安装依赖

本插件依赖以下 Python 包，请确保您的环境中已安装它们。建议使用 requirements.txt 进行安装：

```bash
cd /AstrBot/data/plugins/astrbot_plugin_VisiStat
pip install -r requirements.txt
```

requirements.txt 内容 (包含平台特定依赖):
```
psutil
matplotlib
Pillow
wmi; platform_system == "Windows"
```


## ⌨️ 使用命令


基础命令

发送以下任一命令，即可获取服务器状态卡片：
```
/状态  
/info
/status
```

效果示例：
![](https://github.com/Rentz412/astrbot_plugin_VisiStat/blob/origin/ciallo!.png)
Tips:内置两张壁纸，默认使用bg2.png（横版），可自行切换bg1.png查看竖版

## ⚙️ 配置说明

插件配置位于 _conf_schema.json（或您在 AstrBot WebUI/配置文件中的相应位置）。以下是一些关键配置项：

| 字段 | 描述 | 默认值 | 关键说明 |
| :--- | :--- | :--- | :--- |
| `main_title` | 卡片顶部的主标题 | `服务器运行状态` | |
| `custom_name` | 自定义系统信息/名称 | `default` | 留空或'default'显示系统信息。 |
| `fixed_user_name` | 固定显示的用户昵称 | `AstrBot 用户` | |
| `fixed_avatar_path` | 本地头像图片路径 | `resources/avatar.png` | 相对于插件根目录，留空则使用默认占位符。 |
| `image_path` | 背景图片路径 | `resources/bg2.png` | 相对于插件根目录，留空则使用纯色背景。 |
| `blur_radius` | 背景模糊半径 | `10` | 0为关闭模糊。 |
| `content_font_path` | 字体文件路径 | `fonts/content.ttf` | ttf文件，相对于插件根目录，为空则尝试使用本机字体。 |
| `background` | 纯色背景色 | `#ffffff` | 白色，当无背景图时生效。 |
| `bing_dark` | 饼图已占用色 | `#4c51bf` | 靛蓝 |
| `bing_light` | 饼图未占用色 | `#a8a8a8` | 浅灰 |
| `font_color` | 正文字体颜色 | `#1a202c` | 深蓝灰 |
| `title_font_color` | 主标题和昵称字体颜色 | `#1a202c` | 深蓝灰 |
| `monitor_cpu_temp` | 是否监控 CPU 温度 | `true` | |
| `monitor_gpu_temp` | 是否监控 GPU 温度 | `false` | Win端可能无法监控。 |
| `monitor_bat_temp` | 是否监控 电池 温度 | `false` | 笔记本或移动设备。|
| `monitor_battery_status` | 是否显示电池状态和电量 | `false` | 笔记本或移动设备。|
| `temp_unit` | 温度单位 | `"C"` | 可选 `"C"` (摄氏度) 或 `"F"` (华氏度)。 |
| `show_temp_abbr` | 温度显示是否显示设备缩写 | `true` | 例如CPU:45°C，关闭则只显示45°C。 |
| `vertical_scale` | **竖屏模式整体缩放因子** | `1.0` | 建议根据卡片尺寸以及显示内容进行调整，如 `1.2` 放大 20%。 |
| `horizontal_scale` | **横屏模式整体缩放因子** | `1.4` | 建议根据卡片尺寸以及显示内容进行调整，如 `1.2` 放大 20%。 |


## 📌 注意事项

Linux/macOS 用户： 确保您的系统环境能够顺利安装 psutil 和 matplotlib 的依赖库（通常需要 python3-dev 等开发包）。

Windows 用户： 如果获取不到温度信息，请确保 wmi 库已成功安装（已包含在带环境标记的 requirements.txt 中）。

## 🤝 鸣谢
借鉴插件：
        https://github.com/yanfd/astrbot_plugin_server
        https://github.com/BB0813/astrbot_plugin_sysinfoimg/

## 🤝 参与贡献
1. Fork 本仓库
2. 创建新分支 (`git checkout -b feature/awesome-feature`)
3. 提交修改 (`git commit -m 'Add some feature'`)
4. 推送更改 (`git push origin feature/awesome-feature`)
5. 创建 Pull Request

## 📜 开源协议
本项目采用 [MIT License](LICENSE)
