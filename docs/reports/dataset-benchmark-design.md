# 从数据源到论文：YGO-Bench 数据集与评测设计 v0.1

更新日期：2026-07-20

## 当前最强判断

经过实际采样与覆盖率审计后，项目的主要风险已经不是“有没有数据”，而是**能否用这些数据构造出有效、可归因、抗污染的证据**。

卡牌文本、可执行脚本、禁限表和完整构筑足以支持第一阶段研究；公开数据无法直接支持“模型会像顶尖人类一样构筑/对战”的强结论，因为现有构筑源大多只有最终牌表，缺少逐步构筑决策、matchup、胜负和选择理由，高质量逐动作 duel log 也仍然缺失。

因此推荐把论文中心收紧为：

> **LLM/Agent 能否把静态卡牌与环境知识转化为引擎可验证的规则判断、构筑决策和完整对局能力？哪些微观能力缺陷与 harness 设计决定了最终对局表现？**

这比“游戏王版 PTCG-Bench”更强，也比直接宣称“做一个游戏王 agent”更可验证。

## 本地覆盖率证据

历史审计脚本见 `scripts/legacy/windows/audit_local_coverage.ps1`，审计结果见 `data/coverage/local-coverage.json`。该脚本尚待迁移为 WSL Python 入口。

| 项目 | 审计结果 | 含义 |
|---|---:|---|
| BabelCDB 卡牌/文本连接行 | 14,605 | 卡面与引擎静态数据完整对齐 |
| Official CardScripts | 13,420 | 覆盖 CDB 的 91.30%；不能把无脚本直接当作缺失 |
| ygo-agent 示例牌组 | 31 | 全部 Main Deck 为合法的 40-60 张范围 |
| 示例牌组唯一 ID | 604 | 601 个在当前 CDB，覆盖率 99.50% |
| 在 CDB 但无 official script 的牌组 ID | 14 | 全部是普通怪兽或 token，按设计不需要效果脚本 |
| CDB 中缺失的牌组 ID | 3 | 旧 token 引用，应在导入时规范化，而非视为卡片缺失 |
| TCG 2026.05 禁限表对齐 | 229/229 | 可直接用于当前 TCG snapshot |
| World 2026.05 禁限表对齐 | 274/274 | 可直接用于 Worlds snapshot |
| OCG 2026.07 禁限表对齐 | 198/200 | 需检查两个新/临时 ID |
| GOAT 对当前 CDB 对齐 | 1,492/1,704 | 跨时代实验不能复用当前 CDB，必须单独固定历史 snapshot |

这里最重要的结论有两个：

1. **现代 TCG pilot 的引擎数据覆盖已经足够。** 不需要先解决整个游戏王历史卡池。
2. **snapshot 是一等实体。** GOAT、Rush、OCG、TCG 和不同禁限时期不能共享一个“最新数据库”后声称历史有效。

## 数据能支持什么，不能支持什么

| Claim | 当前数据是否支持 | 正确做法 |
|---|---|---|
| 模型能否判断具体状态下的合法动作 | 支持 | 用 ygopro 生成状态与 legal set，构造最小反事实对 |
| 模型能否预测效果结算后的状态变化 | 支持 | 用 engine state delta 作自动 verifier |
| 模型是否理解响应时点 | 支持 | 从 response window 提取 pass/action 决策并做局部 rollout |
| 模型能否构筑合法牌组 | 支持 | 卡池 + LFLists + 数量/Extra/Side 约束自动验证 |
| 模型能否补全像真实上位牌组的构筑 | 部分支持 | 对 curated deck 做 masked completion，并按时间/赛事切分 |
| 模型能否针对环境调整 Side Deck | 部分支持 | 需要 matchup/context 标签；可先做检索/补全，后用 paired rollout 验证 |
| 模型构筑一定具有竞技强度 | 暂不直接支持 | 最终牌表不是强度标签；需要 outcome 或 engine tournament |
| 模型能否模仿顶尖人类对局 | 不支持 | 缺少高质量人类 action trajectory 与决策理由 |
| agent 是否能完整对战 | 支持评测 | 用 harness 自行生成并记录完整可执行轨迹 |

## 修订后的四个 RQ

### RQ1：Rule Grounding

在固定规则快照和具体游戏状态中，模型能否预测合法动作、发动条件与下一状态，而不是复述卡片知识？

关键证据：legal-set F1、state-delta exact match、counterfactual flip accuracy、置信度校准。

### RQ2：Deck & Meta Competence

在给定卡池、禁限表、环境和 matchup 时，模型能否产生合法、合理且经 rollout 验证的 Main/Extra/Side 决策？

关键证据：hard-constraint pass rate、masked-card recovery、side-deck utility、paired rollout strength、diversity。

### RQ3：Micro-to-Macro Transfer

CardRule、DeckMeta、ChainTiming 和 Replanning 中，哪些指标能预测完整对局表现？静态卡片问答是否真的有迁移价值？

关键证据：跨模型/卡组的相关与回归分析、错误类型对失败回合的归因、控制卡组/先后手/seed 后的解释量。

### RQ4：Harness Responsibility

结构化 observation、legal actions、rule RAG、history/memory 与 planner 分别改善了什么？它们是在表达模型能力，还是替模型做掉核心任务？

关键证据：shown/hidden legal actions 双轨、逐组件消融、invalid rate、调用成本，以及微观能力到胜率的中介变化。

## 三层数据产品

所有层共享 `schemas/benchmark-record.schema.json`，尤其共享 snapshot、provenance、隐藏信息边界、split 和 verifier 定义。

### 1. CardRule

不要把普通卡片 QA 当作主要评测。主任务应从引擎状态生成：

| 子任务 | 输入 | 目标 | Verifier |
|---|---|---|---|
| LegalSet | player observation + card text/history | 全部合法动作 | ygopro legal action set |
| ResolveDelta | state + chosen action | canonical state delta | ygopro next state |
| CounterfactualRule | 只改变一个规则变量的状态对 | 标签是否随变量翻转 | paired engine execution |
| RuleEvidence | 状态 + 结论 | 相关卡片/FAQ/规则依据 | snapshot-locked retrieval + expert spot-check |

优先改变的反事实变量：once-per-turn 是否已使用、卡片位置、cost 是否可支付、target 是否仍合法、priority player、phase/sub-step、chain link、召唤限制、卡位和公开信息。

### 2. DeckMeta

DeckMeta v1 不应直接声称“评测最优构筑”，而应拆成可验证任务：

| 子任务 | 主要标签 | 价值 |
|---|---|---|
| LegalityAudit | 违规位置/卡片/数量与修复 | 硬规则 grounding |
| MaskedCompletion | 上位牌表中隐藏的若干卡位 | 主题、比例和共现理解 |
| TemporalBuild | 给定日期/地区/禁限表的构筑 | 环境与卡池 grounding |
| SideAdapt | 给定 matchup 和已知环境的换入换出 | 对手建模与风险管理 |
| RolloutRanking | 同约束下若干候选构筑的 paired rollout | 将“像人类牌表”与“实战强度”分开 |

必须加入非 LLM baseline：流行度、卡片共现、nearest-deck retrieval、约束求解器、进化/搜索和固定 bot rollout。自动化 Hearthstone deckbuilding 已显示，搜索与 surrogate 是构筑任务的自然强基线；只和 prompting baseline 比较不够。

### 3. DuelBench

| 子任务 | 核心难点 | 指标 |
|---|---|---|
| ChainTiming | 发动、等待或放弃响应 | missed-window、premature interaction、local utility |
| ComboPlan | 长组合与资源约束 | success、长度、资源 regret |
| InterruptionRecovery | 指定位置被打断后重规划 | recovery success、终局价值 |
| ActiveStateTracking | 多次动作后的状态更新/修正 | state accuracy、revision accuracy |
| FullDuel | 隐藏信息下完整对局 | Glicko-2、paired win rate、invalid rate、成本 |

主动记忆应单列，不只把 history 当 prompt 长度问题。GAMBIT 的核心观察是：静态检索接近满分并不代表能在多步交互中持续更新与修正状态。这正对应游戏王的 once-per-turn、已公开卡、剩余资源与召唤限制追踪。

## Split 与抗污染设计

仅做随机切分无效。建议同时维护：

1. `IID`：同卡池、未见局面。
2. `Composition-OOD`：单卡见过，但留出卡片交互对、matchup 或 combo 模板。
3. `Temporal`：按卡片发布时间、禁限表和赛事日期切分。
4. `Name-Masked`：匿名化卡名与 archetype 表面标记，但保留效果语义。
5. `Counterfactual`：公开常见局面的最小状态变体，防止攻略记忆直接命中。
6. `Private`：隐藏 scene generator seed、卡片组合和部分模板，仅通过 evaluator 运行。

TCG-Bench 通过隐藏卡片实现抵抗污染；游戏王无法隐藏既有卡片，因此必须依靠**隐藏状态生成器 + 组合留出 + 反事实对 + 动态对手**。Agent Island 的动态竞争思路可用于后续 leaderboard，但第一版仍需要固定 anchors 保证跨时间可比。

## Benchmark 防投机

BenchJack 表明 agent benchmark 即使没有专门训练，也会自然出现 reward hacking。YGO-Bench 至少要防：

- agent 读取 engine private state 或对手手牌。
- 利用 action ID/排序泄漏最优动作或卡片身份。
- 通过异常、超时、重试或非法动作改变计分。
- 读取 evaluator 文件、seed、完整牌库顺序或隐藏 label。
- 只优化存活回合/局部分数而拒绝推进游戏。
- harness 在失败时自动选择合法/默认动作，却把结果计入模型能力。

设计上应进程隔离 engine state 与 player observation；action ID 每局重映射；非法动作、fallback、重试与超时单独计数；最终发布前对 evaluator 做一次 adversarial audit。

## 与近期工作的关系

| 工作 | 对本项目的约束 | 我们应保留的差异 |
|---|---|---|
| [PTCG-Bench](https://arxiv.org/abs/2605.29653), 2026 | 已覆盖完整 TCG 对局、自演化和 harness ablation | 主贡献必须是响应窗口、分层诊断及微观到宏观迁移 |
| [TCG-Bench](https://openreview.net/forum?id=0HF2Dg0Ldx), 2025/2026 | 游戏 benchmark 必须考虑污染和可调难度 | 用真实规则引擎的私有状态生成与 counterfactual 难度代替隐藏虚构卡 |
| [BALROG](https://arxiv.org/abs/2411.13543), ICLR 2025 | 游戏环境应报告细粒度过程指标，不只成功率 | 游戏王提供规则语义、chain timing 与相同动作空间内的责任边界 |
| [AgentBoard](https://openreview.net/forum?id=09Y7J22N9c), 2024 | 只看最终 success 难以诊断 agent | 用 engine events 定义可复现的进度和错误分类 |
| [GAMBIT](https://openreview.net/pdf/da8ab00e1f37f8b8adb2050cb76e19ebcab44709.pdf), 2026 | 被动检索与主动状态更新能力存在差距 | 将 active state tracking 接到实际 chain/turn 约束和胜负结果 |
| [Predicting Drafted Deck Strength for MTG](https://arxiv.org/abs/2607.04782), 2026 | 构筑强度预测需要大规模真实 outcome/决策序列 | 游戏王最终牌表只能支持补全/约束任务，强度需 rollout 或新数据 |
| [Automated Hearthstone Deckbuilding](https://arxiv.org/abs/2112.03534), 2022 | 构筑有成熟搜索/quality-diversity baseline | DeckMeta 必须与搜索、共现和 surrogate 比，而非只做 LLM 排名 |
| [BenchJack](https://arxiv.org/abs/2605.12673), 2026 | agent benchmark 需要 adversarial security review | 发布前审计 hidden-state、fallback、action encoding 和 scoring |
| [YGO winning strategy hardness](https://arxiv.org/abs/2603.02863), 2026 | 一般形式的获胜策略判定不可计算 | 论文不能暗示求全局最优；应强调固定快照、有限牌组和有界预算 |

截至 2026-07-20，仍未发现专门评测 LLM/Agent 游戏王能力的公开完整 benchmark；但邻近工作已很密集，单纯“接上引擎跑胜率”的新意不够。

## 推荐的最小 Pilot

### 固定范围

- 环境：两个独立纸牌 snapshot，`TCG 2026.05 / KDE-E` 与 `OCG 2026.07 / JP`；单环境主结果分开报告，跨环境仅用于 adaptation 分析。
- 卡组：每个环境 4 个角色不同且与该 snapshot 对齐的 curated tournament decks：combo、midrange、control、blind-second 各 1。
- 引擎：当前已固定的 ygopro-core、CardScripts、BabelCDB 和 LFLists commits。
- 模型：3 个能力/成本档位；固定 temperature、token budget、重试和调用上限。

### 数据量

- CardRule：400 个状态，其中至少 100 组最小 counterfactual pairs。
- DeckMeta：100 个 legality/repair、200 个 masked completion、50 个 side-adapt 场景。
- DuelBench：200 个 decision points；其中 80 个 chain timing、80 个 interruption recovery、40 个 active-memory 长前缀。
- FullDuel：每个模型/harness 对固定 anchor 使用 25 个 paired seeds 并交换先后手，即每组 50 局。

### Harness 条件

1. `Capability`：canonical observation，不展示 legal actions，可检索固定 card/rule snapshot。
2. `Constrained Agent`：canonical observation + legal actions + recent exact history。
3. 可选递增：memory/planner，只在前两条跑通后加入。

### Go/No-Go 判据

继续扩容需要同时满足：

1. 相同 seed/action prefix 的 replay 与 label 重建成功率至少 99%。
2. observation boundary 测试没有对手手牌、牌库顺序或 private engine state 泄漏。
3. counterfactual 指标能区分至少两个模型或 harness，而不是全部接近随机/满分。
4. 至少一个 engine-grounded 微观指标对完整对局错误呈稳定方向关系。
5. 单局调用量和成本允许扩到统计上有意义的 paired matches。

若第 3/4 条失败，应把论文收缩为 benchmark validity/negative-result analysis；若第 1/2 条失败，不应开始模型大实验。

## 推荐的论文结构

第一篇论文采用 **benchmark + failure/transfer analysis**：

1. 定义“优秀游戏王玩家”的可测能力图谱。
2. 提供固定规则快照、统一数据协议和 engine-grounded generators。
3. 展示微观能力与完整对局的关系，而不是只给 leaderboard。
4. 用 harness interventions 分离模型能力与系统帮助。
5. 用 private/counterfactual splits 控制污染，用 benchmark audit 控制投机。

DeckMeta 在第一篇里是重要但有限的能力层，不承担“生成世界最强卡组”的 claim。YGOAgent 方法应作为第二阶段：只针对第一篇明确暴露的 timing、active memory 或 interruption recovery 瓶颈提出结构。

## 接下来三个动作

1. 建立 `TCG-2026.05` snapshot manifest，并让所有数据记录强制引用它。
2. 从 YGOPRODeck curated WCQ 牌表收集首批 50 副构筑，做官方事件交叉核验和 DeckMeta 切分原型。
3. 在 Linux 环境跑通两个现代牌组的固定 seed 双 bot 对局，导出第一条 canonical observation/action/engine-event trace。
