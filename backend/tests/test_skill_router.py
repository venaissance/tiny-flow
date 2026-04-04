"""Tests for skill registry and routing."""
import pytest
from pathlib import Path
from core.skills.registry import scan_skills, parse_frontmatter
from core.skills.router import keyword_filter, select_best_skill
from core.skills.types import Skill


class TestParseFrontmatter:
    def test_parse_basic(self):
        content = '---\nname: test\ndescription: "A test"\ntriggers: [a, b]\n---\nBody here.'
        meta, body = parse_frontmatter(content)
        assert meta["name"] == "test"
        assert meta["triggers"] == ["a", "b"]
        assert body == "Body here."

    def test_parse_no_frontmatter(self):
        meta, body = parse_frontmatter("Just text")
        assert meta == {}
        assert body == "Just text"


class TestRegistry:
    def test_scan_skills(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: test-skill\ndescription: "test"\ntriggers: [hello, world]\nexecution_mode: subagent\npriority: 5\ntimeout: 60\n---\nPrompt body'
        )
        skills = scan_skills([tmp_path])
        assert len(skills) == 1
        s = skills[0]
        assert s.name == "test-skill"
        assert s.execution_mode == "subagent"
        assert s.priority == 5
        assert s.triggers == ["hello", "world"]

    def test_scan_empty_dir(self, tmp_path):
        skills = scan_skills([tmp_path])
        assert skills == []


class TestSkillKeywordMatch:
    def test_match(self):
        s = Skill(name="x", description="", content="", path=Path("."), triggers=["review", "代码审查"])
        assert s.keyword_match("请帮我 review 这段代码") == 1
        assert s.keyword_match("我要代码审查和 review") == 2
        assert s.keyword_match("hello world") == 0


class TestKeywordFilter:
    def test_filters_matching(self):
        skills = [
            Skill(name="review", description="", content="", path=Path("."), triggers=["review", "审查"]),
            Skill(name="summarize", description="", content="", path=Path("."), triggers=["总结", "摘要"]),
            Skill(name="translate", description="", content="", path=Path("."), triggers=["翻译"]),
        ]
        result = keyword_filter(skills, "帮我 review 一下")
        assert len(result) == 1
        assert result[0].name == "review"

    def test_no_match_returns_empty(self):
        skills = [Skill(name="review", description="", content="", path=Path("."), triggers=["review"])]
        result = keyword_filter(skills, "hello world")
        assert result == []

    def test_sorts_by_match_count_then_priority(self):
        skills = [
            Skill(name="a", description="", content="", path=Path("."), triggers=["code", "review"], priority=5),
            Skill(name="b", description="", content="", path=Path("."), triggers=["code"], priority=10),
        ]
        result = keyword_filter(skills, "code review")
        assert result[0].name == "a"


class TestSelectBestSkill:
    def test_single_candidate_no_llm(self):
        skills = [Skill(name="review", description="", content="", path=Path("."), triggers=["review"])]
        result = select_best_skill(skills, "review this code")
        assert result is not None
        assert result.name == "review"

    def test_no_match(self):
        skills = [Skill(name="review", description="", content="", path=Path("."), triggers=["review"])]
        result = select_best_skill(skills, "hello world")
        assert result is None
