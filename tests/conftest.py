"""Pytest fixtures for the test suite."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.config.settings import APIConfig, SimulationDefaults


@pytest.fixture
def api_config() -> APIConfig:
    """Return a test API configuration."""
    return APIConfig()


@pytest.fixture
def simulation_params() -> dict:
    """Return default simulation parameters plus a hidden cause."""
    defaults = SimulationDefaults()
    params = defaults.model_dump()
    params["hidden_cause"] = "Test hidden cause for unit tests"
    return params


@pytest.fixture
def mock_llm_response():
    """Return a mock LLMResponse object."""
    mock = MagicMock()
    mock.content = "Test output"
    mock.tokens_used = 100
    mock.model = "test-model"
    mock.finish_reason = "stop"
    mock.attempt_count = 1
    return mock