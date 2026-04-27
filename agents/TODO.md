# Agent Backlog

Agents identified as valuable for future inclusion, sourced from agency-agents and other references.

## Tier 2 — Next Batch (7 agents)

| Source | Agent | Rationale | Priority |
|--------|-------|-----------|----------|
| `engineering-rapid-prototyper.md` | Rapid Prototyper | MVP/POC fast iteration for early project phases | High |
| `engineering-ai-engineer.md` | AI Engineer | ML model deployment, AI integration for AI-heavy projects | High |
| `engineering-technical-writer.md` | Technical Writer | Docs, API references, README generation | Medium |
| `engineering-git-workflow-master.md` | Git Workflow Master | Branch strategy, conventional commits enforcement | Medium |
| `engineering-incident-response-commander.md` | Incident Commander | Incident management, postmortem for production issues | Medium |
| `testing-performance-benchmarker.md` | Performance Benchmarker | Load testing, profiling, optimization for perf-critical work | High |
| `testing-accessibility-auditor.md` | Accessibility Auditor | WCAG compliance, assistive tech for a11y requirements | Low |

## Tier 3 — On Demand (add when project needs arise)

| Source | Agent | Trigger Scenario |
|--------|-------|-----------------|
| `engineering-sre.md` | SRE | SLO/error budget/observability needs |
| `engineering-data-engineer.md` | Data Engineer | Data pipeline / ETL projects |
| `engineering-mobile-app-builder.md` | Mobile App Builder | iOS/Android projects |
| `engineering-solidity-smart-contract-engineer.md` | Solidity Engineer | Blockchain / Web3 projects |
| `engineering-cms-developer.md` | CMS Developer | WordPress / Drupal projects |
| `engineering-email-intelligence-engineer.md` | Email Intelligence | Email parsing / MIME processing |
| `engineering-voice-ai-integration-engineer.md` | Voice AI Engineer | Voice-to-text / Whisper integration |
| `engineering-wechat-mini-program-developer.md` | WeChat Mini Program | WeChat ecosystem projects |
| `engineering-feishu-integration-developer.md` | Feishu Integration | Lark / Feishu platform projects |
| `engineering-filament-optimization-specialist.md` | Filament Specialist | Laravel Filament admin panels |
| `product-product-manager.md` | Product Manager | Full-lifecycle product ownership |
| `product-product-sprint-prioritizer.md` | Sprint Prioritizer | Agile planning, backlog grooming |
| `specialized-workflow-architect.md` | Workflow Architect | Complex multi-step workflow design |
| `specialized-mcp-builder.md` | MCP Builder | MCP server development |
| `specialized-document-generator.md` | Document Generator | PDF/PPTX/DOCX/XLSX generation from code |

## Routing Integration

Once `harness-dev` skill routing is implemented, each new agent needs:
1. `route_keywords` in frontmatter for auto-discovery
2. Registration in `AGENTS.md` index
3. Route entry in `harness-dev/loop-reference.md` if it has special spawn behavior

## Adaptation Checklist (per agent)

When porting from agency-agents:
- [ ] Add `category: domain` to frontmatter
- [ ] Add `model:` and `tools:` fields
- [ ] Add `route_keywords:` for auto-discovery
- [ ] Remove `color:`, `emoji:`, `vibe:` fields (not used by openharness-cc)
- [ ] Remove agency-agents specific file path references (e.g., `ai/agents/qa.md`)
- [ ] Clean up agency-agents platform-specific assumptions
- [ ] Verify agent prompt aligns with harness output expectations
