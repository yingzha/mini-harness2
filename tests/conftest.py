"""Fixtures shared by the lesson tests."""

import pytest

import config
from steps.s02_executor import Sandbox


@pytest.fixture(scope="session")
def sandbox() -> Sandbox:
    """The real sandbox: tests run model-written code exactly as rollouts do."""
    return Sandbox.from_docker(config.SANDBOX)
