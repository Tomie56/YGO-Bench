# YGO-Bench 当前实验路线图（2026-08-06）

## 1. 一句话结论

当前研究方向仍为 **Promising**。第一篇论文应聚焦于一个引擎可验证、分层诊断、区分 TCG/OCG 且显式消融 harness 责任的 benchmark，并检验理解、构筑和局部策略能力是否能解释完整对局表现。

现在不应直接扩大 LLM 或 Full Duel 实验。关键 pilot 是同时验证两件事：

1. 2026 TCG/OCG 固定资产能否在稳定、可重放且无隐藏信息泄漏的 runtime 中执行；
2. 最小理解与构筑任务能否产生可靠、不饱和且可区分模型的指标。

## 2. 中心 RQ 与实验主张

中心问题：

> LLM/Agent 能否成为优秀的游戏王玩家；卡牌与规则理解、环境化构筑、响应时点和中断后重规划中，哪一层最限制完整对局表现？

第一篇论文只需要支持以下主张：

1. 可以用统一 snapshot 和 schema 分层测量游戏王玩家能力，而不是只报告胜率。
2. 现有模型在规则 grounding、构筑和策略任务上存在可重复的能力差异与失败类型。
3. legal actions、snapshot retrieval 和 bounded memory/planner 对不同能力层的贡献不同。
4. 至少一个 engine-grounded 微观指标能够预测完整对局错误；如果不能，这一负结果本身说明静态 benchmark 不能代表实战能力。

第一篇论文不主张：

- 已经训练出最强游戏王 AI；
- 少量随机对局胜率代表竞技水平；
- Lua callback 等于完整卡牌语义 gold；
- 引擎合法动作或搜索得到的能力属于 LLM 本身；
- 一个环境的结果可以直接外推到所有 YGO 产品和赛制。

## 3. 当前已验证状态

| 模块 | 当前证据 | 状态 |
|---|---|---|
| WSL 与环境 | Ubuntu 22.04；Conda `ygo`；Python 3.10.20 | 通过 |
| GPU 可见性 | RTX 4070 Ti SUPER，16376 MiB，Compute Capability 8.9 | 通过 |
| 旧 runtime 对局链路 | CyberDragon 32 局 random eval；4,592 steps | 功能通过 |
| Trace/replay | 82/82 状态 hash 与动作一致 | 通过 |
| Hidden information | 修复后私有区和里侧身份泄漏为 0 | 通过 |
| Card identity | 修复后己方手牌 0/155 缺失 | 通过 |
| 本地构建吞吐 | 约 115 steps/s，旧预编译记录约 6,882 steps/s | 未通过扩展 Gate |
| 环境生命周期 | 同进程重复创建单环境可在第二次附近 SIGABRT | 未通过扩展 Gate |
| 2026 TCG 固定牌组 | 合法；CDB 23/38，script 22/38 | `engine_ready=false` |
| 2026 OCG 固定牌组 | 合法；CDB 25/41，script 23/41 | `engine_ready=false` |
| 理解非 LLM baseline | 13,334 张卡的文本到 Lua callback 代理标签 | 仅工程 pilot |
| 构筑非 LLM baseline | 31 副历史牌组；候选覆盖率 64.1% | 数据不足 |
| LLM/API 实验 | 尚未运行 | 未开始 |

因此，旧 runtime 的 E0 只能证明基础 harness 可行，不能替代 2026 TCG/OCG 的环境有效性验证。

## 4. 实验对象与两条评价轨道

### 4.1 固定环境

| Regulation | Snapshot | 主用途 |
|---|---|---|
| TCG KDE-E | `tcg-kde-e-2026-05-18` | TCG 单环境任务与 TCG -> OCG 迁移 |
| OCG JP | `ocg-jp-2026-07-01` | OCG 单环境任务与 OCG -> TCG 迁移 |

所有样本必须携带 `snapshot_id`。主结果分别报告 TCG 与 OCG，不用单一 YGO 分数掩盖环境差异。

### 4.2 Capability Track

目标是测模型本身会什么。使用 canonical observation，但限制 harness：

- 不提供引擎搜索；
- 不提供长期 planner；
- legal actions 设为实验变量；
- retrieval 只访问固定 snapshot 语料并记录命中内容。

### 4.3 Agent Performance Track

目标是测可构建的 agent 系统上限。允许：

- structured observation；
- legal-action masking；
- snapshot-locked retrieval；
- bounded memory/planner；
- 后续可选 engine rollout。

论文必须记录每个决策由 LLM、引擎、检索、搜索还是手写控制器完成。

## 5. 工作流 A：2026 Runtime 与 Harness Gate

这是策略和 Full Duel 的前置工程，不是论文方法贡献本身。

### A1. 双 runtime 设计

保留两套可切换资产：

- `runtime-2024`：用于复现已完成的 identity、trace 和 CPU pilot；
- `runtime-2026`：统一版本的 ygopro-core、BabelCDB、CardScripts 与 LFLists，用于正式 TCG/OCG 实验。

不得直接覆盖 2024 runtime。每套 runtime 记录 core/scripts/CDB/LFList commit、文件 hash、build flags、Python 扩展 hash 和 `code_list.txt` hash。

### A2. 2026 适配任务

1. 选择彼此兼容的 ygopro-core、BabelCDB、CardScripts 与公共 Lua 依赖版本。
2. 重新生成稳定的 `code_list.txt`，确保每张可用卡有唯一 observation card ID。
3. 明确 CardScripts 公共 Lua 依赖和脚本搜索路径。
4. 检查 ygoenv 与新版 ocgcore API 的接口差异。
5. 若接口冲突严重，将新版 ocgcore adapter 作为独立 harness 模块，不继续给旧二进制叠加补丁。

### A3. Runtime Gate

以下实验均为 smoke/工程验证，执行前需要用户明确授权：

- TCG 与 OCG 固定牌组均为 `engine_ready=true`；
- 缺卡数与缺 Lua script 数均为 0；
- 两个环境各完成 32 局 random eval；
- hidden-information 与 card-identity audit 通过；
- 固定 seed trace/replay 的 canonical state hash 一致率为 100%；
- 连续创建和销毁 100 次环境不触发 SIGABRT；
- exposed legal-action execution success 为 100%；
- 吞吐恢复到至少 1,000 steps/s。

如果吞吐未达到 1,000 steps/s，但功能、生命周期和重放全部通过，只允许开展小规模场景实验，不开展大规模 Full Duel。

## 6. 工作流 B：最小 Benchmark

理解与构筑的静态部分不依赖 runtime-2026，可以与工作流 A 并行。

### B1. Understanding Pilot

第一版共 200 题，TCG 与 OCG 各 100。共享卡片或共享规则形成显式 paired group，不能作为两个独立样本重复计数。

| 任务 | 规模 | Gold | 主指标 |
|---|---:|---|---|
| CardSemantics | 60/环境 | 卡片文本、规则、Lua 候选标签、人工复核 | field macro-F1 |
| RuleAndTiming | 20/环境 | 规则/裁定与人工复核 | exact accuracy |
| CardPoolGrounding | 20/环境 | snapshot、发行与禁限证据 | exact accuracy |

CardSemantics 至少标注：activation condition、cost、target、once-per-turn scope、resolution operation 和 restriction。Lua 只生成候选标签，不直接作为测试 gold。

先做 30 题 annotation pilot：

- 两位复核者独立标注；
- 记录 disagreement 类型；
- 字段级一致率低于 90% 时先修订协议，不扩到 200 题；
- 同一卡片家族、同一 combo 或同源裁定不得跨 train/test。

runtime-2026 通过后，再增加 LegalSet、ResolveDelta 和最小状态变量 counterfactual；这些不计入当前 200 题静态 pilot。

### B2. Deck Building Pilot

第一版使用 100 个牌组级样本，每个环境 50 个。目标不是与冠军卡组 exact match，而是测环境约束下的合法、合理和可执行构筑。

每环境建议组成：

- 25 副有完整赛事证据的真实牌组；
- 25 副由真实牌组生成的单一或双重 corruption；
- 从同一真实牌组派生的样本必须属于同一 split group。

| 任务 | Gold/Verifier | 主指标 |
|---|---|---|
| LegalityAudit | snapshot validator | violation exact F1 |
| MinimalRepair | constraint solver + 人工抽查 | repair pass rate、edit distance |
| MaskedCompletion | 同环境赛事牌组池 | Recall@5、MRR、candidate coverage |
| CrossRegulationMigration | TCG/OCG snapshot | legality、minimal edit、synergy retention |

数据 Gate：

- 每环境至少 25 副真实牌组；
- deck parser success >= 98%；
- event、region、date、placement、raw hash 和 evidence level 完整；
- `card_pool_cutoff` 未确认的牌组不进入正式测试集；
- MaskedCompletion 的候选覆盖率达到 85%，否则只报告 retrieval coverage，不解释为构筑能力。

### B3. Strategy Pilot

仅在工作流 A 通过后启动。第一版做 20-40 个场景，总量按两个环境平衡：

| 类型 | 目标比例 | 能力 |
|---|---:|---|
| ChainTiming | 40% | 现在发动、等待或 pass |
| InterruptionRecovery | 40% | combo 被打断后的状态更新与重规划 |
| ResourceTracking | 20% | OPT、限制、公开信息和资源维护 |

每个场景必须保存 snapshot、双方牌组、seed、deck order、action prefix、legal actions、engine state hash 和至少一个 counterfactual variant。

引擎只能给出合法性和状态转移 gold。策略最优性使用 bounded rollout、稳定 heuristic 和小规模专家排序共同定义，不能把任意可执行动作当作同等正确。

## 7. Baseline 与模型矩阵

### 7.1 非 LLM Baseline

- Understanding：majority、keyword/regex、已有 Lua callback proxy；
- Deck：constraint solver、popularity、co-occurrence、nearest deck；
- Strategy：random legal、one-step heuristic、固定 bot/policy。

### 7.2 模型

Pilot 只使用三个档位：

- `M0`：非 LLM baseline；
- `M1`：本地 7B/8B 量化模型，用于可重复低成本基线；
- `M3`：一个 frontier reasoning API，用于能力上界。

本地 14B 只在单请求显存、上下文长度和延迟测量通过后作为可选 `M2`，不为凑模型档位牺牲稳定性。v1 不训练或微调新模型。

运行前冻结 model ID、revision/hash、量化方式、上下文长度、temperature、reasoning 配置、prompt、tool schema 和最大调用预算。

### 7.3 Harness 条件

最小比较保留三个条件：

| 条件 | Structured state | Legal actions | Snapshot RAG | Memory/planner |
|---|---:|---:|---:|---:|
| C1 | 是 | 隐藏 | 固定基础语料 | 否 |
| C2 | 是 | 显示 | 同 C1 | 否 |
| C3 | 是 | 显示 | 是 | bounded |

主消融：

- C1 vs C2：legal-action masking 帮助多少；
- C2 vs C3：检索与 bounded planning 帮助多少；
- 同一条件下 TCG vs OCG：环境 grounding 差异；
- 源环境开发、目标环境测试：迁移损失。

Pilot 不做更大的全因子矩阵。

## 8. 指标与统计

四个预注册主终点：

1. Understanding：Counterfactual/paired Group Exact Accuracy；
2. Deck Building：constraint-passing repair rate；
3. Strategy：Interruption Recovery Success@Budget；
4. Integrated：paired Full Duel outcome difference，仅作为集成验证。

统计原则：

- counterfactual group、原始牌组、场景和 duel seed 是分析单位；
- 同源派生样本不视为独立样本；
- 报告 effect size、原始分母、bootstrap 95% CI 和失败类型；
- 预注册主比较使用 Holm correction；
- TCG 与 OCG 分开报告，再给 macro average；
- parser error、invalid action、retry、repair、fallback、token、延迟和成本单独报告。

微观到宏观分析先做 leave-one-model-out 和 leave-one-deck-out。样本量允许时再使用带 model、deck、matchup 随机效应的模型。相关性不能被表述为因果传导。

## 9. Full Duel 计划

Full Duel 不是第一阶段的启动项。只有 runtime、Strategy Pilot 和模型调用成本均通过 Gate 后才进入。

FD0 只验证稳定性：

- 两个环境；
- 一个模型；
- C1 与 C3；
- 每环境一个 matchup；
- 3 个 paired seeds 并交换先后手；
- 共 24 局。

FD0 属于 smoke 实验，执行前需要用户明确授权。通过标准为 completion >= 95%，所有 timeout、invalid、retry 和 fallback 可审计，且单局调用量与延迟允许扩展。

FD1 的样本量不预先固定为大规模数值。先用 FD0/小规模 FD1 估计方差，再做 bootstrap 或 power simulation。不能用几十局高方差胜率给模型做总排名。

## 10. 资源划分

| 工作 | CPU | GPU | API | 人工 |
|---|---:|---:|---:|---:|
| Snapshot/schema/来源审计 | 主要 | 否 | 否 | 来源复核 |
| 理解数据候选生成 | 主要 | 否 | 否 | gold 复核 |
| 构筑合法性与 corruption | 主要 | 否 | 否 | 抽查 |
| Runtime 编译、trace、replay | 主要 | 否 | 否 | 否 |
| Strategy rollout 与场景验证 | 主要 | 否 | 否 | 少量排序 |
| 本地 7B/8B 推理 | 辅助 | 主要 | 否 | 否 |
| Frontier 模型上界 | 辅助 | 否 | 主要 | 否 |
| Full Duel LLM agent | 引擎 | 本地模型时需要 | API 模型时需要 | 否 |

4070 Ti SUPER 主要用于本地模型推理，不用于 ygoenv 引擎。开始本地模型实验前需要单独确认 PyTorch/推理框架与 CUDA 驱动兼容性；`nvidia-smi` 显示的 CUDA 13.1 是驱动兼容上限，不等于环境已安装对应 toolkit。

## 11. 执行顺序与 Gate

### Phase 0：当前基线

已完成：环境、旧 runtime CPU pilot、trace/replay、identity/hidden-information 修复、两套 snapshot 与两副固定赛事牌组。

### Phase 1：并行去风险

工作流 A：完成 runtime-2026 适配设计和版本锁定。

工作流 B：

1. 收集 TCG/OCG 各 10 副赛事牌组做 schema 与证据 audit；
2. 完成 30 题 Understanding 标注协议 pilot；
3. 实现 100 个牌组级样本的生成与 split 方案；
4. 在现有数据上复跑非 LLM baseline，确认指标实现。

Phase 1 不调用 LLM。

### Phase 2：最小模型 Pilot

前置条件：Understanding 标注一致性通过，Deck 数据 Gate 通过，输入输出 schema 和 parser 固定。

运行 M1 与 M3 的最小矩阵：

- Understanding：C1/C2；
- Deck：direct、+checker、+snapshot retrieval；
- Strategy：仅在 runtime Gate 通过后运行 C1/C2/C3。

先控制在约 1,500-2,500 次模型调用。任务无区分度、格式错误主导结果或 gold 不可靠时停止扩展。

### Phase 3：集成验证

前置条件：至少一个 Understanding/Deck 指标和一个 Strategy 指标稳定区分模型或 harness。经用户明确授权后运行 FD0，再决定是否进入 FD1。

## 12. Go/No-Go

继续扩大实验必须满足：

1. runtime-2026 在两个环境通过可执行性、重放、隐藏信息和生命周期 Gate；
2. 理解、构筑、策略至少各有一个可靠且不饱和的任务；
3. 最佳模型得分不低于随机但不高于 90%，避免任务失效或饱和；
4. parser/format error 不解释超过 20% 的模型差异；
5. 至少两个主指标上出现稳定的模型或 harness 差异；
6. Full Duel 的完成率和成本允许扩展，或明确收敛为 benchmark + diagnostic analysis。

遇到以下情况立即停止对应分支：

- engine label 无法稳定重建；
- hidden-information leak 非零；
- 策略 gold 只代表“合法”而不代表“更优”；
- 构筑候选覆盖率不足却被解释为模型失败；
- harness 已直接编码目标策略，无法归因给模型。

## 13. Benchmark 与 Agent 工作边界

Benchmark v1 负责：

- snapshot、schema、split 和 contamination control；
- 理解、构筑、局部策略与 Full Duel 的统一记录协议；
- engine-grounded verifier、少量专家 gold 和非 LLM baseline；
- 模型与 harness 的能力图谱、失败分类和微观到宏观分析。

后续 Agent 工作负责：

- response-window-aware controller；
- 长期 planner 与高频动作 controller 解耦；
- interruption recovery memory；
- engine search、self-play、训练与跨对局学习。

如果 benchmark 尚不能可靠定位失败层，就不应提前开发复杂 agent 方法。

## 14. 接下来三个具体动作

1. 编写 runtime-2026 版本与接口兼容清单，确认双 runtime 目录、commit、Lua 公共依赖、`code_list.txt` 和构建产物协议。
2. 从现有数据源收集并验证 TCG/OCG 各 10 副赛事牌组，先做 event-level 去重、证据等级和 `card_pool_cutoff` audit。
3. 选取 30 道 CardSemantics/RuleAndTiming 样本，完成字段定义、双人复核和 disagreement 记录，验证 Understanding gold 是否可操作。

完成这三项后，再决定先投入 runtime 工程、扩大 DeckMeta 数据，还是接入第一组 LLM。
