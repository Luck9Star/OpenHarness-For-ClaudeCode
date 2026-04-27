# Agent Index

OpenHarness agent templates use YAML frontmatter (`name`, `description`, `category`, `model`, `tools`, `route_keywords`) followed by Markdown prompt body.

## Meta-Process Layer (`agents/meta/`)

Framework-coupled agents that orchestrate the development loop.

| Agent | Purpose | Writes? | Model |
|-------|---------|---------|-------|
| [harness-dev-agent](meta/harness-dev-agent.md) | Code executor — implements from tech spec | Yes | default |
| [harness-eval-agent](meta/harness-eval-agent.md) | Oracle-isolated independent validator | No | sonnet |
| [harness-review-agent](meta/harness-review-agent.md) | Read-only cumulative code reviewer | No | sonnet |

## Domain Capability Layer (`agents/domain/`)

Standalone expertise agents — can be used inside or outside harness workflows.

| Agent | Domain | Writes? | Route Keywords |
|-------|--------|---------|----------------|
| [security-engineer](domain/security-engineer.md) | Threat modeling, vuln assessment, secure code | Yes | security, auth, OWASP, encryption |
| [code-reviewer](domain/code-reviewer.md) | Deep code review, correctness, maintainability | No | review, quality, refactor |
| [database-optimizer](domain/database-optimizer.md) | Schema design, query tuning, migrations | Yes | database, schema, query, SQL |
| [api-tester](domain/api-tester.md) | API validation, performance, security testing | Yes | api, endpoint, integration, REST |
| [evidence-collector](domain/evidence-collector.md) | Evidence-based QA, reality checking | No | QA, evidence, verify, quality |
| [devops-automator](domain/devops-automator.md) | CI/CD, IaC, deployment, monitoring | Yes | deploy, CI/CD, Docker, Kubernetes |

## Routing

`harness-dev` skill auto-selects domain agents via `route_keywords` matching against step descriptions. Manual override via playbook `specialist:` field takes precedence.
