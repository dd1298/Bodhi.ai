"""Verify the JSON salvage path in llm_adapter.parse_json_response handles
the exact truncation patterns observed in production (output cut mid-stream
before the closing brace) without losing already-completed questions."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from llm_adapter import parse_json_response  # noqa: E402


def test_wellformed_paper_still_parses_directly():
    raw = '{"sections": [{"title": "S1", "questions": [{"question": "hi"}]}]}'
    d = parse_json_response(raw)
    assert d["sections"][0]["questions"][0]["question"] == "hi"
    assert not d.get("_recovered_from_truncation")


def test_truncated_mid_question_array_recovers_complete_items():
    raw = (
        '{\n'
        '  "instructions": "Answer all questions.",\n'
        '  "sections": [\n'
        '    {"title": "Section A", "questions": [\n'
        '      {"question": "What is 2+2?", "options": ["3","4","5","6"], "correct_option": 1, "format": "mcq", "marks": 1},\n'
        '      {"question": "What is 5x5?", "options": ["20","25","30","35"], "correct_option": 1, "format": "mcq", "marks": 1},\n'
        '      {"question": "What is the capital of Fra'
    )
    d = parse_json_response(raw)
    assert d["_recovered_from_truncation"] is True
    qs = d["sections"][0]["questions"]
    assert len(qs) == 2  # 3rd was incomplete, dropped
    assert qs[0]["question"] == "What is 2+2?"
    assert qs[1]["question"] == "What is 5x5?"
    assert d["instructions"] == "Answer all questions."


def test_truncated_before_any_complete_question_raises():
    """User's actual production payload: cut off mid-section title BEFORE
    any question objects exist — nothing salvageable, must still error."""
    raw = (
        '{ "instructions": "Answer all questions.", '
        '"sections": [ { "title": "Section A - Information Bas'
    )
    with pytest.raises(ValueError):
        parse_json_response(raw)


def test_well_formed_answers_solution_path():
    raw = '{"answers": [{"q": "1", "a": "2"}, {"q": "3", "a": "4"}]}'
    d = parse_json_response(raw)
    assert len(d["answers"]) == 2


def test_truncated_solution_answers_array_recovers():
    raw = (
        '{"answers": ['
        '{"question_id": "abc", "answer": "Step 1: ... Step 2: ..."},'
        '{"question_id": "def", "answer": "Step 1: ... Step 2: half-fin'
    )
    d = parse_json_response(raw)
    assert "answers" in d
    assert len(d["answers"]) == 1
    assert d["answers"][0]["question_id"] == "abc"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
