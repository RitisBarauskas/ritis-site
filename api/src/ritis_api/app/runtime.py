from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

# Injected so that use cases stay deterministic under test.
Clock = Callable[[], datetime]
IdFactory = Callable[[], str]
