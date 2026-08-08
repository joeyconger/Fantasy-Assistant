from fantasy_assistant.web_components import avatar, format_badge, player_cell, position_badge, stat_tile


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
