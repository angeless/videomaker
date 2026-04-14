"""Review engine module exceptions.

All exceptions inherit from VideoEditorError per coding-standards §4.1.
"""

from modules.exceptions import VideoEditorError


class ReviewEngineError(VideoEditorError):
    """Base exception for review engine module."""
    pass


class VideoDetectionError(ReviewEngineError):
    """Video type detection failed."""
    pass


class TranscriptError(ReviewEngineError):
    """Transcription or transcript editing failed."""
    pass


class RenderError(ReviewEngineError):
    """Video rendering failed."""
    pass


class IntentRouterError(ReviewEngineError):
    """LLM intent routing failed (bad response, schema violation)."""
    pass


class ArtifactNotFoundError(ReviewEngineError):
    """Required artifact from previous version/node not found."""
    pass


class ConflictingCommentsError(ReviewEngineError):
    """Multiple comments on same segment have contradicting instructions."""
    pass


class StockMediaError(ReviewEngineError):
    """Stock media search/download failed."""
    pass


class LockedTrackError(ReviewEngineError):
    """Attempted to modify a locked track or its clips."""
    pass


class OverlapError(ReviewEngineError):
    """Clip operation would create an overlap on a video track."""
    pass
