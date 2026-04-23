# OpenHarness-CC 优化分析

> 基于 GLM-5.1 长程任务最佳实践文档，对照 openharness-cc 当前实现，输出可落地的优化建议。

## 一、对齐度总览

| 文档要求的五层 harness | openharness-cc 覆盖情况 | 状态 |
|------------------------|------------------------|------|
| 循环层（loop） | `/loop` 集成 + `harness-execute` skill | 已覆盖 |
| 状态层（外部文件） | 三层记忆：state(<2KB) + knowledge + execution_stream.log | 已覆盖 |
| 工具层（shell/git/测试） | 通过 Claude Code 内置工具隐式提供 | 部分覆盖 |
| 验证层（eval/check） | Oracle 隔离 eval-agent + verify_instruction | 已覆盖 |
| 安全层（断路器/hook） | 断路器(3次) + PreToolUse hook + 状态只读 | 已覆盖 |

## 二、已对齐的实践

| 文档最佳实践 | openharness-cc 实现 |
|-------------|-------------------|
| 任务目标写清"可交付结果" | `mission.md` 包含 Mission Objective、Done Definition、Output Definition |
| 把任务拆成阶段 | `playbook.md` 动态生成 implement/review/fix/verify 步骤 |
| 状态外置，不靠上下文 | `harness-state.json` + `progress.md` + `logs/execution_stream.log` |
| 每轮"做事+验证+记录"闭环 | execute skill 10 步 workflow：读状态→执行→验证→更新状态 |
| 持续验证，不可自我认证 | Oracle 隔离 eval-agent，独立于主 Agent |
| 安全边界保护 | 断路器(3次失败停止) + PreToolUse hook 阻止违规写入 |

## 三、可进一步优化的点

### P0：每轮结构化报告（"四问"闭环）

**文档要求（3.4 节）：** 每一轮必须回答四个问题——当前子任务是什么、这轮准备怎么做、怎么判断做成了、结果更新到哪。

**当前差距：** execute skill 的日志是自由格式文本（`state-manager.py log "xxx"`），没有结构化。多轮执行后，很难回溯每一轮的具体决策和结果。

**优化方案：** 在 execute skill 步骤 5（执行当前步骤）开头，增加结构化每轮报告模板：

```markdown
## Round Report
- **当前子任务:** <从 playbook 当前步骤提取>
- **执行策略:** <这轮准备怎么做>
- **验证方法:** <怎么判断做成了>
- **状态更新目标:** <结果写入哪个文件>
```

**改动范围：** `skills/harness-execute/SKILL.md` 步骤 5，`scripts/state-manager.py` 增加 `report` 子命令。

**预期效果：** execution_stream.log 从自由文本变为结构化记录，后续 dream skill 和人工审查都能快速理解每轮决策。

---

### P0：阶段性人工 Review 节点

**文档要求（第五节/第六节）：** 在关键节点安排人工 review——最小版本跑通后、核心功能补齐后、交付前各一次。

**当前差距：** openharness-cc 有 `review` 步骤类型，但只派生 AI review-agent，没有暂停等人工确认的机制。loop 会一直跑下去，直到任务完成或断路器触发。

**优化方案：** 增加 `human-review` 步骤类型。执行到此步骤时：

1. 输出当前进展摘要到终端
2. 输出 `<promise>LOOP_PAUSE</promise>` 暂停循环
3. 用户通过 `/harness-dev` 或 `--resume` 恢复执行

playbook 模板在动态生成时，根据任务复杂度自动插入 human-review 节点：
- 简单任务：不插入
- 中等任务：在 50% 进度处插入一次
- 复杂任务：在 33%、66%、100% 各插入一次

**改动范围：** `skills/harness-init/SKILL.md`（模板生成逻辑）、`skills/harness-execute/SKILL.md`（增加 human-review 处理）、`scripts/state-manager.py`（增加 pause/resume 状态）。

---

### P1：目标/验收文件分离

**文档要求（3.1 节 + 3.3 节）：** 建议准备独立文件：goal.md（目标和边界）、acceptance.md（验收标准）、todo.md（拆解和状态）、progress.md（每轮进展）。

**当前差距：** openharness-cc 把目标和验收都放在 `mission.md`，待办和步骤放在 `playbook.md`，进展在 `progress.md`。粒度不够细。

**优化方案：**

| 当前文件 | 拆分后 | 说明 |
|---------|--------|------|
| mission.md | goal.md | 只保留目标、边界、禁止操作 |
| mission.md | acceptance.md | Done Definition 提取为独立验收清单 |
| playbook.md | todo.md | 当前阶段待办清单（自动从 playbook 提取未完成步骤） |
| progress.md | progress.md | 保持不变 |

init skill 模板相应调整，从 4 个文件扩展为 5 个。

**改动范围：** `skills/harness-init/SKILL.md`、`templates/` 目录模板文件。

---

### P1：策略自动切换（功能→集成）

**文档要求（第五节）：** 长程任务中后段应从"做功能"自动切换到"做集成和收敛"。前半段是"把东西做出来"，后半段是"把东西接起来"，两种策略不能混着写。

**当前差距：** playbook 是静态生成的，所有 implement 步骤的策略相同。不会根据执行进度自动调整。

**优化方案：** 在 execute skill 的步骤 9（Mission Completion Check）中增加进度感知：

```
if completed_steps / total_steps >= 0.6:
    inject "integration-mode" constraint:
    - 不新增非必要模块
    - 优先修复模块间依赖和交互问题
    - 补充 README 和启动说明
```

这个约束以 `harness-state.json` 的标记位实现，execute skill 读取后调整后续 implement 步骤的执行策略。

**改动范围：** `skills/harness-execute/SKILL.md` 步骤 9、`scripts/state-manager.py`。

---

### P2：一键验证脚本生成

**文档要求（3.3 节）：** 建议准备 `run.sh` / `test.sh` 一键运行或验证脚本。

**当前差距：** openharness-cc 的 eval-agent 执行 `verify_instruction`，但这是框架层面的验证。项目本身没有自动生成的一键验证脚本。

**优化方案：** init skill 在分析项目结构时，根据检测到的技术栈自动生成验证脚本：

| 检测到的标记文件 | 生成脚本 |
|----------------|---------|
| package.json | `test.sh: npm test` + `run.sh: npm start` |
| requirements.txt / pyproject.toml | `test.sh: pytest` + `run.sh: python main.py` |
| go.mod | `test.sh: go test ./...` + `run.sh: go run .` |
| Cargo.toml | `test.sh: cargo test` + `run.sh: cargo run` |

生成的脚本写入 `eval-criteria.md` 的验证方法中，eval-agent 可直接调用。

**改动范围：** `skills/harness-init/SKILL.md` 步骤 5、`templates/eval-criteria.md`。

---

### P2：工具层可用性检测

**文档要求（第四节/第六节）：** 工具层是五层 harness 之一，需要确保 shell、git、测试脚本等工具可用。

**当前差距：** openharness-cc 不检测工具可用性。如果项目缺少测试框架，eval-agent 的验证会失败但不知道原因。

**优化方案：** init 阶段增加工具扫描，结果写入状态文件：

```markdown
## Tool Availability
- [x] git: available
- [x] node: v20.11.0
- [x] npm: 10.2.4
- [ ] pytest: NOT FOUND
- [x] docker: available
```

eval-agent 在验证前先检查工具可用性，缺失工具时给出明确提示而非模糊的验证失败。

**改动范围：** `skills/harness-init/SKILL.md` 步骤 5（增加工具检测）、`templates/mission.md`（增加工具声明字段）。

---

### P3：独立 todo.md 自动维护

**文档要求（3.3 节）：** todo.md 维护任务拆解和当前状态。

**当前差距：** "当前待办"信息散落在 playbook.md（全部步骤）和 harness-state.json（当前步骤序号）。没有独立的"当前阶段待办清单"。

**优化方案：** 每次 step-advance 时，自动从 playbook.md 提取剩余步骤生成/更新 `todo.md`：

```markdown
## TODO
- [x] Phase 1: 搭建骨架
- [x] Phase 2: 实现核心模块
- [ ] Phase 3: 集成测试 ← current
- [ ] Phase 4: 文档和收敛
```

**改动范围：** `scripts/state-manager.py` step-advance 子命令、`skills/harness-execute/SKILL.md` 步骤 7。

## 四、案例复盘：任务定义失配导致一轮完成

### 背景

用户执行 `/harness-start "评审当前项目中 rust 的实现，还需要检查是否与 Python cli 进行了对齐，完善补齐 E2E 测试，检查修复 rust 的性能情况。迭代开发时候最多生成 2 个子 Agent。" --mode dual --verify "单元测试成功，E2E 的 CLI 测试通过"`

Playbook 生成了 7 个步骤（Code Review → implement → Review Checkpoint → Fix → ... → verify），但一轮就全部跑完并输出 `LOOP_DONE`。

### 问题拆解

**问题 1：任务目标包含"不可机器验证"的维度**

"评审 Rust 实现"是主观判断，不是可交付产物。Agent 把"评审"执行成了 clippy 清理 + 恢复误删函数——这是 `implement` 级别的工作，不是 `review` 级别的架构审查。

**问题 2：`--verify` 只覆盖了任务的一个维度**

任务有 4 个维度（评审、对齐、测试、性能），但 `--verify` 只写了"单元测试成功，E2E 的 CLI 测试通过"。eval-agent 拿着这个 verify instruction 跑 `cargo test`，当然一轮就过。

**问题 3：没有结构化的每轮报告**

Agent 自述"540+ tests, 0 failures"、"17 benches pass"，但没有"怎么判断做成了"的结构化回答。review 步骤做成了表层指标检查（clippy warnings=0），没有深入到每个 crate 的设计模式、跨 crate 依赖合理性、接口抽象层级。

**问题 4：缺少人工 Review 节点**

7 个步骤一口气跑完，没有在关键节点（如 Code Review 完成后）暂停让用户确认审查深度是否足够。

### 与优化项的映射

| 根因 | 对应优化项 | 解决方案 |
|------|-----------|---------|
| "评审"无交付标准 | P0: 每轮四问结构化报告 | 强制要求"怎么判断做成了"有具体标准 |
| verify 只覆盖测试 | 新增: 任务定义指导 | README 中加入 prompt 编写指南，明确 verify 应覆盖所有维度 |
| review 做成 implement | P0: 阶段性人工 Review | review 步骤后暂停，用户确认深度 |
| 一口气跑完 | P0: 阶段性人工 Review | 关键节点插入 LOOP_PAUSE |
| 后半段未收敛 | P1: 策略自动切换 | 60% 进度后切换为集成模式 |

### 改进后的 Prompt 示例

**方案 A：拆任务（推荐）**

```bash
# 任务 1：纯评审（交付物是评审报告）
/harness-start "对当前项目 Rust 实现（6 crate）进行深度代码评审。
交付物：一份评审报告，覆盖架构设计、跨 crate 依赖合理性、
错误处理策略一致性、public API 设计是否符合 Rust 惯用法、
并发安全性。每个问题标注严重等级(critical/major/minor)。"
--verify "评审报告文件存在且包含每个 crate 的至少 3 条具体发现，
所有 critical 发现都有修复建议"

# 任务 2：CLI 对齐
/harness-start "检查 Rust CLI 与 Python CLI 的命令/参数/输出对齐，
修复所有差异"
--verify "对齐报告存在且 E2E CLI 测试全部通过"

# 任务 3：性能优化
/harness-start "检查并优化 Rust 性能瓶颈"
--verify "benchmark 全部在阈值内，无性能回归"
```

**方案 B：单任务但精确 verify**

```bash
/harness-start "完成以下 4 项工作：
1. 深度评审 Rust 6 crate 的架构/API/并发安全，产出评审报告
   （每 crate >=3 条发现，标注严重等级）；
2. 产出 CLI 对齐报告，修复所有差异；
3. 补齐 E2E 测试，覆盖所有子命令；
4. 运行 benchmark，优化超阈值项。
最多 2 个子 Agent。" \
--mode dual \
--verify "
  1. 评审报告存在且每 crate 有 >=3 条具体发现（非 clippy 级别）；
  2. CLI 对齐报告存在且所有差异已修复；
  3. cargo test 全部通过（含 E2E）；
  4. benchmark 全部在阈值内"
```

**关键改动**：
- "评审"变成了有具体交付标准的产物（报告文件 + 数量标准）
- verify 覆盖了全部 4 个维度
- 交付物是文件，不是行为——eval-agent 可以读文件验证

---

## 五、优先级排序与案例复盘

| 优先级 | 优化项 | 改动量 | 预期收益 |
|--------|--------|--------|---------|
| **P0** | 每轮四问结构化报告 | 小（改 skill + script） | 执行可追溯性大幅提升，防止"看起来一直在忙但没形成进展" |
| **P0** | 阶段性人工 Review 节点 | 中（新增步骤类型 + pause 机制） | 防止一轮跑完但质量不达标（见第四章案例） |
| **P1** | 目标/验收文件分离 | 中（重构 init 模板） | 任务定义更清晰 |
| **P1** | 策略自动切换（功能→集成） | 小（改 execute skill） | 长程任务收敛更可靠 |
| **P2** | 一键验证脚本生成 | 小（扩展 init 模板） | eval-agent 验证更有效 |
| **P2** | 工具层可用性检测 | 小（init 阶段增加扫描） | 减少无谓的验证失败 |
| **P3** | 独立 todo.md 自动维护 | 小（改 state-manager） | 进度可视化更直观 |

## 六、实施建议

建议按 P0 → P1 → P2 → P3 顺序分批实施。每批完成后跑一次完整的 `/harness-start` → `/harness-dev` 循环验证。

**第一批（P0，预计改动 2-3 个文件）：**
- execute skill 增加结构化报告模板
- state-manager.py 增加 report 子命令
- 新增 human-review 步骤类型 + LOOP_PAUSE 机制

**第二批（P1，预计改动 3-4 个文件）：**
- init 模板拆分 mission.md → goal.md + acceptance.md
- execute skill 增加进度感知和策略切换逻辑

**第三批（P2+P3，预计改动 2-3 个文件）：**
- init 阶段增加工具检测 + 验证脚本生成
- state-manager step-advance 自动维护 todo.md
