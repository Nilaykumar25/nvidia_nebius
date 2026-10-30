"""Unit tests for provider.py — all pure-logic paths, no live API calls."""
from backend.app.llm.provider import _cache_key, _strip_think, parse_json


# ── cache key ───────────────────────────────────────────────────────────────

def test_cache_key_differs_by_model():
    k1 = _cache_key("model-a", "sys", "user")
    k2 = _cache_key("model-b", "sys", "user")
    assert k1 != k2


def test_cache_key_same_inputs_deterministic():
    k1 = _cache_key("nemotron-ultra", "sys", "user")
    k2 = _cache_key("nemotron-ultra", "sys", "user")
    assert k1 == k2


def test_cache_key_differs_by_prompt():
    k1 = _cache_key("nemotron-ultra", "sys-a", "user")
    k2 = _cache_key("nemotron-ultra", "sys-b", "user")
    assert k1 != k2


# ── think-block stripping ───────────────────────────────────────────────────

def test_strip_think_removes_block():
    raw = "<think>let me reason about this</think>\n{\"key\": \"value\"}"
    assert _strip_think(raw) == '{"key": "value"}'


def test_strip_think_multiline():
    raw = "<think>\nline1\nline2\n</think>\n{\"a\":1}"
    assert "{" in _strip_think(raw)
    assert "<think>" not in _strip_think(raw)


def test_strip_think_no_block_unchanged():
    raw = '{"decisions": []}'
    assert _strip_think(raw) == raw


def test_strip_think_case_insensitive():
    raw = "<THINK>reasoning</THINK>{\"x\":1}"
    assert "<THINK>" not in _strip_think(raw)


# ── parse_json ──────────────────────────────────────────────────────────────

def test_parse_json_plain():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_strips_markdown_fences():
    raw = "```json\n{\"decisions\": []}\n```"
    assert parse_json(raw) == {"decisions": []}


def test_parse_json_with_leading_think():
    raw = "<think>ignore this</think>\n```json\n{\"decisions\": [1]}\n```"
    assert parse_json(raw) == {"decisions": [1]}


def test_parse_json_raises_on_no_object():
    import pytest
    with pytest.raises((ValueError, Exception)):
        parse_json("this has no json at all")


def test_parse_json_extracts_from_prose():
    raw = 'Here is the answer: {"status": "ok"} as requested.'
    assert parse_json(raw) == {"status": "ok"}


def test_parse_json_nested():
    raw = '{"decisions": [{"title": "test", "spans": []}]}'
    result = parse_json(raw)
    assert result["decisions"][0]["title"] == "test"
