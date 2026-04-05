# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
