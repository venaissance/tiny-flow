---
name: summarize
description: "总结长文本或对话内容"
triggers: [summarize, 总结, 摘要, 概括]
execution_mode: prompt_injection
priority: 5
timeout: 60
---

请对用户提供的内容进行简洁的结构化总结。输出格式：
- 核心要点（3-5 条）
- 关键细节
- 结论/建议（如适用）
