"""Tests for configuration loading."""

import os
import tempfile

from agentmux.config import load_config


class TestLoadConfig:
    def test_default_config_when_no_file(self):
        config = load_config("/nonexistent/path.yaml")
        assert config.default_provider == "claude"
        assert config.question_timeout == 300.0

    def test_load_from_yaml(self):
        content = """
default_provider: ollama
question_timeout: 60
providers:
  ollama:
    model: deepseek-coder
aliases:
  ol: ollama
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            config = load_config(f.name)

        os.unlink(f.name)

        assert config.default_provider == "ollama"
        assert config.question_timeout == 60.0
        assert "ollama" in config.providers
        assert config.aliases["ol"] == "ollama"

    def test_env_var_substitution(self):
        os.environ["AGENTMUX_TEST_KEY"] = "my-secret-key"
        content = """
default_provider: claude
providers:
  claude:
    api_key: ${AGENTMUX_TEST_KEY}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            config = load_config(f.name)

        os.unlink(f.name)
        del os.environ["AGENTMUX_TEST_KEY"]

        assert config.providers["claude"]["api_key"] == "my-secret-key"

    def test_env_var_default(self):
        content = """
default_provider: claude
providers:
  claude:
    api_key: ${NONEXISTENT_VAR:-fallback-value}
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            config = load_config(f.name)

        os.unlink(f.name)

        assert config.providers["claude"]["api_key"] == "fallback-value"

    def test_empty_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            config = load_config(f.name)

        os.unlink(f.name)

        assert config.default_provider == "claude"
