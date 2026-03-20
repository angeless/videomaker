#!/usr/bin/env python3
"""测试 AI 工具可导入性（兼容 pytest 收集）。"""

import importlib


MODULES_TO_TEST = [
    ("ultralytics", "YOLOv8 - 物体检测"),
    ("transformers", "BLIP - 场景描述"),
    ("whisper", "Whisper - 语音转文字"),
    ("scenedetect", "PySceneDetect - 场景检测"),
    ("imagehash", "ImageHash - 感知哈希"),
    ("cv2", "OpenCV - 图像处理"),
]


def _try_import(module_name):
    try:
        importlib.import_module(module_name)
        return True, "✅"
    except ImportError as exc:
        return False, f"❌ {exc}"


def test_import_helper_with_stdlib_module():
    success, _ = _try_import("json")
    assert success


def main():
    print("🔍 测试AI工具导入...")
    print("=" * 60)

    all_passed = True
    for module_name, description in MODULES_TO_TEST:
        success, message = _try_import(module_name)
        status = "✅" if success else "❌"
        print(f"{status} {description}: {module_name}")
        if not success:
            all_passed = False
            print(f"   错误: {message}")

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有AI工具安装成功!")
        print("可以开始视频分析了!")
    else:
        print("⚠️  部分工具安装失败，需要检查")

    print("\n激活虚拟环境:")
    print("  source venv/bin/activate")
    print("\n运行测试:")
    print("  python test_ai_tools.py")


if __name__ == "__main__":
    main()
