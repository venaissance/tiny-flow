"""Extract facts from conversation using LLM."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from .storage import Fact

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """分析以下对话，提取值得长期记住的事实。
只提取以下类别：
- preference: 用户的偏好和习惯
- context: 用户的工作背景、项目信息
- behavior: 用户的交互模式
- knowledge: 用户已掌握的知识领域

不要提取：临时性信息、本次对话特有的调试细节、代码片段。

输出 JSON 数组，每项包含 "content" 和 "category"。
如果没有值得提取的信息，输出空数组 []。

对话内容：
{conversation}"""


def extract_facts(messages: list[BaseMessage], model: Any, thread_id: str = "") -> list[Fact]:
    conversation = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
        for m in messages
        if isinstance(m.content, str) and m.content.strip()
    )
    if not conversation.strip():
        return []

    prompt = EXTRACT_PROMPT.format(conversation=conversation)
    try:
        response = model.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        items = json.loads(content)
        if not isinstance(items, list):
            return []
        return [
            Fact(content=item["content"], category=item.get("category", "context"), source_thread=thread_id)
            for item in items if "content" in item
        ]
    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")
        return []
