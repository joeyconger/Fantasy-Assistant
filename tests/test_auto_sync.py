import threading
from datetime import datetime, timezone

from fantasy_assistant import auto_sync


def test_seconds_until_next_run_same_day():
    now = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
    seconds = auto_sync._seconds_until_next_run(now)
    assert seconds == 3 * 3600  # 10:00 -> 13:00 same day


def test_seconds_until_next_run_rolls_to_next_day_when_past():
    now = datetime(2026, 8, 20, 14, 0, 0, tzinfo=timezone.utc)
    seconds = auto_sync._seconds_until_next_run(now)
    assert seconds == 23 * 3600  # 14:00 -> 13:00 the next day


def test_seconds_until_next_run_rolls_to_next_day_when_exactly_on_target():
    now = datetime(2026, 8, 20, 13, 0, 0, tzinfo=timezone.utc)
    seconds = auto_sync._seconds_until_next_run(now)
    assert seconds == 24 * 3600  # exactly at the target counts as "already ran today"


def test_current_nfl_season_mid_season():
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert auto_sync._current_nfl_season(now) == 2026


def test_current_nfl_season_before_kickoff():
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    assert auto_sync._current_nfl_season(now) == 2026


def test_current_nfl_season_rolls_back_during_january():
    """A January game (e.g. playoffs) is still part of the previous
    calendar year's named season."""
    now = datetime(2027, 1, 15, tzinfo=timezone.utc)
    assert auto_sync._current_nfl_season(now) == 2026


def test_current_nfl_season_rolls_forward_in_march():
    now = datetime(2027, 3, 1, tzinfo=timezone.utc)
    assert auto_sync._current_nfl_season(now) == 2027


def test_start_is_a_noop_under_pytest():
    """start() must never spawn a real background thread during a test run —
    PYTEST_CURRENT_TEST is always set while pytest is running a test, which
    is exactly the guard start() checks."""
    before = {t.name for t in threading.enumerate()}
    auto_sync.start()
    after = {t.name for t in threading.enumerate()}
    assert after == before
    assert "daily-sync" not in after
