from astrbot.api.event.filter import command
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
import psutil
import platform
import datetime
import asyncio
import os
import re
from typing import Optional, Dict, Any, Tuple, List
import matplotlib.pyplot as plt
import io
import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import json


try:
    if platform.system() == "Windows":
        import wmi
    else:
        wmi = None
except ImportError:
    wmi = None


PLUGIN_DIR = Path(__file__).parent
CACHE_FILE = PLUGIN_DIR / "layout_cache.json"


def _create_default_avatar(size: int) -> Image.Image:
    img = Image.new('RGBA', (size, size), (100, 100, 100, 255))
    draw = ImageDraw.Draw(img)
    try:
        font_path = '/usr/share/fonts/truetype/wqy/wqy-zenhei.tc' if platform.system() == 'Linux' else 'SimHei.ttf'
        font = ImageFont.truetype(font_path, int(size * 0.4))
    except IOError:
        font = ImageFont.load_default()
    
    text = "A"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2], bbox[3]
    draw.text(((size - text_w) / 2, (size - text_h) / 2 - int(size * 0.05)), 
              text, font=font, fill=(255, 255, 255, 255))
    return img

@register("VisiStat", "Rentz", "可视化监控插件", "1.0", "https://github.com/yanfd/astrbot_plugin_server") 
class ServerMonitor(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self._monitor_task: Optional[asyncio.Task] = None

        self.main_title = self.config.get('main_title', "服务器运行状态")
        self.system_info=self.config.get('custom_name', "")

        self.bg_image_path = self.config.get('background_config', {}).get('image_path', '')
        self.blur_radius = self.config.get('background_config', {}).get('blur_radius', 10)

        self.content_font_path = self.config.get('font_config', {}).get('content_font_path', '')

        self.background_color = self.config.get('color_config', {}).get('background', '#ffffff')
        self.bing_dark = self.config.get('color_config', {}).get('bing_dark', '#4c51bf')
        self.bing_light = self.config.get('color_config', {}).get('bing_light', '#e2e8f0')
        self.font_color = self.config.get('color_config', {}).get('font_color', '#1a202c') 
        self.title_font_color = self.config.get('color_config', {}).get('title_font_color', '#1a202c')

        sensor_cfg = self.config.get('sensor_config', {})
        self.monitor_cpu_temp = sensor_cfg.get('monitor_cpu_temp', True)
        self.monitor_gpu_temp = sensor_cfg.get('monitor_gpu_temp', True)
        self.monitor_bat_temp = sensor_cfg.get('monitor_bat_temp', False)
        self.monitor_battery_status = sensor_cfg.get('monitor_battery_status', True)
        self.temp_unit = sensor_cfg.get('temp_unit', 'C')
        self.show_temp_abbr = sensor_cfg.get('show_temp_abbr', True)

        self.fixed_user_name = self.config.get('user_config', {}).get('fixed_user_name', 'AstroBot 用户')
        self.fixed_avatar_path = self.config.get('user_config', {}).get('fixed_avatar_path', '')

        self.blurred_bg_path: Optional[Path] = None
        self.is_horizontal: bool = False
        
        layout_cfg = self.config.get('layout_config', {})
        self.v_scale_factor = layout_cfg.get('vertical_scale', 1.0)
        self.h_scale_factor = layout_cfg.get('horizontal_scale', 1.0)
        
        self.default_font = self._load_font('', 16) 
        
        self._setup_caching()

    def _setup_caching(self):
        CARD_WIDTH, CARD_HEIGHT = 900, 350
        bg_img = None

        if self.bg_image_path:
            try:
                bg_path = PLUGIN_DIR / self.bg_image_path
                bg_img = Image.open(str(bg_path)).convert("RGBA")
                CARD_WIDTH, CARD_HEIGHT = bg_img.size
            except Exception:
                pass
        
        if CARD_HEIGHT > 0:
            aspect_ratio = CARD_WIDTH / CARD_HEIGHT
            self.is_horizontal = aspect_ratio > 1.2 
        
        if self.blur_radius <= 0 or not self.bg_image_path:
            return

        cache_data = {}
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            except Exception:
                pass

        original_bg_name = self.bg_image_path
        
        cached_blur_path = cache_data.get('blurred_bg_path')
        cached_blur_source = cache_data.get('source_image')
        cached_blur_radius = cache_data.get('blur_radius')

        if (cached_blur_path and 
            (PLUGIN_DIR / cached_blur_path).exists() and
            cached_blur_source == original_bg_name and
            cached_blur_radius == self.blur_radius):
            
            self.blurred_bg_path = PLUGIN_DIR / cached_blur_path
        
        elif bg_img:
            try:
                blurred_img = bg_img.convert("RGB").filter(ImageFilter.GaussianBlur(self.blur_radius)).convert("RGBA")
                
                bg_stem = Path(original_bg_name).stem
                new_blur_filename = f"cached_blurred_{bg_stem}_{self.blur_radius}.png"
                self.blurred_bg_path = PLUGIN_DIR / new_blur_filename
                blurred_img.save(str(self.blurred_bg_path))
                
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        'blurred_bg_path': new_blur_filename,
                        'source_image': original_bg_name,
                        'blur_radius': self.blur_radius
                    }, f)
            except Exception as e:
                self.blurred_bg_path = None
                self.context.logger.error(f"Background blur caching failed: {e}")

    def _load_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont:
        if font_path:
            try:
                full_path = PLUGIN_DIR / font_path
                return ImageFont.truetype(str(full_path), size)
            except IOError:
                pass
        
        try:
            font_path = '/usr/share/fonts/truetype/wqy/wqy-zenhei.tc' if platform.system() == 'Linux' else 'SimHei.ttf'
            return ImageFont.truetype(font_path, size)
        except IOError:
            return ImageFont.load_default()

    def _load_avatar(self, size: int) -> Image.Image:
        if self.fixed_avatar_path:
            try:
                avatar_path = PLUGIN_DIR / self.fixed_avatar_path
                img = Image.open(str(avatar_path)).convert("RGBA")
                return img
            except Exception:
                pass
        
        return _create_default_avatar(size)

    def _get_uptime(self) -> str:
        boot_time = psutil.boot_time()
        now = datetime.datetime.now().timestamp()
        uptime_seconds = int(now - boot_time)
        
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_units = []
        if days > 0:
            time_units.append(f"{days}天")
        if hours > 0:
            time_units.append(f"{hours}小时")
        if minutes > 0:
            time_units.append(f"{minutes}分")
        
        return " ".join(time_units)


    def _make_circular(self, img: Image.Image) -> Image.Image:
        size = img.size[0]
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        
        circular_img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
        circular_img.paste(img, (0, 0), mask)
        return circular_img

    def _create_pie_chart(self, value: float, color: str, bg_color: str, size: int) -> Image.Image:
        buffer = io.BytesIO()
        
        plt.figure(figsize=(size/100, size/100), dpi=100) 
        
        sizes = [value, 100 - value]
        colors = [color, bg_color]
        

        try:
            font = self._load_font(self.content_font_path, int(size*0.09)).getname()
            plt.rcParams['font.family'] = font[0]
            plt.rcParams['font.sans-serif'] = [font[0]]
            plt.rcParams['axes.unicode_minus'] = False
        except Exception:
            pass 
        
        plt.pie(sizes, colors=colors, startangle=90, wedgeprops={'edgecolor': 'none', 'linewidth': 0})
        plt.axis('equal')
        
        center_text = f"{value:.1f}%"
        
        font_size_pt = size * 0.09 * (72 / 100) 
        plt.text(0, 0, center_text, ha='center', va='center', fontsize=font_size_pt, color='#ffffff', fontweight='bold')
        
        plt.savefig(buffer, format='png', bbox_inches='tight', transparent=True, pad_inches=0)
        buffer.seek(0)
        
        chart_image = Image.open(buffer).convert("RGBA")
        chart_image = chart_image.resize((size, size), Image.Resampling.LANCZOS)
        
        plt.clf()
        plt.close('all')
        return chart_image

    def _get_linux_temp_data(self, temp_unit: str) -> Dict[str, Optional[float]]:
        temp_data = {'cpu_temp': None, 'gpu_temp': None, 'bat_temp': None}
        
        if not hasattr(psutil, "sensors_temperatures"):
            return temp_data

        try:
            fahrenheit = temp_unit.upper() == 'F'
            temps = psutil.sensors_temperatures(fahrenheit=fahrenheit)
        except Exception:
            return temp_data
        
        if self.monitor_cpu_temp:
            cpu_temps = temps.get('coretemp', temps.get('cpu_thermal'))
            if not cpu_temps:
                for name, entries in temps.items():
                    if 'cpu' in name.lower() or 'package' in name.lower():
                        cpu_temps = entries
                        break

            if cpu_temps:
                temp_data['cpu_temp'] = max(e.current for e in cpu_temps if e.current is not None) if cpu_temps else None

        if self.monitor_gpu_temp:
            for name, entries in temps.items():
                if 'gpu' in name.lower() or 'amdgpu' in name.lower() or 'nouveau' in name.lower() or 'nvidia' in name.lower():
                    temp_data['gpu_temp'] = max(e.current for e in entries if e.current is not None) if entries else None
                    break
        
        if self.monitor_bat_temp:
            for name, entries in temps.items():
                if 'battery' in name.lower() and entries:
                    temp_data['bat_temp'] = max(e.current for e in entries if e.current is not None) if entries else None
                    break
                    
        return temp_data

    def _get_windows_temp_via_wmi(self, temp_unit: str) -> Dict[str, Optional[float]]:
        temp_results = {}
        if wmi is None:
            return temp_results

        if self.monitor_cpu_temp:
            try:
                c = wmi.WMI(namespace="root\\wmi")
                temperature_data = c.MSAcpi_ThermalZoneTemperature()
                if temperature_data:
                    temp_k_times_10 = temperature_data[0].CurrentTemperature
                    temp_c = (temp_k_times_10 - 2732) / 10.0
                    if temp_unit.upper() == 'F':
                        temp_results['cpu_temp'] = temp_c * 9/5 + 32
                    else:
                        temp_results['cpu_temp'] = temp_c
            except Exception:
                temp_results['cpu_temp'] = None
        
        return temp_results

    def _get_sensor_data(self) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
        temp_results = {}
        
        if platform.system() == "Linux":
            temp_results = self._get_linux_temp_data(self.temp_unit)
        elif platform.system() == "Windows":
            temp_results = self._get_windows_temp_via_wmi(self.temp_unit)
        else:
            if self.monitor_cpu_temp:
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures(fahrenheit=self.temp_unit.upper() == 'F')
                    cpu_temps = temps.get('coretemp', [])
                    if cpu_temps:
                        temp_results['cpu_temp'] = max(e.current for e in cpu_temps if e.current is not None)
                

        bat = psutil.sensors_battery()
        bat_data = {'percent': None, 'status_text': '电池信息: N/A'}
        
        if self.monitor_battery_status and bat:
            bat_percent = bat.percent
            is_charging = bat.power_plugged
            
            if is_charging:
                status_text = f"电池状态: 充电中 ({bat_percent:.1f}%)"
            else:
                secsleft = bat.secsleft
                if secsleft == psutil.POWER_TIME_UNLIMITED:
                    time_left = "无限"
                elif secsleft == psutil.POWER_TIME_UNKNOWN:
                    time_left = "未知"
                else:
                    minutes, seconds = divmod(int(secsleft), 60)
                    hours, minutes = divmod(minutes, 60)
                    time_left = f"{hours}时{minutes}分"
                
                status_text = f"电池状态: 剩余 {bat_percent:.1f}% ({time_left})"
            
            bat_data = {'percent': bat_percent, 'status_text': status_text}

        return temp_results, bat_data


    def _manual_wrap_text(self, text, font, draw_obj, max_width):
        if not text: return [""]
        lines = []
        words_and_spaces = re.findall(r'[\S\u4e00-\u9fa5]+|\s+', text)
        current_line = ""
        
        for segment in words_and_spaces:
            test_line = (current_line + segment).strip() 
            bbox = draw_obj.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width or not current_line.strip():
                current_line = current_line + segment
            else:
                lines.append(current_line.rstrip()) 
                current_line = segment.lstrip() 
        
        if current_line.strip():
            lines.append(current_line.rstrip())
        
        return lines

    def _format_temp_data(self, temp_results: Dict[str, Optional[float]]) -> List[Tuple[str, str]]:
        temp_data_list = []
        unit = self.temp_unit.upper()
        
        mapping = [
            ('cpu_temp', 'CPU', self.monitor_cpu_temp),
            ('gpu_temp', 'GPU', self.monitor_gpu_temp),
            ('bat_temp', 'BAT', self.monitor_bat_temp),
        ]

        for key, abbr, enabled in mapping:
            if enabled:
                temp_val = temp_results.get(key)
                device_abbr = abbr if self.show_temp_abbr else ""
                
                if temp_val is not None and temp_val > 0.1: 
                    formatted_temp = f"{temp_val:.1f}°{unit}"
                else:
                    formatted_temp = "N/A" 
                    
                temp_data_list.append((f"{device_abbr}: ", formatted_temp))
        
        return temp_data_list


    def _draw_vertical_layout(self, canvas, data, avatar_img, user_name):
        CARD_WIDTH, CARD_HEIGHT = canvas.size
        base_ref = min(CARD_WIDTH, CARD_HEIGHT) 
        SCALE_FACTOR = self.v_scale_factor 
        
        MARGIN_BASE = int(base_ref * 0.05 * SCALE_FACTOR)
        
        TITLE_FONT_SIZE = int(base_ref * 0.08 * SCALE_FACTOR) 
        NAME_FONT_SIZE = int(base_ref * 0.06 * SCALE_FACTOR) 
        CONTENT_FONT_MEDIUM_SIZE = int(base_ref * 0.045 * SCALE_FACTOR) 
        LINE_SPACING = int(base_ref * 0.06 * SCALE_FACTOR)
        
        AVATAR_SIZE = int(base_ref * 0.15 * SCALE_FACTOR) 
        
        SEPARATOR_WIDTH = 2

        main_font = self._load_font(self.content_font_path, TITLE_FONT_SIZE)
        name_font = self._load_font(self.content_font_path, NAME_FONT_SIZE)
        content_font_medium = self._load_font(self.content_font_path, CONTENT_FONT_MEDIUM_SIZE)
        
        draw = ImageDraw.Draw(canvas)
        text_block_fill = self.font_color
        x_pos = MARGIN_BASE
        INFO_MAX_WIDTH = CARD_WIDTH - 2 * MARGIN_BASE


        name_bbox = draw.textbbox((0, 0), user_name, font=name_font)
        name_h = name_bbox[3] - name_bbox[1]
        small_gap = int(base_ref * 0.01 * SCALE_FACTOR)
        main_bbox = draw.textbbox((0, 0), self.main_title, font=main_font)
        main_h = main_bbox[3] - main_bbox[1]
        
        H_text_A = name_h + small_gap + main_h
        H_A = max(AVATAR_SIZE, H_text_A)

        L_B = 0
        
        prefix_sys = "系统信息: "
        prefix_width_sys = draw.textbbox((0, 0), prefix_sys, font=content_font_medium)[2] 
        content_max_width_sys = INFO_MAX_WIDTH - prefix_width_sys 
        system_info_content_lines = self._manual_wrap_text(data['system_info'], content_font_medium, draw, content_max_width_sys)
        L_sys = len(system_info_content_lines)
        L_B += L_sys
        
        temp_data_list = self._format_temp_data(data['temp_results'])
        L_temp = len(temp_data_list)
        L_B += max(1, L_temp) 
        
        L_bat = 1 if self.monitor_battery_status and data['bat_data']['percent'] is not None else 0
        L_B += L_bat
        
        L_fixed = 2 
        L_B += L_fixed
        
        H_B = L_B * LINE_SPACING

        gap_charts = MARGIN_BASE // 2
        CHART_SIZE = (CARD_WIDTH - 2 * MARGIN_BASE - 2 * gap_charts) // 3 
        
        label_font = content_font_medium 

        label_h = draw.textbbox((0, 0), "CPU", font=label_font)[3] 
        label_v_margin = MARGIN_BASE // 4 

        H_C = (2 * LINE_SPACING) + MARGIN_BASE + label_h + label_v_margin + CHART_SIZE

        
        M = MARGIN_BASE 
        

        H_FIXED_GAPS = 5 * M
        
        H_REQUIRED = H_A + H_B + H_C + H_FIXED_GAPS + SEPARATOR_WIDTH
        

        OFFSET_Y = 0
        if CARD_HEIGHT > H_REQUIRED:
            OFFSET_Y = (CARD_HEIGHT - H_REQUIRED) // 2
        

        HEADER_Y_START = OFFSET_Y + M
        
        avatar_img = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
        avatar_img = self._make_circular(avatar_img)
        

        avatar_y_start = HEADER_Y_START + (H_A - AVATAR_SIZE) // 2 
        
        canvas.paste(avatar_img, (x_pos, avatar_y_start), avatar_img)

        text_y_start = HEADER_Y_START + (H_A - H_text_A) // 2 
        
        draw.text((x_pos + AVATAR_SIZE + MARGIN_BASE, text_y_start), user_name, font=name_font, fill=self.title_font_color)
        draw.text((x_pos + AVATAR_SIZE + MARGIN_BASE, text_y_start + name_h + small_gap), self.main_title, font=main_font, fill=self.title_font_color)


        current_y = HEADER_Y_START + H_A + M 
        
        prefix_sys = "系统信息: "
        prefix_width_sys = draw.textbbox((0, 0), prefix_sys, font=content_font_medium)[2] 
        draw.text((x_pos, current_y), prefix_sys + system_info_content_lines[0], font=content_font_medium, fill=text_block_fill)
        current_y += LINE_SPACING
        
        for line in system_info_content_lines[1:]:
            draw.text((x_pos + prefix_width_sys, current_y), line.lstrip(), font=content_font_medium, fill=text_block_fill) 
            current_y += LINE_SPACING

        temp_data_list = self._format_temp_data(data['temp_results'])
        temp_prefix = "系统温度: "
        temp_prefix_width = draw.textbbox((0, 0), temp_prefix, font=content_font_medium)[2]
        temp_start_x = x_pos + temp_prefix_width
        
        if not temp_data_list:
             draw.text((x_pos, current_y), f"{temp_prefix}N/A", font=content_font_medium, fill=text_block_fill)
             current_y += LINE_SPACING
        else:
            first_label, first_value = temp_data_list[0]
            draw.text((x_pos, current_y), temp_prefix + first_label + first_value, 
                      font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING
            
            for label, value in temp_data_list[1:]:
                draw.text((temp_start_x, current_y), label + value, 
                          font=content_font_medium, fill=text_block_fill)
                current_y += LINE_SPACING
        
        if self.monitor_battery_status and data['bat_data']['percent'] is not None:
            draw.text((x_pos, current_y), data['bat_data']['status_text'], font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING

        info_lines_block1_simple = [
            (f"运行时间: {data['uptime']}", content_font_medium),
            (f"当前时间: {data['current_time']}", content_font_medium),
        ]

        for line, font in info_lines_block1_simple:
            draw.text((x_pos, current_y), line, font=font, fill=text_block_fill)
            current_y += LINE_SPACING
        

        SEP_Y = current_y + M + SEPARATOR_WIDTH // 2 
        draw.line([(MARGIN_BASE, SEP_Y), (CARD_WIDTH - MARGIN_BASE, SEP_Y)], fill=self.font_color, width=SEPARATOR_WIDTH)

        current_y = SEP_Y + SEPARATOR_WIDTH // 2 + M 

        traffic_title = f"网络流量:"
        traffic_data = f"↑{data['net_sent']:.2f}MB ↓{data['net_recv']:.2f}MB" 
        
        title_bbox = draw.textbbox((0, 0), traffic_title, font=content_font_medium)
        title_w = title_bbox[2] - title_bbox[0]
        title_x_centered = (CARD_WIDTH - title_w) // 2 
        

        data_bbox = draw.textbbox((0, 0), traffic_data, font=content_font_medium)
        data_w = data_bbox[2] - data_bbox[0]
        data_x_centered = (CARD_WIDTH - data_w) // 2
        
        draw.text((title_x_centered, current_y), traffic_title, font=content_font_medium, fill=text_block_fill)
        current_y += LINE_SPACING
        
        draw.text((data_x_centered, current_y), traffic_data, font=content_font_medium, fill=text_block_fill)
        current_y += LINE_SPACING
        

        current_y += MARGIN_BASE 
        
        charts = [
            ("CPU", data['cpu_percent'], data['cpu_image']),
            ("MEM", data['mem_percent'], data['mem_image']),
            ("DISK", data['disk_percent'], data['disk_image']),
        ]

        gap_charts = MARGIN_BASE // 2
        CHART_SIZE = (CARD_WIDTH - 2 * MARGIN_BASE - 2 * gap_charts) // 3
        

        total_charts_width = len(charts) * CHART_SIZE + (len(charts) - 1) * gap_charts

        remaining_gap_on_sides = CARD_WIDTH - 2 * MARGIN_BASE - total_charts_width 
        start_x = MARGIN_BASE + remaining_gap_on_sides // 2
        

        label_font = content_font_medium 
        label_h = draw.textbbox((0, 0), "CPU", font=label_font)[3] 
        label_v_margin = MARGIN_BASE // 4 
        
        chart_y_start = current_y + label_h + label_v_margin 
        
        label_y = current_y - LINE_SPACING + (LINE_SPACING + label_h + label_v_margin) // 2 
        
        chart_y = chart_y_start
        
        for i, (label, value, chart_img) in enumerate(charts):
            resized_chart_img = chart_img.resize((CHART_SIZE, CHART_SIZE), Image.Resampling.LANCZOS)
            
            chart_x = start_x + i * (CHART_SIZE + gap_charts)
            
            label_bbox = draw.textbbox((0, 0), label, font=label_font)
            label_w = label_bbox[2]

            label_x = chart_x + (CHART_SIZE - label_w) // 2
            
            draw.text((label_x, label_y), label, font=label_font, fill=self.font_color)
            
            canvas.paste(resized_chart_img, (chart_x, int(chart_y)), resized_chart_img)
            
        return canvas


    def _draw_horizontal_layout(self, canvas, data, avatar_img, user_name):
        CARD_WIDTH, CARD_HEIGHT = canvas.size
        base_ref = CARD_HEIGHT 
        
        aspect_ratio = CARD_WIDTH / CARD_HEIGHT
        max_scale = 1.5 
        min_ratio = 1.2 
        
        if aspect_ratio > min_ratio:
            clamped_ratio = min(3.0, max(min_ratio, aspect_ratio))
            dynamic_scale = 1.0 + (max_scale - 1.0) * ((clamped_ratio - min_ratio) / (3.0 - min_ratio) if 3.0 > min_ratio else 0)
        else:
            dynamic_scale = 1.0
            
        SCALE_FACTOR = dynamic_scale * self.h_scale_factor 
        
        MARGIN = int(base_ref * 0.04 * SCALE_FACTOR)
        
        H_GAP = MARGIN 
        MIDDLE_GAP = int(H_GAP * 0.75) 
        
        TITLE_FONT_SIZE = int(base_ref * 0.06 * SCALE_FACTOR)
        NAME_FONT_SIZE = int(base_ref * 0.05 * SCALE_FACTOR)
        CONTENT_FONT_LARGE_SIZE = int(base_ref * 0.04 * SCALE_FACTOR)
        CONTENT_FONT_MEDIUM_SIZE = int(base_ref * 0.035 * SCALE_FACTOR)
        LINE_SPACING = int(base_ref * 0.045 * SCALE_FACTOR) 
        
        AVATAR_SIZE = int(base_ref * 0.12 * SCALE_FACTOR)
        AVATAR_X = H_GAP 

        main_font = self._load_font(self.content_font_path, TITLE_FONT_SIZE)
        name_font = self._load_font(self.content_font_path, NAME_FONT_SIZE)
        content_font_large = self._load_font(self.content_font_path, CONTENT_FONT_LARGE_SIZE)
        content_font_medium = self._load_font(self.content_font_path, CONTENT_FONT_MEDIUM_SIZE)

        draw = ImageDraw.Draw(canvas)
        text_block_fill = self.font_color

        
        num_charts = 3
        
        BASE_GAP_PIXELS = 15
        gap = BASE_GAP_PIXELS 

        LABEL_CHART_GAP = MARGIN // 3
        
        label_font = content_font_medium 
        label_h = draw.textbbox((0, 0), "MEM", font=label_font)[3] - draw.textbbox((0, 0), "MEM", font=label_font)[1]
        LABEL_TOP_PADDING = MARGIN // 4 
        
        total_card_vertical_space = CARD_HEIGHT - 2 * MARGIN

        single_chart_vertical_overhead = label_h + LABEL_TOP_PADDING + LABEL_CHART_GAP
        total_vertical_spacing = num_charts * single_chart_vertical_overhead + (num_charts - 1) * gap

        CHART_SIZE_Vertical = (total_card_vertical_space - total_vertical_spacing) // num_charts
        
        MIN_CHART_SIZE = 100
        CHART_SIZE = max(MIN_CHART_SIZE, CHART_SIZE_Vertical)
        
        CHART_BLOCK_WIDTH = CHART_SIZE + MARGIN // 2 

        
        CHART_AREA_RIGHT_START_X = CARD_WIDTH - H_GAP - CHART_BLOCK_WIDTH 

        INFO_MAX_WIDTH = CHART_AREA_RIGHT_START_X - AVATAR_X - MIDDLE_GAP 


        x_pos = AVATAR_X 


        name_h_estimate = draw.textbbox((0, 0), user_name, font=name_font)[3] - draw.textbbox((0, 0), user_name, font=name_font)[1]
        title_h_estimate = draw.textbbox((0, 0), self.main_title, font=main_font)[3] - draw.textbbox((0, 0), self.main_title, font=main_font)[1]
        name_title_gap = int(base_ref * 0.01 * SCALE_FACTOR)
        
        HEADER_TEXT_HEIGHT = name_h_estimate + title_h_estimate + name_title_gap
        HEADER_H = max(AVATAR_SIZE, HEADER_TEXT_HEIGHT) + MARGIN // 2 

        prefix_sys = "系统信息: "
        prefix_width_sys = draw.textbbox((0, 0), prefix_sys, font=content_font_medium)[2] 
        content_max_width_sys = INFO_MAX_WIDTH - prefix_width_sys 
        system_info_content_lines = self._manual_wrap_text(data['system_info'], content_font_medium, draw, content_max_width_sys)
        sys_info_lines_count = len(system_info_content_lines)
        
        temp_data_list = self._format_temp_data(data['temp_results'])
        temp_lines_count = max(1, len(temp_data_list))
        
        simple_lines_count = 4 
        if self.monitor_battery_status and data['bat_data']['percent'] is not None:
             simple_lines_count += 1
        
        total_A_content_lines = sys_info_lines_count + temp_lines_count + simple_lines_count
        total_A_content_height = total_A_content_lines * LINE_SPACING + MARGIN // 2
        
        HEADER_CONTENT_GAP = MARGIN // 2 
        total_A_block_height = HEADER_H + HEADER_CONTENT_GAP + total_A_content_height

        initial_y_offset_A = (total_card_vertical_space - total_A_block_height) // 2 
        A_BLOCK_START_Y = MARGIN + initial_y_offset_A
        
        HEADER_Y_START = A_BLOCK_START_Y
        avatar_y = HEADER_Y_START + (HEADER_H - AVATAR_SIZE) // 2
        avatar_img = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
        avatar_img = self._make_circular(avatar_img)
        canvas.paste(avatar_img, (AVATAR_X, avatar_y), avatar_img)
        
        text_y_start = HEADER_Y_START + (HEADER_H - HEADER_TEXT_HEIGHT) // 2 
        draw.text((AVATAR_X + AVATAR_SIZE + H_GAP, text_y_start), user_name, font=name_font, fill=self.title_font_color)
        draw.text((AVATAR_X + AVATAR_SIZE + H_GAP, text_y_start + name_h_estimate + name_title_gap), self.main_title, font=main_font, fill=self.title_font_color)
        
        current_y = A_BLOCK_START_Y + HEADER_H + HEADER_CONTENT_GAP
        
        draw.text((x_pos, current_y), prefix_sys + system_info_content_lines[0], font=content_font_medium, fill=text_block_fill)
        current_y += LINE_SPACING
        
        for line in system_info_content_lines[1:]:
            draw.text((x_pos + prefix_width_sys, current_y), line.lstrip(), font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING

        temp_prefix = "系统温度: "
        temp_prefix_width = draw.textbbox((0, 0), temp_prefix, font=content_font_medium)[2]
        temp_start_x = x_pos + temp_prefix_width
        
        if not temp_data_list:
            draw.text((x_pos, current_y), f"{temp_prefix}N/A", font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING
        else:
            first_label, first_value = temp_data_list[0]
            draw.text((x_pos, current_y), temp_prefix + first_label + first_value, 
                      font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING
            
            for label, value in temp_data_list[1:]:
                draw.text((temp_start_x, current_y), label + value, 
                          font=content_font_medium, fill=text_block_fill)
                current_y += LINE_SPACING
        
        if self.monitor_battery_status and data['bat_data']['percent'] is not None:
            draw.text((x_pos, current_y), data['bat_data']['status_text'], font=content_font_medium, fill=text_block_fill)
            current_y += LINE_SPACING

        info_lines_block1_simple = [
            (f"运行时间: {data['uptime']}", content_font_medium),
            (f"当前时间: {data['current_time']}", content_font_medium),
        ]

        for line, font in info_lines_block1_simple:
            draw.text((x_pos, current_y), line, font=font, fill=text_block_fill)
            current_y += LINE_SPACING

        current_y += MARGIN // 2

        net_traffic_text = f"网络流量: ↑{data['net_sent']:.2f}MB ↓{data['net_recv']:.2f}MB"
        draw.text((x_pos, current_y), net_traffic_text, font=content_font_medium, fill=text_block_fill)
        current_y += LINE_SPACING

        charts = [
            ("CPU", data['cpu_percent'], data['cpu_image']),
            ("MEM", data['mem_percent'], data['mem_image']),
            ("DISK", data['disk_percent'], data['disk_image']),
        ]
        
        total_B_block_height = num_charts * CHART_SIZE + total_vertical_spacing

        initial_y_offset_B = (total_card_vertical_space - total_B_block_height) // 2 
        current_chart_y = MARGIN + initial_y_offset_B
        
        chart_center_x = CHART_AREA_RIGHT_START_X + CHART_SIZE // 2 

        for label, value, chart_img in charts:

            label_y = current_chart_y + LABEL_TOP_PADDING 
            
            label_text = label 
            label_bbox = draw.textbbox((0, 0), label_text, font=label_font)
            label_w = label_bbox[2] - label_bbox[0]
            label_x = chart_center_x - label_w // 2 
            
            draw.text((label_x, label_y), label_text, font=label_font, fill=self.font_color)

            chart_y = label_y + label_h + LABEL_CHART_GAP 
            chart_x = chart_center_x - CHART_SIZE // 2 

            resized_chart_img = chart_img.resize((CHART_SIZE, CHART_SIZE), Image.Resampling.LANCZOS) 

            canvas.paste(resized_chart_img, (int(chart_x), int(chart_y)), resized_chart_img) 
            
            current_chart_y = chart_y + CHART_SIZE + gap 

        return canvas
    

    def _draw_status_card(self, data: Dict[str, Any], avatar_img: Image.Image, user_name: str) -> Image.Image:
        canvas = None
        
        if self.bg_image_path:
            try:
                if self.blurred_bg_path:
                    canvas = Image.open(str(self.blurred_bg_path)).convert("RGBA")
                else:
                    bg_path = PLUGIN_DIR / self.bg_image_path
                    canvas = Image.open(str(bg_path)).convert("RGBA")
                    
                    if self.blur_radius > 0:
                        canvas = canvas.convert("RGB").filter(ImageFilter.GaussianBlur(self.blur_radius)).convert("RGBA")
                        
            except Exception:
                pass
        
        if canvas is None:
            CARD_WIDTH, CARD_HEIGHT = 900, 350 
            canvas = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), self.background_color).convert("RGBA")

        if self.is_horizontal:
            return self._draw_horizontal_layout(canvas, data, avatar_img, user_name)
        else:
            return self._draw_vertical_layout(canvas, data, avatar_img, user_name)

    @command("状态", alias=["status","info"])
    async def server_status(self, event):
        user_name = self.fixed_user_name
        avatar_img = self._load_avatar(300) 
        
        try:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            mem_percent = mem.percent
            
            disk_percent = disk.percent
            
            cpu_usage = psutil.cpu_percent(interval=0.1)         

            net = psutil.net_io_counters()

            total_bytes_sent = net.bytes_sent
            total_bytes_recv = net.bytes_recv

            total_mb_sent = total_bytes_sent / (1024 * 1024)
            total_mb_recv = total_bytes_recv / (1024 * 1024)

            temp_results, bat_data = self._get_sensor_data()

            chart_size_placeholder = 300 
            cpu_image = self._create_pie_chart(cpu_usage, self.bing_dark, self.bing_light, chart_size_placeholder)
            mem_image = self._create_pie_chart(mem_percent, self.bing_dark, self.bing_light, chart_size_placeholder)
            disk_image = self._create_pie_chart(disk_percent, self.bing_dark, self.bing_light, chart_size_placeholder)


            status_data = {
                'cpu_percent': cpu_usage,
                'mem_percent': mem_percent,
                'disk_percent': disk_percent,
                'cpu_image': cpu_image,
                'mem_image': mem_image,
                'disk_image': disk_image,
                'temp_results': temp_results, 
                'bat_data': bat_data, 
                'system_info': f"{platform.system()} {platform.release()} ({platform.machine()})" if self.system_info == 'default' or not self.system_info else self.system_info,
                'uptime': self._get_uptime(),
                'net_sent': total_mb_sent,
                'net_recv': total_mb_recv,
                'current_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            
            pic = self._draw_status_card(status_data, avatar_img, user_name)
            
            file_path = "status.png"
            pic.save(file_path)
            
            yield event.image_result(file_path)

        except Exception as e:
            import traceback
            error_message = f"⚠️ 状态获取失败: {str(e)}\nTraceback: {traceback.format_exc()}"
            yield event.plain_result(error_message)

    async def terminate(self):
        if self._monitor_task and not self._monitor_task.cancelled():
            self._monitor_task.cancel()
        await super().terminate()