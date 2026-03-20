#!/usr/bin/env python3
"""
增强版视频分析：结合技术、内容、视角、情感多维度
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib

class EnhancedVideoAnalyzer:
    def __init__(self):
        self.analysis_dimensions = {
            "technical": ["resolution", "framerate", "codec", "bitrate", "duration"],
            "content": ["objects", "scene", "action", "perspective", "shot_type"],
            "emotional": ["mood", "energy", "aesthetic"],
            "business": ["quality", "usage", "audience", "value"]
        }
    
    def analyze_video(self, video_path):
        """综合分析视频"""
        video_path = Path(video_path)
        
        result = {
            "basic_info": self._get_basic_info(video_path),
            "technical_analysis": self._analyze_technical(video_path),
            "content_analysis": self._analyze_content(video_path),
            "emotional_analysis": self._analyze_emotional(video_path),
            "business_analysis": self._analyze_business(video_path),
            "search_index": self._create_search_index(video_path)
        }
        
        return result
    
    def _get_basic_info(self, video_path):
        """获取基础信息"""
        stat_info = video_path.stat()
        
        return {
            "filename": video_path.name,
            "filepath": str(video_path),
            "size_bytes": stat_info.st_size,
            "size_human": f"{stat_info.st_size / 1024 / 1024:.2f} MB",
            "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "file_hash": hashlib.sha256(
                f"{video_path.name}_{stat_info.st_size}_{stat_info.st_mtime}".encode()
            ).hexdigest()[:16]
        }
    
    def _analyze_technical(self, video_path):
        """技术分析"""
        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = json.loads(output)
            
            # 提取视频流信息
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if video_stream:
                width = video_stream.get("width", 0)
                height = video_stream.get("height", 0)
                
                # 质量评分
                quality_score = self._calculate_quality_score(width, height)
                
                return {
                    "resolution": f"{width}x{height}",
                    "width": width,
                    "height": height,
                    "codec": video_stream.get("codec_name", "unknown"),
                    "framerate": video_stream.get("r_frame_rate", "unknown"),
                    "bitrate": data.get("format", {}).get("bit_rate", "unknown"),
                    "duration": data.get("format", {}).get("duration", "unknown"),
                    "quality_score": quality_score,
                    "quality_level": self._get_quality_level(quality_score)
                }
        except Exception as e:
            return {"error": str(e)}
        
        return {"error": "无法分析技术信息"}
    
    def _analyze_content(self, video_path):
        """内容分析（基于文件名和简单推断）"""
        filename = video_path.name.lower()
        
        # 推断拍摄视角
        perspective = self._infer_perspective(filename)
        
        # 推断动作类型
        action = self._infer_action(filename)
        
        # 推断场景类型
        scene = self._infer_scene(filename)
        
        # 推断镜头类型
        shot_type = self._infer_shot_type(filename)
        
        # 物体识别（模拟）
        objects = self._infer_objects(filename)
        
        return {
            "perspective": perspective,
            "action": action,
            "scene": scene,
            "shot_type": shot_type,
            "objects": objects,
            "description": self._generate_description(perspective, action, scene)
        }
    
    def _analyze_emotional(self, video_path):
        """情感氛围分析（基于内容推断）"""
        content = self._analyze_content(video_path)
        
        # 基于场景和动作推断情感
        mood = self._infer_mood(content["scene"], content["action"])
        energy = self._infer_energy(content["action"])
        aesthetic = self._infer_aesthetic(content["scene"])
        
        return {
            "mood": mood,
            "energy": energy,
            "aesthetic": aesthetic,
            "emotional_tags": self._get_emotional_tags(mood, energy, aesthetic)
        }
    
    def _analyze_business(self, video_path):
        """业务价值分析"""
        technical = self._analyze_technical(video_path)
        content = self._analyze_content(video_path)
        emotional = self._analyze_emotional(video_path)
        
        quality = technical.get("quality_level", "unknown")
        usage = self._suggest_usage(content, emotional)
        audience = self._suggest_audience(content, emotional)
        value = self._estimate_value(quality, usage)
        
        return {
            "quality_tier": quality,
            "suggested_usage": usage,
            "target_audience": audience,
            "business_value": value,
            "recommendations": self._generate_recommendations(technical, content, emotional)
        }
    
    def _create_search_index(self, video_path):
        """创建搜索索引"""
        basic = self._get_basic_info(video_path)
        technical = self._analyze_technical(video_path)
        content = self._analyze_content(video_path)
        emotional = self._analyze_emotional(video_path)
        business = self._analyze_business(video_path)
        
        # 收集所有标签
        tags = []
        
        # 技术标签
        tags.append(f"res_{technical.get('resolution', 'unknown')}")
        tags.append(f"quality_{technical.get('quality_level', 'unknown')}")
        tags.append(f"codec_{technical.get('codec', 'unknown')}")
        
        # 内容标签
        tags.append(content["perspective"])
        tags.append(content["action"])
        tags.append(content["scene"])
        tags.append(content["shot_type"])
        tags.extend(content["objects"])
        
        # 情感标签
        tags.extend(emotional["emotional_tags"])
        
        # 业务标签
        tags.extend(business["suggested_usage"])
        tags.append(f"tier_{business['quality_tier']}")
        
        # 去重和清理
        tags = [tag for tag in tags if tag and tag != "unknown"]
        tags = list(set(tags))
        
        return {
            "video_id": basic["file_hash"],
            "filename": basic["filename"],
            "tags": sorted(tags),
            "search_fields": {
                "technical": {
                    "resolution": technical.get("resolution"),
                    "quality": technical.get("quality_level"),
                    "duration": technical.get("duration")
                },
                "content": {
                    "perspective": content["perspective"],
                    "action": content["action"],
                    "scene": content["scene"]
                },
                "emotional": emotional["emotional_tags"],
                "business": business["suggested_usage"]
            },
            "preview": {
                "thumbnail": f"thumb_{basic['file_hash']}.jpg",
                "duration": technical.get("duration"),
                "resolution": technical.get("resolution")
            }
        }
    
    # 辅助方法
    def _calculate_quality_score(self, width, height):
        """计算质量评分"""
        if width >= 3840 or height >= 2160:
            return 0.95  # 4K
        elif width >= 1920 or height >= 1080:
            return 0.85  # 1080p
        elif width >= 1280 or height >= 720:
            return 0.70  # 720p
        else:
            return 0.50  # 低于720p
    
    def _get_quality_level(self, score):
        """获取质量等级"""
        if score >= 0.85:
            return "high"
        elif score >= 0.70:
            return "medium"
        else:
            return "low"
    
    def _infer_perspective(self, filename):
        """推断拍摄视角"""
        if "pov" in filename or "first" in filename or "第一人称" in filename:
            return "first_person"
        elif "aerial" in filename or "drone" in filename or "航拍" in filename:
            return "aerial"
        elif "handheld" in filename or "手持" in filename:
            return "handheld"
        elif "static" in filename or "tripod" in filename or "固定" in filename:
            return "static"
        else:
            return "unknown"
    
    def _infer_action(self, filename):
        """推断动作类型"""
        if "ski" in filename or "snowboard" in filename or "滑雪" in filename:
            return "skiing"
        elif "hike" in filename or "walk" in filename or "徒步" in filename:
            return "hiking"
        elif "drive" in filename or "car" in filename or "驾驶" in filename:
            return "driving"
        elif "display" in filename or "show" in filename or "展示" in filename:
            return "display"
        else:
            return "general"
    
    def _infer_scene(self, filename):
        """推断场景类型"""
        if "mountain" in filename or "snow" in filename or "山" in filename or "雪" in filename:
            return "mountain"
        elif "city" in filename or "urban" in filename or "城市" in filename:
            return "city"
        elif "indoor" in filename or "room" in filename or "室内" in filename:
            return "indoor"
        elif "culture" in filename or "traditional" in filename or "文化" in filename:
            return "cultural"
        else:
            return "general"
    
    def _infer_shot_type(self, filename):
        """推断镜头类型"""
        # 基于简单推断
        return "medium_shot"  # 默认中景
    
    def _infer_objects(self, filename):
        """推断物体（模拟）"""
        objects = []
        
        if "ski" in filename or "snow" in filename:
            objects.extend(["person", "snow", "mountain", "tree"])
        elif "mountain" in filename:
            objects.extend(["mountain", "sky", "tree", "cloud"])
        elif "instrument" in filename or "wood" in filename:
            objects.extend(["instrument", "wood", "room", "shelf"])
        
        return objects
    
    def _generate_description(self, perspective, action, scene):
        """生成描述"""
        desc_parts = []
        
        if perspective != "unknown":
            perspective_map = {
                "first_person": "第一人称视角",
                "aerial": "航拍视角",
                "handheld": "手持拍摄",
                "static": "固定机位"
            }
            desc_parts.append(perspective_map.get(perspective, perspective))
        
        if action != "general":
            action_map = {
                "skiing": "滑雪",
                "hiking": "徒步",
                "driving": "驾驶",
                "display": "展示"
            }
            desc_parts.append(action_map.get(action, action))
        
        if scene != "general":
            scene_map = {
                "mountain": "雪山场景",
                "city": "城市景观",
                "indoor": "室内环境",
                "cultural": "文化展示"
            }
            desc_parts.append(scene_map.get(scene, scene))
        
        return " ".join(desc_parts) if desc_parts else "一般视频内容"
    
    def _infer_mood(self, scene, action):
        """推断情感氛围"""
        if action == "skiing":
            return "adventurous"
        elif scene == "mountain":
            return "serene"
        elif scene == "cultural":
            return "cultural"
        else:
            return "neutral"
    
    def _infer_energy(self, action):
        """推断能量水平"""
        if action in ["skiing", "driving"]:
            return "high"
        elif action in ["hiking", "display"]:
            return "medium"
        else:
            return "low"
    
    def _infer_aesthetic(self, scene):
        """推断美学风格"""
        if scene == "mountain":
            return "majestic"
        elif scene == "city":
            return "urban"
        elif scene == "cultural":
            return "authentic"
        else:
            return "general"
    
    def _get_emotional_tags(self, mood, energy, aesthetic):
        """获取情感标签"""
        tags = [mood, f"energy_{energy}", aesthetic]
        return [tag for tag in tags if tag != "neutral" and tag != "general"]
    
    def _suggest_usage(self, content, emotional):
        """建议使用场景"""
        usages = []
        
        # 基于内容
        if content["action"] == "skiing":
            usages.extend(["action_sports", "travel_vlog", "adventure"])
        if content["scene"] == "mountain":
            usages.extend(["landscape", "nature", "travel"])
        if content["scene"] == "cultural":
            usages.extend(["education", "documentary", "culture"])
        
        # 基于情感
        if emotional["mood"] == "adventurous":
            usages.append("exciting_intro")
        if emotional["mood"] == "serene":
            usages.append("calm_background")
        
        return list(set(usages))
    
    def _suggest_audience(self, content, emotional):
        """建议目标受众"""
        audiences = []
        
        if content["action"] == "skiing":
            audiences.extend(["sports_enthusiasts", "adventure_travelers"])
        if content["scene"] == "cultural":
            audiences.extend(["culture_lovers", "educators"])
        if emotional["mood"] == "serene":
            audiences.append("relaxation_seekers")
        
        return list(set(audiences)) if audiences else ["general_audience"]
    
    def _estimate_value(self, quality, usage):
        """估计业务价值"""
        value = 0
        
        # 质量权重
        if quality == "high":
            value += 3
        elif quality == "medium":
            value += 2
        else:
            value += 1
        
        # 使用场景权重
        if "action_sports" in usage or "travel_vlog" in usage:
            value += 2
        if "documentary" in usage or "education" in usage:
            value += 1
        
        return value
    
    def _generate_recommendations(self, technical, content, emotional):
        """生成建议"""
        recommendations = []
        
        # 技术建议
        if technical.get("quality_level") == "low":
            recommendations.append("考虑使用更高分辨率的版本")
        
        # 内容建议
        if content["perspective"] == "first_person":
            recommendations.append("适合制作沉浸式体验内容")
        if content["scene"] == "mountain" and emotional["mood"] == "serene":
            recommendations.append("适合作为冥想或放松视频的背景")
        
        # 业务建议
        if "action_sports" in self._suggest_usage(content, emotional):
            recommendations.append("可用于运动品牌合作内容")
        
        return recommendations

def analyze_videos_in_directory(directory="."):
    """分析目录中的所有视频"""
    analyzer = EnhancedVideoAnalyzer()
    video_dir = Path(directory)
    
    # 查找视频文件
    video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"]
    video_files = []
    for ext in video_extensions:
        video_files.extend(video_dir.glob(f"*{ext}"))
        video_files.extend(video_dir.glob(f"*{ext.upper()}"))
    
    print(f"找到 {len(video_files)} 个视频文件")
    print("=" * 80)
    
    all_results = {}
    
    for video_file in video_files:
        print(f"分析: {video_file.name}")
        
        try:
            result = analyzer.analyze_video(video_file)
            all_results[result["basic_info"]["file_hash"]] = result
            
            # 显示摘要
            idx = result["search_index"]
            print(f"  ID: {idx['video_id']}")
            print(f"  视角: {result['content_analysis']['perspective']}")
            print(f"  动作: {result['content_analysis']['action']}")
            print(f"  场景: {result['content_analysis']['scene']}")
            print(f"  情感: {result['emotional_analysis']['mood']}")
            print(f"  质量: {result['technical_analysis']['quality_level']}")
            print(f"  标签: {', '.join(idx['tags'][:5])}")
            print()
            
        except Exception as e:
            print(f"  错误: {e}")
            print()
    
    # 保存结果
    output_file = "enhanced_analysis_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_videos": len(all_results),
            "results": all_results
        }, f, ensure_ascii=False, indent=2)
    
    print("=" * 80)
    print(f"分析完成！结果已保存到: {output_file}")
    
    # 统计信息
    all_tags = []
    for result in all_results.values():
        all_tags.extend(result["search_index"]["tags"])
    
    unique_tags = set(all_tags)
    print(f"生成标签总数: {len(all_tags)}")
    print(f"唯一标签数: {len(unique_tags)}")
    print(f"热门标签: {sorted(list(unique_tags))[:15]}")
    
    return all_results

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "."
    
    analyze_videos_in_directory(directory)

if __name__ == "__main__":
    main()