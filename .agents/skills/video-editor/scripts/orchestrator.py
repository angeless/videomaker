#!/usr/bin/env python3
"""
VideoEditer - 编排器 (Orchestrator)
三级确认流 + 10分钟超时熔断
将五阶段工作流转化为可交互的阻塞式确认点
"""

import json
import time
import signal
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


class Stage(Enum):
    """工作流阶段"""
    PLANNING = "策划审核"      # 第一阶段：大纲 + 素材清单
    MATERIAL = "素材确认"      # 第二阶段：素材匹配
    RENDER = "渲染前确认"      # 第三阶段：渲染执行
    COMPLETE = "完成"         # 完成


class Decision(Enum):
    """用户决策"""
    APPROVE = "approve"      # 确认继续
    REJECT = "reject"        # 拒绝中止
    MODIFY = "modify"        # 请求修改
    TIMEOUT = "timeout"      # 超时默认


@dataclass
class Checkpoint:
    """确认点配置"""
    stage: Stage
    name: str
    description: str
    timeout_seconds: int = 600  # 默认 10 分钟
    default_action: Decision = Decision.APPROVE  # 超时默认行为
    required_inputs: List[str] = field(default_factory=list)


@dataclass
class WorkflowState:
    """工作流状态"""
    current_stage: Stage
    stage_history: List[Dict] = field(default_factory=list)
    user_decisions: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = datetime.now()
    
    def is_timeout(self, timeout_seconds: int) -> bool:
        """检查是否超时"""
        elapsed = (datetime.now() - self.last_activity).total_seconds()
        return elapsed > timeout_seconds


class TimeoutException(Exception):
    """超时异常"""
    pass


class WorkflowOrchestrator:
    """
    工作流编排器
    
    实现三级确认点：
    1. 策划确认 - 大纲 + 素材清单
    2. 素材确认 - 匹配结果 + 重写建议
    3. 渲染确认 - 最终参数确认
    
    熔断机制：
    - 每个确认点 10 分钟超时
    - 超时执行默认策略
    - 可配置为：自动继续 / 安全中止 / 默认方案
    """
    
    def __init__(
        self,
        timeout_seconds: int = 600,
        auto_continue_on_timeout: bool = False,
        default_strategy: str = "conservative"  # conservative / aggressive
    ):
        self.timeout_seconds = timeout_seconds
        self.auto_continue_on_timeout = auto_continue_on_timeout
        self.default_strategy = default_strategy
        
        # 定义确认点
        self.checkpoints = {
            Stage.PLANNING: Checkpoint(
                stage=Stage.PLANNING,
                name="策划审核",
                description="请确认视频大纲、叙事节奏和候选素材清单",
                timeout_seconds=timeout_seconds,
                default_action=Decision.MODIFY if default_strategy == "conservative" else Decision.APPROVE,
                required_inputs=["outline", "rhythm", "materials_list"]
            ),
            Stage.MATERIAL: Checkpoint(
                stage=Stage.MATERIAL,
                name="素材确认",
                description="请确认素材匹配结果，查看重写建议",
                timeout_seconds=timeout_seconds,
                default_action=Decision.MODIFY,
                required_inputs=["matched_materials", "coverage_report", "rewrite_suggestions"]
            ),
            Stage.RENDER: Checkpoint(
                stage=Stage.RENDER,
                name="渲染前确认",
                description="请确认渲染参数：分辨率、磨皮、调色、字幕样式",
                timeout_seconds=timeout_seconds,
                default_action=Decision.APPROVE,
                required_inputs=["render_config", "preview_info"]
            )
        }
        
        self.state = WorkflowState(current_stage=Stage.PLANNING)
        self.callbacks: Dict[Stage, Callable] = {}
    
    def register_callback(self, stage: Stage, callback: Callable):
        """注册阶段回调函数"""
        self.callbacks[stage] = callback
    
    def run_stage(
        self,
        stage: Stage,
        context: Dict,
        user_input_func: Optional[Callable] = None
    ) -> Tuple[Decision, Dict]:
        """
        运行单个阶段
        
        Args:
            stage: 当前阶段
            context: 上下文数据
            user_input_func: 用户输入函数 (None 则使用自动模式)
        
        Returns:
            (用户决策, 输出数据)
        """
        checkpoint = self.checkpoints[stage]
        print(f"\n{'='*60}")
        print(f"🔷 {checkpoint.name}")
        print(f"{'='*60}")
        print(f"\n{checkpoint.description}")
        print(f"\n⏱️  超时设置: {checkpoint.timeout_seconds//60} 分钟")
        print(f"   超时默认: {'自动继续' if checkpoint.default_action == Decision.APPROVE else '请求修改'}")
        
        # 执行阶段回调获取数据
        if stage in self.callbacks:
            stage_output = self.callbacks[stage](context)
        else:
            stage_output = self._default_stage_handler(stage, context)
        
        # 展示待确认内容
        self._present_for_approval(stage, stage_output)
        
        # 获取用户决策
        if user_input_func:
            decision = self._get_user_decision_with_timeout(
                checkpoint, user_input_func
            )
        else:
            # 自动模式（无交互）
            decision = self._auto_decision(stage, stage_output)
        
        # 记录决策
        self.state.user_decisions[stage.value] = {
            "decision": decision.value,
            "timestamp": datetime.now().isoformat(),
            "timeout_used": decision == Decision.TIMEOUT
        }
        
        # 处理决策
        if decision == Decision.REJECT:
            print("\n❌ 用户中止工作流")
            raise RuntimeError("用户中止")
        
        elif decision == Decision.MODIFY:
            print("\n📝 返回修改...")
            return decision, stage_output
        
        elif decision == Decision.TIMEOUT:
            print(f"\n⏰ 超时，执行默认策略: {checkpoint.default_action.value}")
            # 超时后如果默认是继续，则继续
            if checkpoint.default_action == Decision.APPROVE:
                decision = Decision.APPROVE
            else:
                return Decision.MODIFY, stage_output
        
        # 确认继续
        print(f"\n✅ 确认通过，进入下一阶段")
        self.state.artifacts[stage.value] = stage_output
        return decision, stage_output
    
    def _get_user_decision_with_timeout(
        self,
        checkpoint: Checkpoint,
        user_input_func: Callable
    ) -> Decision:
        """带超时的用户决策获取"""
        
        print(f"\n💬 请选择: [Y]确认 [N]中止 [M]修改")
        print(f"   ({checkpoint.timeout_seconds//60}分钟内无响应将自动{checkpoint.default_action.value})")
        
        # 设置超时信号
        def timeout_handler(signum, frame):
            raise TimeoutException()
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(checkpoint.timeout_seconds)
        
        try:
            user_input = user_input_func().strip().upper()
            signal.alarm(0)  # 取消超时
            
            if user_input in ["Y", "YES", "确认", "是"]:
                return Decision.APPROVE
            elif user_input in ["N", "NO", "中止", "否", "取消"]:
                return Decision.REJECT
            elif user_input in ["M", "MODIFY", "修改", "返回"]:
                return Decision.MODIFY
            else:
                print(f"   无效输入，使用默认: {checkpoint.default_action.value}")
                return checkpoint.default_action
                
        except TimeoutException:
            return Decision.TIMEOUT
        except KeyboardInterrupt:
            return Decision.REJECT
    
    def _auto_decision(self, stage: Stage, stage_output: Dict) -> Decision:
        """自动决策（无用户交互）"""
        checkpoint = self.checkpoints[stage]
        
        # 检查是否需要关注
        if stage == Stage.MATERIAL:
            coverage = stage_output.get("coverage_rate", 1.0)
            if coverage < 0.5:
                print(f"\n⚠️  警告: 素材覆盖率仅 {coverage*100:.0f}%，建议检查")
                if self.default_strategy == "conservative":
                    return Decision.MODIFY
        
        return checkpoint.default_action
    
    def _present_for_approval(self, stage: Stage, data: Dict):
        """展示待确认内容"""
        if stage == Stage.PLANNING:
            print(f"\n📋 视频大纲:")
            print(f"   标题: {data.get('title', 'N/A')}")
            print(f"   预计时长: {data.get('duration', 'N/A')}秒")
            print(f"   段落数: {len(data.get('segments', []))}")
            
            print(f"\n🎬 候选素材 ({len(data.get('materials', []))}个):")
            for i, mat in enumerate(data.get('materials', [])[:5], 1):
                print(f"   {i}. {mat.get('filename', 'N/A')}")
        
        elif stage == Stage.MATERIAL:
            print(f"\n📊 素材匹配报告:")
            print(f"   覆盖率: {data.get('coverage_rate', 0)*100:.1f}%")
            print(f"   完全匹配: {data.get('fully_matched', 0)}段")
            print(f"   部分匹配: {data.get('partial_matched', 0)}段")
            print(f"   缺失: {data.get('missing', 0)}段")
            
            if data.get('rewrite_suggestions'):
                print(f"\n📝 剧本重写建议 ({len(data['rewrite_suggestions'])}处):")
                for sug in data['rewrite_suggestions'][:3]:
                    print(f"   - [{sug.get('clip_index')}] {sug.get('reason')}")
        
        elif stage == Stage.RENDER:
            config = data.get('config', {})
            print(f"\n⚙️  渲染参数:")
            print(f"   分辨率: {config.get('width', 1080)}x{config.get('height', 1920)}")
            print(f"   磨皮: {'启用' if config.get('enable_skin_smooth') else '禁用'}")
            print(f"   调色: {'启用' if config.get('enable_color_grading') else '禁用'}")
            print(f"   预计输出: {data.get('output_path', 'N/A')}")
    
    def _default_stage_handler(self, stage: Stage, context: Dict) -> Dict:
        """默认阶段处理器"""
        return context
    
    def run_full_workflow(
        self,
        initial_context: Dict,
        user_input_func: Optional[Callable] = None
    ) -> Dict:
        """
        运行完整工作流
        
        Returns:
            最终输出数据
        """
        stages = [Stage.PLANNING, Stage.MATERIAL, Stage.RENDER]
        context = initial_context.copy()
        
        for stage in stages:
            self.state.current_stage = stage
            
            while True:
                decision, output = self.run_stage(stage, context, user_input_func)
                
                if decision == Decision.APPROVE:
                    context.update(output)
                    break
                elif decision == Decision.MODIFY:
                    # 允许修改后重新进入同一阶段
                    print("\n请修改后重新提交...")
                    if user_input_func:
                        input("按回车继续...")
                    continue
                elif decision == Decision.REJECT:
                    raise RuntimeError(f"工作流在 {stage.value} 阶段被中止")
            
            # 记录阶段历史
            self.state.stage_history.append({
                "stage": stage.value,
                "completed_at": datetime.now().isoformat()
            })
        
        self.state.current_stage = Stage.COMPLETE
        print(f"\n{'='*60}")
        print("🎉 工作流完成！")
        print(f"{'='*60}")
        
        return context
    
    def save_state(self, path: str):
        """保存工作流状态"""
        state_dict = {
            "current_stage": self.state.current_stage.value,
            "stage_history": self.state.stage_history,
            "user_decisions": self.state.user_decisions,
            "artifacts": self.state.artifacts,
            "start_time": self.state.start_time.isoformat(),
            "total_duration": str(datetime.now() - self.state.start_time)
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=2)
    
    def load_state(self, path: str):
        """加载工作流状态"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.state.current_stage = Stage(data.get("current_stage", "planning"))
        self.state.stage_history = data.get("stage_history", [])
        self.state.user_decisions = data.get("user_decisions", {})
        self.state.artifacts = data.get("artifacts", {})


def demo_interactive():
    """演示交互式工作流"""
    
    def mock_user_input():
        """模拟用户输入"""
        return input("\n你的选择: ")
    
    def planning_handler(context):
        """策划阶段处理"""
        return {
            "title": "2024 冰岛之旅",
            "duration": 60,
            "segments": [
                {"type": "opening", "duration": 8},
                {"type": "body", "duration": 44},
                {"type": "ending", "duration": 8}
            ],
            "materials": [
                {"filename": "DJI_0001.mp4", "score": 9.2},
                {"filename": "DSC_0002.mp4", "score": 8.8}
            ]
        }
    
    def material_handler(context):
        """素材阶段处理"""
        return {
            "coverage_rate": 0.85,
            "fully_matched": 5,
            "partial_matched": 2,
            "missing": 1,
            "rewrite_suggestions": [
                {
                    "clip_index": 3,
                    "reason": "素材缺失，建议删除此段落",
                    "original": "站在冰川前感受大自然",
                    "rewritten": "[跳过此段落]"
                }
            ]
        }
    
    def render_handler(context):
        """渲染阶段处理"""
        return {
            "config": {
                "width": 1080,
                "height": 1920,
                "enable_skin_smooth": True,
                "enable_color_grading": True
            },
            "output_path": "./output/iceland_trip.mp4"
        }
    
    # 创建编排器
    orchestrator = WorkflowOrchestrator(
        timeout_seconds=600,
        auto_continue_on_timeout=False,
        default_strategy="conservative"
    )
    
    # 注册回调
    orchestrator.register_callback(Stage.PLANNING, planning_handler)
    orchestrator.register_callback(Stage.MATERIAL, material_handler)
    orchestrator.register_callback(Stage.RENDER, render_handler)
    
    # 运行工作流
    try:
        result = orchestrator.run_full_workflow(
            initial_context={"project_name": "冰岛之旅"},
            user_input_func=mock_user_input
        )
        
        print(f"\n最终结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except RuntimeError as e:
        print(f"\n工作流中止: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_interactive()
    else:
        print("Usage: python orchestrator.py --demo")
        print("\nThis module provides workflow orchestration with 3-stage checkpoints:")
        print("  1. Planning - Outline + materials confirmation")
        print("  2. Material - Match results + rewrite suggestions")
        print("  3. Render - Final render parameters")
        print("\nFeatures:")
        print("  - 10-minute timeout with configurable default action")
        print("  - Circuit breaker pattern for error handling")
        print("  - State persistence for resuming workflows")
