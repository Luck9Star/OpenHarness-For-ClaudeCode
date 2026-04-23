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

## 安装

```bash
# 方式一：启动时指定插件目录
claude --plugin-dir /path/to/openharness-cc

# 方式二：克隆到 Claude Code 插件目录
git clone https://github.com/Luck9Star/OpenHarness-For-ClaudeCode ~/.claude/plugins/openharness-cc
```

安装后，在任意项目目录启动 Claude Code 即可使用 `/harness-start`、`/harness-dev`、`/harness-status` 命令。

## 使用流程

### 第一步：初始化任务 `/harness-start`

告诉 Claude Code 你要做什么。插件会自动生成合约文件。

```bash
/harness-start "为当前项目添加用户注册和登录功能" --verify "npm test"
```

**这条命令会做什么：**

1. 在当前项目目录下创建 `.claude/harness-state.local.md`（状态文件）
2. 生成 `mission.md` — 任务合约，定义"做什么"和"什么算完成"
3. 生成 `playbook.md` — 执行步骤，Agent 按步骤执行
4. 生成 `eval-criteria.md` — 验证标准，每步完成后外部验证
5. 生成 `progress.md` — 进度日志，记录每次执行结果

**参数说明：**

| 参数 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `"任务描述"` | 是 | 一句话描述你想让 Agent 完成什么 | `"构建 REST API"` |
| `--mode single\|dual` | 否 | 执行模式，默认 `single`（见下方说明） | `--mode dual` |
| `--verify "命令"` | 否 | 每步完成后自动运行的验证命令 | `--verify "npm test"` |

### 第二步：启动开发循环 `/harness-dev`

Agent 开始自主工作，循环执行直到任务完成。

```bash
/harness-dev --verify "npm test"
```

**这条命令会做什么：**

1. 读取 `mission.md` 了解任务目标
2. 读取 `playbook.md` 按步骤执行
3. 每完成一个步骤：
   - 运行 `--verify` 指定的命令（如 `npm test`）
   - 派生独立的 eval-agent 做 Oracle 隔离验证
   - 验证通过 → 进入下一步
   - 验证失败 → 读取错误，自动修复，重试
4. 连续失败 3 次 → **断路器触发**，自动停止，防止无限循环浪费 token
5. 全部步骤完成且验证通过 → 循环退出

**参数说明：**

| 参数 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `--mode single\|dual` | 否 | 执行模式，默认 `single` | `--mode dual` |
| `--verify "命令"` | 否 | 每步完成后的验证命令，失败则自动修复重试 | `--verify "pytest"` |
| `--max-iterations N` | 否 | 最大循环次数，0 表示无限（默认） | `--max-iterations 10` |

### 第三步（可选）：查看状态 `/harness-status`

随时查看当前任务进度。

```bash
/harness-status
```

显示：任务名称、执行模式、当前步骤、失败次数、断路器状态、总执行次数。

## `--verify` 的作用

`--verify` 是 OpenHarness 外部验证机制的核心抓手。它指定一条**客观的、机器可执行的命令**，用来判断当前步骤是否真正完成。

**为什么需要它：** Agent 不能自我认证"我做完了"——这是 Harness Engineering 的基本原则。必须通过外部命令来验证。

**常用示例：**

```bash
# Node.js 项目
/harness-dev --verify "npm test"

# Python 项目
/harness-dev --verify "pytest"

# 带构建检查
/harness-dev --verify "npm run build && npm test"

# 自定义验证脚本
/harness-dev --verify "bash scripts/check.sh"
```

如果不指定 `--verify`，Agent 仍会执行 playbook 步骤，但只使用 eval-agent 做主观验证（检查文件是否存在、内容是否合理等），缺少客观的自动化检测。

## 执行模式

### Single 模式（默认）

```
主 Agent（规划 + 编码）→ eval-agent（独立验证）→ 通过/失败
```

Agent 自己规划步骤，自己写代码，但**验证环节由独立的 eval-agent 完成**。适合 bugfix、单文件修改、小功能开发。

### Dual 模式

```
主 Agent（只规划）→ dev-agent（隔离 worktree 中编码）→ eval-agent（独立验证）→ 通过/失败
```

规划和编码严格分离。主 Agent 写 tech spec，派生 `harness-dev-agent` 在独立 git worktree 中实现代码，eval-agent 验证。适合多模块开发、架构重构等需要严格隔离的场景。

```bash
/harness-dev --mode dual --verify "npm test"
```

## 完整工作流示例

```
你在 Claude Code 中输入:
  /harness-start "为 Express 应用添加 JWT 认证中间件" --verify "npm test"

插件自动生成:
  mission.md      → 定义目标：实现 JWT 认证，所有测试通过
  playbook.md     → 步骤：1.安装依赖 2.写中间件 3.写路由 4.写测试
  eval-criteria.md → 验证：测试通过、中间件文件存在、路由受保护
  harness-state.local.md → 状态：idle, Step 1

你启动循环:
  /harness-dev --verify "npm test"

第1轮循环:
  → 读状态文件: Step 1
  → 执行: 安装 jsonwebtoken 等依赖
  → 验证: npm test → PASS
  → 状态更新: Step 1 完成，进入 Step 2

第2轮循环:
  → 读状态文件: Step 2
  → 执行: 编写 auth.middleware.js
  → 验证: npm test → FAIL (缺少测试用例)
  → 自动修复: 补充测试
  → 验证: npm test → PASS
  → 状态更新: Step 2 完成，进入 Step 3

...（自动继续直到所有步骤完成）

最终:
  → 所有步骤完成 + 验证通过
  → 输出 <promise>LOOP_DONE</promise>
  → 循环退出
```

## 安全机制

| 机制 | 说明 |
|---|---|
| 断路器 | 连续 3 次验证失败后自动停止，防止无限循环浪费 token |
| PreToolUse Hook | 自动阻止违反 `mission.md` 禁止操作的文件写入 |
| Oracle 隔离 | eval-agent 无法看到主 Agent 的推理过程，只看工作区产物 |
| 状态文件保护 | `mission.md` 和状态文件在初始化后变为只读，Agent 不可修改 |

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
