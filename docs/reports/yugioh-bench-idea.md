# LLM/Agent能否成为优秀的游戏王玩家：研究方案与 YGO-Bench

更新日期：2026-07-20

## 一句话结论

这项研究的中心问题不是如何做一个“游戏王版 PTCG-Bench”，而是：**LLM/Agent 能否成为优秀的游戏王玩家？** `YGO-Bench` 是回答这一问题的测量工具；卡牌、规则、历史环境与卡组数据是知识和训练底座；YGOPro harness 负责把模型接入可执行对局；后续 YGOAgent framework 则针对 benchmark 暴露的失败提出方法。

研究的关键是检验：静态的卡牌、规则和构筑能力能否迁移为引擎验证的实战能力，以及哪些数据、harness 和学习机制能完成这种迁移。

可行性判断：**Promising**。静态知识与构筑数据相对充足，高质量人类对战轨迹较少，但规则引擎可以生成可执行、可重复、可反事实的决策与对局数据。当前需要一个关键 pilot，验证跨能力层的相关性和 harness 的真实增益。

## 我对 idea 的理解

目标是系统研究并逐步构建 LLM-based 游戏王玩家，而不是在第一阶段就训练一个最强游戏王 AI。研究需要评价并连接以下能力：

1. **卡牌与规则理解**：能否把卡片条件、cost、target、once-per-turn、时点、连锁和效果结算落到具体状态，而非背诵常见裁定或 combo。
2. **卡组构筑与环境理解**：能否在给定地区、日期、卡池和禁限表下，构筑合法、稳定且有竞争力的 Main/Extra/Side，并针对环境和先后手进行调整。
3. **完整对局决策**：能否在隐藏信息和 chain/priority 响应窗口中管理风险，维护跨几十次动作的状态，并在长组合被中断后重新规划。
4. **学习与适应**：卡牌/规则/构筑数据、引擎生成轨迹、自博弈和少量专家反馈，能否提升实际对局能力并迁移到新卡、新禁限表和未知对手。
5. **Harness 与责任边界**：结构化 observation、合法动作、检索、历史、记忆、规划和搜索是在帮助模型表达决策，还是替模型完成了核心规则与战略推理。

推荐的论文问题是：

> 在规则引擎可验证的环境中，LLM-based agent 能否获得竞技游戏王玩家所需的卡牌与规则理解、环境感知与卡组构筑、响应式长时序决策和跨环境适应能力？哪些数据、harness 与学习机制能够把静态知识转化为实战能力？

第一阶段更具体的论文问题是：

> 现有 LLM 的卡牌、规则和构筑能力能否预测并迁移到引擎验证的游戏王对局表现？哪些 harness 组件真正改善了响应时点、资源管理和中断后重规划？

## PTCG-Bench 读后总结

[PTCG-Bench](https://arxiv.org/abs/2605.29653) 将 PTCG 建模为 POMDP，使用规则引擎提供部分可观察状态与参数化合法动作，agent harness 把状态转成 prompt、把模型 tool call 映射回动作。它有三条主线：固定 agent 的 round-robin、固定 anchor 下的跨局 self-evolution、以及 observation/legal-action/history 三个 harness 模块的消融。

关键实验结果：

- 统一 ReAct harness 下，10 个 LLM backbone 的 Glicko-2 从 1237 到 1854，相差 617 分，说明环境能拉开模型差异。
- 五类 self-evolution baseline（Reflexion、ExpeL、LTM、prompt evolution、skill library）在 8 轮中都没有稳定、单调提升，也没有可靠超过同 backbone 的静态 ReAct。
- 移除结构化 observation 下降 33 Glicko 分；移除 legal-action masking 下降 118 分；移除 recent history 下降 115 分；minimal harness 下降 151 分。
- 去掉 history 后 tool calls 从 78.8 增至 385.7，说明接口设计会显著改变测得的“模型能力”和推理成本。

代码层面可直接借鉴：

- `BaseAgent.predict(obs, info) -> Action` 的统一 agent contract。
- observer、tool schema、executor、memory/skills 与 evaluation pipeline 的模块边界。
- 固定 agent 用 round-robin，自演化 agent 用 frozen anchors，避免所有策略同时变化造成 rating drift。
- 同 seed、双方换位、Glicko-2 + win rate + invalid action + tool calls 的联合报告。

不能直接照搬的地方：

- PTCG 的回合内行动大多由当前玩家连续完成；游戏王的 chain/priority 使一次动作不断把控制权交给双方，agent-environment contract 必须是一等公民地表达 `priority_player`、response window 和 chain state。
- PTCG-Bench 把 engine 的 legal actions 当权威输入。若 YGO-Bench 也只做这一种设置，就无法声称测到了完整的规则理解，因为发动合法性已经由引擎替模型算好。
- 只汇报完整对局胜率，很难知道失败来自规则、解析、状态遗忘、时点、战术还是隐藏信息。

## 相关研究与位置

### 直接近邻

| 工作 | 主要贡献 | 与本 idea 的关系 |
|---|---|---|
| [PTCG-Bench](https://arxiv.org/abs/2605.29653), 2026 | 真实 PTCG 完整对局、self-evolution、harness ablation | 最近邻；完整 YGO 对局本身不足以形成强新意 |
| [TCG-Bench](https://openreview.net/forum?id=0HF2Dg0Ldx), 2025/2026 | 自造 TCG、隐藏卡实现抗污染、Monte Carlo 难度、英阿双语 | 提醒我们必须处理游戏王的训练污染和难度控制 |
| [GENSTRAT](https://research.google/pubs/genstrat-toward-a-science-of-strategic-reasoning-in-large-language-models/), 2026 | 程序生成两人零和不完全信息卡牌游戏 | 程序生成能避免固定游戏的污染，但缺少真实规则语义与真实长 combo |

### 邻近游戏与算法工作

| 工作 | 价值 | 差异 |
|---|---|---|
| [Mastering Strategy Card Game (Hearthstone)](https://arxiv.org/abs/2303.05197), 2023 | 展示复杂 CCG 的 RL/self-play 与人类对局 | 不是 LLM agent benchmark；Hearthstone 没有同等密度的对手回合响应链 |
| [OpenGuanDan](https://arxiv.org/abs/2602.00676), 2026 | 大规模不完全信息、多方合作与竞争环境 | 研究对象是学习/规则 agent，不强调自然语言卡片规则与工具调用 |
| [游戏王 Deep CFR 可行性研究](https://research-repository.uwa.edu.au/en/publications/the-feasibility-of-deep-counterfactual-regret-minimisation-for-tr), 2022 | 证明游戏王已被作为超大状态/动作空间案例研究 | 算法可行性，不是 LLM、多层诊断或可复现 benchmark |
| [Optimal play in Yu-Gi-Oh! TCG is hard](https://arxiv.org/abs/2603.02863), 2026 | 从理论上说明最优游戏王对局的困难性 | 支持环境难度动机，但不直接提供 benchmark 设计 |

### 当前 novelty 判断

截至 2026-07-20，本轮未发现公开的完整游戏王 LLM-agent benchmark。这是一个 **open gap**，但与 PTCG-Bench 是明显 close neighbor。

可发表的新意不应是游戏名称，而应是以下组合：

1. 首个针对 **interruptible long-horizon decision making** 的引擎验证分层 benchmark。
2. 用最小 counterfactual state pairs 测量规则与时点推理，而不是只测卡组攻略记忆。
3. 建立微观诊断与完整对局之间的预测关系，回答“哪类能力真正决定胜负”。
4. 通过 legal-action shown/hidden、history、card-name masking 等受控 harness 条件分离模型能力、游戏知识和脚手架贡献。

## 为什么游戏王是不同的问题

### 1. 对手回合也持续决策

游戏王不是简单的“你一回合、我一回合”。chain、fast effect、damage step 等机制不断创建短暂响应窗口。真正困难的动作常常是 **不响应** 或把交互留到更高价值的 choke point。

### 2. 规则语义高度组合化

合法性和结算依赖 cost/effect、target/non-target、once-per-turn、卡片当前位置、之前是否成功发动、chain link、召唤限制和效果残留。只给卡片文本做 QA，无法覆盖实际状态依赖。

### 3. 单回合长组合具有可中断性

现代卡组的计划不是一条固定脚本。每次被打断后都要重规划，资源、额外卡组、卡位和召唤限制持续变化。这比“复述一条 combo”更接近真实 agent planning。

### 4. 流行知识带来严重污染

模型可能记住公开 deck guide、combo video、ruling FAQ 和卡表。原始卡名上的高分不能直接解释为推理能力，需要匿名化、时间切分、组合留出和 counterfactual 测试。

## 推荐强化版本

### Working title

**YGO-Bench: Diagnosing Rule Grounding, Reactive Timing, and Long-Horizon Planning in LLM Game Agents**

中文工作名：**YGO-Bench：诊断大模型游戏智能体的规则落地、响应时点与长时序规划**。

### 核心假设

1. 静态卡片/规则问答与完整对局表现的相关性有限。
2. engine-grounded 的状态转移、counterfactual consistency 和响应时点指标，更能预测完整对局质量。
3. legal-action masking 会大幅提高胜率，却掩盖规则 grounding 弱点；结构化 observation 与合理历史压缩则主要改善状态跟踪。
4. 大模型的关键失误不是单纯“不会 combo”，而是错误消耗交互、错过响应窗口以及中断后无法重规划。

### 贡献声明

建议把论文贡献写成：

- 一个基于成熟规则引擎、覆盖微观规则到完整对局的多粒度评测框架。
- 一个由 engine verifier 自动标注的 counterfactual 数据生成方法，控制卡名记忆与表面模式。
- 一套面向响应式游戏的新指标：missed-window、premature interaction、chain efficiency、interruption recovery。
- 一项跨模型、跨 harness、跨卡组的实证分析，揭示哪些诊断能力能解释完整对局强度。

### 四层任务设计

| 层级 | 任务 | 输入/输出 | 主要指标 |
|---|---|---|---|
| L1 RuleGround | 合法动作、发动条件、cost/target、效果结算 | 状态 + 卡片文本 -> 合法集合/下一状态 | set F1、state-delta exact match、counterfactual consistency |
| L2 ChainTiming | 是否响应、用什么响应、chain 顺序 | chain state + history -> pass/action | missed-window、premature interaction、response utility |
| L3 ComboPlan | 展开、解场、斩杀、中断后恢复 | 局面 + 目标 -> 多步 action sequence | success、步数、资源 regret、interruption recovery |
| L4 FullDuel | 固定卡组完整对局 | partial observation -> executable action | Glicko-2、win rate、invalid rate、first/second split、cost |

可选 L5 `AdaptShift` 放到后续：在未知卡片组合、banlist 变化或对手策略变化后测试跨局适应。它不应成为第一版的主贡献，否则会与 PTCG-Bench 的 self-evolution 主线正面重合，并显著增加实验成本。

## 数据构造

### 来源

- 使用 `ygopro-core` 作为确定性状态机和 verifier。
- 使用 Project Ignis canonical card scripts 与数据库，固定 commit、规则版本和 banlist。
- 用 WindBot、随机合法 agent、LLM agent 与人工脚本产生多样 replay/action prefixes。
- 不分发卡图；卡片文本、数据库与脚本的再分发范围在 release 前单独做许可审查。

### Counterfactual pairs

从真实决策点复制一份状态，只改变一个变量并让标签翻转，例如：

- 本回合是否已经发动同名 once-per-turn 效果。
- 某张卡当前在手牌、墓地、场上或除外区。
- chain 中是否已有一个满足条件的 link。
- cost 能否支付、target 是否仍合法、卡位是否空闲。
- 当前 priority player、phase 或 damage-step 子阶段。
- 对手公开信息中是否出现某个已检索/已展示的卡。

它比随机问答更能区分“理解状态依赖”与“背过常见裁定”。

### 切分

- `IID`: 相同卡池、未见局面。
- `Composition-OOD`: 见过单卡，但留出卡片交互对或 archetype matchup。
- `Name-Masked`: 稳定匿名 ID 替换卡名，保留效果语义。
- `Temporal`: 在条件允许时按卡片首次发布/引擎脚本时间切分。
- `Private Eval`: 保留一部分生成 seed、局面构造模板与卡组组合，只在 evaluator 上运行。

注意：name masking 只能降低直接攻略记忆，不能消除从效果文本识别卡片的可能，因此必须与 counterfactual 和组合留出联合使用。

## Harness 与实验控制

至少报告以下条件：

| 维度 | 条件 |
|---|---|
| Observation | raw protocol / canonical structured text |
| Legal actions | shown / hidden |
| History | none / recent exact / compressed summary |
| Rule access | no retrieval / snapshot-locked rule RAG |
| Card identity | original / name-masked |
| Reasoning budget | fixed tokens、固定最大重试、固定模型调用数 |

`legal-actions shown` 测的是受约束选择与战略；`legal-actions hidden` 才包含规则合法性。两者不能混成一个总分。

## Baselines

1. Random legal agent：环境下限。
2. WindBot：固定、可复现、deck-specific heuristic anchor；不能当作最优 oracle。
3. ReAct LLM：结构化状态 + tool actions。
4. No-mask ReAct：不提供合法动作，测试规则 grounding。
5. Rule-RAG ReAct：检索固定 snapshot 的卡片文本和规则。
6. Hierarchical plan-act agent：低频计划 + 高频受约束动作，用来研究调用成本。
7. Search-assisted agent：只在小规模战术题使用 engine rollouts，不作为全量默认基线。

模型选择应覆盖至少 3 个能力/成本档位，并对同一 backbone 固定温度、上下文预算、重试次数和工具 schema。

## 评价与统计

### 微观指标

- Legal Set F1 / exact match。
- Engine execution success 与 retry/fallback rate。
- Canonical next-state/delta exact match。
- Counterfactual consistency。
- Calibration：对隐藏牌、对手 archetype 或响应成功率预测计算 Brier/NLL。

### 战术指标

- Puzzle success@budget。
- 与 expert/搜索参考线相比的动作或资源 regret。
- Missed critical response rate。
- Premature interaction rate。
- Interruption recovery success。

### 完整对局

- Glicko-2 `mu +/- phi` 和 head-to-head win rate。
- first/second player 分层结果与双方换位。
- 每局模型调用、tokens、延迟与成本。
- 按卡组、matchup、决策阶段和失败类型分层。

使用 paired seeds、bootstrap 置信区间和固定 anchor。不要只用几十局的裸胜率给模型排序。

## 技术路径

推荐架构：

```text
ygopro-core worker
  -> protocol decoder
  -> canonical hidden state
  -> player-specific observation filter
  -> legal action enumerator / action ID map
  -> agent adapter
  -> response encoder
  -> engine verifier + trace recorder
  -> metrics / tournament runner
```

重要工程事实：当前 `ygopro-core` C API 支持创建/销毁对局、推进状态机、读取消息/场面、提交响应与加载脚本，但没有通用的任意对局快照序列化/恢复接口。局面任务应采用：

- `seed + deck order + action prefix` 确定性重放；或
- 专用 debug scene builder 构造状态；
- 不要把“直接保存 Python state dict 再恢复”当作既有能力。

## 主要风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| 与 PTCG-Bench 太近 | 被评价为换游戏复刻 | 把主 claim 放在 chain/timing 分层诊断和微观-宏观关联 |
| legal action 泄漏规则答案 | 无法声称规则理解 | shown/hidden 分轨报告，不合并总分 |
| 训练污染 | 模型背 combo/裁定 | counterfactual、name masking、组合留出、private seeds |
| 引擎协议复杂且无 snapshot | 数据生成慢、难分支 | 先做 replay-prefix 与小型 scene builder pilot |
| 隐藏信息泄漏 | benchmark 失效 | observation boundary 单测；engine state 与 agent view 进程隔离 |
| 对局方差和先后手偏差 | 排名不稳定 | paired seeds、换位、固定 anchors、rating uncertainty |
| WindBot 非最优且 deck-specific | 错误当作 oracle | 只作 anchor；战术标签用 engine + 搜索/专家复核 |
| LLM 调用过多 | 成本失控 | semantic decision points、最大调用预算、层级 agent |
| AGPL 与卡牌 IP | release 受限 | 分离 adapter 与依赖、遵守 AGPL、无卡图、发布前法律/许可复核 |

## 可行性判断

### Novelty

`Promising`。完整游戏王 LLM benchmark 暂未发现，且响应式 chain/timing 是 PTCG-Bench 未覆盖的结构差异。但如果只有 full-duel + Glicko + self-evolution，属于 incremental extension。

### Technical feasibility

`中等`。成熟引擎、卡片脚本和 WindBot 已存在，省掉规则实现；真正困难的是二进制协议 adapter、合法动作稳定 ID、隐藏信息隔离和状态重放。最小 pilot 可在两周内验证，完整平台预计需要 6-10 周工程投入。

### Empirical feasibility

`中等偏高`。微观标签可由引擎自动生成；完整对局需要大量模型调用。先用 200 个局面、3 个模型、2 个 harness 和 50-100 局对局即可验证信号，再决定是否扩容。

### 最强反对意见

“游戏更复杂”不是论文贡献；复杂性还可能让结果更难解释。这个项目只有在 **诊断可解释、标签可验证、污染受控、且微观指标能解释宏观胜率** 时才值得做成 paper。

## 四个版本的取舍

| 版本 | 贡献强度 | 工程风险 | 判断 |
|---|---:|---:|---|
| A. PTCG-Bench 的 YGO full-duel 复刻 | 低 | 中 | 不推荐作为最终论文 |
| B. 分层诊断 + full-duel 关联分析 | 高 | 中 | 最推荐 |
| C. 在 banlist/meta shift 下做 self-evolution | 中高 | 高 | 适合作为第二阶段 |
| D. 进一步包含 deck building/side decking | 高 | 很高 | 独立后续项目，不进 v1 |

## 最小验证实验

采用 [pilot spec](pilot-spec.md)：锁定一个引擎/规则快照、两个 WindBot 支持的卡组，生成 200 个引擎验证局面，其中至少 100 个是最小 counterfactual pairs；用 3 个模型在 shown/hidden legal-actions 下测试，再跑 50-100 局固定对手对局。

最关键的图不是 leaderboard，而是：

1. IID accuracy vs counterfactual consistency。
2. legal-actions shown/hidden 的能力差与 invalid rate。
3. 各诊断指标对 full-duel error/win rate 的解释力。

若这三张图没有清晰信号，应停止扩完整平台或改研究问题。

## 接下来三个动作

1. 完成 `ygopro-core -> canonical observation/action` 的最薄 adapter，并写隐藏信息与确定性重放测试。
2. 从两个固定卡组产生首批 20 个真实 decision points，手工验证 10 对 counterfactual labels。
3. 用一个强模型和一个便宜模型跑 shown/hidden legal-action 小样，测一次真实调用量、错误类型与成本。

## 需要你决定的三个问题

1. 论文定位：是否接受“benchmark + failure analysis”为主，而不是必须提出新 agent 方法？我的建议是接受。
2. 游戏范围：v1 是否只做固定规则快照、固定卡组完整对局，把 deck building 和 side deck 留到后续？我的建议是是。
3. 资源边界：可用模型 API/算力预算与目标 venue 是什么？这会决定最终模型数量、对局数和是否能加入 expert annotation。

## 总结

推荐推进，但先把项目的核心卖点从“YGO 更复杂”改为：

> **YGO-Bench 用确定性规则引擎和 counterfactual states，把规则理解、响应时点、长组合规划和完整对局拆开测量，并研究这些能力如何共同决定真实游戏表现。**

这个版本能继承 PTCG-Bench 的工程经验，又有清楚的结构性差异、可验证标签和可做因果消融的实验空间。
