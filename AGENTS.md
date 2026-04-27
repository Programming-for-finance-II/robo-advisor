# AGENTS.md — AI Agents Strategy

## Project: AI-Powered Robo-Advisor Platform
**Course:** Programming in Finance II (2026) — USI  
**Design version:** v3.1 Smart Single Portfolio (EU-Aware)

---

## Agent Roles

### Agent 1: CI Validator (ci.yml)
- **Trigger:** Every push and PR to `main`
- **Role:** Runs `ruff check` (lint) and `pytest` (test suite)
- **Output:** Green/red status on every PR — blocks merge on failure

### Agent 2: Docstring PR Agent (agent_pr.yml)
- **Trigger:** `workflow_dispatch` or push to `backend/optimizer/`
- **Role:** Calls Claude API to generate/update docstrings in the optimizer module
- **Output:** Opens an automatic PR with diff and descriptive body
- **Status:** 🔜 Planned for Week 4 (P1 owner)

---

## Agentic Workflow Philosophy

This project is organized as an agentic project per Prof. Gruber's requirements.
AI agents contribute to:
1. **Code quality enforcement** (CI agent — automated)
2. **Documentation generation** (Docstring PR agent — Claude API)
3. **Development assistance** (Claude used interactively by all team members)

All AI tool usage is acknowledged in the academic PDF (Section 7: Lessons Learned).

---

## Evidence Log

| Date | Agent | Action | PR / Link |
|------|-------|--------|-----------|
| *To be populated during development* | | | |

---

## Notes for Graders
The `agent_pr.yml` workflow (Week 4) will demonstrate a full agentic loop:
GitHub Actions triggers → Claude API called → code diff generated → PR opened automatically.
This satisfies the mandatory criterion: *"at least one pull request made by an AI agent."*