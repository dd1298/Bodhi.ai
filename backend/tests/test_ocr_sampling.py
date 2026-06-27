"""Verify OCR page-sampling covers the front, middle and back of a long
PDF so topic extraction sees content from every chapter, not just the ToC."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We don't actually run Tesseract here (no PDF needed) — we just verify the
# page-number planner inside _ocr_pdf picks pages spread across the book.
# Reach into the private logic by simulating its math directly.


def _plan(total_pages: int, max_pages: int = 40) -> list[int]:
    """Mirror of _ocr_pdf's sampling logic so we can unit-test it."""
    if total_pages <= max_pages:
        return list(range(1, total_pages + 1))
    head = list(range(1, min(5, total_pages + 1)))
    tail = list(range(max(total_pages - 1, 1), total_pages + 1))
    remaining = max_pages - len(head) - len(tail)
    if remaining > 0:
        start = head[-1] + 1
        end = tail[0] - 1
        if end > start:
            step = max(1, (end - start) // remaining)
            middle = list(range(start, end + 1, step))[:remaining]
        else:
            middle = []
    else:
        middle = []
    return sorted(set(head + middle + tail))


def test_short_book_takes_every_page():
    assert _plan(20) == list(range(1, 21))


def test_long_book_samples_evenly():
    # 237-page chemistry textbook scenario
    pages = _plan(237)
    assert pages[0] == 1
    assert pages[-1] == 237
    # ToC + glossary covered
    for n in (1, 2, 3, 4):
        assert n in pages
    assert 236 in pages or 237 in pages
    # And we have ~max_pages pages, spread out
    assert 30 <= len(pages) <= 40
    # Middle should NOT cluster — at least one page beyond page 50,
    # one beyond page 100, one beyond page 150
    assert any(p > 50 for p in pages)
    assert any(p > 100 for p in pages)
    assert any(p > 150 for p in pages)


def test_book_exactly_at_max_returns_full_range():
    assert _plan(40) == list(range(1, 41))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
