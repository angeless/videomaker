"""Review engine module — AI smart rough cut + timeline review.

Public API for the review_engine module. External modules should only
import from this file, never from internal submodules directly.
"""

from .contracts import (
    VideoType,
    DetectionResult,
    TranscriptDoc,
    Paragraph,
    Word,
    Segment,
    FillerMark,
    RetakeMark,
    SceneInfo,
    EditInstruction,
)
from .exceptions import (
    ReviewEngineError,
    VideoDetectionError,
    TranscriptError,
    RenderError,
    IntentRouterError,
    ArtifactNotFoundError,
    ConflictingCommentsError,
    StockMediaError,
)

__all__ = [
    # Data contracts
    "VideoType",
    "DetectionResult",
    "TranscriptDoc",
    "Paragraph",
    "Word",
    "Segment",
    "FillerMark",
    "RetakeMark",
    "SceneInfo",
    "EditInstruction",
    # Exceptions
    "ReviewEngineError",
    "VideoDetectionError",
    "TranscriptError",
    "RenderError",
    "IntentRouterError",
    "ArtifactNotFoundError",
    "ConflictingCommentsError",
    "StockMediaError",
]
