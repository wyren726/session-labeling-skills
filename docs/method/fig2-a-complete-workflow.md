# Fig. 2(a) Session 分析与候选筛选流程

## 文档目的

本文整理 Fig. 2(a) 所表达的完整方法流程，供方法汇报、流程图说明和后续 `session-labeling-skills` 重构使用。它描述的是**目标方法及其语义边界**，不表示当前仓库已经完整实现所有环节。后续代码、数据合同、提示词、测试和审计材料应以本文确认后的内容为依据。

整理依据包括历史仓库 `wyren726/mlcoding-trace-analysis` 中的用户侧分析、Agent 核验与归因、痛点结果构造及 Stage 06 筛选逻辑，以及 `wyren726/session-labeling-skills` 现有 canonical 命名和确定性筛选设计。历史语义基线为 `mlcoding-trace-analysis@7af6547d3cbb0ff00ac5612d132006c720feed57`；新仓库核对基线为 `session-labeling-skills@bcedd6d00b0b4ebc38d30c09ce248d9c719f117c`。

## 流程总览

```text
Raw sessions
  → 1 Normalize
  → 2 Detect needs
  → 3 Verify & attribute
  → 4 Label
  → 5 Select
  → 6 Audit & export
  → Selected sessions
```

Raw sessions 是输入，Selected sessions 是输出；中间六项是处理步骤。该图是面向读者的整合视图，不是历史仓库 Stage 01–06 的逐项改名：历史 Stage 02 的用户侧分析、Stage 03 的 Agent 核验、Stage 04 的结果构造、Stage 05 的报告发布，以及 Stage 06 的增量标注和筛选，在整合后的流程中按职责重新组织。报告或发布属于分析结果的呈现，不应被误认为新的任务判断门槛。

| 步骤 | 输入 | 主要处理 | 输出 |
|---|---|---|---|
| 1 Normalize | 原始 session 记录 | 解析并标准化记录、轮次和事件，保留原始来源、稳定标识及工具调用/结果关联 | 可追溯的标准化 session、turn、event 序列 |
| 2 Detect needs | 标准化后的真实用户消息 | 识别连续任务片段、初步目标、需求及演进、用户侧候选反馈信号 | Episode 初步理解及带用户原文依据的候选信号 |
| 3 Verify & attribute | 用户侧初步理解、候选信号及 Episode 完整交互证据 | 核对真实目标、需求完成情况和问题；分析问题是否与 Agent 有关、可能原因及有证据支持的能力缺口 | 经核验的任务/需求结果、问题与归因记录、证据及未决项 |
| 4 Label | 经核验的任务信息、需求、证据和标签体系 | 对任务需求做 taxonomy 映射，并评估任务难度等属性 | 结构化标签、映射、支持证据和语义判断 |
| 5 Select | 标签、关联证据、适用范围和 selection policy | 运行前置检查并核验 S1–S4，按决策表分流 | selected、not_selected、pending_review 或 invalid 及逐项理由 |
| 6 Audit & export | 筛选决定、标签/分析记录、原始 session 与来源信息 | 重算和核对决定、校验 schema/引用/来源，生成审计记录并导出入选原始 session | Selected sessions 及关联元数据、证据索引和审计记录 |

## 各阶段说明

### 1. Normalize：标准化会话并保留来源

**输入：** 原始 session 记录，可能包含用户消息、Agent 回复、模型/工具调用、工具结果、错误、附件或其他记录。

**处理：** 将记录转成有序的规范结构，恢复 session、turn、event 标识及记录间关系；关联工具调用与工具结果；保存原始来源位置、来源快照/哈希、解析限制和未知记录。标准化不能把工具调用等同于工具成功，也不能因无法解析而静默丢弃原始记录。

**输出：** 可供后续按 Episode 和事件回查的标准化会话。事件 ID、turn ID 和来源位置是分析证据的定位依据。

### 2. Detect needs：用户侧理解与反馈信号发现

本阶段只分析真实用户消息，建立待后续核验的任务理解。历史方法把用户侧信息组织为 R1–R8；它们是理解和路由信息，不可整体等同于后续的 S1–S4 选择规则。

| Rubric | 判断内容 | 典型输出 |
|---|---|---|
| R1 目标领域 | 任务属于目标领域、相邻领域、范围外或暂不确定 | 领域判断及用户证据 |
| R2 分析/构题价值 | 初步判断是否存在真实、有实质内容且原则上可验证的任务价值 | high / medium / low / uncertain 及理由；不能因对话短就判低 |
| R3 Episode 边界 | 按连续目标识别任务片段；背景补充、澄清、纠正、重试和返工通常留在同一 Episode；独立交付目标才拆分 | 起止 turn、边界判断和理由 |
| R4 初始 Query | 定位 Episode 中首次提出可执行核心任务的用户消息 | Query turn 与理由 |
| R5 初始 Query 清晰度 | 仅按提出 Query 时可用的用户上下文判断清晰程度 | clear / partly_clear / unclear 及理由 |
| R6 初步目标与需求 | 根据用户消息形成待完整交互验证的目标假设及需求 | preliminary goal、需求、各自用户来源证据 |
| R7 需求演进 | 区分对原意的澄清、对既有要求的纠正、后来真正新增的要求 | clarification / correction / new_requirement 及原文证据 |
| R8 候选反馈信号 | 识别值得进入完整交互核验的用户侧信号 | signal 类型、用户事件和连续原文引用 |

候选信号类型沿用历史分析语义：`explicit_rejection`、`result_defect`、`constraint_repeated`、`redo_or_rollback`、`retry_after_failure`、`user_takeover`、`blocked_or_abandoned`。候选信号表达“需要进一步查看什么”，不表达“Agent 已失败”。普通澄清、回答澄清问题、正常新增要求、中性追问、正常推进、“继续/下一步/再看看”或单纯没听懂，都不能自动当作痛点信号。

**输入/证据边界：** 本阶段不能看 Agent 回复、工具结果或隐藏推理来判定 Agent 责任。需求和信号应引用真实用户事件；quote 必须是对应消息中的连续原文。用户侧无法确定的内容应标为 uncertain/insufficient，而不是补猜。

**输出：** Episode 边界、初步目标/需求及变化记录、R1–R8 判断、候选信号及用户侧证据。这些输出等待下一阶段验证，不是已确认的失败分析。

### 3. Verify & attribute：完整交互核验及原因归因

本阶段使用完整 Episode 证据，而不只是上一阶段的摘要或用户反馈。必要时也可查看 Episode 末端之后明确标记的后续用户上下文，用于判断用户是否查看、评价或继续修改交付物；该上下文不得反向变成 Episode 内新增需求。

**核验材料包括：** 用户消息、Agent 回复、工具调用、工具结果、错误、可观察产物/文件/测试结果，以及与这些事件相关的来源索引。工具调用只证明尝试；成功应由结果、产物、测试或用户确认等可观察证据支持。

**核验与归因至少回答：**

1. 用户侧 preliminary goal 是否成立、需要修订，或仍不足以判断；
2. 每项用户需求是否满足、部分满足、未满足或未知，并分别链接需求来源证据与完成状态证据；
3. 每个候选信号是否对应真实问题，还是正常澄清/迭代、新增需求、权限限制、外部故障、用户输入不足等其他情况；
4. 可观察任务结果如何，以及 Agent 自称完成与证据核验结果是否一致；
5. 问题是否可归因于 Agent；若可归因，记录归因类别、理由和有证据支持的具体 capability gap；若证据不足，保留未决并说明还缺什么证据。

分析中必须分开记录：**用户表达不满或反馈信号、任务/需求是否失败、问题是否与 Agent 有关、Agent 的能力缺口是什么。** 其中任何一项都不能单独推出其他项。尤其是在判定未响应、未执行或中断前，应检查目标用户指令之后全部可观察的 Agent、工具和产物事件；若 Agent 回复因用户主动打断而不完整，不能仅凭不完整输出判作 Agent 能力失败。主动打断本身也不能说明具体不满原因，必须结合后续用户表达核对。

归因类别沿用历史体系的语义范围，至少能区分推理/回答、执行/验证、工具、上下文、权限、外部因素、用户输入和未知等原因。归因应基于具体事件证据；不能因最终 outcome 为 failure 就自动判 `agent_related=true`。只有 Agent 责任成立且有证据支持时才记录 capability gap；该 gap 是失败分析注释，不是第 4 步的任务能力 taxonomy 标签。

**输出：** 目标核验结果、逐项需求结果、任务结果、问题/Agent 责任判断、归因类别、能力缺口、精确证据引用、证据充分性和 limitations/待查项。此阶段不决定 S1–S4 是否通过。

### 4. Label：任务能力映射与属性标注

本阶段针对 Episode 所表达的任务需求，使用统一 capability taxonomy 建立需求—能力映射，并评估任务难度等属性；每个判断需链接已校验的证据，不能仅凭关键词匹配或发明用户未提出的验收标准。

图中 `Capability · Difficulty` 是标签内容的简写，不是完整标签目录。taxonomy mapping 表达“任务需要什么能力”；第 3 步的 capability gap 表达“核验到的 Agent 问题暴露了什么能力不足”。二者目的、证据语境和数据字段均不同，不能互相替代或合并。pain/失败归因状态也不是任务标签或 S1–S4 决定。

**输出：** taxonomy 映射、难度等任务属性、标签 claim、证据引用、未解决判断及限制。primary/auxiliary 等筛选角色应由配置/程序规则决定，不交由模型臆定。

### 5. Select：按既定 Policy 执行 Prechecks 与 S1–S4

选择阶段独立读取结构化标签、证据和适用 policy。历史选择语义及当前配置所定义的核心规则为：

| 检查 | 含义 | 通过条件概要 |
|---|---|---|
| Prechecks | 结构、证据引用、选择范围及关键未决冲突是否可接受 | 按 policy 逐项判定；无效结构/引用不能当作质量失败 |
| S1 Evidence-backed | 至少一个 primary 主需求能力映射有支持证据 | 存在有效证据支持的 primary mapping；仅 auxiliary 不满足 S1 |
| S2 Challenging | 任务是否有实质性挑战 | 难度为 medium/high；low 经核验可判不入选，未知则待复核 |
| S3 Recoverable goals | 是否能从记录连贯还原任务要求 | 有依据判定目标/需求可连贯还原；信息不足为 pending |
| S4 Checkable outcome | 是否有可核对的完成条件 | 有依据说明可判定任务完成与否；信息不足为 pending |

四项规则对应图中的简短英文标签。筛选采用 `selected`、`not_selected`、`pending_review`、`invalid` 四类 canonical 决定；历史报告中 `priority_candidate`、`review` 是相应兼容用语。只有前置检查和 S1–S4 都通过才 selected；任一已核验失败可 not_selected；无已确认排除条件但存在未知/待查项时为 pending_review；结构或引用错误归为 invalid。

用户侧 R1–R8 和第 3 步痛点核验不替代 S1–S4。候选信号存在不加分，候选信号缺失也不自动扣分；Agent 失败不是通用入选前提。历史执行记录明确：confirmed/review 痛点状态本身不作为通用任务筛选的加分项或排除项；如果另行开展痛点专题，应单独定义入口和规则，不能暗改通用 Policy。

### 6. Audit & export：审计决定并交付入选会话

审计环节验证从原始来源到分析、标签和选择决定的关联关系，包括 schema、session/Episode/event/evidence ID、精确引用、来源快照、policy 与产物版本；重新计算可确定性重算的选择逻辑，检查导出清单与决定是否一致。

**输出：** 审计记录、入选 session 清单/原始 session 导出，以及可回查的 Episode、标签、选择理由、元数据和证据索引。候选语料及关联元数据的交付不表示已生成完整 Benchmark task，也不自动表示 workspace 已获取、任务可复现或 Agent 曾成功完成任务。workspace、材料完整性及后续复现可行性应在后续环节评估。

## 关键概念边界

| 概念 | 回答的问题 | 不能据此推出 |
|---|---|---|
| 候选反馈信号 | 哪些用户消息值得回查完整交互？ | Agent 已失败或应归责 Agent |
| 问题/需求结果 | 用户要求是否满足、任务发生了什么？ | 失败必然由 Agent 造成 |
| Agent 责任归因 | 问题是否有证据表明与 Agent 行为有关，可能原因是什么？ | 可以跳过 S1–S4 或自动入选 |
| Capability gap | 已核验的 Agent 问题暴露出什么能力缺口？ | 等同于任务需求的 taxonomy mapping |
| Taxonomy mapping | 任务需要哪些能力？ | 代表 Agent 在该会话中失败 |
| S1–S4 selection | 该 Episode 是否满足通用候选集的筛选标准？ | 已完成 Benchmark 构造、workspace 获取或复现验证 |

## 流程输出及保密边界

本流程对外交付的是经过筛选的原始 session 及其关联分析元数据和证据索引。图示或方法说明应使用抽象流程和经过授权的示意信息，不披露完整真实任务包或含隐私信息的原始会话。报告案例若需展示，应另行确认可披露范围和脱敏方式；不能为了填图而编造任务事实、标签、失败归因或模型成绩。

## 面向后续实现的约束

后续依据本文重构时，应将语义合同贯穿 schema、prompt、规范化/验证逻辑、Skill 文档、selection/audit、checkpoint 兼容和测试；不能只增加字段或改流程图。关键测试至少覆盖：正常澄清和“继续”不自动成为候选痛点、用户信号必须来自 Episode 内真实用户事件及精确 quote、完整交互证据可以推翻表面信号、无充分证据时归因保持未决、capability gap 与 taxonomy mapping 分离、候选信号/归因不改变既有 S1–S4 决策，以及旧 checkpoint 在合同变更后的正确失效或迁移。

## 参考实现

- 历史用户侧分析与 Agent 核验：`mlcoding-trace-analysis` Stage 02/03，基线提交 `7af6547d3cbb0ff00ac5612d132006c720feed57`。
- 历史痛点结果构造和筛选说明：`mlcoding-trace-analysis` 的 Stage 04 builder 与 `docs/TRACE_SCREENING_WORKFLOW.md`。
- 新仓库现有规范化、canonical artifacts、taxonomy 和 S1–S4 policy：`session-labeling-skills`，核对基线提交 `bcedd6d00b0b4ebc38d30c09ce248d9c719f117c`。

文档版本：0.1（待方法负责人确认；确认后作为后续实现基线）。
