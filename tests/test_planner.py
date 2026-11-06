"""Tests for the planner module — 45-minute enforcement."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.generation.planner import (
    _validate_time_budget,
    _proportional_scale,
    LessonOutline,
    PlannedSection,
)


class TestTimeBudgetValidation:
    """Test the 45-minute time budget enforcement."""

    def _make_outline(self, minutes_list: list[float]) -> LessonOutline:
        """Create a test outline with given section minutes."""
        sections = [
            PlannedSection(
                heading=f"Section {i+1}",
                type="concept",
                est_minutes=m,
                description=f"Test section {i+1}",
            )
            for i, m in enumerate(minutes_list)
        ]
        return LessonOutline(
            sections=sections,
            total_minutes=sum(minutes_list),
        )

    def test_valid_45_minutes(self):
        """45 minutes should be valid."""
        outline = self._make_outline([3, 8, 8, 7, 8, 5, 4, 2])
        is_valid, msg = _validate_time_budget(outline)
        assert is_valid
        assert "OK" in msg

    def test_valid_43_minutes(self):
        """43 minutes (lower bound) should be valid."""
        outline = self._make_outline([3, 7, 7, 7, 8, 5, 4, 2])
        is_valid, msg = _validate_time_budget(outline)
        assert is_valid

    def test_valid_47_minutes(self):
        """47 minutes (upper bound) should be valid."""
        outline = self._make_outline([3, 9, 9, 7, 8, 5, 4, 2])
        is_valid, msg = _validate_time_budget(outline)
        assert is_valid

    def test_too_short_rejected(self):
        """Under 43 minutes should be rejected."""
        outline = self._make_outline([3, 5, 5, 5, 5, 3, 3, 2])
        is_valid, msg = _validate_time_budget(outline)
        assert not is_valid
        assert "short" in msg.lower()

    def test_too_long_rejected(self):
        """Over 47 minutes should be rejected."""
        outline = self._make_outline([5, 10, 10, 10, 10, 5, 5, 3])
        is_valid, msg = _validate_time_budget(outline)
        assert not is_valid
        assert "long" in msg.lower()

    def test_proportional_scale_short_to_45(self):
        """Proportional scaling should bring short lessons to ~45 min."""
        outline = self._make_outline([2, 4, 4, 4, 4, 3, 3, 1])
        scaled = _proportional_scale(outline)
        total = sum(s.est_minutes for s in scaled.sections)
        assert 43 <= total <= 47

    def test_proportional_scale_long_to_45(self):
        """Proportional scaling should bring long lessons to ~45 min."""
        outline = self._make_outline([6, 12, 12, 10, 10, 6, 5, 4])
        scaled = _proportional_scale(outline)
        total = sum(s.est_minutes for s in scaled.sections)
        assert 43 <= total <= 47

    def test_proportional_scale_minimum_1_minute(self):
        """No section should be scaled below 1 minute."""
        # When scaling down from a high total (e.g. 15+15+15+15+15+15+15 = 105 min -> scaled down to 45)
        # Small 1-minute sections should remain at least 1.0 minute.
        outline = self._make_outline([1, 1, 1, 15, 15, 15, 15, 15])
        scaled = _proportional_scale(outline)
        for section in scaled.sections:
            assert section.est_minutes >= 1.0

