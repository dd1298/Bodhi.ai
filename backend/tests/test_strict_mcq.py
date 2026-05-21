"""Verify strict_mcq normalisation drops anything that isn't a complete
4-option MCQ when the locked format mandates 100% MCQ."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from competitive_routes import _normalise_questions  # noqa: E402


def test_strict_mcq_drops_non_mcq_items():
    sections = [{
        "title": "S1",
        "questions": [
            {  # valid
                "question": "Q1", "format": "mcq",
                "options": ["a", "b", "c", "d"], "correct_option": 2,
            },
            {  # numerical, no options → DROP
                "question": "Q2 numerical", "format": "numerical",
            },
            {  # short answer with options missing → DROP
                "question": "Q3 short", "format": "short_answer",
            },
            {  # only 3 options → DROP
                "question": "Q4", "format": "mcq",
                "options": ["a", "b", "c"], "correct_option": 0,
            },
            {  # correct_option out of range → DROP
                "question": "Q5", "format": "mcq",
                "options": ["a", "b", "c", "d"], "correct_option": 9,
            },
            {  # valid even though format label missing — we force mcq
                "question": "Q6", "options": ["w", "x", "y", "z"], "correct_option": 0,
            },
        ],
    }]
    kept = _normalise_questions(sections, "medium", strict_mcq=True)
    questions = sections[0]["questions"]
    assert len(kept) == 2  # Q1 and Q6
    assert all(q["format"] == "mcq" for q in questions)
    assert all(len(q["options"]) == 4 for q in questions)
    assert all(0 <= q["correct_option"] <= 3 for q in questions)


def test_lenient_keeps_non_mcq():
    sections = [{
        "title": "S1",
        "questions": [
            {"question": "Q1", "format": "mcq",
             "options": ["a", "b", "c", "d"], "correct_option": 1},
            {"question": "Q2", "format": "numerical"},  # KEPT in lenient
        ],
    }]
    kept = _normalise_questions(sections, "medium", strict_mcq=False)
    assert len(kept) == 2
    # numerical question should have options popped
    numerical = [q for q in kept if q["format"] == "numerical"][0]
    assert "options" not in numerical
    assert "correct_option" not in numerical


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
