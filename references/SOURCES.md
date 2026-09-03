# Sources

检索与下载日期：2026-07-20。

## 已下载

| 资料 | 本地位置 | 固定版本 | 许可/用途 |
|---|---|---|---|
| PTCG-Bench code | `references/PTCG-Bench/` | `d360a50b350808dde825fd9e529a63243dcbf03d` | MIT；benchmark 架构参照 |
| PTCG-Bench paper | `references/papers/PTCG-Bench_arXiv_2605.29653.pdf` | arXiv:2605.29653v1, 2026-05-28 | 论文原文；SHA256 `763334EC081B1D3879CFB04DE0FBBC6F7D023EECFFCBE0B30AD44D9905D0025F` |
| edo9300/ygopro-core | `references/ygopro-core/` | `0764db0c75b3d1d574880d365aa3695ab1f13b43`，2026-06-21 | AGPL-3.0-or-later；EDOPro 现代 `OCG_*` API 规则引擎 |
| lua/lua | `references/ygopro-core/lua/src/` | `6e22fedb74cf0c9b6656e9fce8b7331db847c605`（Lua 5.4.8；2026-08-09 恢复） | MIT；现代 core 固定子模块，以 C++ 编译以支持错误时的栈展开；archive SHA256 `3D7C84B8D255A831DAB310C7FAE723CF778FCAC6CA0C6CFE46822B18F7DB0AF8` |
| Fluorohydride/ygopro-core | `references/build-deps/ygopro-core/` | `f96929650ff8685b82fd48670126eae406366734` | MIT；ygo-agent `xmake 0.0.2` 固定的旧 API 构建依赖，含本地兼容补丁 |
| ProjectIgnis/windbot | `references/windbot/` | `0a29836e02acf6f635f56e75dbbc2c1471fefeec` | AGPL-3.0-or-later；固定策略/对手基线 |
| sbl1996/ygo-agent | `references/ygo-agent/` | `dbf5142d49aab2e6beb4150788d4fffec39ae3e5` | MIT（部分 envpool 代码 Apache-2.0）；Gym 环境起点 |
| ProjectIgnis/CardScripts | `references/cardscripts/` | `aeb606ccfa9c1bf1b6a52970ab90053d760bc24e`，2026-07-19 | AGPL-3.0-or-later；卡片效果脚本 |
| ProjectIgnis/BabelCDB | `references/babelcdb/` | `ba612a7a2961098e978893b2a2c8600e317d2e61`，2026-07-19 | 卡牌 SQLite 数据库；快照未发现明确 LICENSE，正式再分发前核验 |
| ProjectIgnis/LFLists | `references/lflists/` | `64ebb3bb88c3a941bc1b504a408407251eff6501`，2026-07-17 | 机器可读禁限表；快照未发现明确 LICENSE，正式再分发前核验 |

源码以 GitHub branch archive 下载，因此目录内不含 `.git` 历史；上表记录了下载时对应的 HEAD commit。

现代动态环境统一绑定 `snapshots/runtime-modern-v1-2026-07-20.json`。该 runtime 的资产截止日为 2026-07-20；TCG/OCG 的禁限表生效日和卡池截止日仍由各自 environment snapshot 独立记录。现代 core 源码与配套 CardScripts/BabelCDB 已就绪，但 ygoenv adapter 尚未从旧 API 迁移到 `OCG_*` API，因此不能把 source-ready 解释为 engine-ready。

关键文件校验：

- `references/babelcdb/cards.cdb`：SHA256 `51CE57AE0024790385D7DAF185CED1E045253D7768A3DFFCB4F1581EF4951891`
- `references/lflists/OCG.lflist.conf`：SHA256 `A2039953C509AD8FA72BC98567FF4D4D8AB0464248A1AA1557EA3FE23A30A3CD`
- `references/lflists/0TCG.lflist.conf`：SHA256 `61229E75B8559F8B1A0B26BB11D874BC0A21F8C56124C60F10031DB919091653`

## 在线数据源

| 资料 | 性质 | 用途 |
|---|---|---|
| [KONAMI Neuron/Card Database](https://www.db.yugioh-card.com/yugiohdb/) | 官方在线库 | 卡名、文本、发售、禁限和赛事牌组的权威校验；不作为 bulk API |
| [YGOPRODeck API v7](https://ygoprodeck.com/api-guide/) | 在线 API | 卡片批量归一化、卡包和 TCG/OCG 发售日期；必须本地缓存 |
| [YGOPRODeck Tournament Meta Decks](https://ygoprodeck.com/category/format/tournament%20meta%20decks%20) | curated archive | 完整大赛卡组、赛事/日期/名次和 YDK；与官方赛事页交叉验证 |
| [Road of the King](https://roadoftheking.com/) | OCG 环境汇总 | OCG 多地区上位卡组与环境占比；无稳定公开 API |
| [百鸽 API](https://ygocdb.com/api) | 在线 API | 中文名称、官方 cid、临时卡号变更和 bulk `cards.zip` |
| [YGOResources API](https://db.ygoresources.com/about/api) | 在线 API | 卡片 FAQ/Q&A 与裁定检索；按需请求并缓存 |
| KONAMI/主办方赛事页 | 官方网页 | 确认赛事、日期、赛制、规模与名次 |
| “一起来决斗”小程序 | 官方报名系统 | 中国大陆官方赛事事实；未发现公共批量 API |
| “游戏王查卡器”小程序 | 社区赛事系统 | 比赛、对阵、成绩与锁定 YDK；优先申请导出，不逆向为主数据管线 |

详细结论见 `docs/reports/data-source-research.md`。

## 主要论文与项目

- [PTCG-Bench: Can LLM Agents Master Pokémon Trading Card Game?](https://arxiv.org/abs/2605.29653), 2026-05-28。
- [PTCG-Bench code](https://github.com/zjunet/PTCG-Bench)。
- [Cards Against Contamination: TCG-Bench for Difficulty-Scalable Multilingual LLM Reasoning](https://openreview.net/forum?id=0HF2Dg0Ldx), ICML 2025 World Models Workshop；后续版本发表于 EACL 2026 Findings。
- [GENSTRAT: Toward a Science of Strategic Reasoning in Large Language Models](https://research.google/pubs/genstrat-toward-a-science-of-strategic-reasoning-in-large-language-models/), 2026。
- [Mastering Strategy Card Game (Hearthstone) with Improved Techniques](https://arxiv.org/abs/2303.05197), 2023。
- [OpenGuanDan: A Large-Scale Imperfect Information Game Benchmark](https://arxiv.org/abs/2602.00676), 2026。
- [Optimal play in Yu-Gi-Oh! TCG is hard](https://arxiv.org/abs/2603.02863), 2026。
- [The Feasibility of Deep Counterfactual Regret Minimisation for Trading Card Games](https://research-repository.uwa.edu.au/en/publications/the-feasibility-of-deep-counterfactual-regret-minimisation-for-tr), 2022；以游戏王为复杂 TCG 案例，但不是 LLM benchmark。
- [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688), 2023。
- [Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent Benchmarks with BenchJack](https://arxiv.org/abs/2605.12673), 2026；用于 benchmark 防投机设计。
- [BALROG: Benchmarking Agentic LLM and VLM Reasoning On Games](https://arxiv.org/abs/2411.13543), ICLR 2025；游戏 agent 的细粒度过程评测参考。
- [GAMBIT: A Benchmark for Active Memory in Long-Horizon LLM Agents](https://openreview.net/pdf/da8ab00e1f37f8b8adb2050cb76e19ebcab44709.pdf), 2026；区分被动检索与交互中的主动状态更新。
- [Predicting Drafted Deck Strength for Magic: the Gathering](https://arxiv.org/abs/2607.04782), CoG 2026；构筑结果预测与真实 outcome 数据的最近邻。
- [Deep Surrogate Assisted MAP-Elites for Automated Hearthstone Deckbuilding](https://arxiv.org/abs/2112.03534), GECCO 2022；构筑搜索、surrogate 与 quality-diversity baseline。
- [Agent Island: A Saturation- and Contamination-Resistant Benchmark from Multiagent Games](https://arxiv.org/abs/2605.04312), 2026；动态竞争、污染控制与不确定性排名参考。

## 检索结论边界

截至 2026-07-20，本轮用 arXiv、OpenReview、官方项目页与 GitHub 搜索，没有发现一个公开、完整、专门评测 LLM agent 玩游戏王的 benchmark。这个结论是检索结果而不是“不存在”的证明；投稿前应再做一次 Google Scholar/Semantic Scholar 引文追踪和同名项目检查。
