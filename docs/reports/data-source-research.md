# YGO-Bench 对战底座与数据来源调研

更新时间：2026-07-20

## 结论

数据和对战底座都能落地。建议采用以下分层，而不是依赖单一网站：

1. **对战环境**：以 [`sbl1996/ygo-agent`](https://github.com/sbl1996/ygo-agent) 的 `ygoenv` 为工程起点，升级到固定版本的 [`ygopro-core`](https://github.com/edo9300/ygopro-core)、[`CardScripts`](https://github.com/ProjectIgnis/CardScripts) 和 [`BabelCDB`](https://github.com/ProjectIgnis/BabelCDB)。
2. **规则与效果真值**：由 `ygopro-core + CardScripts` 执行验证；不能把自然语言卡片文本或社区 FAQ 当作状态转移真值。
3. **卡片元数据**：运行时用 `BabelCDB`；发售时间和跨区信息用 KONAMI 官方数据库校验，YGOPRODeck API 做批量归一化，百鸽补中文名称映射。
4. **环境与禁限表**：当前表用 KONAMI 官方页面校验，机器可读版本用 `LFLists`；历史环境从 `LFLists` Git 历史恢复并固定 commit。
5. **赛事与上位卡组**：官方赛事页确认赛事事实，YGOPRODeck 的 curated Tournament Meta Decks 或主办方公开卡表提供完整卡组；两者交叉验证后才进入 gold 集。
6. **中国赛事**：官方“一起来决斗”小程序适合确认报名、赛果等事实；“游戏王查卡器”小程序适合补充比赛、对阵和锁定后的 YDK。两者均没有已确认的公共批量 API，首选联系运营方导出，不建议把逆向小程序接口作为论文数据管线。

因此，YGO-Bench 可以支持完整对局，也可以构造按历史环境分层的数据集。当前最大工程风险不是“没有数据”，而是 `ygo-agent` 的依赖快照停留在 2024 年、合法动作默认上限会静默截断，以及赛事卡组的真实性需要多源校验。

## 一、能否基于 YGOPro 对战

### 1. ygopro-core 能做什么

`ygopro-core` 是无界面规则引擎，不是完整客户端。它提供完整对局状态机：

- `OCG_CreateDuel`：创建对局；
- `OCG_DuelNewCard`：把卡组和场上卡片送入对局；
- `OCG_StartDuel`：开始；
- `OCG_DuelProcess`：持续推进，直到需要玩家响应或对局结束；
- `OCG_DuelGetMessage`：读取二进制事件/请求；
- `OCG_DuelSetResponse`：提交玩家选择；
- `OCG_DuelQuery*`：读取卡片、区域和全局状态。

调用方必须提供卡片数据回调、Lua 脚本回调、双方卡组、随机种子、协议解析和双方决策。换言之：**它能完整对战，但不能单独运行成一个 Gym 环境或 LLM agent 工具。**

本次固定的 `ygopro-core` 版本为 `0764db0c75b3d1d574880d365aa3695ab1f13b43`，许可证为 AGPL-3.0-or-later。

### 2. 推荐直接从 ygo-agent/ygoenv 起步

`ygo-agent` 已经完成了最费工程量的一层：

- 在 `ygopro-core` 上提供 Gym/Gymnasium 接口；
- 解析 YGOPro 消息并生成离散合法动作；
- 支持随机、贪心、自博弈、模型对模型；
- 支持固定 seed、录像和人机对战；
- 自带 31 个 `.ydk` 卡组；
- `code_list.txt` 收录 13,473 个卡片 ID，本次检查 31 个卡组的卡片都在该列表中。

适合作为 YGO-Bench 的环境骨架，但不能原样作为最终 benchmark：

1. 当前 HEAD `dbf5142d49aab2e6beb4150788d4fffec39ae3e5` 最后更新于 2024-08-16，Makefile 还固定了更旧的 MyCard 数据库/脚本；新环境需要升级依赖。
2. 默认 `max_options=16`。当合法动作超过上限时，`ygopro.h:2373-2375` 直接 `resize(max_options())`，会静默丢弃合法动作。必须改为动态动作列表，或设置经审计的高上限并在溢出时硬失败。
3. 现有 `(cards, global, actions, history, mask)` 数值观察为 RL 设计。LLM 版本需要额外输出 canonical structured observation、清晰的 chain/priority 信息和稳定 action ID。
4. 必须审计 `oppo_info=false` 下的隐藏信息边界，确保对手手牌、牌库顺序和盖卡身份不会泄漏。
5. `ygo-agent` 主代码为 MIT，但实际运行依赖 AGPL 的 core/scripts；发布组合系统时要按依赖分别履行许可证义务。

### 3. 其他项目的位置

| 项目 | 作用 | 结论 |
|---|---|---|
| [`ProjectIgnis/windbot`](https://github.com/ProjectIgnis/windbot) | 每套卡组手写 executor 的确定性 AI | 适合固定基线和 anchor，不适合任意卡组 oracle |
| [`EDOpro-server-ts`](https://github.com/diangogav/EDOpro-server-ts) | 兼容 EDOPro/YGOPro 协议的房间服务器 | 适合真人客户端接入和线上服务，不是首选 benchmark core |
| EDOPro GUI | 完整客户端 | 用于人工复核/演示，不应成为无头评测的核心依赖 |
| `melvinzhang/yugioh-ai` | 早期 Python/MCTS 原型 | 已较旧，工程起点不如 `ygo-agent` |

### 4. 本机验证边界

本轮完成了 API、消息循环和环境代码级核查，但没有在当前 Windows 机器跑通实际双 bot 对局。`ygo-agent` 预编译环境面向 Ubuntu 22.04，当前机器没有可用 WSL、Docker、xmake 或 CMake。下一步应在 Linux CI/容器中完成 deterministic smoke test。

## 二、卡片、脚本和规则数据

### 1. ProjectIgnis/CardScripts：效果执行真值

用途：`ygopro-core` 执行卡片效果所需的 Lua 脚本。项目自述为 EDOPro canonical script collection，强调快速先行卡支持和准确裁定。

本地快照：`references/cardscripts/`

- commit：`aeb606ccfa9c1bf1b6a52970ab90053d760bc24e`
- 22,541 个 Lua 文件；其中 `official/` 下 13,420 个卡片脚本，`pre-release/` 129 个，`unofficial/` 5,526 个
- 许可证：AGPL-3.0-or-later

使用原则：只把 `official/` 和明确选择的 prerelease 范围用于正式 benchmark；每个 release 固定 commit。

### 2. ProjectIgnis/BabelCDB：运行时卡片数据库

用途：EDOPro 使用的 SQLite `.cdb`，包含卡片 ID、区域标记、类型、等级、属性、种族、攻守、名称、效果文本和辅助字符串。

本地快照：`references/babelcdb/`

- commit：`ba612a7a2961098e978893b2a2c8600e317d2e61`
- `cards.cdb` 中 `datas` 与 `texts` 各 14,605 行
- SHA256：`51CE57AE0024790385D7DAF185CED1E045253D7768A3DFFCB4F1581EF4951891`
- 另有 unofficial、prerelease、Rush 和 Skill 数据库，不能默认混入 OCG/TCG bench

注意：下载快照根目录没有发现明确的 LICENSE 文件。卡片文本和图像还涉及 KONAMI/权利人的内容权利。建议发布抓取 manifest、commit 和转换脚本，而不是把整库和卡图直接打包进论文仓库；正式开源前做一次许可证核查。

### 3. ProjectIgnis/LFLists：机器可读禁限表

本地快照：`references/lflists/`

- commit：`64ebb3bb88c3a941bc1b504a408407251eff6501`
- 当前包含 OCG 2026.07、TCG 2026.05，以及 GOAT、Traditional、World、Speed、Rush 等表
- `OCG.lflist.conf` SHA256：`A2039953C509AD8FA72BC98567FF4D4D8AB0464248A1AA1557EA3FE23A30A3CD`
- `0TCG.lflist.conf` SHA256：`61229E75B8559F8B1A0B26BB11D874BC0A21F8C56124C60F10031DB919091653`

仓库 HEAD 只保留当前文件，但 Git 历史可恢复过去环境。例如 OCG 文件有 2024-12、2025-04/07/10、2026-04/07 等更新提交；TCG 文件也按列表更新留有历史。每个历史环境必须固定具体 commit，而不是固定 `master`。

与 BabelCDB 一样，下载快照未发现明确 LICENSE 文件；正式再分发前需要核验。

### 4. KONAMI 官方卡片数据库：权威校验层

- 全球/Neuron 数据库：<https://www.db.yugioh-card.com/yugiohdb/>
- 简中数据库：<https://db.yugioh-card-cn.com/>

适合校验官方卡名、效果文本、产品/发售日期、当前禁限表和官方 FAQ 链接。它不是公开 bulk API；应低频抓取、缓存并遵守站点条款。简中站前端虽然存在 JSON 接口，但牌组列表需要用户 token，不应依赖公开脚本里的签名实现做大规模采集。

### 5. 批量归一化与中文映射

| 来源 | 优点 | 限制 | 建议角色 |
|---|---|---|---|
| [YGOPRODeck API v7](https://ygoprodeck.com/api-guide/) | 免费公开 API；卡片 ID、类型、文本、卡包、TCG/OCG 日期、禁限信息；明确要求缓存 | 非 KONAMI 官方；卡图/文本有内容权利；没有正式 decklist API | 主批量元数据入口，结果固定 JSON 快照并用官方库抽样校验 |
| [百鸽 API](https://ygocdb.com/api) | 可下载 `cards.zip`；支持 id/cid/名称批量查询；中文、日文、英文多套名称和临时 ID 变更记录 | 社区服务，不保证稳定；不要依赖卡图 CDN | 中文名称映射和 ID 归一化补充层 |
| [YGOResources API](https://db.ygoresources.com/about/api) | 以 KONAMI database ID 提供 card/FAQ/Q&A JSON；有 cache revision/manifest | 社区服务，明确要求按需查询和缓存，不鼓励全库拉取 | 裁定解释、FAQ/RAG 辅助，不作为 engine 状态转移真值 |

卡图不是本 benchmark 的必要输入，第一版不要分发或依赖卡图。

## 三、历史环境、赛事和上位卡组

### 1. 需要区分三种“真值”

| 数据 | 真值来源 | 不能替代它的来源 |
|---|---|---|
| 赛事是否发生、日期、赛制、规模、名次 | KONAMI/主办方赛事页、官方 coverage、正式赛果 | 只有“上位”标题的社区帖子 |
| 完整 Main/Extra/Side 卡表 | 官方公开卡表、锁定的参赛 YDK、可靠 curated deck archive | 环境饼图、卡组截图、主播口述 |
| 某时间段环境占比 | 多场赛事的可审计聚合 | 单次冠军卡组、流行度榜 |

### 2. TCG/国际赛事

一级事实来源：KONAMI 的 [YCS/WCQ/Event 页面](https://www.yugioh-card.com/eu/events/)。这些页面能确认日期、地点、赛事类型、规则和 coverage，但并不总是发布所有 Top Cut 完整卡表。

完整卡表的首选补充：

- [YGOPRODeck Tournament Meta Decks](https://ygoprodeck.com/category/format/tournament%20meta%20decks%20)：页面明确说明该分类由站方 curated，普通用户不能直接上传；记录赛事、日期、名次、选手、人数，并可从页面卡号数组生成 YDK。分 TCG、OCG、亚洲英文和中国等类别。
- [KONAMI Neuron Deck Search](https://www.db.yugioh-card.com/yugiohdb/category/2/deck_search.action)：可筛选 Official tournament、YCS、WCQ，并展示完整 Main/Extra/Side。但平台也允许普通用户公开牌组，`Tournament` 标签本身不是官方认证。必须结合发布账号、comment 和官方赛事页交叉验证。
- [Yu-Gi-Oh! Top Decks 历史归档](https://www.yugiohtopdecks.org/)：用于补 2022 年前后的历史卡组，作为低一档来源，逐条保留原始出处。

### 3. OCG 环境

- [Road of the King](https://roadoftheking.com/)：适合环境级统计。其 2026.04 总结明确给出 185 场赛事、1,084 套上位卡组的聚合，覆盖日本、中国大陆、香港和多个亚洲地区。优点是长期连续和环境叙事完整；缺点是没有稳定公开 API，且应追溯每套卡组的原始赛事证明。
- YGOPRODeck 的 OCG/Asian-English/China Tournament Meta Deck 分类：适合拿到结构化完整卡表和 YDK。
- KONAMI Neuron/官方赛事页面：用于验证 YCSJ、官方大会和禁限环境。

环境占比可用 Road of the King/YGOPRODeck 生成候选池，但 gold decklist 仍要逐条保留来源证据。

### 4. 中国大陆与“小程序”

本轮确认了两个不同系统，用户所说的 “Yugi 小程序”可能指其中之一：

1. **“一起来决斗”**：简中官方活动常用的报名系统。官方赛事公告要求玩家用它报名，适合确认赛事、参赛者和结果。没有发现公共批量导出/API 文档。
2. **“游戏王查卡器”**：社区小程序，具备比赛发布、报名、对阵、成绩提交、积分、赛前 YDK 上传和开赛后卡组锁定。它确实收录上位卡组，但参赛卡组通常只对裁判/承办方可见，也没有发现公共数据 API。

建议：先向两个平台或熟悉的赛事主办方申请一份只含公开赛事与上位卡组的脱敏导出。若无法导出，再把公开页面/小程序截图作为人工审核证据，不能把不可复现的私有接口抓取当作论文主数据源。

## 四、数据准入规范

### 1. 环境快照

每个 benchmark 环境定义为：

```text
environment_id = region
               + master_rule
               + banlist_effective_date
               + card_pool_cutoff
               + ygopro_core_commit
               + cardscripts_commit
               + cdb_commit
               + lflist_commit
```

牌组进入该环境前必须验证：

- 每张卡在 `card_pool_cutoff` 前已于该区域合法发售；
- Main/Extra/Side 数量合法；
- 同名卡数量满足当期禁限表；
- 所有卡在固定 CDB 与 scripts 中可加载；
- 环境回归测试中无脚本异常。

### 2. 赛事卡组记录

最少字段：

```text
event_id, event_name, event_date, region, organizer,
event_level, participant_count, rounds, placement, player,
format, banlist_effective_date, card_pool_cutoff,
main_deck, extra_deck, side_deck,
event_proof_url, decklist_url, original_post_url,
retrieved_at, source_tier, reviewer, checksum
```

### 3. 证据等级

| 等级 | 条件 | 用途 |
|---|---|---|
| A | 官方赛事/主办方赛果 + 官方或锁定参赛卡表 | gold test 与正式环境统计 |
| B | 官方赛事事实 + curated archive 完整卡表，信息一致 | gold 候选，人工复核后使用 |
| C | 可信主办方/小程序赛果 + 完整 YDK | 训练、开发集或补充环境分析 |
| D | 社区帖子、自报 Tournament 标签、截图无原始链接 | 只做候选发现，不进入正式评测 |

### 4. 防数据污染与时间切分

- 保存原页面 URL、抓取时间、原始 HTML/JSON/YDK 的 SHA256；
- 训练/开发/测试按赛事时间和卡组构成同时去重，不只按标题分割；
- 对热门卡组做 card-name masking、counterfactual state 和未公开生成局面；
- 论文报告中公开来源 manifest 和转换脚本，受权利限制的数据由用户自行抓取。

## 五、已下载快照

| 本地目录 | 固定版本 | 用途 |
|---|---|---|
| `references/ygopro-core/` | `0764db0c75b3d1d574880d365aa3695ab1f13b43` | 规则引擎 |
| `references/ygo-agent/` | `dbf5142d49aab2e6beb4150788d4fffec39ae3e5` | Gym 环境起点 |
| `references/windbot/` | `0a29836e02acf6f635f56e75dbbc2c1471fefeec` | 固定 baseline |
| `references/cardscripts/` | `aeb606ccfa9c1bf1b6a52970ab90053d760bc24e` | 卡片效果脚本 |
| `references/babelcdb/` | `ba612a7a2961098e978893b2a2c8600e317d2e61` | 卡片数据库 |
| `references/lflists/` | `64ebb3bb88c3a941bc1b504a408407251eff6501` | 禁限表 |

## 六、建议的下一步

1. 在 Linux CI 中跑通 `ygo-agent` 随机/贪心双 bot 的固定 seed 对局，并保存 replay 与 state hash。
2. 把 `ygo-agent` 的 core/scripts/CDB 升级到本次快照，选 4 套卡组做脚本兼容性回归。
3. 先修复 legal-action 截断和隐藏信息审计，再接 LLM。
4. 写三个采集器：YGOPRODeck curated deck 页面 -> YDK；KONAMI event/Neuron -> 赛事证据；LFLists Git commit -> 历史禁限快照。
5. 与“一起来决斗”或“游戏王查卡器”运营/主办方确认是否能导出公开上位卡组数据；拿不到授权时只把它们作为人工验证源。

完成以上五步后，数据来源与对战环境就足以支撑第一版 pilot。
