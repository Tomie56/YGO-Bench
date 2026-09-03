# YGO-Bench 实验执行计划

更新日期：2026-07-27

适用范围：v1，纸牌 TCG + OCG
对应总协议：`docs/reports/experiment-plan-v1.md`

## 1. 目标与最小论文闭环

核心 RQ：**LLM/Agent 能否成为优秀的游戏王玩家；规则 grounding、状态跟踪、构筑、响应时点和长规划中，哪一层最限制完整对局表现？**

第一篇工作的最小闭环是：

1. 构造引擎可验证的理解、构筑和实战策略任务；
2. 在 TCG 与 OCG 两个独立 snapshot 上测量能力，而不是混成一个 YGO 分数；
3. 对 observation、legal actions、retrieval/memory/planner 做受控 harness 对比；
4. 检验微观能力指标能否解释完整对局错误和表现；
5. 即使完整对局效果弱，也能得到可发表的 failure/transfer analysis。

v1 不训练新模型，不把 self-play/RL 当成必要贡献，不纳入 Master Duel 或 Duel Links。

## 2. 当前状态

| 模块 | 状态 | 已有证据 | 下一阻塞 |
|---|---|---|---|
| TCG/OCG snapshot | 部分完成 | 两个 JSON snapshot、LFList hash、统一 schema | event-specific card pool cutoff |
| U1 自动标签代理 | 已完成 | 13,334 张卡；表面词法 baseline 差异明显 | 语义 gold 与人工抽查 |
| D1 legality audit | 已完成 | TCG 1/31、OCG 0/31 | 同 snapshot 赛事牌表 |
| D2 masked completion | 已完成 | 688 query，候选覆盖率 64.1% | 每环境至少 50 副牌表 |
| ygopro/ygo-agent | 未完成 | 源码与预编译说明已拉取 | Ubuntu 22.04 + E0 smoke test |
| 本地模型 | 未完成 | RTX 4070 Ti SUPER 16 GB，可跑 7B/14B 量化 | 模型权重与统一推理接口 |
| Full Duel | 未开始 | 协议已有 | engine trace、agent adapter、固定牌组 |

当前结果只证明数据管线与 snapshot mismatch 检测可行，不能回答模型能力或环境强弱。

## 3. 固定实验对象

### 3.1 环境

| 环境 | Snapshot | 主结果用途 |
|---|---|---|
| TCG | `tcg-kde-e-2026-05-18` | 单环境能力、构筑、对局 |
| OCG | `ocg-jp-2026-07-01` | 单环境能力、构筑、对局 |

所有结果必须按 snapshot 分开报告。跨环境迁移只进入独立 transfer 表，不进入单环境主分数。

### 3.2 牌组

每个环境先固定 2 副牌组，E0 通过后扩到 4 副：

| 阶段 | 角色 | 要求 |
|---|---|---|
| Smoke | combo + midrange | 脚本覆盖稳定、可被固定 bot 驱动、有同 snapshot 赛事证据 |
| Pilot | + control + blind-second | 覆盖对手回合决策、资源循环、解场与 OTK |

TCG 与 OCG 可以使用同一 archetype，但牌表必须分别来自对应 snapshot，不能直接复制后只改禁卡。

### 3.3 模型

执行前冻结完整 model ID、权重 hash/API 日期、量化、temperature、reasoning level、max tokens 和 tool schema。

| 代号 | 类型 | Pilot 用途 |
|---|---|---|
| M0 | 非 LLM baseline | random legal、heuristic、retrieval/constraint solver |
| M1 | 本地 7B/8B instruct 或 reasoning，4-bit | 低成本、可重复 baseline |
| M2 | 本地 14B 量化或中等成本 API | 中档能力 |
| M3 | frontier reasoning API | 能力上界 |

最小 pilot 先跑 M1 + M3；M2 在任务和 parser 稳定后加入。若本地 14B 无法在 16 GB VRAM 下稳定运行，不为凑档位牺牲可重复性。

### 3.4 Harness 条件

| 条件 | Observation | Legal actions | Retrieval | Memory/Planner | 解释 |
|---|---|---|---|---|---|
| C1 | canonical structured | hidden | 固定 card/rule corpus | 无 | Capability 主条件 |
| C2 | canonical structured | shown | 同 C1 | 无 | legal-action masking 增益 |
| C5 | canonical structured | shown | snapshot RAG | active memory + bounded planner | Agent 性能条件 |

理解任务先跑 C1/C2；实战决策跑 C1/C2/C5；Full Duel smoke 只跑 C1/C5。所有 retry、repair 和 fallback 单独计数。

## 4. 实验依赖图

```text
P1 Snapshot/Data audit
  -> P2 Engine validity (E0)
      -> P3 Understanding
      -> P4 Deck legality/completion
      -> P5 Strategy decision points
          -> P6 Harness + TCG/OCG transfer
              -> P7 Full Duel + micro-to-macro analysis
```

P3 与 P4 的静态部分可在 Windows 并行准备；P2、P5、P7 必须等 WSL/engine 可用。

## 5. P1：Snapshot 与数据审计

### 目的

确保每条 label 的规则、禁限表、卡池、赛事日期和来源都可追溯。

### 工作

1. 为两个 snapshot 固定官方 banlist 归档、LFList、CDB、CardScripts 与 ygopro-core hash。
2. 补齐 `master_rule` 和 event-specific `card_pool_cutoff`。
3. 每环境收集至少 50 副同 snapshot 上位/优胜牌表；目标 100 副。
4. 记录 event、region、date、placement、Main/Extra/Side、source URL、raw hash 和证据等级。
5. 赛事与近重复牌表分组去重，禁止跨 train/test。

### 验证与 Gate P1

- snapshot schema validation = 100%；
- artifact hash match = 100%；
- deck parser success >= 98%；
- 确定性 legality label 有效样本 >= 50/环境；
- 不允许 `card_pool_cutoff = null` 的赛事牌表进入正式 test。

## 6. P2：Engine 有效性 E0

### Smoke test

使用 Ubuntu 22.04 上的 ygo-agent 预编译模块，先跑仓库自带 random strategy：

- 32 episodes；
- 16 vector environments；
- 固定 deck directory；
- 保存 stdout、依赖版本和失败日志。

### Canonical trace test

为 TCG/OCG 各选择 2 副牌组：

1. 固定 seed、deck order 和双方策略，重复 20 次；
2. 导出 raw engine trace、player observation、legal actions 和 canonical state hash；
3. 从每个 response window 重放 action prefix；
4. 对所有 exposed legal actions 做执行测试；
5. 自动扫描 observation 是否包含对方手牌、盖卡身份、牌库顺序或 private flags。

### Gate E0

- 相同输入的 terminal outcome 与 canonical hash 一致率 >= 99%；
- hidden-information leak = 0；
- exposed legal-action execution success = 100%；
- replay/label reconstruction >= 99%；
- crash/timeout/fallback 能独立归因。

任一条件不满足，停止模型实验，优先修 engine adapter 和 observation schema。

## 7. P3：理解能力实验

### 任务与 Pilot 规模

| ID | 任务 | Pilot 规模 | Gold | 主指标 |
|---|---|---:|---|---|
| U1 | CardSemantics | 200 shared cards | 文本 schema + 双人抽查 | macro-F1 |
| U2 | LegalSet | 100 states/environment | engine | set exact match |
| U3 | ResolveDelta | 100 actions/environment，与 U2 同源 | engine | state-delta exact match |
| U4 | CounterfactualRule | 50 groups x 4 variants/environment | engine | group exact accuracy |
| U5 | ActiveStateTracking | 50 multi-step prefixes/environment | trace-derived | field exact accuracy |

CardSemantics 使用固定英文 canonical text，避免把 TCG/OCG 差异和语言能力混为一谈；环境差异主要通过 state、banlist 和 card pool 注入。

### Baselines

- keyword/regex；
- majority label；
- text-only LLM；
- C1 structured state；
- C2 structured state + legal actions。

### 关键分析

- IID accuracy 与 counterfactual group accuracy 的差距；
- illegal action 是知识缺失、状态遗漏还是 parser failure；
- TCG/OCG 内得分及 cross-regulation drop；
- legal actions shown 对规则 grounding 缺陷的掩盖程度。

### Gate P3

- 至少一个高信号任务不饱和，最佳模型得分位于 40%-90%；
- engine 与人工抽查冲突率 < 2%；
- parser/format error 不解释超过 20% 的模型差异。

## 8. P4：构筑能力实验

### 任务与 Pilot 规模

| ID | 任务 | Pilot 规模 | 主指标 |
|---|---|---:|---|
| D1 | LegalityAudit/Repair | 50 real + 50 corrupted decks/environment | violation exact F1、repair pass rate |
| D2 | MaskedCompletion | 200 queries/environment | Recall@5、MRR、candidate coverage |
| D3 | ConstrainedBuild | 20 prompts/model/environment | hard-constraint pass rate |
| D4 | CrossRegulationMigration | 30 TCG->OCG + 30 OCG->TCG | minimal edit + post-repair utility |
| D5 | SideAdapt | 25 matchup states/environment | legality + paired rollout utility |

### Corruption generator

每副真实牌表只注入 1-3 类可审计错误：禁卡超量、卡池不可用、Main/Extra/Side 尺寸、跨区禁限表、重复卡总量。保留原始合法牌表和 corruption seed。

### Baselines

- constraint solver；
- card popularity；
- co-occurrence/association rules；
- nearest tournament deck；
- LLM direct；
- LLM + checker；
- LLM + snapshot retrieval。

### Gate P4

- 训练候选覆盖率 >= 85%，否则 D2 只解释为 retrieval coverage；
- deterministic repair gold 抽查冲突率 < 2%；
- 先报告 legality，再报告 rollout utility；非法牌表不得进入强度比较。

## 9. P5：实战策略实验

### 决策点数据

每环境 100 个，合计 200 个：

| 类型 | 每环境数量 | 主要能力 |
|---|---:|---|
| ChainTiming | 40 | 现在发动、等待或 pass |
| InterruptionRecovery | 40 | 受阻后的状态更新与重规划 |
| ActiveTracking/Resource | 20 | 已用效果、限制、公开信息与资源 |

每个场景保存 `snapshot + seed + deck order + action prefix`，并提供至少一个最小 counterfactual 版本。

### Baselines 与条件

- random legal；
- one-step heuristic；
- fixed WindBot/ygo-agent policy；
- M1/M3 x C1/C2/C5。

### 指标

主指标：`Interruption Recovery Success@Budget`。

次指标：normalized regret、missed critical response、premature interaction、terminal utility、resource efficiency、invalid/retry/fallback、tokens、latency。

### Gate P5

- 至少 80% 场景能由 seed + prefix 稳定重建；正式发布前提升到 99%；
- reference rollout 在不同 seeds 下方向一致；
- timing/recovery 任务能区分至少两个模型或 harness 条件。

## 10. P6：Harness 与跨环境实验

### 核心比较

| 比较 | 归因 |
|---|---|
| C1 vs C2 | legal-action masking |
| C2 vs C5 | retrieval + memory + planner 的整体增益 |
| 同模型 TCG vs OCG | regulation/card-pool grounding |
| source snapshot -> target snapshot | adaptation/transfer loss |

不做完整全因子。先在 U2、U4、ChainTiming、InterruptionRecovery 上运行，再决定是否扩展到全部任务。

### 非对局调用预算

Pilot 目标约 4,000-6,000 次模型调用：

- Understanding：约 2,000-2,400；
- Deck tasks：约 600-1,000；
- Strategy：约 1,200-1,800；
- parser retry 与人工复核预留 10%。

每次记录 input/output tokens、wall time、retry、repair、fallback 和估算成本。

## 11. P7：Full Duel 与微观到宏观

### FD0：执行 smoke

只验证 agent 能稳定完成对局，不用于排名：

- 2 environments；
- 1 model；
- C1/C5；
- 1 matchup/environment；
- 3 paired seeds 并交换先后手；
- 共 24 games。

通过标准：completion >= 95%，所有 timeout/invalid/fallback 可审计，单局调用量和耗时可接受。

### FD1：Pilot comparison

FD0 通过后：

- 2 environments x 2 models x 3 harnesses；
- 2 matchups/environment；
- 5 paired seeds 并交换先后手；
- 最多 240 games。

若 seed 方差过大，不直接扩局数；先用 FD1 估计方差并做 bootstrap/power simulation，再冻结 scale-up 样本量。

### 结果

- paired win-rate difference + bootstrap CI；
- completion/invalid/timeout/fallback；
- first/second、deck、matchup 分层；
- 微观指标对 duel outcome/error rate 的 mixed-effects 或 leave-one-model/deck-out 分析。

不以极少量胜率给模型总排名。主张优先是“哪类能力限制对局”及“harness 增益来自哪里”。

## 12. 统计与预注册

四个预注册主终点：

1. Understanding：Counterfactual Group Exact Accuracy；
2. Deck Building：Constraint-Passing Rollout Utility；
3. Strategy：Interruption Recovery Success@Budget；
4. Integrated：paired Full Duel win-rate difference，作为集成验证而非唯一结论。

分析单位使用 counterfactual group、deck、duel seed 或 agent configuration，不能把同源 decision point 当独立样本。报告原始分母、effect size、95% CI，并对预注册主比较做 Holm correction。

## 13. 八周执行表

| 周 | 工作 | 交付物 | Gate |
|---|---|---|---|
| 1 | Ubuntu/ygo-agent、双环境数据清单 | environment report、source manifest | P1 初审 |
| 2 | engine adapter、trace、replay、leak tests | E0 report、首条 canonical trace | E0 |
| 3 | U2/U3/U4 generator、人工抽查 | Understanding pilot dataset | P3 数据 |
| 4 | TCG/OCG 赛事牌表、D1/D2/D4 | Deck pilot dataset + baselines | P4 静态 |
| 5 | ChainTiming/Recovery scenes、rollout | Strategy pilot dataset | P5 数据 |
| 6 | M1/M3 x C1/C2/C5 | model/harness result tables | P3/P5 |
| 7 | FD0、必要时 FD1 | duel traces、成本与稳定性报告 | FD0 |
| 8 | transfer、统计、failure taxonomy | pilot report、预注册修订稿 | 总 Go/No-Go |

周次从 WSL/engine 可用后开始计算。数据收集可以提前并行进行。

## 14. 立即执行队列

### Windows 现在可做

1. 建立 TCG/OCG tournament deck manifest，先各收集 20 副做 schema audit；
2. 实现 deck near-duplicate grouping 与 event-level split；
3. 扩展 D1 corruption/repair generator；
4. 从 U1 disagreement 中抽 100 张卡做语义标注协议；
5. 固定模型 I/O JSON schema 与 parser tests。

### WSL 可用后第一天

1. 跑 ygo-agent README 的 32-episode random eval；
2. 固定依赖版本并保存环境 manifest；
3. 导出第一条完整 trace；
4. 重复 20 次验证 determinism；
5. 从 trace 生成 20 个 decision points 和 10 个 counterfactual groups。

## 15. 最终 Go/No-Go

继续 scale-up 需要同时满足：

- E0 环境有效；
- 理解、构筑、策略至少各有一个不饱和且可靠的任务；
- 至少两个模型或 harness 在两个主指标上存在稳定差异；
- parser/invalid 不是绝大多数差异的唯一来源；
- FD0 完成率与单局成本允许扩展；
- 至少一个 engine-grounded 微观指标与完整对局错误呈稳定关系，或得到可信负结论：静态理解/构筑不能预测实战，而 timing/replanning 可以。

若 E0 或标签可靠性失败，论文暂停在 benchmark construction；若 Full Duel 成本过高但微观任务稳定，收敛为 benchmark + diagnostic analysis，不强行宣称完整 agent 排名。
