#!/usr/bin/env python3
"""
VideoEditer - 剧本自适应重写引擎
当素材匹配度不足时，自动调整剧本而非强行匹配
"""

import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class MaterialMatch:
    """素材匹配结果"""
    video_id: str
    score: float
    reasons: List[str]
    data: Dict
    
    @property
    def is_good_match(self) -> bool:
        return self.score >= 7.0
    
    @property
    def is_acceptable(self) -> bool:
        return self.score >= 4.0


@dataclass
class RewriteSuggestion:
    """重写建议"""
    original_text: str
    suggested_text: str
    change_reason: str
    confidence: float


class AdaptiveRewriter:
    """
    自适应剧本重写器
    
    触发条件：
    - similarity_score < 0.6（素材不匹配）
    - 素材缺失（找不到对应场景）
    - 时长不足（脚本需要 10s，素材只有 5s）
    """
    
    def __init__(self, similarity_threshold: float = 0.6):
        self.similarity_threshold = similarity_threshold
        
    def analyze_material_fit(
        self,
        script_segment: Dict,
        matched_materials: List[MaterialMatch]
    ) -> Tuple[bool, str, List[RewriteSuggestion]]:
        """
        分析素材匹配度，决定是否需要重写
        
        Returns:
            (是否需要重写, 原因, 建议列表)
        """
        if not matched_materials:
            return True, "未找到匹配素材", self._generate_no_material_suggestions(script_segment)
        
        best_match = matched_materials[0]
        
        # 匹配度足够，不需要重写
        if best_match.score >= 7.0:
            return False, "匹配度良好", []
        
        # 匹配度不足，需要重写
        if best_match.score < 4.0:
            return True, "匹配度低", self._generate_low_match_suggestions(
                script_segment, best_match
            )
        
        # 匹配度一般，可以优化
        return True, "匹配度一般，建议优化", self._generate_optimization_suggestions(
            script_segment, best_match
        )
    
    def _generate_no_material_suggestions(
        self,
        script_segment: Dict
    ) -> List[RewriteSuggestion]:
        """无匹配素材时的建议"""
        suggestions = []
        
        cn_text = script_segment.get("cn_text", "")
        
        # 建议1：跳过此段落
        suggestions.append(RewriteSuggestion(
            original_text=cn_text,
            suggested_text="[跳过此段落]",
            change_reason="未找到对应素材，建议删除此段落或补充拍摄",
            confidence=0.9
        ))
        
        # 建议2：使用通用描述
        generic_alternatives = self._generate_generic_alternatives(cn_text)
        for alt in generic_alternatives:
            suggestions.append(RewriteSuggestion(
                original_text=cn_text,
                suggested_text=alt,
                change_reason="使用更通用的描述，可能匹配到现有素材",
                confidence=0.6
            ))
        
        return suggestions
    
    def _generate_low_match_suggestions(
        self,
        script_segment: Dict,
        best_match: MaterialMatch
    ) -> List[RewriteSuggestion]:
        """匹配度低时的建议"""
        suggestions = []
        
        cn_text = script_segment.get("cn_text", "")
        
        # 获取匹配到的素材特征
        content = best_match.data.get("content_summary", {})
        available_objects = content.get("objects", [])
        available_mood = content.get("mood", "")
        
        # 建议：调整描述以匹配现有素材
        adjusted_text = self._adjust_text_to_material(
            cn_text, available_objects, available_mood
        )
        
        suggestions.append(RewriteSuggestion(
            original_text=cn_text,
            suggested_text=adjusted_text,
            change_reason=f"根据可用素材调整（匹配度{best_match.score:.1f}）：现有素材包含 {', '.join(available_objects[:3])}",
            confidence=0.7
        ))
        
        return suggestions
    
    def _generate_optimization_suggestions(
        self,
        script_segment: Dict,
        best_match: MaterialMatch
    ) -> List[RewriteSuggestion]:
        """匹配度一般时的优化建议"""
        suggestions = []
        
        cn_text = script_segment.get("cn_text", "")
        
        # 轻微调整文案，增强匹配度
        optimized = self._optimize_text(cn_text, best_match.reasons)
        
        if optimized != cn_text:
            suggestions.append(RewriteSuggestion(
                original_text=cn_text,
                suggested_text=optimized,
                change_reason=f"优化措辞以更好地匹配素材（匹配度{best_match.score:.1f}）",
                confidence=0.8
            ))
        
        return suggestions
    
    def _generate_generic_alternatives(self, original_text: str) -> List[str]:
        """生成通用替代文案"""
        alternatives = []
        
        # 通用旅游 vlog 过渡文案
        generic_phrases = [
            "继续前行，探索未知的风景",
            "旅途中的每一刻都值得铭记",
            "风景在变，心情在变",
            "这一路的风景，都是最好的安排"
        ]
        
        # 根据原文本关键词选择最接近的
        if "海" in original_text or "沙滩" in original_text:
            alternatives.append("海边的风景总是让人心旷神怡")
        if "山" in original_text or "峰" in original_text:
            alternatives.append("站在高处，感受大自然的壮阔")
        if "城市" in original_text or "街" in original_text:
            alternatives.append("城市的每一个角落都有故事")
        
        # 如果没有特定匹配，使用通用文案
        if not alternatives:
            alternatives = generic_phrases[:2]
        
        return alternatives
    
    def _adjust_text_to_material(
        self,
        original_text: str,
        available_objects: List[str],
        available_mood: str
    ) -> str:
        """根据素材特征调整文本"""
        
        # 提取关键词映射
        object_keywords = {
            "海滩": ["海", "沙滩", "海浪", "海岸"],
            "山": ["山", "峰", "山脉", "登山"],
            "建筑": ["建筑", "房子", "楼房", "古迹"],
            "人物": ["我", "人", "游客", "当地人"]
        }
        
        # 检查原文本中的关键词是否在可用素材中
        adjusted = original_text
        
        for obj, keywords in object_keywords.items():
            if obj in available_objects:
                continue  # 素材中有这个物体，不需要调整
            
            # 素材中没有，但原文本提到了，需要替换
            for keyword in keywords:
                if keyword in adjusted:
                    # 替换为通用描述
                    adjusted = adjusted.replace(keyword, "风景")
                    break
        
        return adjusted
    
    def _optimize_text(self, original_text: str, match_reasons: List[str]) -> str:
        """根据匹配原因优化文本"""
        optimized = original_text
        
        # 根据匹配原因调整
        for reason in match_reasons:
            if "标签匹配" in reason:
                # 标签匹配但描述不匹配，可以增强描述
                tag = reason.split(":")[-1].strip()
                if tag not in optimized:
                    optimized = f"{optimized}，{tag}的景色令人难忘"
                    break
        
        return optimized
    
    def rewrite_script(
        self,
        script: Dict,
        materials_index: Dict,
        search_func=None
    ) -> Tuple[Dict, List[Dict]]:
        """
        重写整个剧本
        
        Args:
            script: 原始剧本
            materials_index: 素材索引
            search_func: 素材搜索函数（外部传入）
        
        Returns:
            (重写后的剧本, 修改记录列表)
        """
        rewritten = json.loads(json.dumps(script))  # 深拷贝
        changes = []
        
        for i, clip in enumerate(rewritten.get("clips", [])):
            # 获取此片段的字幕
            subtitle = None
            if i < len(rewritten.get("subtitles", [])):
                subtitle = rewritten["subtitles"][i]
            
            # 搜索匹配素材
            if search_func:
                matched = search_func(clip, subtitle, materials_index)
            else:
                matched = self._mock_search(clip, subtitle, materials_index)
            
            # 分析是否需要重写
            needs_rewrite, reason, suggestions = self.analyze_material_fit(
                subtitle or clip, matched
            )
            
            if needs_rewrite and suggestions:
                # 应用第一个建议（置信度最高的）
                best_suggestion = max(suggestions, key=lambda x: x.confidence)
                
                if subtitle:
                    old_text = subtitle.get("cn_text", "")
                    subtitle["cn_text"] = best_suggestion.suggested_text
                    subtitle["_rewritten"] = True
                    subtitle["_rewrite_reason"] = best_suggestion.change_reason
                
                changes.append({
                    "clip_index": i,
                    "original": best_suggestion.original_text,
                    "rewritten": best_suggestion.suggested_text,
                    "reason": best_suggestion.change_reason,
                    "confidence": best_suggestion.confidence
                })
        
        return rewritten, changes
    
    def _mock_search(
        self,
        clip: Dict,
        subtitle: Optional[Dict],
        materials_index: Dict
    ) -> List[MaterialMatch]:
        """
        模拟素材搜索（实际应调用 manage-videos 的搜索功能）
        """
        # 简单的关键词匹配模拟
        query = ""
        if subtitle:
            query = subtitle.get("cn_text", "") + " " + subtitle.get("en_text", "")
        else:
            query = clip.get("description", "")
        
        matches = []
        videos = materials_index.get("videos", {})
        
        for vid, vdata in videos.items():
            score = 0
            reasons = []
            
            content = vdata.get("content_summary", {})
            description = content.get("description", "")
            
            # 简单关键词匹配
            keywords = query.split()
            for kw in keywords:
                if len(kw) > 1 and kw in description:
                    score += 2
                    reasons.append(f"关键词匹配: {kw}")
            
            if score > 0:
                matches.append(MaterialMatch(
                    video_id=vid,
                    score=min(score, 10),
                    reasons=reasons,
                    data=vdata
                ))
        
        # 按分数排序
        matches.sort(key=lambda x: x.score, reverse=True)
        return matches


class ScriptGapAnalyzer:
    """剧本缺口分析器"""
    
    def __init__(self):
        pass
    
    def analyze_coverage(
        self,
        script: Dict,
        materials_index: Dict
    ) -> Dict:
        """
        分析剧本与素材的覆盖度
        
        Returns:
            {
                "coverage_rate": 0.8,  # 覆盖率
                "missing_segments": [],  # 缺失的段落
                "partial_matches": [],   # 部分匹配的段落
                "suggestions": []        # 建议
            }
        """
        total_segments = len(script.get("clips", []))
        if total_segments == 0:
            return {"coverage_rate": 0, "missing_segments": [], "suggestions": []}
        
        rewriter = AdaptiveRewriter()
        
        covered = 0
        missing = []
        partial = []
        
        for i, (clip, subtitle) in enumerate(zip(
            script.get("clips", []),
            script.get("subtitles", [])
        )):
            matched = rewriter._mock_search(clip, subtitle, materials_index)
            
            if not matched:
                missing.append({
                    "index": i,
                    "subtitle": subtitle,
                    "reason": "无匹配素材"
                })
            elif matched[0].score < 6.0:
                partial.append({
                    "index": i,
                    "subtitle": subtitle,
                    "best_match_score": matched[0].score,
                    "reason": "匹配度低"
                })
            else:
                covered += 1
        
        coverage_rate = covered / total_segments
        
        suggestions = []
        if coverage_rate < 0.5:
            suggestions.append("覆盖率过低，建议大幅调整剧本或补充拍摄素材")
        elif coverage_rate < 0.8:
            suggestions.append("覆盖率一般，建议优化部分段落")
        
        if missing:
            suggestions.append(f"有 {len(missing)} 个段落完全无匹配素材，建议删除或重写")
        
        return {
            "coverage_rate": coverage_rate,
            "covered_segments": covered,
            "total_segments": total_segments,
            "missing_segments": missing,
            "partial_matches": partial,
            "suggestions": suggestions
        }


def main():
    """CLI 入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="剧本自适应重写")
    parser.add_argument("--script", "-s", required=True, help="原始剧本")
    parser.add_argument("--materials", "-m", required=True, help="素材索引")
    parser.add_argument("--output", "-o", required=True, help="输出剧本")
    parser.add_argument("--threshold", "-t", type=float, default=0.6, help="匹配度阈值")
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.script, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    with open(args.materials, 'r', encoding='utf-8') as f:
        materials = json.load(f)
    
    # 分析覆盖度
    analyzer = ScriptGapAnalyzer()
    coverage = analyzer.analyze_coverage(script, materials)
    
    print("=== 剧本覆盖度分析 ===")
    print(f"覆盖率: {coverage['coverage_rate']*100:.1f}%")
    print(f"完全匹配: {coverage['covered_segments']}/{coverage['total_segments']}")
    print(f"缺失段落: {len(coverage['missing_segments'])}")
    print(f"部分匹配: {len(coverage['partial_matches'])}")
    
    if coverage['suggestions']:
        print("\n建议:")
        for sug in coverage['suggestions']:
            print(f"  - {sug}")
    
    # 执行重写
    if coverage['coverage_rate'] < 1.0:
        print("\n=== 执行剧本重写 ===")
        rewriter = AdaptiveRewriter(similarity_threshold=args.threshold)
        rewritten, changes = rewriter.rewrite_script(script, materials)
        
        if changes:
            print(f"\n重写 {len(changes)} 处:")
            for change in changes:
                print(f"\n  [{change['clip_index']}] {change['reason']}")
                print(f"    原文: {change['original'][:50]}...")
                print(f"    改写: {change['rewritten'][:50]}...")
        
        # 保存
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(rewritten, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 重写完成: {args.output}")
    else:
        print("\n✅ 剧本完全匹配，无需重写")


if __name__ == "__main__":
    main()
