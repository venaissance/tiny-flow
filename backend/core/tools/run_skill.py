"""Run a Claude Code skill as a tool — enables agents to invoke local skills."""
from __future__ import annotations

import json
import logging
import subprocess

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool("run_skill", parse_docstring=True)
def run_skill(skill_name: str, args: str = "") -> str:
    """Run a Claude Code skill by name. Use this to invoke local skills like pulse, frontend-slides, etc.

    Args:
        skill_name: The skill name to invoke (e.g. "pulse", "frontend-slides").
        args: Optional arguments to pass to the skill.
    """
    try:
        cmd = ["claude", "-p", f"/{skill_name} {args}".strip()]
        logger.info(f"Running skill: {' '.join(cmd)}")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=None,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0 and proc.stderr:
            output += f"\n\nStderr: {proc.stderr.strip()}"
        return json.dumps({
            "status": "completed" if proc.returncode == 0 else "failed",
            "output": output[:5000],  # Cap output size
            "skill_name": skill_name,
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "timed_out", "error": f"Skill {skill_name} timed out after 300s"})
    except FileNotFoundError:
        return json.dumps({"status": "failed", "error": "claude CLI not found. Is Claude Code installed?"})
    except Exception as e:
        return json.dumps({"status": "failed", "error": str(e)})
