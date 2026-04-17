"""Shared helpers for FFmpeg concat-demuxer file list writing.

The FFmpeg ``-f concat`` demuxer reads a file list where each line is
``file '<path>'``. Single quotes within the path must be escaped as
``'\\''`` (close the literal, insert an escaped quote, reopen). Without
this, a filename containing ``'`` breaks the quoted literal and lets
an attacker inject arbitrary demuxer directives — including ``file``
lines pointing at ``/etc/passwd`` or similar.

Round 11 fixed one callsite (auto_render.py) but left 6 others with
the same ``f"file '{path}'"`` pattern. Round 14 hoisted the escape
helper here so every concat writer uses the same hardened implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union

PathLike = Union[str, Path]


def escape_concat_path(path: PathLike) -> str:
    """Escape a single path for inclusion in an FFmpeg concat list line.

    >>> escape_concat_path("normal.mp4")
    'normal.mp4'
    >>> escape_concat_path("tricky's file.mp4")
    "tricky'\\\\''s file.mp4"
    """
    return str(path).replace("'", r"'\''")


def concat_list_line(path: PathLike) -> str:
    """Return a single ``file 'PATH'\\n`` line with proper escaping."""
    return f"file '{escape_concat_path(path)}'\n"


def concat_list_body(paths: Iterable[PathLike]) -> str:
    """Return a complete concat-demuxer list body (newline-terminated)."""
    return "".join(concat_list_line(p) for p in paths)


def safe_ffmpeg_arg(path: PathLike) -> str:
    """Return a path safe to pass as a positional FFmpeg/ffprobe argument.

    FFmpeg parses any argument starting with ``-`` as an option, which
    means a filename like ``-filter_complex;evil`` or a path containing
    dash-prefixed components supplied by an attacker could smuggle
    additional options into the command line (even in argv mode, no
    ``shell=True`` needed).

    The POSIX-standard escape is ``./<relative>`` for relative paths and
    leaving absolute paths alone (they already start with ``/``). This
    helper applies that rule without changing the path's semantics.

    Round 15.5: hoisted here so every FFmpeg-invoking module uses the
    same guard (audio_enhancer, bgm_selector, scene_selector,
    social_reframe, video_detector, frame_preview, color_grade).
    """
    s = str(path)
    if not s:
        raise ValueError("empty path rejected by safe_ffmpeg_arg")
    # Absolute path — already unambiguous.
    if s.startswith("/") or (len(s) > 1 and s[1] == ":"):  # unix abs or win drive
        return s
    # Any other path that would be parsed as a flag — prefix with ./
    if s.startswith("-"):
        return "./" + s
    return s
