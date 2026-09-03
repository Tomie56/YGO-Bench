# LLM/Agent能否成为优秀的游戏王玩家

更新时间：2026-07-20

## 当前最强表述

这项研究的本体不是做一个“游戏王版 PTCG-Bench”，也不只是把 LLM 接入 YGOPro。中心问题是：

> **在规则引擎可验证的环境中，LLM-based agent 能否获得竞技游戏王玩家所需的卡牌与规则理解、环境感知与卡组构筑、响应式长时序决策和跨对局适应能力？什么数据、harness 和学习机制是必要的？**

`YGO-Bench` 是回答这个问题的测量工具；卡牌/规则/卡组数据集是知识与训练底座；YGOPro harness 是把模型变成可执行玩家的接口；后续 agent framework 则是对 benchmark 暴露出的失败进行方法改进。

这形成一条连续研究链：

```text
数据源与规则快照
  -> 多层能力数据集与 YGO-Bench
  -> 基础模型能力图谱与失败分类
  -> harness 消融和责任边界分析
  -> YGOAgent 方法/系统
  -> 完整对局、环境迁移与持续学习
```

## “优秀玩家”必须被操作化

如果只用胜率定义优秀，无法区分模型能力、harness 代算、卡组强弱和运气。建议把优秀玩家定义为四类能力的联合：

| 能力 | 玩家需要做到什么 | 主要测量 |
|---|---|---|
| Card & Rule Grounding | 理解效果、条件、cost、target、时点、连锁和裁定 | 合法集合、状态转移、counterfactual consistency |
| Deck & Meta Competence | 在指定卡池/禁限表/环境下构筑合法且有竞争力的 Main/Extra/Side | 合法率、卡组强度、环境适配、构筑 regret |
| Duel Decision Making | 在隐藏信息、响应窗口和长 combo 中执行与重规划 | 战术成功、交互时机、资源效率、完整对局 rating |
| Adaptation & Learning | 面对新卡、禁限变化、未知对手和新环境持续改进 | temporal/OOD generalization、sample efficiency、跨局提升 |

最终结论不能只是一个总分，而应回答：模型在哪一层开始失效，这个失效是否能预测完整对局表现，以及 harness/训练能否真正补上它。

## 主 RQ 与子问题

### Central RQ

**LLM/Agent 能否成为优秀的游戏王玩家？**

### RQ1：知识与规则理解

模型是否真正理解卡牌和规则，并能把自然语言文本落到具体游戏状态，而不是背过卡片介绍、裁定或常见 combo？

证据包括：

- 卡片效果结构化解析；
- 给定状态下的合法动作集合；
- cost、target、once-per-turn、chain 和时点判断；
- 引擎验证的下一状态；
- 只改变一个变量时答案是否正确翻转。

### RQ2：卡组构筑与环境理解

模型能否在给定地区、卡池截止日和禁限表下，构筑合法、稳定且适应环境的卡组？

不能只用“与冠军卡组重合度”评估，因为有多种有效构筑。建议同时测：

- 形式合法性和当期卡池合法性；
- engine/card-script 可运行性；
- 引擎对局中的强度与稳定性；
- 与上位卡组分布的距离，而非单一参考答案 exact match；
- 针对已知 meta 的 matchup coverage；
- Side Deck 和先后手方案；
- 在禁限表或新卡变化后的重构能力。

### RQ3：完整对局决策

在部分可观察、可中断、响应窗口密集的长时序对局中，模型能否可靠选择动作并维持计划？

这一层使用 `ygopro-core/ygoenv`，同时报告：

- 固定卡组和 paired seeds 下的胜率/Glicko-2；
- 先后手与 matchup 分层；
- missed response、premature interaction、无效动作；
- 中断后的 replanning；
- 调用次数、token、延迟和成本。

### RQ4：harness 与 agent 方法

哪些工程组件能把“知道卡牌”转化为“会打牌”？提升来自模型决策，还是来自系统替模型完成了规则和规划？

核心组件：

- canonical structured observation；
- legal-action shown/hidden；
- snapshot-locked rule/card/deck RAG；
- 精确近期历史与压缩长期记忆；
- 分层 planner-controller；
- chain/response-window controller；
- engine rollout/search；
- replay reflection、self-play 和技能记忆。

## 两种评价口径必须分开

### 1. Capability Track：模型本身会什么

限制 harness，重点评估规则 grounding、状态跟踪和决策能力。包括 legal actions hidden、无搜索、受限检索等条件。

### 2. Agent Performance Track：能否构建优秀玩家系统

允许结构化状态、合法动作、检索、记忆和规划等合理工具，直接测完整对局竞争力、稳定性与成本。

这两条轨道共同回答中心 RQ：

- Capability Track 防止把规则引擎和手写逻辑的能力算到 LLM 身上；
- Agent Performance Track 避免因为裸模型接口笨拙而低估 agent 系统的上限。

论文必须报告组件消融和“责任分配”：每个关键决策是 LLM、规则引擎、搜索还是手写控制器完成的。否则一个以 LLM 为装饰的传统 bot 也可能获得高胜率。

## 数据可行性与你的判断

你的判断基本正确，但可以更精确地表述为：

> **静态知识与构筑监督相对充足；高质量人类对战轨迹和决策理由稀缺；不过规则引擎允许我们生成可执行、可反事实、可重复的对战数据。**

### 充足的数据

- 卡片属性、效果文本、发售时间和多语言名称；
- 规则、FAQ 和裁定；
- 历史禁限表和卡池；
- 上位/优胜卡组与环境占比；
- 部分 combo、攻略和 deck profile 文本。

这些数据适合训练或增强：卡牌理解、规则检索、卡组表示、构筑先验和环境知识。

### 稀缺的数据

- 完整、高水平、机器可执行的人类 action trajectory；
- 每个响应窗口为何发动或不发动；
- 隐藏信息下的信念和风险判断；
- 中断后重规划的思考过程；
- 同一局面的专家候选动作排序。

这些数据不应完全依赖公开日志，可以用以下方式补足：

1. 引擎 + WindBot/随机/LLM/self-play 产生多样 replay；
2. 从 replay 采样真实 decision points；
3. 用引擎执行所有候选动作，生成合法性、状态转移和局部 rollout 标签；
4. 对高价值 timing/choke-point 小样本请专家排序，而不是标注海量完整对局；
5. 用 counterfactual state pairs 构造训练数据，避免只模仿常见 combo。

因此，缺少人类对战数据会限制“模仿顶尖人类”的主张，但不会阻止 benchmark、engine-grounded training 或 agent 系统研究。

## 数据集与 benchmark 的三层结构

### Dataset A：CardRule

输入卡片、规则和具体状态，训练/评测结构化效果理解、合法性、裁定与状态转移。

来源：BabelCDB、KONAMI 数据库、CardScripts、YGOResources/官方 FAQ，加上引擎生成的状态条件。

### Dataset B：DeckMeta

以 `region + date + banlist + card pool` 为上下文，训练/评测卡组补全、构筑、Side Deck、环境分类和禁限变化适应。

来源：官方赛事证据、YGOPRODeck curated tournament decks、Road of the King、官方/小程序公开结果。

### Benchmark C：DuelBench

由引擎生成微观决策点、战术局面、counterfactual pairs 和完整对局。

分为：

- RuleGround；
- ChainTiming；
- Combo/Replanning；
- FullDuel；
- 后续可选 MetaShift/Adaptation。

三个层次的数据使用相同 card ID、environment snapshot 和 action schema，才能分析 CardRule/DeckMeta 分数是否真正预测 DuelBench 表现。

## 推荐的论文与项目脉络

### 第一阶段：Benchmark/Dataset Paper

目标：回答当前模型具备哪些玩家能力，静态知识是否能转化为构筑与对局能力。

主要贡献：

- 游戏王玩家能力分类；
- CardRule + DeckMeta + DuelBench 的统一数据协议；
- engine-grounded labels 与 counterfactual generation；
- 基础模型和简单 agent 的能力图谱；
- 微观能力对完整对局表现的解释。

这比单纯“YGO full-duel leaderboard”更稳，也比一开始宣称做最强 agent 更容易形成可信证据。

### 第二阶段：YGOAgent Method/System Paper

目标：根据第一阶段发现的瓶颈，构建能可靠打完整对局的 LLM-centered agent。

可能的方法主线：

- 规则/卡牌/环境分层检索；
- response-window-aware controller；
- 长期计划与高频动作解耦；
- state/action memory 和 interruption recovery；
- engine search 与语言模型价值判断结合。

评价重点是相对于同 backbone 的增益、跨卡组/环境泛化、责任边界和计算成本，而不是只与随机 bot 比胜率。

### 第三阶段：Learning and Adaptation

目标：研究卡牌/构筑数据、合成轨迹、自博弈和少量专家反馈能否持续提高 agent，并适应新卡与禁限变化。

这一阶段可以研究：

- CardRule/DeckMeta 训练是否迁移到实战；
- imitation + engine feedback + self-play；
- 新卡/新环境 temporal split；
- deck building 与 playing 联合优化；
- 长期 memory/skill library 是否在真实 meta shift 中有效。

## 最强反对意见

1. **“优秀”定义过宽。** 解决：用四层能力和两条评价轨道操作化，不依赖单一胜率。
2. **数据很多但大多是知识记忆。** 解决：静态数据只负责 CardRule/DeckMeta；DuelBench 必须由引擎状态与 counterfactual 验证。
3. **harness 可以代替模型打牌。** 解决：明确责任边界，做 legal-action、RAG、memory、planner、search 的逐项消融。
4. **没有人类轨迹就不能称为优秀玩家。** 解决：第一阶段只主张 engine-grounded competence 与竞技代理表现；若要声称接近高水平人类，再加入专家盲评和有限人机比赛。
5. **YGO 只是更复杂的 PTCG。** 解决：贡献落在 chain/response timing、可中断长规划、构筑-实战统一评价和 harness 责任分析，而不是游戏名称。

## 可行性判断

结论：**Promising，且比原来的“YGO-Bench 项目”表述更强。**

- Novelty：完整游戏王 LLM agent benchmark 暂未发现；与 PTCG-Bench 是 close neighbor，但统一研究知识、构筑、响应式对局和 harness 责任具有清晰差异。
- Technical feasibility：卡牌、规则、卡组数据充足；对局可由 `ygopro-core/ygoenv` 生成。主要风险是环境适配、合法动作截断、隐藏信息和高频调用成本。
- Empirical feasibility：先做 200-500 个 decision points、2-4 套卡组、3-5 个模型、两种 harness track，即可验证关键相关性。
- Contribution shape：第一篇适合 benchmark + dataset + analysis；后续自然发展为 method/system 和 adaptation paper。

## 最小验证实验

在同一个历史环境中选 4 套风格不同且脚本稳定的卡组：combo、control、midrange、blind-second 各一套。

对 3-5 个模型测：

1. CardRule：100 个引擎验证状态；
2. DeckMeta：每个模型构筑/修订 4 套卡组；
3. DuelBench：200 个 decision points + 每个模型 50-100 局固定对手对局；
4. Harness：base、structured observation、+legal actions、+rule RAG、+memory/planner 五个递增条件。

最关键的分析：

- CardRule、DeckMeta 分数能否预测 DuelBench 胜率和关键错误；
- 哪个 harness 组件带来最大增益；
- 增益是减少无效动作，还是改善 timing、资源与 replanning；
- 结构化/检索增强后，模型间差距是扩大还是缩小。

只要微观能力与完整对局之间出现稳定关系，这条研究脉络就成立；如果没有关系，也会得到一个重要负结果：现有静态知识 benchmark 不能代表 agentic game competence。

## 下一步

1. 把 v1 明确写成 `CardRule + DeckMeta + DuelBench`，统一 environment snapshot 和数据 schema。
2. 在 Linux 环境跑通 4 套固定卡组，生成第一批可执行 decision points。
3. 先跑 base LLM 与 structured/legal-action agent 的小规模消融，验证“知识 -> 对局”关联和 harness 增益。
