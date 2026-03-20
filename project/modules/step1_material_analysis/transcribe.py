#!/usr/bin/env python3
"""
视频语音转录模块 — Video Speech Transcription

使用 faster-whisper (优先) 或 openai-whisper 对视频音频进行语音识别，
输出带时间戳的转录文本，可集成到语义分析流程中。

输出格式:
{
  "transcript": "完整转录文本",
  "segments": [
    {"start": 0.0, "end": 3.5, "text": "你好", "confidence": 0.92},
    ...
  ],
  "language": "zh",
  "duration": 120.5,
  "has_speech": true,
  "speech_ratio": 0.65,   # 有语音的时长占比
  "method": "faster-whisper/medium"
}
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 检测可用的 ASR 引擎 ──────────────────────────────────────

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

try:
    import whisper as openai_whisper
    HAS_OPENAI_WHISPER = True
except ImportError:
    HAS_OPENAI_WHISPER = False


def _extract_audio(video_path: str, output_wav: str, timeout: int = 60) -> bool:
    """用 FFmpeg 从视频提取 16kHz 单声道 WAV 音频"""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn",                        # 不要视频
        "-acodec", "pcm_s16le",       # 16-bit PCM
        "-ar", "16000",               # 16kHz (Whisper 标准)
        "-ac", "1",                   # 单声道
        output_wav,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode == 0 and os.path.exists(output_wav)
    except Exception as e:
        logger.warning("音频提取失败: %s — %s", video_path, e)
        return False


def _check_audio_has_content(wav_path: str) -> bool:
    """检查音频是否有实际内容（非静音）"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=duration",
        "-of", "json", wav_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = json.loads(r.stdout)
        streams = info.get("streams", [])
        if streams:
            dur = float(streams[0].get("duration", 0))
            return dur > 0.5  # 至少0.5秒
    except Exception:
        pass
    return False


def transcribe_video(
    video_path: str,
    model_size: str = "medium",
    language: str = None,
    max_duration: float = None,
) -> dict:
    """
    转录视频中的语音。

    Args:
        video_path: 视频文件路径
        model_size: Whisper 模型大小 ("tiny", "base", "medium", "large-v3")
        language: 强制语言 (None=自动检测, "zh"=中文, "en"=英文)
        max_duration: 最大转录时长（秒），None=全部

    Returns:
        转录结果字典
    """
    video_path = str(video_path)
    if not os.path.exists(video_path):
        return {"error": f"文件不存在: {video_path}", "has_speech": False}

    # 提取音频到临时 WAV
    tmp_dir = tempfile.mkdtemp(prefix="transcribe_")
    wav_path = os.path.join(tmp_dir, "audio.wav")

    # 如果有 max_duration，加 -t 参数
    if max_duration:
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-t", str(max_duration),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            wav_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
        except Exception:
            pass
    else:
        _extract_audio(video_path, wav_path, timeout=120)

    if not os.path.exists(wav_path) or not _check_audio_has_content(wav_path):
        _cleanup(tmp_dir)
        return {
            "transcript": "",
            "segments": [],
            "language": "",
            "duration": 0,
            "has_speech": False,
            "speech_ratio": 0,
            "method": "no_audio",
        }

    # 选择 ASR 引擎
    result = None
    if HAS_FASTER_WHISPER:
        result = _transcribe_faster_whisper(wav_path, model_size, language)
    elif HAS_OPENAI_WHISPER:
        result = _transcribe_openai_whisper(wav_path, model_size, language)
    else:
        logger.error("没有可用的 ASR 引擎！请安装 faster-whisper 或 openai-whisper")
        _cleanup(tmp_dir)
        return {
            "error": "no_asr_engine",
            "transcript": "",
            "segments": [],
            "has_speech": False,
            "method": "none",
        }

    _cleanup(tmp_dir)
    return result


def _transcribe_faster_whisper(
    wav_path: str, model_size: str, language: str = None
) -> dict:
    """使用 faster-whisper 转录"""
    logger.info("使用 faster-whisper/%s 转录...", model_size)

    try:
        model = FasterWhisperModel(
            model_size,
            device="cpu",       # faster-whisper CTranslate2 不支持 MPS
            compute_type="int8",
        )

        segments_iter, info = model.transcribe(
            wav_path,
            language=language,
            beam_size=5,
            vad_filter=True,    # VAD 过滤静音段
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )

        segments = []
        full_text_parts = []
        total_speech_dur = 0.0

        for seg in segments_iter:
            segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "confidence": round(seg.avg_log_prob, 3) if hasattr(seg, 'avg_log_prob') else 0.0,
            })
            full_text_parts.append(seg.text.strip())
            total_speech_dur += seg.end - seg.start

        duration = info.duration if hasattr(info, 'duration') else 0
        detected_lang = info.language if hasattr(info, 'language') else ""

        return {
            "transcript": " ".join(full_text_parts),
            "segments": segments,
            "language": detected_lang,
            "duration": round(duration, 2),
            "has_speech": len(segments) > 0,
            "speech_ratio": round(total_speech_dur / max(duration, 0.1), 3),
            "method": f"faster-whisper/{model_size}",
        }

    except Exception as e:
        logger.error("faster-whisper 转录失败: %s", e)
        # 回退到 openai-whisper
        if HAS_OPENAI_WHISPER:
            logger.info("回退到 openai-whisper...")
            return _transcribe_openai_whisper(wav_path, model_size, language)
        return {
            "error": str(e),
            "transcript": "",
            "segments": [],
            "has_speech": False,
            "method": f"faster-whisper/{model_size}/error",
        }


def _transcribe_openai_whisper(
    wav_path: str, model_size: str, language: str = None
) -> dict:
    """使用 openai-whisper 转录"""
    logger.info("使用 openai-whisper/%s 转录...", model_size)

    try:
        # MPS 加速 (Apple Silicon)
        import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"

        model = openai_whisper.load_model(model_size, device=device)

        opts = {"language": language} if language else {}
        result = model.transcribe(wav_path, **opts)

        segments = []
        total_speech_dur = 0.0
        for seg in result.get("segments", []):
            segments.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": seg["text"].strip(),
                "confidence": round(seg.get("avg_logprob", 0), 3),
            })
            total_speech_dur += seg["end"] - seg["start"]

        full_text = result.get("text", "").strip()
        detected_lang = result.get("language", "")

        # 估算总时长
        duration = segments[-1]["end"] if segments else 0

        return {
            "transcript": full_text,
            "segments": segments,
            "language": detected_lang,
            "duration": round(duration, 2),
            "has_speech": len(segments) > 0,
            "speech_ratio": round(total_speech_dur / max(duration, 0.1), 3),
            "method": f"openai-whisper/{model_size}/{device}",
        }

    except Exception as e:
        logger.error("openai-whisper 转录失败: %s", e)
        return {
            "error": str(e),
            "transcript": "",
            "segments": [],
            "has_speech": False,
            "method": f"openai-whisper/{model_size}/error",
        }


def _cleanup(tmp_dir: str):
    """清理临时文件"""
    import shutil
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def batch_transcribe(
    video_paths: list,
    model_size: str = "medium",
    language: str = None,
    max_duration: float = None,
    on_progress=None,
) -> dict:
    """
    批量转录多个视频。

    Args:
        video_paths: 视频路径列表
        model_size: Whisper 模型大小
        language: 强制语言
        max_duration: 每个视频最大转录时长
        on_progress: 回调 (index, total, filename, result)

    Returns:
        {filename: result_dict} 映射
    """
    results = {}
    total = len(video_paths)

    for i, vp in enumerate(video_paths):
        fname = Path(vp).name
        logger.info("[%d/%d] 转录: %s", i + 1, total, fname)

        result = transcribe_video(vp, model_size, language, max_duration)
        results[fname] = result

        if on_progress:
            on_progress(i, total, fname, result)

        # 简要输出
        if result.get("has_speech"):
            text_preview = result["transcript"][:60] + "..." if len(result.get("transcript", "")) > 60 else result.get("transcript", "")
            logger.info("  ✓ %s [%s] %.1fs: %s",
                        fname, result.get("language", "?"),
                        result.get("duration", 0), text_preview)
        else:
            logger.info("  - %s: 无语音", fname)

    return results


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="视频语音转录")
    parser.add_argument("input", nargs="+", help="视频文件或目录")
    parser.add_argument("--model", default="medium", help="Whisper 模型大小")
    parser.add_argument("--language", default=None, help="强制语言 (zh/en)")
    parser.add_argument("--max-duration", type=float, default=None, help="最大转录时长(秒)")
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    # 收集视频路径
    paths = []
    for inp in args.input:
        p = Path(inp)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.MOV")) + sorted(p.glob("*.mp4")))
        elif p.is_file():
            paths.append(p)

    if not paths:
        print("未找到视频文件")
        exit(1)

    print(f"将转录 {len(paths)} 个视频 (model={args.model})")
    results = batch_transcribe(
        [str(p) for p in paths],
        model_size=args.model,
        language=args.language,
        max_duration=args.max_duration,
    )

    # 输出
    out_path = args.output or "transcripts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n转录结果已保存到: {out_path}")

    # 统计
    speech_count = sum(1 for r in results.values() if r.get("has_speech"))
    print(f"有语音: {speech_count}/{len(results)}")
