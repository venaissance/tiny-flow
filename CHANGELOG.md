# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-04-11

### Added
- ReAct Agent architecture for subagents — Observe-Think-Act loop with multi-tool support
- MiniMax M2.7 model support as default LLM provider
- Skill tool integration — agents can invoke local skills (pulse, frontend-slides, etc.)
- ExecutorPool replacing bare ThreadPool with timeout support for ultra mode
- Dispatch node for ultra mode parallel task distribution
- Skill node for skill-matched query routing
- Skill awareness in plan generation
- Current date injection into ReAct prompts
- Pulse E2E test suite (298 tests) and ReAct agent test suite (303 tests)

### Fixed
- Reflector loop — use explicit 'done' route to prevent infinite loops
- `<think>` block stripping for MiniMax M2.7 compatibility
- Duplicate content emission from reflector node
- Duplicate execution prevention in ReAct loop
- Recursion limit configuration (set in graph config, not compile)
- Sequential compound tasks correctly routed to pro mode

## [0.1.0] - 2026-04-06

### Added
- 4 execution modes: Flash (direct answer), Thinking (deep reasoning), Pro (plan & execute), Ultra (parallel research)
- LangGraph-based graph orchestration engine with configurable state machine
- 4-way intelligent router with middleware pipeline system
- TODO planning and tracking within execution flow
- Per-TODO real-time streaming updates via Server-Sent Events
- Auto Pro-to-Ultra upgrade when task complexity warrants it
- Per-thread independent SSE connections for concurrent execution
- Memory system with fact extraction, confidence scoring, and time-decay merging
- YAML-based skill plugin system with keyword matching and hot-reload
- Artifact panel with live HTML/CSS/JS preview
- Bilingual README (English + Chinese)
- CI/CD pipeline with GitHub Actions (backend tests, frontend tests, type checking)
- Comprehensive test suite: 257 backend (pytest) + 30 frontend (vitest) + 10 E2E (Playwright)

### Fixed
- Loop termination and detection in plan-execute cycles
- Ultra routing reliability for complex queries
- User copy button alignment in chat UI
- Step spinner persistence after completion
- Thread reload consistency
- Processing spinner persistence during execution
