"""Tests for shared agent helpers."""

from src.agents.base_agent import strip_code_fence


class TestStripCodeFence:
    def test_plain_json(self):
        assert strip_code_fence('{"a": 1}') == '{"a": 1}'

    def test_fenced_json(self):
        assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fenced_no_lang(self):
        assert strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_whitespace_around(self):
        assert strip_code_fence('  ```json\n{"a": 1}\n```  ') == '{"a": 1}'

    def test_no_fence_passthrough(self):
        text = '{"client_id": "CLT-10001"}'
        assert strip_code_fence(text) == text
