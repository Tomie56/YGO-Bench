# YGO-Bench 实验计划 v1：理解、构筑与实战策略

执行顺序、最小样本与逐阶段 Gate 见 `docs/reports/experiment-execution-plan.md`；本文保留完整研究协议与统计设计。

更新日期：2026-07-22

状态：实验设计草案，可用于实现排期与 pilot 预注册
中心问题：**LLM/Agent 能否成为优秀的游戏王玩家？**

## 1. 研究目标

在固定规则与环境快照下，分别测量 LLM/Agent 的三类核心能力：

1. **理解（Understanding）**：把卡片文本和规则落到具体状态，正确判断合法性、时点、cost、target、连锁和结算。
2. **构筑（Deck Building）**：在卡池、禁限表、环境和 matchup 约束下，产生合法、协同、稳定且有竞争力的 Main/Extra/Side。
3. **实战策略（Gameplay Strategy）**：在隐藏信息、响应窗口和长时序中选择动作、管理资源、规划并在受阻后重规划。

实验最终不只回答“谁胜率高”，还要回答：

- 模型在哪一类能力上首先失效；
- 三类微观能力是否能解释完整对局表现；
- harness 改善的是表达/接口问题，还是替模型完成了规则或策略推理；
- 静态知识、构筑能力和真实对局能力之间是否存在迁移。

## 2. 非目标

v1 不追求：

- 训练世界最强游戏王 AI；
- 覆盖全部历史赛制、全部卡组和全部卡片交互；
- 从最终上位牌表推断唯一“最优构筑”；
- 用少量完整对局给模型做稳定总排名；
- 把 self-evolution、强化学习或大规模 finetuning 作为第一篇的必要贡献。

第一篇优先定位为 **benchmark + dataset + failure/transfer analysis**。新的 YGOAgent 方法放在 benchmark 暴露出稳定瓶颈之后。

## 3. 研究问题与假设

### RQ1：理解

模型能否把卡片和规则正确落到具体游戏状态，而不是背诵卡片介绍、裁定或常见 combo？

- **H1a**：普通卡片/规则问答得分显著高于状态条件化的 legal-set 与 resolution 任务。
- **H1b**：模型在 IID 状态上的准确率显著高于最小 counterfactual pairs 的 pair accuracy。
- **H1c**：Rule Grounding 与 Active State Tracking 比静态 Card Semantics 更能解释实战错误。

### RQ2：构筑

模型能否在环境约束下构筑合法、合理并具有实战效用的卡组？

- **H2a**：LLM 能生成表面合理的牌表，但在日期、禁限表、Main/Extra/Side 和卡池约束上存在系统性错误。
- **H2b**：constraint-aware agent 会显著提高合法率，但合法率提升不必然带来 rollout strength 提升。
- **H2c**：环境条件化与 matchup 条件化能改善 Side Deck utility，但简单复制高频卡/最近邻牌表是强 baseline。

### RQ3：实战策略

模型能否在隐藏信息、响应窗口和可中断长规划中可靠决策？

- **H3a**：主要失败不是单纯不会 combo，而是过早交互、错过窗口、状态遗忘和中断后无法重规划。
- **H3b**：legal actions shown 主要减少非法动作；memory 主要改善状态追踪；planner 主要改善多步成功率。三者作用机制不同。
- **H3c**：Chain Timing、Interruption Recovery 与 Active State Tracking 比静态 QA 更能预测 Full Duel 表现。

### RQ4：Harness 与迁移

- **H4a**：structured observation 能改善解析稳定性，但不会自动解决规则和战略错误。
- **H4b**：legal-action masking 会提高 agent 胜率，同时掩盖模型的规则 grounding 缺陷。
- **H4c**：若增强后的 agent 主要通过减少 invalid/fallback 获益，应解释为接口增益；只有 timing、regret、replanning 同时改善，才能解释为战略能力提升。

## 4. 实验快照与研究对象

### 4.1 初始快照

Pilot 使用两个独立 snapshot：`snapshots/tcg-kde-e-2026-05-18.json` 与 `snapshots/ocg-jp-2026-07-01.json`：

- Regulation/Region：TCG KDE-E 与 OCG JP；
- Format：TCG Advanced BO3 与 OCG Ranking Duel BO3；
- Forbidden & Limited List：分别于 2026-05-18 与 2026-07-01 生效；
- 固定 `ygopro-core`、CardScripts、BabelCDB、LFLists commit 和文件 hash；
- 在正式生成数据前补齐 Master Rule 标签和 event-specific card pool cutoff。

所有 benchmark record 必须引用 snapshot，不允许只写“当前环境”。

### 4.2 v1 环境范围：TCG + OCG

v1 先只覆盖纸牌环境的 TCG 与 OCG，分别使用 `tcg-kde-e-2026-05-18` 和 `ocg-jp-2026-07-01`。两个环境的主结果分开报告，不把 legality、deck meta 或对局结果混成单一 YGO 分数。跨环境只作为 adaptation slice，测量禁限表/卡池 grounding、牌组迁移与策略迁移。

Master Duel 与 Duel Links 暂不进入 v1。完整定义、切分与成功标准见 `docs/reports/tcg-ocg-scope.md`。

### 4.3 卡组池

Pilot 首先选 4 个角色不同、脚本覆盖稳定的现代牌组：

| 角色 | 选择标准 | 主要能力压力 |
|---|---|---|
| Combo | 长展开、多资源约束、可被中断 | Planning、state tracking、replanning |
| Midrange | 多路线、资源循环、交互密集 | Timing、resource management |
| Control | 对手回合决策、延迟收益 | Belief、pass/act、long-term value |
| Blind-second | 解场、伤害计算、次序敏感 | Tactical search、risk、OTK planning |

每副牌保存赛事、日期、地区、名次、来源 URL、完整 Main/Extra/Side、证据等级与原文件 hash。Pilot 可以先用其中 2 副，四副全部验证后再扩容。

## 5. 实验包

| 编号 | 实验 | 目的 | 是否属于 v1 benchmark |
|---|---|---|---|
| E0 | Infrastructure Validity | 验证重放、隐藏信息、动作与 verifier | 是，发布前置条件 |
| E1 | Understanding | 测 Card Semantics、Rule Grounding、State Tracking | 是，核心能力层 |
| E2 | Deck Building | 测合法性、补全、环境与 Side 适应、rollout utility | 是，核心能力层 |
| E3 | Gameplay Decisions | 测 timing、战术、规划和中断恢复 | 是，核心能力层 |
| E4 | Harness Ablation | 分离 observation/legal actions/RAG/memory/planner 的作用 | 是，核心分析 |
| E5 | Full Duel & Transfer | 测集成表现以及微观到宏观关系 | 是，集成验证 |
| E6 | Learning/Adaptation | finetuning、self-play、新禁限表持续学习 | 否，后续 agent/method 工作 |

## 6. E0：基础设施有效性

开始模型实验前必须通过：

1. 同 snapshot、seed、deck order、action prefix 得到相同 canonical state hash。
2. 玩家 observation 不含对手手牌、盖卡身份、牌库顺序和 private engine flags。
3. 每个 exposed legal action 都能由引擎无修复执行。
4. action ID 不通过顺序、命名或稳定编号泄漏最优动作。
5. counterfactual 修改只改变声明变量和预期 label。
6. first/second、timeout、retry、fallback 和 crash 不会被错误计入模型能力。
7. 原始引擎 trace、player observation 与评分 trace 分层保存，能够审计。

E0 的 Go/No-Go：

- replay/label 重建成功率 `>= 99%`；
- 隐藏信息测试必须零泄漏；
- legal-action execution success `= 100%`；
- 未通过时不启动大规模模型调用。

## 7. E1：理解能力

### 7.1 子任务

| 子任务 | 输入 | 输出 | 标签类型 |
|---|---|---|---|
| U1 Card Semantics | 单卡文本 | condition/cost/target/limit/effect schema | 文本 + 人工抽查 |
| U2 LegalSet | observation + 相关卡片文本 | 完整合法动作集合 | 确定性引擎真值 |
| U3 ResolveDelta | state + action | canonical next-state delta | 确定性引擎真值 |
| U4 CounterfactualRule | 仅改变一个变量的状态组 | 每个状态的 legal/result label | 确定性引擎真值 |
| U5 ActiveStateTracking | 多步 event/history | 当前已用效果、公开信息和限制 | trace-derived 真值 |

### 7.2 Counterfactual 变量

- once-per-turn 是否已经使用；
- 卡片位于手牌、场上、墓地或除外；
- cost 是否可支付；
- target 是否存在且仍合法；
- priority player 与 phase/sub-step；
- chain 中是否已有相关 link；
- 召唤次数、召唤限制和卡位；
- 卡是否被无效、离场或改变控制权；
- 对手公开过的卡片信息。

### 7.3 主指标

预注册主指标：**Counterfactual Group Exact Accuracy**，即同一最小反事实组全部答对才计为正确。

次指标：

- Card Semantics macro-F1；
- Legal Set exact match / micro-F1；
- State Delta exact match；
- Active State Tracking field accuracy；
- calibration（Brier/NLL，当模型输出置信度时）；
- execution success、retry 和 parser failure。

## 8. E2：构筑能力

### 8.1 子任务

| 子任务 | 输入 | 输出 | Verifier/评价 |
|---|---|---|---|
| D1 LegalityAudit | 含若干错误的完整牌表 + snapshot | 错误清单与修复牌表 | banlist/card-pool validator |
| D2 MaskedCompletion | 隐藏 3-10 个卡位的上位牌表 | 候选补全 | 多参考 + set metrics |
| D3 TemporalBuild | 日期、地区、环境描述与约束 | Main/Extra/Side | 合法性 + 分布距离 |
| D4 SideAdapt | deck、matchup、先后手与 meta | 换入/换出计划 | 合法性 + paired rollout |
| D5 RolloutRanking | 同约束下的候选构筑 | 排序/选择 | 固定 agent paired rollout |

### 8.2 构筑标签的边界

必须区分：

- **确定性标签**：是否合法、卡是否已发售、禁限数量、Main/Extra/Side 数量；
- **人类构筑分布**：上位卡组中出现频率和共现，不是唯一正确答案；
- **近似强度标签**：固定 pilot agent 下的 paired rollout utility；
- **专家偏好**：用于抽查 Side/候选排序，不能和确定性标签混成一个准确率。

### 8.3 Baselines

- 只满足硬约束的 constraint solver；
- 卡片/主题流行度；
- card co-occurrence / association rule；
- nearest tournament deck retrieval；
- LLM direct generation；
- LLM + constraint checker；
- LLM + retrieval；
- search/evolution + fixed-agent rollout（规模允许时）。

### 8.4 主指标

预注册主指标：**Constraint-Passing Rollout Utility**。

先要求候选牌表通过全部硬约束，再用相同 seeds、相同 pilot agent 和相同对手池计算相对基线的 paired utility。非法牌表不进入强度比较，并单独计为失败。

次指标：

- hard-constraint pass rate；
- violation count 与 repair success；
- masked-card Recall@k / set-F1；
- archetype/card-distribution distance；
- Side Deck paired utility；
- 多样性、稳定性和对不同 matchup 的 worst-case utility。

## 9. E3：实战策略

### 9.1 子任务

| 子任务 | 核心问题 | 标签与参考 |
|---|---|---|
| S1 TacticalChoice | 当前局面选什么动作 | limited rollout + expert spot-check |
| S2 ChainTiming | 现在响应、等待还是放弃 | response-window rollout/preference |
| S3 ComboPlan | 如何在动作/资源预算内完成目标 | engine success + plan efficiency |
| S4 InterruptionRecovery | 指定位置被打断后如何重规划 | engine success + terminal utility |
| S5 Belief & Risk | 对隐藏信息形成何种信念 | Brier/NLL + action robustness |
| S6 FullDuel | 能否稳定完成完整对局 | paired matches + rating |

### 9.2 决策点生成

来源包括：

- WindBot/固定 bot 对局；
- 随机合法 agent 与多样化策略 agent；
- LLM agent 失败轨迹；
- 上位牌组之间的 engine self-play；
- 专用 scene builder 构造的规则/时点边界状态。

局面通过 `seed + deck order + action prefix` 重放。不存在稳定 engine snapshot API 时，不把 Python state dump 当作可恢复真值。

### 9.3 主指标

预注册主指标：**Interruption Recovery Success@Budget**。

原因：它同时要求状态理解、资源管理和重新规划，比固定 combo completion 更接近游戏王实战差异。

次指标：

- normalized action regret；
- missed critical response rate；
- premature interaction rate；
- tactical success@budget；
- plan length / resource efficiency；
- execution success、invalid、retry、fallback；
- belief calibration；
- token、调用数、延迟和估算成本。

## 10. E4：Harness 条件

### 10.1 两条轨道

**Capability Track** 测模型本身：

- 标准 public observation；
- legal actions hidden；
- 无 engine search；
- 固定或受限 rule/card retrieval；
- 固定调用与 token 预算。

**Agent Performance Track** 测系统上限：

- 允许 legal actions、RAG、memory、planner 和有界 rollout；
- 报告竞争力、稳定性、成本与责任边界；
- 所有自动 repair/fallback 必须显式记录。

### 10.2 实验条件

| 条件 | Observation | Legal actions | RAG | Memory | Planner/Search | 用途 |
|---|---|---|---|---|---|---|
| C0 | raw/minimal | hidden | no | recent raw | no | 最弱接口下限 |
| C1 | canonical structured | hidden | no | recent exact | no | Capability 主条件 |
| C2 | canonical structured | shown | no | recent exact | no | legal-action 贡献 |
| C3 | canonical structured | shown | snapshot RAG | recent exact | no | 知识检索贡献 |
| C4 | canonical structured | shown | no | active memory | no | 状态记忆贡献 |
| C5 | canonical structured | shown | snapshot RAG | active memory | bounded planner | Agent 完整条件 |

不运行完整全因子。使用以下受控比较：

- `C0 vs C1`：observation 表达；
- `C1 vs C2`：legal-action masking；
- `C2 vs C3`：RAG；
- `C2 vs C4`：active memory；
- `C2 vs C5`：完整 agent 增益。

所有 6 个条件先跑 decision-point 子集；Full Duel 只保留 C1、C2、C5，控制成本。

## 11. 模型与 Baseline

### 11.1 模型选择

Pilot 选择 3 个档位：

1. frontier reasoning/API model；
2. 中等成本通用模型；
3. 可本地运行或低成本 open-weight model。

Scale-up 扩到 5-6 个模型。执行前冻结完整 model ID、provider、版本日期、temperature、reasoning level、max tokens、tool schema、重试和并发设置。不同模型必须使用相同语义信息预算。

### 11.2 非 LLM 与简单 Agent Baseline

- random legal agent；
- greedy/one-step heuristic；
- WindBot deck executor；
- retrieval-only / nearest-deck；
- constraint solver；
- ReAct LLM；
- ReAct + snapshot RAG；
- reference memory/planner agent。

WindBot 是固定 anchor，不是最优 oracle；rollout value 也只能解释为给定对手、agent 和预算下的近似效用。

## 12. 数据规模

### 12.1 Pilot

| 数据 | 数量 | 说明 |
|---|---:|---|
| Understanding records | 400 | 至少 100 个 counterfactual groups |
| Legality/repair | 100 | 按错误类型平衡 |
| Masked completion | 200 | 按赛事/牌组分组切分 |
| Side adaptation | 50 | 覆盖 matchup 与先后手 |
| Gameplay decision points | 200 | timing 80、recovery 80、active tracking 40 |
| Full Duel | 5 paired seeds/config/deck | 仅测执行、方差和调用成本，不用于稳定排名 |

### 12.2 Scale-up

Pilot 后根据以下量决定最终规模：

- counterfactual group 的模型间方差；
- paired rollout 与 Full Duel 的 seed 方差；
- 单局决策次数、token 和费用；
- 目标主效应大小与可接受 CI 宽度。

最终样本量通过 pilot bootstrap/power simulation 预注册，不在看到主结果后任意追加。Full Duel 的目标是估计关键条件差异，不追求覆盖所有模型 × harness × deck 的全排列。

## 13. 数据切分与污染控制

同时维护：

- `test_iid`：同卡池、未见状态；
- `test_composition_ood`：留出卡片交互对、combo 模板或 matchup；
- `test_temporal`：新卡、新赛事、新禁限表；
- `test_name_masked`：匿名卡名/主题表面标记；
- `test_private`：隐藏 generator seeds、组合和模板。

切分单位不能是单条 record：

- counterfactual group 必须整体进入同一 split；
- 同一原始 duel/action prefix 的衍生状态不能跨 split；
- 同一赛事或近重复牌表不能跨 train/test；
- 时间切分以卡片发售、禁限生效和赛事日期为准。

## 14. 标签质量与专家标注

标签分三级：

| 等级 | 含义 | 例子 |
|---|---|---|
| L1 Deterministic | 引擎/validator 可唯一验证 | legal set、resolution、牌表合法性 |
| L2 Approximate | 有界 rollout/search 得到近似效用 | tactical action、deck ranking |
| L3 Preference | 多个合理答案，需要专家判断 | timing、Side 选择、风格/风险偏好 |

要求：

- L1 自动测试并抽查 `>= 10%`；
- L2 保存 rollout policy、seeds、budget 与置信区间；
- L3 至少双人独立标注冲突样本，报告一致率/Krippendorff's alpha 或 pairwise agreement；
- 主论文不把 L1/L2/L3 混成一个“accuracy”。

## 15. Full Duel 协议

- LLM agent 对固定 anchor pool，不让所有对手同时变化；
- 使用 paired seeds、相同 deck order，并交换先后手；
- 按 deck、matchup、first/second 分层；
- 每个响应窗口记录 observation hash、可用动作、选择、模型原始输出、executor 结果与 fallback；
- timeout/parse error/invalid/fallback 单独计数；
- 规定每局最大模型调用、token、墙钟时间和失败处理；
- 不用极少量裸胜率宣称模型排名。

主要报告：paired win rate difference + bootstrap CI。Glicko-2 用于规模扩展后的 arena 汇总，不替代 head-to-head 置信区间。

## 16. 统计分析

### 16.1 预注册主终点

- Understanding：Counterfactual Group Exact Accuracy；
- Deck Building：Constraint-Passing Rollout Utility；
- Gameplay Strategy：Interruption Recovery Success@Budget；
- Integrated：paired Full Duel win-rate difference（次于前三个主能力指标）。

### 16.2 比较方法

- paired task：McNemar、paired permutation 或 paired bootstrap；
- 连续/效用指标：cluster bootstrap，cluster 为 counterfactual group、deck、duel seed；
- 多模型/多 harness：混合效应模型，控制 deck、matchup、first/second、seed；
- 多重比较：Holm correction；
- 同时报告 effect size、95% CI 和原始分母，不只报告 p-value。

### 16.3 微观到宏观迁移

分析单位优先使用 `agent configuration × deck × matchup`，而不是把每条决策当独立样本。

候选模型：

```text
FullDuelOutcome ~ Understanding + DeckBuilding + Strategy
                  + Harness + FirstPlayer + Matchup
                  + (1 | Model) + (1 | Deck) + (1 | Seed)
```

补充分析：

- leave-one-model-out：能力到对局的跨模型预测；
- leave-one-deck-out：是否只学会固定主题；
- 错误分解：harness 增益来自 invalid 减少、timing 改善还是 replanning 改善；
- 不构造未经验证的单一总分，优先报告能力 profile 和 Pareto frontier。

## 17. 成本控制

Pilot 粗略调用量：

- 非对局任务：约 4,000-8,000 次模型调用，取决于条件覆盖与是否批处理；
- Full Duel：先用 5 paired seeds 估计每局 20-100 次语义决策的实际分布；
- 只对通过前置门槛的模型/条件扩充对局；
- 缓存固定 RAG 结果和 observation serialization，但不缓存模型决策；
- 所有实验记录 input/output tokens、latency、retry 和费用。

为避免完整对局吞噬预算，优先级是：E0 > E1/E3 > E4 > E2 > E5。构筑 rollout 与 Full Duel 在固定 agent/harness 下批量执行。

## 18. Go/No-Go

### Gate A：环境有效

E0 全部通过，否则停止模型实验。

### Gate B：任务有区分度

- 至少两个模型或 harness 在两个主指标上出现稳定差异；
- counterfactual group accuracy 不饱和，且不是全部接近随机；
- parser/invalid 不是解释大部分模型差异的唯一因素。

### Gate C：研究主线成立

- 至少一个 engine-grounded 微观指标与 Full Duel 错误呈稳定方向关系；或
- 得到可信负结果：静态理解/构筑指标不能预测实战，而 timing/replanning 可以。

### Gate D：可扩展

- 成本和延迟支持预注册后的最终样本量；
- 数据生成、重放和评分可以无人工逐条介入；
- 专家标注只集中在 L2/L3 高价值子集。

## 19. 时间表

| 周 | 工作 | 交付物 |
|---|---|---|
| Week 1-2 | headless engine、双 bot、trace、observation/action、隐藏信息测试 | E0 报告 + 第一条 canonical trace |
| Week 3 | Understanding generator 与 counterfactual tests | E1 pilot dataset |
| Week 4 | Deck importer、legality/repair、masked completion | E2 pilot dataset |
| Week 5 | timing/recovery scene 与 rollout evaluator | E3 pilot dataset |
| Week 6 | 3 模型 × 核心 harness pilot | pilot 结果与成本报告 |
| Week 7 | 修订任务、标注协议、power simulation | 预注册/冻结版协议 |
| Week 8-9 | scale-up 与 Full Duel | 主结果表、trace 与失败案例 |
| Week 10 | transfer/harness 分析、benchmark audit | 论文图表与 release checklist |

## 20. 预期论文图表

1. 三类能力 profile：Understanding / Deck Building / Strategy，不给未经验证的总分。
2. IID accuracy vs Counterfactual Group Accuracy。
3. C0-C5 harness 分解：invalid、timing、replanning、cost。
4. Hard legality vs Rollout utility：证明合法构筑不等于强构筑。
5. 微观指标对 Full Duel 的解释/预测图。
6. first/second、deck、matchup 分层结果与失败类型 Sankey/堆叠图。

## 21. Benchmark 与 Agent 工作边界

### Benchmark v1 负责

- 能力定义、snapshot、数据生成器与切分；
- player observation、action schema 和隐藏信息边界；
- deterministic/approximate/preference verifier；
- 固定 reference harness 条件；
- baselines、指标、统计协议和 evaluator audit；
- 微观能力到完整对局的迁移分析。

### 后续 YGOAgent 负责

- 更好的 rule/meta retrieval；
- active state memory；
- response-window-aware controller；
- planner-controller 与 bounded engine search；
- interruption recovery；
- self-play、finetuning 和跨禁限表适应。

Agent 方法必须在 benchmark 的相同 snapshot、预算和责任记录下比较，不能通过扩大搜索/调用预算或静默 fallback 获得不可解释增益。

## 22. 立即执行的三个动作

1. 在 Linux/headless 环境跑通两副现代牌组的固定 seed 双 bot 对局，导出 canonical trace。
2. 从 trace 中生成首批 20 个 decision points 和 10 个最小 counterfactual groups，人工核验 schema 与标签。
3. 用一个强模型和一个低成本模型跑 C1/C2 小样，实测 invalid、counterfactual gap、单局调用数和费用，再冻结完整 pilot 规模。
