"""Shared test isolation."""

from __future__ import annotations

from typing import Any, NoReturn

import pytest
import requests


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_request(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError('Tests must mock HTTP transport')

    monkeypatch.setattr(requests.Session, 'request', reject_request)
