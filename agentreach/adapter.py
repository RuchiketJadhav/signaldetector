from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass
class ContentItem:
    platform: str
    title: str
    body: str
    url: str
    engagement: int = 0
    community: str | None = None
    tags: list[str] | None = None
    author: str | None = None
    created_at: str | None = None


class AgentReachAdapter:
    """
    Phase 2 adapter stub.

    In Phase 3, this will:
    - read sources.yaml
    - call the source-specific ingestion logic
    - normalize everything into ContentItem objects
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent
        self.config_path = Path(config_path) if config_path else base_dir / "sources.yaml"
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def fetch(self) -> list[ContentItem]:
        """
        Phase 2 stub: return no data yet.
        This lets you wire the adapter into the app without changing the rest.
        """
        return []
