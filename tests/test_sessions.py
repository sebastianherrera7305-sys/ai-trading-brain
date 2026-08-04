"""Tests for the Sessions module (AI Trading Brain v1, Phase 1)."""

import unittest
from datetime import time

from trading_brain.sessions import (
    SessionWindow,
    is_allowed_to_trade,
    tag_session,
)


class TestTagSession(unittest.TestCase):
    def test_off_session(self):
        self.assertEqual(tag_session(time(3, 0)).window, SessionWindow.OFF_SESSION)
        self.assertEqual(tag_session(time(22, 0)).window, SessionWindow.OFF_SESSION)

    def test_london_open(self):
        self.assertEqual(tag_session(time(7, 30)).window, SessionWindow.LONDON_OPEN)

    def test_london_killzone_after_open_window_ends(self):
        self.assertEqual(tag_session(time(9, 30)).window, SessionWindow.LONDON_KILLZONE)

    def test_new_york_open_is_reachable(self):
        # Regression: NEW_YORK_OPEN is a strict subset of LONDON_NY_OVERLAP, so it
        # was previously shadowed and could never be returned for any input.
        self.assertEqual(tag_session(time(12, 30)).window, SessionWindow.NEW_YORK_OPEN)
        self.assertEqual(tag_session(time(13, 0)).window, SessionWindow.NEW_YORK_OPEN)

    def test_new_york_killzone_is_reachable(self):
        # Same regression, for the window between NY's own open ending and NY's
        # kill zone ending.
        self.assertEqual(tag_session(time(14, 30)).window, SessionWindow.NEW_YORK_KILLZONE)

    def test_overlap_tail_after_ny_specific_windows_end(self):
        self.assertEqual(tag_session(time(15, 30)).window, SessionWindow.LONDON_NY_OVERLAP)

    def test_late_ny_general_session(self):
        self.assertEqual(tag_session(time(19, 0)).window, SessionWindow.NEW_YORK_GENERAL)

    def test_every_window_is_reachable(self):
        # No enum variant should be permanently shadowed by a broader one that's
        # checked earlier -- scan the whole day and confirm each label appears.
        seen = set()
        for h in range(24):
            for m in range(0, 60, 5):
                seen.add(tag_session(time(h, m)).window)
        for window in SessionWindow:
            self.assertIn(window, seen, f"{window} is unreachable for any time of day")

    def test_preferred_and_tradeable_flags_unaffected_by_the_reorder_fix(self):
        # NEW_YORK_OPEN and LONDON_NY_OVERLAP are both preferred+tradeable, so
        # which one wins the label must not change the gate itself.
        for t in (time(12, 30), time(13, 0), time(15, 30)):
            tag = tag_session(t)
            self.assertTrue(tag.is_tradeable)
            self.assertTrue(tag.is_preferred)


class TestIsAllowedToTrade(unittest.TestCase):
    def test_off_session_is_not_allowed(self):
        self.assertFalse(is_allowed_to_trade(time(3, 0)))

    def test_preferred_window_is_allowed(self):
        self.assertTrue(is_allowed_to_trade(time(7, 30)))

    def test_general_session_is_allowed_but_not_preferred(self):
        t = time(10, 30)  # between London kill zone end and NY start
        self.assertTrue(is_allowed_to_trade(t))
        self.assertFalse(tag_session(t).is_preferred)


if __name__ == "__main__":
    unittest.main()
