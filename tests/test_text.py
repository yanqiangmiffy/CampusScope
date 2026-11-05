"""Temporal anchoring of dates and the deployed chunker."""
from datetime import date

from campusscope.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunk
from campusscope.text import anchor, undouble


def test_a_date_with_the_wrong_year_is_anchored_near_publication():
    assert anchor(date(2025, 1, 12), "2026-01-07") == date(2026, 1, 12)
    assert anchor(date(2026, 3, 1), "2026-01-07") == date(2026, 3, 1)


def test_doubled_bold_runs_are_undone():
    assert undouble("中中关关村村校校区区") == "中关村校区"


def test_chunks_are_bounded_and_overlap():
    text = "。".join(f"第{i}条安排" for i in range(400))
    parts = chunk(text)
    assert len(parts) > 1 and all(len(p) <= CHUNK_SIZE for p in parts)
    assert parts[0][-20:] in parts[1][:CHUNK_OVERLAP + 20]
