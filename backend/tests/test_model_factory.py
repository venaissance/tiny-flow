# tests/test_model_factory.py
"""P0 tests for model factory and provider detection."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from core.models.providers import detect_provider


# ═══════════════════════════════════════════════════════════════════════════
# detect_provider
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectProvider:
    def test_claude_sonnet(self):
        assert detect_provider("claude-sonnet-4") == "claude"

    def test_claude_opus(self):
        assert detect_provider("claude-opus-4-20250514") == "claude"

    def test_claude_case_insensitive(self):
        assert detect_provider("Claude-3-Haiku") == "claude"

    def test_glm_flash(self):
        assert detect_provider("glm-4-flash") == "glm"

    def test_glm_case_insensitive(self):
        assert detect_provider("GLM-4") == "glm"

    def test_gpt4o(self):
        assert detect_provider("gpt-4o") == "openai"

    def test_gpt4o_mini(self):
        assert detect_provider("gpt-4o-mini") == "openai"

    def test_unknown_defaults_to_openai(self):
        assert detect_provider("some-random-model") == "openai"


# ═══════════════════════════════════════════════════════════════════════════
# create_chat_model
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateChatModel:
    def test_creates_anthropic_for_claude(self):
        mock_cls = MagicMock()
        with patch("core.models.factory.detect_provider", return_value="claude"), \
             patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            from core.models.factory import create_chat_model
            create_chat_model(name="claude-sonnet-4")
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4"
        assert call_kwargs.kwargs["streaming"] is True

    def test_creates_openai_for_gpt(self):
        mock_cls = MagicMock()
        with patch("core.models.factory.detect_provider", return_value="openai"), \
             patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}):
            from core.models.factory import create_chat_model
            create_chat_model(name="gpt-4o")
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["model"] == "gpt-4o"

    def test_creates_openai_with_glm_base_url(self):
        mock_cls = MagicMock()
        with patch("core.models.factory.detect_provider", return_value="glm"), \
             patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=mock_cls)}), \
             patch.dict("os.environ", {"GLM_API_KEY": "test-key"}, clear=False):
            import os
            from core.models.factory import create_chat_model
            create_chat_model(name="glm-4-flash")
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["model"] == "glm-4-flash"
        assert "bigmodel.cn" in call_kwargs["base_url"]

    def test_claude_thinking_enabled(self):
        mock_cls = MagicMock()
        with patch("core.models.factory.detect_provider", return_value="claude"), \
             patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=mock_cls)}):
            from core.models.factory import create_chat_model
            create_chat_model(name="claude-sonnet-4", thinking_enabled=True)
        call_kwargs = mock_cls.call_args.kwargs
        assert "thinking" in call_kwargs
        assert call_kwargs["thinking"]["type"] == "enabled"


# ═══════════════════════════════════════════════════════════════════════════
# get_default_model
# ═══════════════════════════════════════════════════════════════════════════


class TestGetDefaultModel:
    def test_reads_from_config(self, tmp_config):
        """Uses tmp_config fixture to verify config file parsing."""
        with patch("core.models.factory._CONFIG_PATH", tmp_config):
            from core.models.factory import _load_config
            _load_config.cache_clear()
            from core.models.factory import get_default_model
            assert get_default_model() == "gpt-4o-mini"
            _load_config.cache_clear()

    def test_missing_config_defaults_to_gpt4o(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        with patch("core.models.factory._CONFIG_PATH", missing):
            from core.models.factory import _load_config
            _load_config.cache_clear()
            from core.models.factory import get_default_model
            assert get_default_model() == "gpt-4o"
            _load_config.cache_clear()
