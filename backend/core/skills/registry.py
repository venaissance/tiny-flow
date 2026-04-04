"""Skill discovery — scans directories for SKILL.md files."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from threading import Lock
from typing import Any

from .types import Skill

logger = logging.getLogger(__name__)

_cache: list[Skill] | None = None
_cache_lock = Lock()


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    meta: dict[str, Any] = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if value.startswith("[") and value.endswith("]"):
            value = [i.strip().strip("\"'") for i in value[1:-1].split(",") if i.strip()]
        elif value.isdigit():
            value = int(value)
        meta[key] = value

    return meta, match.group(2).strip()


def _load_skill(skill_md: Path) -> Skill | None:
    try:
        content = skill_md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        return Skill(
            name=meta.get("name", skill_md.parent.name),
            description=meta.get("description", ""),
            content=body,
            path=skill_md,
            triggers=meta.get("triggers", []),
            execution_mode=meta.get("execution_mode", "prompt_injection"),
            tools=meta.get("tools", []),
            priority=int(meta.get("priority", 0)),
            timeout=int(meta.get("timeout", 300)),
        )
    except Exception as e:
        logger.warning(f"Failed to load skill from {skill_md}: {e}")
        return None


def scan_skills(dirs: list[str | Path]) -> list[Skill]:
    skills: list[Skill] = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for skill_dir in sorted(d.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skill = _load_skill(skill_md)
                if skill:
                    skills.append(skill)
    return skills


def get_all_skills(dirs: list[str | Path] | None = None) -> list[Skill]:
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        if dirs is None:
            base = Path(__file__).parent.parent.parent
            dirs = [base / "skills"]
        _cache = scan_skills(dirs)
        return _cache


def reload_skills(dirs: list[str | Path] | None = None) -> list[Skill]:
    global _cache
    with _cache_lock:
        _cache = None
    return get_all_skills(dirs)
