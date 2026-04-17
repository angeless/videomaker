"""Regression tests for FFmpeg concat-demuxer quote escaping (Round-14)."""

from modules.render_engine.concat_utils import (
    concat_list_body,
    concat_list_line,
    escape_concat_path,
)


def test_escape_normal_path_unchanged():
    assert escape_concat_path("normal.mp4") == "normal.mp4"
    assert escape_concat_path("/tmp/video file.mp4") == "/tmp/video file.mp4"


def test_escape_single_quote_uses_posix_trick():
    # 'foo's → foo'\''s (close, literal quote, reopen)
    assert escape_concat_path("foo's") == r"foo'\''s"


def test_escape_multiple_quotes():
    assert escape_concat_path("a'b'c") == r"a'\''b'\''c"


def test_concat_line_always_terminates_with_newline():
    line = concat_list_line("x.mp4")
    assert line == "file 'x.mp4'\n"


def test_concat_line_escapes_quote_in_path():
    line = concat_list_line("foo's.mp4")
    # The whole line must parse as a single ffmpeg concat directive:
    # file 'foo'\''s.mp4'
    assert line == "file 'foo'\\''s.mp4'\n"


def test_concat_body_joins_multiple():
    body = concat_list_body(["a.mp4", "b.mp4"])
    assert body == "file 'a.mp4'\nfile 'b.mp4'\n"


def test_concat_body_attack_payload_neutralized():
    """Attacker-controlled filename cannot break out of its quoted literal.

    Without escaping, a filename like ``foo'\nfile '/etc/passwd`` would
    appear in the concat list as two directives (foo', then a second
    file directive pointing to /etc/passwd).

    With escaping, every single quote in the payload becomes `'\\''`,
    which closes the outer quote, inserts a literal escaped quote, and
    reopens — meaning the payload stays within ONE logical file directive
    from ffmpeg's perspective, even if the string visually spans multiple
    lines.
    """
    payload = "foo'\nfile '/etc/passwd"
    body = concat_list_body([payload])
    # The payload contains two `'` characters, each of which must have
    # been escaped exactly as `'\''` — that's 4 new single-quote chars
    # emitted (close + escaped + reopen = 3 per payload quote: ' + \ + '
    # + the reopening '; we check for the escape pattern directly).
    assert r"'\''" in body, "single quotes in payload were not escaped"
    # Verify escapes came in pairs (one per payload quote).
    assert body.count(r"'\''") == 2
    # The body MUST end with our terminator (the trailing `'` + newline),
    # not with an orphaned `/etc/passwd'`.
    assert body.endswith("passwd'\n")
