#!/usr/bin/env python3
"""
视界工具箱 - Video Asset Toolkit
本地/云端多维度视频分析工具
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib

class VideoAssetToolkit:
    def __init__(self, config_path=None):
        self.config = self.load_config(config_path)
        self.results_dir = Path(self.config.get("results_dir", "./results"))
        self.results_dir.mkdir(exist_ok=True)
        
    def load_config(self, config_path):
        """加载配置文件"""
        default_config = {
            "local_models": {
                "enabled": True,
                "object_detection": True,
                "scene_description": True,
                "technical_analysis": True
            },
            "cloud_models": {
                "enabled": False,
                "gemini_api_key": "",
                "openai_api_key": ""
            },
            "analysis_dimensions": [
                "objects",
                "scenes", 
                "colors",
                "composition",
                "mood",
                "business_value",
                "technical_quality"
            ],
            "output_formats": ["json", "markdown", "csv"],
            "max_videos_per_batch": 100
        }
        
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except:
                print(f"警告: 无法读取配置文件 {config_path}, 使用默认配置")
                
        return default_config
    
    def analyze_videos(self, video_paths, output_format="all"):
        """分析视频列表"""
        if isinstance(video_paths, (str, Path)):
            video_paths = [video_paths]
            
        results = {}
        for video_path in video_paths:
            video_path = Path(video_path)
            if not video_path.exists():
                print(f"警告: 视频不存在 {video_path}")
                continue
                
            print(f"分析: {video_path.name}")
            result = self.analyze_single_video(video_path)
            
            # 生成唯一ID
            video_hash = self.generate_video_hash(video_path)
            results[video_hash] = {
                "filename": video_path.name,
                "path": str(video_path),
                "hash": video_hash,
                "analysis": result,
                "timestamp": datetime.now().isoformat()
            }
            
        # 保存结果
        self.save_results(results, output_format)
        return results
    
    def generate_video_hash(self, video_path):
        """生成视频哈希（指纹）"""
        try:
            # 使用文件大小和修改时间生成简单哈希
            stat = video_path.stat()
            hash_input = f"{video_path.name}_{stat.st_size}_{stat.st_mtime}"
            return hashlib.md5(hash_input.encode()).hexdigest()[:12]
        except:
            return hashlib.md5(video_path.name.encode()).hexdigest()[:12]
    
    def analyze_single_video(self, video_path):
        """分析单个视频"""
        result = {
            "metadata": self.extract_metadata(video_path),
            "local_analysis": {},
            "cloud_analysis": {},
            "recommendations": []
        }
        
        # 本地分析
        if self.config["local_models"]["enabled"]:
            result["local_analysis"] = self.local_analysis(video_path)
            
        # 云端分析
        if self.config["cloud_models"]["enabled"]:
            result["cloud_analysis"] = self.cloud_analysis(video_path)
            
        # 生成建议
        result["recommendations"] = self.generate_recommendations(result)
        
        return result
    
    def extract_metadata(self, video_path):
        """提取视频元数据"""
        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            metadata = json.loads(output)
            
            # 提取关键信息
            format_info = metadata.get("format", {})
            streams = metadata.get("streams", [])
            
            video_streams = []
            audio_streams = []
            
            for stream in streams:
                if stream.get("codec_type") == "video":
                    video_streams.append({
                        "codec": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "fps": stream.get("r_frame_rate"),
                        "bitrate": stream.get("bit_rate")
                    })
                elif stream.get("codec_type") == "audio":
                    audio_streams.append({
                        "codec": stream.get("codec_name"),
                        "channels": stream.get("channels"),
                        "sample_rate": stream.get("sample_rate")
                    })
            
            return {
                "duration": format_info.get("duration"),
                "size": format_info.get("size"),
                "bitrate": format_info.get("bit_rate"),
                "format": format_info.get("format_name"),
                "video_streams": video_streams,
                "audio_streams": audio_streams,
                "tags": format_info.get("tags", {})
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def local_analysis(self, video_path):
        """本地模型分析"""
        result = {}
        
        # 技术质量分析
        if self.config["local_models"].get("technical_analysis", True):
            result["technical"] = self.technical_analysis(video_path)
            
        # 物体检测（模拟）
        if self.config["local_models"].get("object_detection", True):
            result["objects"] = self.object_detection_simulation(video_path)
            
        # 场景描述（模拟）
        if self.config["local_models"].get("scene_description", True):
            result["scene"] = self.scene_description_simulation(video_path)
            
        return result
    
    def technical_analysis(self, video_path):
        """技术质量分析"""
        try:
            metadata = self.extract_metadata(video_path)
            if "error" in metadata:
                return {"error": metadata["error"]}
                
            video_stream = metadata.get("video_streams", [{}])[0]
            
            # 计算质量评分
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            bitrate = video_stream.get("bitrate", "0")
            
            # 分辨率评分
            if width >= 3840 or height >= 2160:  # 4K
                resolution_score = 0.95
            elif width >= 1920 or height >= 1080:  # 1080p
                resolution_score = 0.85
            elif width >= 1280 or height >= 720:  # 720p
                resolution_score = 0.70
            elif width >= 640 or height >= 480:  # 480p
                resolution_score = 0.50
            else:
                resolution_score = 0.30
                
            # 码率评分
            try:
                bitrate_num = int(bitrate)
                if bitrate_num > 10000000:  # 10 Mbps
                    bitrate_score = 0.95
                elif bitrate_num > 5000000:  # 5 Mbps
                    bitrate_score = 0.85
                elif bitrate_num > 2000000:  # 2 Mbps
                    bitrate_score = 0.70
                elif bitrate_num > 1000000:  # 1 Mbps
                    bitrate_score = 0.50
                else:
                    bitrate_score = 0.30
            except:
                bitrate_score = 0.50
                
            overall_quality = (resolution_score + bitrate_score) / 2
            
            return {
                "resolution": f"{width}x{height}",
                "resolution_score": resolution_score,
                "bitrate": bitrate,
                "bitrate_score": bitrate_score,
                "codec": video_stream.get("codec", "未知"),
                "fps": video_stream.get("fps", "未知"),
                "overall_quality": overall_quality,
                "quality_level": self.get_quality_level(overall_quality)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_quality_level(self, score):
        """获取质量等级"""
        if score >= 0.8:
            return "优秀"
        elif score >= 0.6:
            return "良好"
        elif score >= 0.4:
            return "一般"
        else:
            return "较差"
    
    def object_detection_simulation(self, video_path):
        """物体检测模拟"""
        # 根据文件名猜测内容
        filename = Path(video_path).name.lower()
        
        if "snow" in filename or "powder" in filename:
            objects = ["person", "snow", "mountain", "sky", "tree"]
        elif "ushguli" in filename:
            objects = ["building", "snow", "mountain", "person", "stone"]
        elif "instrument" in filename or "wood" in filename:
            objects = ["instrument", "wood", "pot", "shelf", "room"]
        else:
            objects = ["person", "building", "vehicle", "nature"]
            
        return {
            "detected_objects": objects,
            "confidence": 0.85,
            "method": "模拟物体检测",
            "note": "实际应使用 YOLOv8/COCO 模型"
        }
    
    def scene_description_simulation(self, video_path):
        """场景描述模拟"""
        filename = Path(video_path).name.lower()
        
        if "snow" in filename or "powder" in filename:
            description = "Snowboarder carving through fresh powder on mountain slope"
            mood = "adventurous, energetic, free"
        elif "ushguli" in filename:
            description = "Aerial view of Europe's highest settlement Ushguli in winter"
            mood = "serene, timeless, remote"
        elif "instrument" in filename or "wood" in filename:
            description = "Traditional wooden musical instruments and rustic artifacts"
            mood = "cultural, historical, authentic"
        else:
            description = "Scenic landscape or urban environment"
            mood = "varied"
            
        return {
            "description": description,
            "mood": mood,
            "confidence": 0.78,
            "method": "模拟场景描述",
            "note": "实际应使用 BLIP/CLIP 模型"
        }
    
    def cloud_analysis(self, video_path):
        """云端分析（需要API密钥）"""
        if not self.config["cloud_models"]["enabled"]:
            return {"enabled": False, "message": "云端分析未启用"}
            
        # 这里应该调用真实的API
        return {
            "enabled": True,
            "status": "需要配置API密钥",
            "gemini_api_key": bool(self.config["cloud_models"].get("gemini_api_key")),
            "openai_api_key": bool(self.config["cloud_models"].get("openai_api_key")),
            "note": "配置API密钥后可使用Gemini Vision/OpenAI进行深度分析"
        }
    
    def generate_recommendations(self, analysis_result):
        """生成建议"""
        recommendations = []
        
        # 技术质量建议
        technical = analysis_result.get("local_analysis", {}).get("technical", {})
        if technical and "overall_quality" in technical:
            quality = technical["overall_quality"]
            if quality < 0.5:
                recommendations.append({
                    "type": "technical",
                    "priority": "high",
                    "message": "视频质量较低，建议使用更高分辨率和码率拍摄",
                    "action": "检查相机设置，使用专业模式"
                })
            elif quality < 0.7:
                recommendations.append({
                    "type": "technical", 
                    "priority": "medium",
                    "message": "视频质量一般，可优化拍摄参数",
                    "action": "调整曝光和稳定器设置"
                })
        
        # 内容建议
        scene = analysis_result.get("local_analysis", {}).get("scene", {})
        if scene and "description" in scene:
            desc = scene["description"].lower()
            if "snow" in desc or "mountain" in desc:
                recommendations.append({
                    "type": "content",
                    "priority": "medium",
                    "message": "适合旅行/冒险类内容",
                    "action": "可制作滑雪教程或旅行vlog"
                })
            elif "instrument" in desc or "cultural" in desc:
                recommendations.append({
                    "type": "content",
                    "priority": "medium",
                    "message": "适合文化/教育类内容",
                    "action": "可制作文化遗产介绍视频"
                })
        
        return recommendations
    
    def save_results(self, results, output_format="all"):
        """保存分析结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"video_analysis_{timestamp}"
        
        formats = []
        if output_format == "all":
            formats = ["json", "markdown", "csv"]
        elif isinstance(output_format, str):
            formats = [output_format]
        else:
            formats = output_format
            
        saved_files = []
        
        # JSON格式
        if "json" in formats:
            json_file = self.results_dir / f"{base_name}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            saved_files.append(str(json_file))
            
        # Markdown格式
        if "markdown" in formats:
            md_file = self.results_dir / f"{base_name}.md"
            md_content = self.generate_markdown_report(results)
            md_file.write_text(md_content, encoding='utf-8')
            saved_files.append(str(md_file))
            
        # CSV格式（简化）
        if "csv" in formats:
            csv_file = self.results_dir / f"{base_name}.csv"
            csv_content = self.generate_csv_report(results)
            csv_file.write_text(csv_content, encoding='utf-8')
            saved_files.append(str(csv_file))
            
        print(f"\n分析结果已保存到:")
        for file in saved_files:
            print(f"  - {file}")
            
        return saved_files
    
    def generate_markdown_report(self, results):
        """生成Markdown报告"""
        lines = []
        lines.append("# 视频资产分析报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"分析视频数量: {len(results)}")
        lines.append("")
        
        for video_id, data in results.items():
            lines.append(f"## {data['filename']}")
            lines.append(f"**文件哈希**: {video_id}")
            lines.append(f"**分析时间**: {data['timestamp']}")
            lines.append("")
            
            # 元数据
            metadata = data['analysis'].get('metadata', {})
            lines.append("### 元数据")
            lines.append(f"- 时长: {metadata.get('duration', '未知')}秒")
            lines.append(f"- 大小: {metadata.get('size', '未知')}字节")
            lines.append(f"- 格式: {metadata.get('format', '未知')}")
            
            # 技术分析
            technical = data['analysis'].get('local_analysis', {}).get('technical', {})
            if technical:
                lines.append("### 技术质量")
                lines.append(f"- 分辨率: {technical.get('resolution', '未知')}")
                lines.append(f"- 质量评分: {technical.get('overall_quality', 0):.2f} ({technical.get('quality_level', '未知')})")
                lines.append(f"- 编码: {technical.get('codec', '未知')}")
            
            # 物体检测
            objects = data['analysis'].get('local_analysis', {}).get('objects', {})
            if objects:
                lines.append("### 物体识别")
                lines.append(f"- 检测物体: {', '.join(objects.get('detected_objects', []))}")
                lines.append(f"- 置信度: {objects.get('confidence', 0):.2f}")
            
            # 场景描述
            scene = data['analysis'].get('local_analysis', {}).get('scene', {})
            if scene:
                lines.append("### 场景描述")
                lines.append(f"- 描述: {scene.get('description', '无')}")
                lines.append(f"- 情绪: {scene.get('mood', '无')}")
            
            # 建议
            recommendations = data['analysis'].get('recommendations', [])
            if recommendations:
                lines.append("### 优化建议")
                for rec in recommendations:
                    lines.append(f"- **{rec.get('priority', '').upper()}**: {rec.get('message', '')}")
                    lines.append(f"  → 操作: {rec.get('action', '')}")
            
            lines.append("")
            lines.append("---")
            lines.append("")
            
        return "\n".join(lines)
    
    def generate_csv_report(self, results):
        """生成CSV报告（简化版）"""
        lines = []
        # 表头
        lines.append("filename,hash,duration,resolution,quality_score,detected_objects,scene_description,recommendations")
        
        for video_id, data in results.items():
            filename = data['filename']
            
            # 元数据
            metadata = data['analysis'].get('metadata', {})
            duration = metadata.get('duration', '')
            
            # 技术信息
            technical = data['analysis'].get('local_analysis', {}).get('technical', {})
            resolution = technical.get('resolution', '')
            quality_score = technical.get('overall_quality', '')
            
            # 物体
            objects = data['analysis'].get('local_analysis', {}).get('objects', {})
            detected_objects = ','.join(objects.get('detected_objects', [])) if objects else ''
            
            # 场景
            scene = data['analysis'].get('local_analysis', {}).get('scene', {})
            scene_description = scene.get('description', '').replace(',', ';') if scene else ''
            
            # 建议
            recommendations = data['analysis'].get('recommendations', [])
            rec_text = '|'.join([r.get('message', '').replace(',', ';') for r in recommendations])
            
            # 构建CSV行
            line = f'"{filename}","{video_id}","{duration}","{resolution}","{quality_score}","{detected_objects}","{scene_description}","{rec_text}"'
            lines.append(line)
            
        return "\n".join(lines)
