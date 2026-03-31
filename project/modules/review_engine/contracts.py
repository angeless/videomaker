"""Review engine data contracts.

Shared data structures used across the review_engine module and by
external callers. All types are plain dataclasses for easy serialization.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class VideoType(str, Enum):
    """Video classification based on VAD analysis."""
    SPEECH = "speech"    # speech_ratio > 0.6
    SCENIC = "scenic"    # speech_ratio < 0.15
    MIXED = "mixed"      # 0.15 <= speech_ratio <= 0.6


@dataclass
class DetectionResult:
    """Result of video type detection (VAD)."""
    video_type: VideoType
    speech_ratio: float
    duration_s: float
    has_audio: bool
    method: str = "webrtcvad"


@dataclass
class Word:
    """Single word with timing from Whisper transcription."""
    text: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0
    speaker: Optional[str] = None


@dataclass
class FillerMark:
    """A filler word or phrase mark."""
    word_idx: int
    start_ms: int
    end_ms: int
    filler_type: str  # "filler_word" | "dead_air" | "filler_sentence"
    text: str
    auto_marked: bool = True


@dataclass
class RetakeMark:
    """A detected retake / bad take."""
    paragraph_idx: int
    start_ms: int
    end_ms: int
    retake_type: str  # "semantic_repeat" | "false_start" | "hesitation_restart"
    keep_idx: Optional[int] = None  # which paragraph to keep (the later one)
    similarity: float = 0.0


@dataclass
class Paragraph:
    """A paragraph (continuous speech segment) in the transcript."""
    idx: int
    speaker: Optional[str]
    start_ms: int
    end_ms: int
    words: List[Word] = field(default_factory=list)
    is_deleted: bool = False
    is_hook: bool = False
    filler_marks: List[FillerMark] = field(default_factory=list)
    retake_marks: List[RetakeMark] = field(default_factory=list)


@dataclass
class TranscriptDoc:
    """Complete transcript document with paragraphs and metadata."""
    video_path: str
    duration_ms: int
    paragraphs: List[Paragraph] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)
    language: str = "zh"
    whisper_model: str = "base"


@dataclass
class Segment:
    """A video segment in the edit list (EDITS)."""
    source_path: str
    start_ms: int
    end_ms: int
    segment_type: str = "keep"  # "keep" | "removed" | "inserted"
    paragraph_idx: Optional[int] = None
    label: Optional[str] = None


@dataclass
class SceneInfo:
    """A detected scene from scene segmentation."""
    scene_idx: int
    start_ms: int
    end_ms: int
    duration_ms: int
    thumbnail_path: Optional[str] = None
    scene_type: Optional[str] = None  # "landscape" | "person" | "action" | etc.
    quality_score: float = 0.0
    description: Optional[str] = None
    selected: bool = False


@dataclass
class EditInstruction:
    """A structured edit instruction from the intent router."""
    instruction_type: str  # extend/trim/remove/insert/reorder/split/merge/transition/subtitle/speaker/hook/speed/broll/audio
    segment_idx: Optional[int] = None
    params: Dict = field(default_factory=dict)
    source_comment_id: Optional[str] = None
