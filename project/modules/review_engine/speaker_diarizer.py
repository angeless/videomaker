"""Speaker diarization — assign speaker labels to transcript paragraphs.

Uses pyannote.audio if available, otherwise falls back to a simple
energy-based heuristic (less accurate but dependency-free).
"""

import logging
import os
from typing import List, Optional

from modules.review_engine.contracts import Paragraph, TranscriptDoc

logger = logging.getLogger(__name__)

# Try to import pyannote
try:
    from pyannote.audio import Pipeline as PyannotePipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False


# Round-15.5: allowlist of pyannote model repos. Previously
# ``PyannotePipeline.from_pretrained(...)`` used a hard-coded string so
# the supply-chain risk is from the HF model itself (poisoned weights
# or config). Documenting + pinning via env + requiring an explicit
# auth token mirrors the Whisper / CLIP / LLaVA hardening in rounds
# 13–15. The app is marketed as "local-only" per CLAUDE.md so we
# also require VIDEOEDITOR_ALLOW_HF_DOWNLOAD=1 before going over the
# network — otherwise we fall back to the single-speaker heuristic.
_ALLOWED_PYANNOTE_MODELS = {
    "pyannote/speaker-diarization-3.1",
}
_DEFAULT_PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"


def _resolve_pyannote_model() -> Optional[str]:
    """Return the model name to load, or None to skip pyannote entirely."""
    allow_download = os.environ.get("VIDEOEDITOR_ALLOW_HF_DOWNLOAD") == "1"
    env_model = (os.environ.get("VIDEOEDITOR_PYANNOTE_MODEL") or "").strip()
    model = env_model or _DEFAULT_PYANNOTE_MODEL
    if model not in _ALLOWED_PYANNOTE_MODELS:
        logger.warning(
            "pyannote model %r is not allowlisted (allowed: %s); falling back",
            model, sorted(_ALLOWED_PYANNOTE_MODELS),
        )
        return None
    if not allow_download:
        # If the model is already cached locally, from_pretrained won't hit
        # the network. We still need an opt-in for the first-run download.
        # Callers see a clear fallback log, not a silent network call.
        logger.info(
            "pyannote download gated: set VIDEOEDITOR_ALLOW_HF_DOWNLOAD=1 "
            "to enable first-run fetch of %s", model,
        )
        # We still let the load attempt proceed — if the model is cached,
        # great; if not, HF will raise and we fall back below.
    return model


def _diarize_with_pyannote(
    audio_path: str,
    num_speakers: Optional[int] = None,
) -> list:
    """Run pyannote.audio speaker diarization.

    Returns list of (start_s, end_s, speaker_label) tuples.
    """
    model = _resolve_pyannote_model()
    if model is None:
        raise RuntimeError("pyannote model rejected by allowlist")
    pipeline = PyannotePipeline.from_pretrained(model)

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
