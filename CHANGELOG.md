# 更新日志 - Release

## v2.0.0 - 2026-06-15

## 对模块进行了重构

### 新增模块（拆分自旧 main.py）：

- config.py — 配置解析、默认值、类型校验与兜底
- monitor.py — 系统监控数据采集（psutil / 可选 wmi）
- renderer.py — 图片卡片渲染（纯 Pillow，含环形图）
- utils.py — 路径、字体、颜色、头像、临时目录工具
- astrbot_plugin_VisiStat/__init__.py — 使插件成为标准包，保证相对导入稳定

### 重写/同步：

- main.py — 精简为插件入口
- metadata.yaml — 版本升到 v2.0.0，补 short_desc
- requirements.txt — 移除 matplotlib
- README.md — 重写，含新结构说明
- .gitignore — 追加 cache/ 等运行时文件
- _conf_schema.json — 已审查，所有要求的配置项均兼容，无需改动（兼容旧版，但建议清除模块配置以应用新版默认配置）
