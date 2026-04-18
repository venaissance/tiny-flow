"""Async background compaction — main agent never blocks on summarization."""
from .async_runner import AsyncCompactor, ensure_message_ids, get_async_compactor

__all__ = ["AsyncCompactor", "ensure_message_ids", "get_async_compactor"]
