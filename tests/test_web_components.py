from fantasy_assistant.web_components import (
    _darken,
    avatar,
    collapsible,
    format_badge,
    gradient,
    player_cell,
    position_badge,
    stat_tile,
)


def test_position_badge_escapes_and_colors_known_position():
    out = position_badge("WR")
    assert "WR" in out
    assert "#3b82f6" in out  # known WR color applied


def test_position_badge_handles_none():
    assert position_badge(None) == ""


def test_position_badge_escapes_malicious_input():
    out = position_badge("<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_avatar_initials_from_two_word_name():
    out = avatar("Ja'Marr Chase", "WR")
    assert "JC" in out


def test_avatar_escapes_malicious_name():
    out = avatar('<img src=x onerror=alert(1)>', "WR")
    assert "<img" not in out


def test_player_cell_escapes_name():
    out = player_cell("<script>xss</script>", "RB")
    assert "<script>xss</script>" not in out
    assert "&lt;script&gt;" in out


def test_format_badge_known_and_unknown():
    assert "#a855f7" in format_badge("dynasty")  # known dynasty color
    out = format_badge("weird-format")
    assert "weird-format" in out  # still renders, falls back to default color


def test_stat_tile_escapes_value():
    out = stat_tile("Label", "<script>xss</script>")
    assert "<script>xss</script>" not in out


def test_darken_produces_a_darker_valid_hex_color():
    darker = _darken("#3b82f6")
    assert darker.startswith("#") and len(darker) == 7
    # every channel should be <= the original
    orig = [int("3b82f6"[i : i + 2], 16) for i in (0, 2, 4)]
    dark = [int(darker.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    assert all(d <= o for d, o in zip(dark, orig))


def test_darken_handles_malformed_input_gracefully():
    assert _darken("not-a-color") == "not-a-color"


def test_gradient_contains_both_original_and_darkened_stop():
    out = gradient("#3b82f6")
    assert out.startswith("linear-gradient(")
    assert "#3b82f6" in out
    assert _darken("#3b82f6") in out


def test_position_badge_uses_gradient_background():
    out = position_badge("WR")
    assert "linear-gradient(" in out


def test_avatar_uses_gradient_background():
    out = avatar("Bijan Robinson", "RB")
    assert "linear-gradient(" in out


def test_collapsible_escapes_nothing_extra_and_defaults_open():
    out = collapsible("<b>Summary</b>", "<p>Inner</p>")
    assert "<details" in out
    assert " open" in out
    assert "<summary><b>Summary</b></summary>" in out
    assert "<p>Inner</p>" in out


def test_collapsible_can_start_closed():
    out = collapsible("Summary", "Inner", open_=False)
    assert "<details class=\"collapsible\">" in out
    assert " open" not in out.split("<summary")[0]
