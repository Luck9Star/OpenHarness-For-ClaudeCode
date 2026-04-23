# OpenHarness for Claude Code

基于 [OpenHarness](https://github.com/thu-nmrc/OpenHarness) Harness Engineering 原则，为 Claude Code 适配的自主 AI Agent 执行框架。

[English](README.en.md) | 中文

## 它做什么

通过**机械约束、外部审计、100% 可追溯**，将 Claude Code 变成 24/7 自主开发工作者：

- **机器可验证合约** — 客观的"完成"判定条件，拒绝主观判断
- **Oracle 隔离验证** — 独立 agent 验证你的工作，你不能自我认证
- **断路器保护** — 连续 3 次失败后自动停止
- **三层记忆** — 状态指针 (<2KB) + 知识文件 + 执行流日志
- **可切换执行模式** — single（规划+编码）或 dual（规划 → 派生编码 agent）
- **`/loop` 集成** — 无需外部 cron，使用 Claude Code 内置循环

## 快速开始

```bash
# 安装插件
claude --plugin-dir /path/to/openharness-cc

# 初始化新任务
/harness-start "构建用户管理的 REST API" --verify "npm test"

# 启动自主开发循环
/harness-dev --mode single --verify "npm test"

# 查看当前状态
/harness-status
```

## 命令

| 命令 | 说明 |
|---|---|
| `/harness-start` | 初始化新的 harness 任务（创建 mission、playbook、eval criteria） |
| `/harness-dev` | 启动自主开发循环（single 或 dual 模式） |
| `/harness-status` | 显示工作区状态、进度和断路器状态 |

## 架构

```
openharness-cc/
  skills/          5 个行为技能（core, init, execute, eval, dream）
  commands/        3 个斜杠命令（start, dev, status）
  agents/          2 个自主 agent（dev-agent, eval-agent）
  hooks/           3 个事件 hook（SessionStart, PreToolUse, Stop）
  scripts/         4 个工具脚本（state-manager, eval-check, setup-loop, cleanup）
  templates/       4 个脚手架模板（mission, playbook, eval-criteria, progress）
```

## 执行模式

### Single 模式（默认）
主 agent 同时负责规划和编码。eval-agent 独立验证。适合 bugfix、单文件修改、小功能。

### Dual 模式
主 agent 只负责规划，派生 `harness-dev-agent` 在隔离 worktree 中编码。eval-agent 验证。适合多模块开发、架构重构。

## 核心工作流

```
/harness-start "任务描述"
  → 创建 mission.md（合约）+ playbook.md（步骤）+ eval-criteria.md（验证标准）
  → 初始化 .claude/harness-state.local.md（状态文件）

/harness-dev --verify "npm test"
  → Stop Hook 驱动每轮循环
  → 每轮: 读状态 → 执行 playbook 步骤 → spawn eval-agent 验证 → 更新状态
  → 连续失败 >= 3 → 断路器触发，停止执行
  → 全部完成 → <promise>LOOP_DONE</promise> → 循环退出
```

## OpenHarness 映射

| OpenHarness (OpenClaw/Codex) | 本插件 |
|---|---|
| `cron` + `harness_setup_cron.py` | `/loop` 内置命令 |
| `harness_coordinator.py` | Claude Code agent spawning + worktree |
| `harness_eval.py` | `harness-eval-agent`（Oracle 隔离） |
| `harness_boot.py` 断路器 | Stop hook + 状态文件 |
| `harness_dream.py` | `harness-dream` skill + `/loop 24h` |
| `harness_linter.py` | PreToolUse hook |
| `heartbeat.md` | `.claude/harness-state.local.md` |

## 许可证

基于 [OpenHarness](https://github.com/thu-nmrc/OpenHarness) by thu-nmrc (BSL 1.1)。
本 Claude Code 适配版本按原样提供。
