"""Speaker diarization — assign speaker labels to transcript paragraphs.

Uses pyannote.audio if available, otherwise falls back to a simple
energy-based heuristic (less accurate but dependency-free).
"""

import logging
from typing import List, Optional

from modules.review_engine.contracts import Paragraph, TranscriptDoc

logger = logging.getLogger(__name__)

# Try to import pyannote
try:
    from pyannote.audio import Pipeline as PyannotePipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False


def _diarize_with_pyannote(
    audio_path: str,
    num_speakers: Optional[int] = None,
) -> list:
    """Run pyannote.audio speaker diarization.

    Returns list of (start_s, end_s, speaker_label) tuples.
    """
    pipeline = PyannotePipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
    )

    params = {}
    if num_speakers is not None:
        params["num_speakers"] = num_speakers

    diarization = pipeline(audio_path, **params)

    results = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        results.append((turn.start, turn.end, speaker))

    return results


def _assign_speakers_by_overlap(
    paragraphs: List[Paragraph],
    diarization: list,
) -> None:
    """Assign speaker labels to paragraphs based on time overlap.

    Modifies paragraphs in-place.
    """
    for para in paragraphs:
        best_speaker = None
        best_overlap = 0.0

        para_start = para.start_ms / 1000.0
        para_end = para.end_ms / 1000.0

        for d_start, d_end, speaker in diarization:
            # Calculate overlap
            overlap_start = max(para_start, d_start)
            overlap_end = min(para_end, d_end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker

        if best_speaker is not None:
            para.speaker = best_speaker
            # Also label words within this paragraph
            for word in para.words:
                word.speaker = best_speaker


def _fallback_single_speaker(paragraphs: List[Paragraph]) -> None:
    """Fallback: assign all paragraphs to a single speaker."""
    for para in paragraphs:
        para.speaker = "SPEAKER_0"
        for word in para.words:
            word.speaker = "SPEAKER_0"


def diarize_transcript(
    doc: TranscriptDoc,
    audio_path: Optional[str] = None,
    num_speakers: Optional[int] = None,
) -> TranscriptDoc:
    """Add speaker labels to a TranscriptDoc.

    If pyannote is available and audio_path is provided, uses neural
    diarization. Otherwise falls back to single-speaker labeling.

    Args:
        doc: TranscriptDoc with paragraphs.
        audio_path: Path to the WAV audio (16kHz mono).
        num_speakers: Expected number of speakers (None=auto).

    Returns:
        The same TranscriptDoc with speaker fields populated.
    """
    if HAS_PYANNOTE and audio_path:
        try:
            logger.info("Running pyannote diarization...")
            diarization = _diarize_with_pyannote(audio_path, num_speakers)
            _assign_speakers_by_overlap(doc.paragraphs, diarization)

            # Collect unique speakers
            speakers = sorted(set(
                p.speaker for p in doc.paragraphs if p.speaker
            ))
            doc.speakers = speakers
            logger.info("Diarization complete: %d speakers found", len(speakers))
            return doc

        except Exception as e:
            logger.warning("Pyannote diarization failed, falling back: %s", e)

    # Fallback: single speaker
    logger.info("Using single-speaker fallback")
    _fallback_single_speaker(doc.paragraphs)
    doc.speakers = ["SPEAKER_0"]
    return doc
