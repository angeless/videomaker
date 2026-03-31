"""Transcript editor — Whisper word-level transcription + paragraph grouping.

Wraps the existing transcribe module to produce word-level TranscriptDoc,
which is the data model for the Descript-style text editor.
"""

import logging
import os
import subprocess
import tempfile
import shutil
from typing import Dict, List, Optional

from modules.review_engine.contracts import (
    Paragraph,
    TranscriptDoc,
    Word,
)
from modules.review_engine.exceptions import TranscriptError

logger = logging.getLogger(__name__)

# Paragraph splitting: gap > this threshold starts a new paragraph
PARAGRAPH_GAP_MS = 1500  # 1.5 seconds

# Try to import ASR engines
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


def _extract_audio_wav(video_path: str, output_wav: str) -> None:
    """Extract 16kHz mono WAV from video using FFmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    cmd = [
        ffmpeg_bin, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_wav,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise TranscriptError(f"Audio extraction timed out: {video_path}")

    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")[:500]
        raise TranscriptError(f"Audio extraction failed: {stderr}")


def _transcribe_faster_whisper_words(
    wav_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
) -> tuple:
    """Transcribe with faster-whisper, returning word-level timestamps.

    Returns:
        (words: List[dict], duration: float, detected_language: str)
    """
    model = FasterWhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
    )

    segments_iter, info = model.transcribe(
        wav_path,
        language=language,
        beam_size=5,
        word_timestamps=True,  # Key: word-level timing
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
        ),
    )

    words = []
    for seg in segments_iter:
        if seg.words:
            for w in seg.words:
                words.append({
                    "text": w.word.strip(),
                    "start": w.start,
                    "end": w.end,
                    "confidence": round(w.probability, 3) if hasattr(w, "probability") else 0.5,
                })

    duration = info.duration if hasattr(info, "duration") else 0.0
    detected_lang = info.language if hasattr(info, "language") else ""

    return words, duration, detected_lang


def _transcribe_openai_whisper_words(
    wav_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
) -> tuple:
    """Transcribe with openai-whisper, returning word-level timestamps.

    Note: openai-whisper's word_timestamps are less reliable than faster-whisper.
    """
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = openai_whisper.load_model(model_size, device=device)

    opts = {"language": language} if language else {}
    result = model.transcribe(wav_path, word_timestamps=True, **opts)

    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words.append({
                "text": w["word"].strip(),
                "start": w["start"],
                "end": w["end"],
                "confidence": round(w.get("probability", 0.5), 3),
            })

    duration = result["segments"][-1]["end"] if result.get("segments") else 0.0
    detected_lang = result.get("language", "")

    return words, duration, detected_lang


def _group_words_into_paragraphs(
    words: List[Dict],
    gap_threshold_ms: int = PARAGRAPH_GAP_MS,
) -> List[Paragraph]:
    """Group words into paragraphs based on silence gaps.

    A new paragraph starts when the gap between consecutive words
    exceeds gap_threshold_ms.
    """
    if not words:
        return []

    paragraphs = []
    current_words = []
    para_idx = 0

    for i, w in enumerate(words):
        word_obj = Word(
            text=w["text"],
            start_ms=int(w["start"] * 1000),
            end_ms=int(w["end"] * 1000),
            confidence=w.get("confidence", 0.5),
        )

        if current_words:
            gap_ms = word_obj.start_ms - current_words[-1].end_ms
            if gap_ms > gap_threshold_ms:
                # Close current paragraph
                paragraphs.append(Paragraph(
                    idx=para_idx,
                    speaker=None,
                    start_ms=current_words[0].start_ms,
                    end_ms=current_words[-1].end_ms,
                    words=current_words,
                ))
                current_words = []
                para_idx += 1

        current_words.append(word_obj)

    # Close last paragraph
    if current_words:
        paragraphs.append(Paragraph(
            idx=para_idx,
            speaker=None,
            start_ms=current_words[0].start_ms,
            end_ms=current_words[-1].end_ms,
            words=current_words,
        ))

    return paragraphs


def transcribe_to_doc(
    video_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
    paragraph_gap_ms: int = PARAGRAPH_GAP_MS,
) -> TranscriptDoc:
    """Transcribe video to word-level TranscriptDoc.

    Args:
        video_path: Path to the video file.
        model_size: Whisper model size ("tiny", "base", "medium", "large-v3").
        language: Force language (None=auto, "zh", "en").
        paragraph_gap_ms: Gap threshold for paragraph splitting.

    Returns:
        TranscriptDoc with word-level paragraphs.

    Raises:
        TranscriptError: If transcription fails.
    """
    if not os.path.isfile(video_path):
        raise TranscriptError(f"Video file not found: {video_path}")

    # Extract audio
    tmp_dir = tempfile.mkdtemp(prefix="review_transcribe_")
    wav_path = os.path.join(tmp_dir, "audio.wav")

    try:
        _extract_audio_wav(video_path, wav_path)

        # Transcribe with word timestamps
        if HAS_FASTER_WHISPER:
            raw_words, duration, lang = _transcribe_faster_whisper_words(
                wav_path, model_size, language
            )
        elif HAS_OPENAI_WHISPER:
            raw_words, duration, lang = _transcribe_openai_whisper_words(
                wav_path, model_size, language
            )
        else:
            raise TranscriptError(
                "No ASR engine available. Install faster-whisper or openai-whisper."
            )

        # Group into paragraphs
        paragraphs = _group_words_into_paragraphs(raw_words, paragraph_gap_ms)

        return TranscriptDoc(
            video_path=video_path,
            duration_ms=int(duration * 1000),
            paragraphs=paragraphs,
            language=lang or "zh",
            whisper_model=model_size,
        )

    except TranscriptError:
        raise
    except Exception as e:
        raise TranscriptError(f"Transcription failed: {e}") from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
