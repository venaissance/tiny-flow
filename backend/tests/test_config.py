"""Config validation tests — verify config.yaml schema and constraints."""
from __future__ import annotations

import yaml
from pathlib import Path

import pytest

# The production config loader lives in core.models.factory._load_config.
# We test the real config.yaml directly rather than going through the cached loader,
# to avoid polluting the lru_cache during tests.

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@pytest.fixture
def config():
    """Load config.yaml as a plain dict for every test."""
    assert CONFIG_PATH.exists(), f"config.yaml not found at {CONFIG_PATH}"
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "config.yaml must parse to a dict"
    return data


# ---------------------------------------------------------------------------
# Top-level load
# ---------------------------------------------------------------------------

class TestConfigLoad:
    def test_loads_successfully(self, config):
        assert config is not None

    def test_top_level_sections_exist(self, config):
        for section in ("model", "executor", "memory", "skills", "graph"):
            assert section in config, f"Missing top-level section: {section}"


# ---------------------------------------------------------------------------
# model.*
# ---------------------------------------------------------------------------

class TestModelConfig:
    def test_default_is_non_empty_string(self, config):
        default = config["model"]["default"]
        assert isinstance(default, str)
        assert len(default) > 0


# ---------------------------------------------------------------------------
# executor.*
# ---------------------------------------------------------------------------

class TestExecutorConfig:
    def test_scheduler_workers_positive_int(self, config):
        val = config["executor"]["scheduler_workers"]
        assert isinstance(val, int)
        assert val > 0

    def test_execution_workers_positive_int(self, config):
        val = config["executor"]["execution_workers"]
        assert isinstance(val, int)
        assert val > 0

    def test_default_timeout_positive(self, config):
        val = config["executor"]["default_timeout"]
        assert isinstance(val, (int, float))
        assert val > 0


# ---------------------------------------------------------------------------
# memory.*
# ---------------------------------------------------------------------------

class TestMemoryConfig:
    def test_token_budget_positive(self, config):
        val = config["memory"]["token_budget"]
        assert isinstance(val, (int, float))
        assert val > 0

    def test_decay_factor_range(self, config):
        val = config["memory"]["decay_factor"]
        assert isinstance(val, (int, float))
        assert 0 < val <= 1, f"decay_factor must be in (0, 1], got {val}"

    def test_min_confidence_range(self, config):
        val = config["memory"]["min_confidence"]
        assert isinstance(val, (int, float))
        assert 0 < val <= 1, f"min_confidence must be in (0, 1], got {val}"

    def test_max_facts_positive(self, config):
        val = config["memory"]["max_facts"]
        assert isinstance(val, int)
        assert val > 0


# ---------------------------------------------------------------------------
# graph.*
# ---------------------------------------------------------------------------

class TestGraphConfig:
    def test_max_iterations_positive(self, config):
        val = config["graph"]["max_iterations"]
        assert isinstance(val, int)
        assert val > 0


# ---------------------------------------------------------------------------
# skills.*
# ---------------------------------------------------------------------------

class TestSkillsConfig:
    def test_dirs_is_list(self, config):
        val = config["skills"]["dirs"]
        assert isinstance(val, list)
