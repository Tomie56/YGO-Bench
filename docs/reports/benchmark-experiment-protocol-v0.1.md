# YGO-Bench 首轮实验协议 v0.1

更新时间：2026-08-07  
状态：设计稿；尚未授权运行 smoke、LLM、API 或 Full Duel 实验

## 1. 研究目标

中心问题是：

> **LLM/Agent 能否成为优秀的游戏王玩家？**

第一篇论文不直接以“做出最强 Agent”为目标，而是构建同时覆盖理解、构筑和策略的 `YGO-Bench`，回答以下可检验问题：

1. 模型对卡片和规则的静态知识，能否转化为具体引擎状态中的正确判断？
2. 模型能否在 TCG/OCG 的时间、卡池和禁限约束下完成合法且有实战价值的构筑？
3. 模型能否在响应窗口、隐藏信息和组合被打断时做出稳定决策？
4. 理解与构筑指标能否解释局部策略和完整对局表现？
5. structured state、legal actions、RAG、checker、memory 和 planner 分别改善什么，提升应归因于模型还是 harness？

实验的主要产物不是一个单一排行榜，而是模型的三层能力图谱、失败分类、harness 责任边界和微观能力到完整对局的关系。

## 2. 实验对象与统一控制变量

### 2.1 三层 Benchmark

| 层次 | 核心问题 | 主要实验单位 | 主要 Verifier |
|---|---|---|---|
| 理解 | 是否理解条件、cost、target、OPT、连锁和结算 | counterfactual group / engine state | 规则快照、人工复核、ygopro-core |
| 构筑 | 是否能在指定环境中合法、合理地构筑与调整 | source deck / corrupted deck / matchup | snapshot validator、赛事牌组、paired rollout |
| 策略 | 是否能正确响应、管理资源并在中断后重规划 | scenario / paired duel seed | engine execution、bounded rollout、专家排序 |

同源派生样本不能被当作独立样本。例如同一张卡的多个反事实状态、同一赛事牌组的多个 corruption、同一局面的多个 action variant，都必须共享 `group_id`。

### 2.2 固定环境

首轮只研究两个环境：

| Format | Snapshot | 用途 |
|---|---|---|
| TCG KDE-E | `tcg-kde-e-2026-05-18` | TCG 单环境能力与 TCG -> OCG 迁移 |
| OCG JP | `ocg-jp-2026-07-01` | OCG 单环境能力与 OCG -> TCG 迁移 |

每条样本必须记录 `snapshot_id`、卡池截止日、禁限表版本、CDB hash、CardScripts commit、引擎 commit、来源抓取时间和 verifier 版本。TCG 与 OCG 分别报告结果，只在最后给 macro average。

### 2.3 两条评价轨道

**Capability Track** 测模型本身会什么：不给搜索和长期 planner；legal actions 是受控变量；RAG 只能访问冻结快照。

**Agent Performance Track** 测可构建系统的上限：允许 structured observation、legal-action masking、snapshot RAG、checker、bounded memory/planner 和后续的有限 rollout。

每次决策必须记录由 LLM、引擎、检索、checker、搜索或手写控制器分别完成了什么。

## 3. 核心假设

| 编号 | 可证伪假设 | 支持证据 |
|---|---|---|
| H1 | 文本语义得分不能充分代表具体状态中的规则 grounding | CardSemantics 与 LegalSet/ResolveDelta 的相关性较弱或存在系统性反例 |
| H2 | 最小反事实组比普通单题更容易暴露条件、OPT、target 和时点错误 | paired group exact 显著低于普通 item accuracy，并产生稳定错误类型 |
| H3 | snapshot RAG 主要改善版本化知识，legal actions 主要减少非法动作，但二者不必改善策略质量 | 组件对不同指标产生可区分增益 |
| H4 | checker 能显著提高构筑合法率，但不会自动带来同等幅度的 rollout strength 提升 | legality 与 paired rollout utility 增益不同步 |
| H5 | memory/planner 对 InterruptionRecovery 的帮助大于对一步 LegalSet 的帮助 | 任务与 harness 组件存在交互效应 |
| H6 | 至少一个 engine-grounded 微观指标能够解释控制模型、卡组、先后手和 seed 后的完整对局差异 | leave-one-model/deck-out 分析具有稳定预测力 |

如果 H6 不成立，也应报告为主要结果：现有微观能力评测不足以代表完整对局能力。

## 4. 数据和 Gold

### 4.1 数据来源

| 数据 | 核心来源 | 用途 |
|---|---|---|
| 卡片属性与文本 | BabelCDB；YGOPRODeck API；YGOResources | 理解输入、卡池和 ID 对齐 |
| 可执行效果 | Project Ignis CardScripts | 候选语义、引擎结算和状态生成 |
| 规则与裁定 | KONAMI Card Database；YGOResources；ygocdb FAQ | RuleEvidence 与人工复核 |
| 禁限表 | Project Ignis LFLists | TCG/OCG snapshot 和构筑合法性 |
| 赛事牌组 | YGOPRODeck Tournament；经核验的 Neuron 牌组 | 构筑、补全和环境迁移 |
| 赛事身份 | KONAMI Event pages | 日期、地区和赛事证据 |
| 环境分布 | Road of the King | OCG 时间窗和主题先验 |
| 策略轨迹 | ygopro-core/ygoenv 自生成 | 状态、合法动作、replay 和 counterfactual |

中文小程序当前没有可复现公开接口，只能作为人工交叉核验，不进入正式自动化数据链。

### 4.2 Gold 等级

| 等级 | 定义 | 可否进入主测试集 |
|---|---|---|
| G1 | 引擎确定的合法集合、状态转移或硬约束 | 可以 |
| G2 | 官方规则/裁定加独立人工复核 | 可以 |
| G3 | 多个固定 policy 的 bounded rollout 与专家排序一致 | 可用于策略主测试集 |
| G4 | 单一 Lua callback、卡组共现或单一 Agent 生成标签 | 只能作候选或弱监督 |

引擎只能证明动作是否合法和如何结算，不能单独证明策略最优。被测 Agent 不能为自己的测试样本生成最终 Gold。

## 5. 实验总览

| 实验 | 目的 | 依赖 | 是否需要 GPU/API | 当前是否可启动 |
|---|---|---|---|---|
| E0 | 数据、标注与 verifier 可靠性 | 现有静态数据 | 否 | 可以，非 smoke |
| E1 | 理解能力与 engine grounding | E0；动态部分依赖 runtime-2026 | M1 用 GPU，M3 用 API | 静态部分可准备 |
| E2 | 构筑、修复和跨环境迁移 | E0；赛事牌组 Gate | M1 用 GPU，M3 用 API | 数据准备可启动 |
| E3 | Agent/harness 责任边界 | E1/E2 schema 固定 | GPU/API | 尚不运行 |
| E4 | ChainTiming 与 InterruptionRecovery | runtime-2026 Gate | GPU/API + CPU 引擎 | 尚不可运行 |
| E5 | 微观能力到完整对局的解释 | E1-E4 | 主要 CPU 统计 | 尚不可运行 |
| E6 | Full Duel 集成验证 | E4 与成本 Gate | GPU/API + CPU 引擎 | smoke，需用户授权 |

## 6. E0：数据和评测协议资格测试

E0 不评价 LLM，只判断 Benchmark 是否值得扩展。

### E0-U：理解标注 Pilot

- 从 TCG/OCG 平衡抽取 30 个 CardSemantics/RuleAndTiming 样本；共享规则样本组成 paired group。
- 两位复核者独立标注 activation condition、cost、target、OPT scope、resolution operation 和 restriction。
- 记录 disagreement 类型，不能只记录最终一致答案。
- 字段级一致率低于 90% 时停止扩展，先修改标注协议。
- Lua callback 只作为候选提示，标注者必须核对卡片文本、规则或可执行状态。

### E0-D：赛事牌组与构筑协议 Pilot

- TCG/OCG 各收集 10 副牌组，优先选择可核验赛事、日期、名次和完整 Main/Extra/Side 的样本。
- 检查 passcode/cid 桥接、卡池截止日、禁限合法性、解析结果和来源 hash。
- parser success 低于 98%，或关键 provenance 缺失时，不进入模型实验。
- 同一赛事中的高度相似牌组只能进入同一 split，避免事件泄漏。

### E0-S：策略 Gold 协议 Pilot

在 runtime-2026 通过后，选 10 个局面比较：随机合法、一步 heuristic、固定 bot 和 bounded rollout 的排序一致性。若不同 verifier 对候选动作没有稳定排序，则该类场景只用于合法性评测，不用于策略最优性评测。

## 7. E1：理解实验

### 7.1 任务组成

第一阶段先建立 200 个静态/规则样本，TCG/OCG 各 100；runtime-2026 通过后扩展为 400 个 engine-grounded states，并包含至少 100 个最小反事实组。

| 子任务 | 输入 | 输出 | 主指标 |
|---|---|---|---|
| CardSemantics | 卡片文本与 snapshot | 结构化效果字段 | field macro-F1 |
| RuleAndTiming | 规则问题与具体上下文 | 结论与规则依据 | group exact accuracy |
| CardPoolGrounding | 卡片、日期和环境 | 是否可用及限制数 | exact accuracy |
| LegalSet | 玩家可见状态 | 全部合法动作 | set F1、exact set |
| ResolveDelta | 状态与指定动作 | canonical state delta | delta exact match |
| CounterfactualRule | 单变量变化的状态组 | 正确翻转的答案组 | paired group exact |

主终点为 `Counterfactual Group Exact Accuracy`。普通 item accuracy、字段 F1、置信度校准和格式错误率作为次要指标。

### 7.2 对照

- M0：majority、keyword/regex、Lua callback proxy；
- M1：本地 7B/8B 4-bit 模型；
- M3：一个冻结版本的 frontier reasoning API；
- U1：structured input、legal actions 隐藏、无工具；
- U2：U1 + snapshot RAG；
- U3：legal actions 显示，仅用于区分 capability 与 agent performance。

解析失败直接计为失败，不做静默重试。若测试显式评价“带 checker 的 Agent”，修复轮数必须预先固定并计入调用、token 和延迟。

## 8. E2：构筑实验

### 8.1 样本和任务

正式 Pilot 使用 100 个牌组级实验单位，每环境 50 个；同一 source deck 的所有 corruption 和 masked variants 留在同一 split。

| 子任务 | 设计 | 主指标 |
|---|---|---|
| LegalityAudit | 定位数量、位置、禁限和卡池违规 | violation exact F1 |
| MinimalRepair | 修复单一或双重 corruption | constraint pass rate、edit distance |
| MaskedCompletion | 隐藏真实牌表中的若干卡位 | Recall@5、MRR、candidate coverage |
| CrossRegulationMigration | TCG/OCG 间迁移完整牌组 | legality、minimal edit、synergy retention |
| SideAdapt | 给定 matchup 后换入换出 | side legality、paired rollout utility |

不使用“与唯一冠军牌表 exact match”代表构筑质量。构筑结果分别评价硬合法性、同期牌组分布合理性和固定策略下的实战效用。

### 8.2 对照

- D0：constraint solver、popularity、co-occurrence、nearest-deck retrieval；
- D1：模型直接构筑；
- D2：D1 + deterministic checker，最多两轮显式修复；
- D3：D2 + snapshot-locked deck/meta retrieval。

主要比较 D1 vs D2 的合法性增益，以及 D2 vs D3 的环境适配和补全增益。checker 修复是实验条件，不得被隐藏为通用 fallback。

## 9. E3：Agent 与 harness 责任实验

E3 不另造一套任务，而是在 E1、E2、E4 的相同样本上改变 harness。

| 条件 | Structured state | Legal actions | Snapshot RAG | Checker | Memory/planner |
|---|---:|---:|---:|---:|---:|
| C1 Capability | 是 | 隐藏 | 否 | 否 | 否 |
| C2 Grounded | 是 | 隐藏 | 是 | 构筑任务可用 | 否 |
| C3 Agent | 是 | 显示 | 是 | 是 | bounded |

为避免全因子爆炸，只预注册以下比较：

1. C1 vs C2：冻结检索改善哪些版本化知识错误；
2. C2 vs C3：legal masking 与 bounded planning 改善哪些执行/策略错误；
3. 同一条件下 TCG vs OCG：环境 grounding 差异；
4. 同一 backbone 下比较，不能把模型升级和 harness 升级混为一个处理。

除了任务得分，还要报告 invalid action、parser error、checker repair、tool call、token、延迟和成本。论文中给出组件责任表，说明每类输入和决策由谁产生。

## 10. E4：局部策略实验

### 10.1 场景

首轮目标为 200 个 decision points；在正式扩展前先用 20-40 个场景验证协议。

| 类型 | 比例 | Gold 与指标 |
|---|---:|---|
| ChainTiming | 40% | action/wait/pass；missed-window、premature interaction、local utility |
| InterruptionRecovery | 40% | recovery success@budget、终局价值、资源 regret |
| ResourceTracking | 20% | OPT、限制、公开资源和状态准确率 |

每个场景必须保存 snapshot、双方牌组、seed、deck order、action prefix、玩家可见 observation、verifier-only private state、legal actions、前后 state hash 和至少一个 counterfactual variant。

### 10.2 策略 Gold

1. engine execution 排除非法候选；
2. 对合法候选使用固定预算、固定对手 policy 和相同随机种子的 bounded rollout；
3. 只保留排序在多个 seed/policy 下稳定的场景；
4. 对主测试集高影响样本做少量专家 pairwise review；
5. 无稳定最优动作的状态使用 set-valued acceptable actions，不强造单一答案。

主终点是 `Interruption Recovery Success@Budget`。ChainTiming utility、资源 regret、非法动作率和响应窗口错误为次要终点。

## 11. E5：微观到宏观分析

E5 是论文的核心分析，而不是把三个榜单并排放置。

预测变量包括：CardSemantics、CounterfactualRule、LegalSet、构筑合法性、SideAdapt、ChainTiming 和 Recovery。结果变量包括局部策略效用、失败回合类型和 paired Full Duel outcome。

分析顺序：

1. 按模型、harness、format 和 deck style 描述能力图谱；
2. 使用 group-level bootstrap 报告 effect size 与 95% CI；
3. 做 leave-one-model-out 和 leave-one-deck-out 预测；
4. 样本量允许时再使用包含 model、deck、matchup 随机效应的模型；
5. 将相关性表述为解释/预测关系，不表述为因果传导。

第一版不计算未经验证的单一“优秀玩家总分”。如果需要汇总，只给三层 macro profile，并保留所有原始分母。

## 12. E6：Full Duel 集成验证

Full Duel 只验证三层能力和 Agent 条件能否在完整执行链中产生一致结果，不作为唯一主指标。

FD0 配置沿用当前路线图：两个环境、一个模型、C1/C3、每环境一个 matchup、3 个 paired seeds 并交换先后手，共 24 局。

FD0 属于 smoke 实验，必须获得用户明确授权后运行。开始前还必须满足：

- runtime-2026 在 TCG/OCG 中可执行、可重放且无隐藏信息泄漏；
- 环境生命周期和 legal-action execution Gate 通过；
- E4 至少一个指标稳定且策略 Gold 可靠；
- 单局调用量、延迟和成本已经由局部策略实验测得。

FD0 只判断 completion、审计性和成本能否扩展。FD1 的局数应根据 FD0/小规模 FD1 的方差做 power simulation 后决定，不能用几十局高方差胜率给模型做总排名。

### 12.1 Runtime Gate protocol

动态实验统一受 `configs/runtime-modern-gates-v0.1.json` 约束。正式结果必须匹配该文件的 ID 与 SHA-256，并分别通过 TCG/OCG 的 legal step、动态隐藏信息、trace/replay、100 次生命周期、吞吐和 32 局 random eval Gate。

reset 隐藏信息检查只证明初始状态。动态检查使用 native `card_visibility_` provenance 区分私有隐藏、所有者可见、公开场上、确认展示、当前可选主卡组和对手盖卡；除了确认展示或当前合法选择，私有行不得出现 identity 或详情。动态 Gate 还必须覆盖至少一次确认展示，不能把“从未遇到展示场景”算作通过。

trace/replay hash 同时覆盖 observation、visibility provenance、合法动作数、行动方、自对弈标记与终局原因。吞吐固定为 16 env、16 threads、batch 16，在 512 个 warmup transition 后计时 8,192 个 transition，门槛为 1,000 steps/s。不同并行规模或把 init/reset 时间混入计时的结果不可直接比较。

## 13. 模型配置与资源预算

### 13.1 M1 本地模型

- 使用 RTX 4070 Ti SUPER 16GB；
- 目标为一个冻结 revision 的 7B/8B instruct 模型；
- 优先 4-bit AWQ/GPTQ 或 GGUF Q4_K_M；
- 第一轮上下文上限 8K；
- 固定 temperature、seed、system prompt、输出 schema 和最大生成长度；
- 正式运行前单独测量显存、prefill、decode、批处理吞吐和结构化输出成功率。

### 13.2 请求规模

首轮模型 Pilot 控制在约 1,500-2,500 次调用。先运行 M0 和 M1；只有任务 Gold、区分度和 parser 稳定性通过后才调用 M3。API 成本按冻结模型的实际输入/输出 token 单独预算，设计阶段不预填不可靠金额。

CPU 负责数据处理、verifier、引擎、rollout 和统计；GPU 只负责本地模型推理；API 只负责 frontier 上界。第一版不训练或微调模型。

## 14. 切分、污染与统计规则

- 按 card family、ruling source、source deck、event、scenario prefix 和 replay 分组切分；
- 同一卡片家族、同一 combo、同一赛事和同一原始牌组不得跨 train/dev/test；
- 保留 temporal holdout，并分别报告 TCG/OCG；
- 同源派生样本的分析单位是 group，而不是 item；
- 主比较报告 effect size、原始分母、bootstrap 95% CI，并使用 Holm correction；
- parser error、invalid、retry、repair、fallback、token、延迟和成本必须单独报告；
- 正式测试 prompt、模型 revision、retrieval corpus 和 tool schema 在测试前冻结。

## 15. Go/No-Go

扩大实验前必须满足：

1. 标注字段级一致率至少 90%；
2. 构筑 parser success 至少 98%，关键 provenance 完整；
3. MaskedCompletion candidate coverage 至少 85%；
4. engine state/replay 可稳定重建，hidden-information leak 为 0；
5. 最佳模型的主任务得分高于随机但低于 90%，避免任务失效或饱和；
6. parser/format error 不解释超过 20% 的模型差异；
7. 策略 Gold 不仅代表“合法”，还能给出稳定的相对效用；
8. 至少两个主指标出现稳定模型差异或 harness 差异，才进入 FD0。

若某一 Gate 未通过，停止对应分支并修复数据或协议，不用更大模型和更多样本掩盖测量问题。

## 16. 推荐执行顺序

1. 完成 E0-U 的 30 题标注协议和 E0-D 的 TCG/OCG 各 10 副赛事牌组审计；
2. 固定统一 benchmark record、model output 和 evaluation result schema；
3. 在 E1/E2 上实现并运行所有非 LLM baseline；
4. 只在通过数据 Gate 后部署本地 M1，先测理解和构筑；
5. 完成 runtime-2026 Gate 后构造 E0-S 和 20-40 个策略场景；
6. 冻结 E4 协议后再运行 M1/M3 与 C1-C3；
7. 完成 E5 分析后，经明确授权运行 FD0。

当前最优先的实际工作不是下载模型，而是完成两种输入数据的资格测试：30 题理解标注协议和 TCG/OCG 各 10 副赛事牌组 provenance audit。它们决定后续模型结果是否具有论文解释力。
