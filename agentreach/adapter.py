from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass
class ContentItem:
    """
    Common representation of content from any source.

    Every ingestion connector (Reddit, dev.to, Medium, Substack,
    Hacker News, Agent-Reach, etc.) should return this object.
    """

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
    Central ingestion layer.

    Today:
        - Reads sources.yaml
        - Exposes one fetch() method
        - Individual source methods are placeholders

    Later:
        - Calls Agent-Reach connectors
        - Normalizes everything into ContentItem objects

    The rest of the pipeline should ONLY call fetch().
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent
        self.config_path = (
            Path(config_path)
            if config_path
            else base_dir / "sources.yaml"
        )

        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}

        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def fetch(self) -> list[ContentItem]:
        """
        Fetch content from every configured source.

        Phase 2:
            Returns an empty list because connectors
            are not implemented yet.

        Phase 3:
            Each fetch_* method will call Agent-Reach
            (or another connector) and return normalized
            ContentItem objects.
        """

        items: list[ContentItem] = []

        items.extend(self.fetch_reddit())
        items.extend(self.fetch_devto())
        items.extend(self.fetch_medium())
        items.extend(self.fetch_hackernews())
        items.extend(self.fetch_substack())

        return items

    # -------------------------------------------------------
    # Source connectors (Phase 2 placeholders)
    # -------------------------------------------------------

    def fetch_reddit(self) -> list[ContentItem]:
        return []

    def fetch_devto(self) -> list[ContentItem]:
        return []

    def fetch_medium(self) -> list[ContentItem]:
        return []

    def fetch_hackernews(self) -> list[ContentItem]:
        return []

    def fetch_substack(self) -> list[ContentItem]:
        return []
