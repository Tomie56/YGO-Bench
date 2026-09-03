# Yu-Gi-Oh! 数据源最小采样与 Schema 审计

采样日期：2026-07-20（Asia/Shanghai）

## 结论

本轮对 16 个来源入口进行了最小采样：14 个来源成功取得可解析样本，2 个小程序因没有公开 API 或导出而标为 `not_sampled`。所有生成的 JSON 均已通过解析验证。

最关键的工程结论是：

1. **卡牌基础数据链可确定。** Project Ignis 用八位卡片 passcode 作为主键；KONAMI Card Database、Neuron 与 YGOResources 使用 KONAMI `cid`。YGOPRODeck 的 `misc_info.konami_id` 和 ygocdb 的 `{id, cid}` 可以建立稳定桥接。
2. **规则与引擎数据可确定。** BabelCDB 提供卡面数值/文本，CardScripts 提供可执行效果逻辑，LFLists 提供环境禁限卡表；三者都以 passcode 对齐。
3. **完整构筑可取得。** YGOPRODeck Tournament 页面直接嵌入 main/extra/side 的 passcode 数组；Neuron 页面给出完整 `40/15/15` 牌表，但牌使用 `cid`，且赛事身份多来自发布者填写的标题/备注，需要第二来源核验。
4. **环境统计可取得，但不是原始比赛事实表。** Road of the King 提供明确时间窗、地区、赛事数、上位牌组数和主题分布，适合环境快照，不足以恢复每一场赛事和每一副牌的关系。
5. **官方赛事页只稳定覆盖事件元数据。** KONAMI 页面可提取赛事名称、日期、城市、类型和 coverage 锚点；没有发现统一公开的完整名次与牌表 API。
6. **两个中文小程序暂时不能作为可复现主数据源。** 在获得官方导出、接口许可或组织者数据之前，只能作为人工交叉核验入口。

## 已采样来源与实际 Schema

| 来源 | 格式 / 主键 | 实际字段 | 可用于 | 判断 |
|---|---|---|---|---|
| ProjectIgnis/BabelCDB | SQLite；`datas.id = texts.id = passcode` | `datas(id, ot, alias, setcode, type, atk, def, level, race, attribute, category)`；`texts(id, name, desc, str1..str16)` | 卡牌静态属性、卡面文本、引擎对齐 | **核心源**；字段是引擎位掩码，需要枚举解码 |
| ProjectIgnis/CardScripts | Lua；文件名 `c<passcode>.lua` | `initial_effect`，以及 Effect 的 description/category/type/code/range/count-limit/condition/cost/target/operation 等设置 | 规则可执行验证、合法动作与结算测试 | **核心源**；这是程序，不是事实表 |
| ProjectIgnis/LFLists | 行配置；`list + passcode` | `list_name`；条目 `{card_id, limit, section, name_comment}` | OCG/TCG 禁限卡合法性、环境版本 | **核心源**；应保存仓库 commit 与生效日期 |
| sbl1996/ygo-agent | YDK + registry；passcode | 牌组 `{name, format, main[], extra[], side[]}`；支持表 `{card_id, has_script}` | harness 接入、牌组加载、支持卡覆盖率 | **工程参考**；示例牌组不是比赛真值 |
| YGOPRODeck API v7 | JSON；`data[].id = passcode` | 卡名、类别、效果、种族、攻防、等级、属性、主题、卡包、图片、价格；`misc_info` 含 formats、TCG/OCG 日期、`konami_id` 等 | 英文卡牌元数据、卡包、ID 桥接 | **推荐辅助核心源**；有 DB version endpoint，可做快照版本化 |
| ygocdb API | JSON；同时给出 `id=passcode`、`cid=KONAMI cid` | 多语言名称；`text`；引擎 `data`；FAQ `{fid,title,date,question,answer,refer}`；日/英卡包 | 中文文本、FAQ、ID 桥接、卡包 | **高价值辅助源**；非官方，需固定响应快照和抓取时间 |
| YGOResources | JSON；`cardId = KONAMI cid` | `cardData.<locale>` 下的属性、效果文本、prints；`faqData.entries/meta`；`qaIndex` | 多语言官方卡库镜像、FAQ/QA | **高价值辅助源**；以 cid 对齐，需记录上游更新时间 |
| KONAMI Card Database | HTML；URL 参数 `cid` | 名称、属性、等级、ATK/DEF、种族/卡类、说明文本 | 官方文本抽查、gold reference | **官方核验源**；无公开 bulk JSON，不宜作为唯一批量入口 |
| YGOPRODeck Tournament Meta Decks | HTML + 嵌入数组；`deck_id` | `deck_name, category, creator, tournament, placement`；`main[]/extra[]/side[]` 为 passcode | 完整上位牌表、构筑任务 | **当前最干净的比赛构筑入口**；赛事与名次仍需外部核验 |
| KONAMI Neuron Deck Search | HTML；复合键 `{cgid,dno}` | 标题、deck type、playstyle、registered category、comment、总数；牌项 `{zone,cid,name,quantity}` | 完整公开牌表、官方平台上的 deck artifact | **可用但弱标签**；本样本完整解析为 `40/15/15`，赛事归属不是平台认证字段 |
| Road of the King | 编辑页 HTML；`post_id + period` | 标题、发布时间、环境、起止日期、地区、赛事数、上位牌组数、主题分布 `{count,archetype,variants_text}` | OCG 环境快照、主题先验、时间切片 | **聚合统计源**；不能反推逐赛事牌表 |
| KONAMI Event Page | HTML；事件 URL | 赛事名、日期、城市、国家、赛事类型、coverage 锚点 | 官方事件表、赛事身份与时间核验 | **官方事件主表候选**；名次与牌表覆盖不统一 |
| “一起决斗”小程序 | 私有小程序 | 未发现公开 API/schema/export | 潜在中文赛事与构筑数据 | **暂不纳入可复现 pipeline** |
| “游戏王查卡器”小程序 / 集换社 CMS | 私有小程序 + 公开产品页 | 未发现公开赛事/牌表 API | 潜在中文赛事与构筑数据 | **暂不纳入可复现 pipeline** |

## 样本中确认的具体形状

### 卡牌与规则

- BabelCDB 样本包含 3 张卡，连接后的字段为：`id, ot, alias, setcode, type, atk, def, level, race, attribute, category, name, desc, str1, str2`。
- CardScripts 样本为灰流丽 `c14558127.lua`。效果由函数和回调图表达，适合生成引擎测试，却不能只靠列式 schema 表达完整语义。
- YGOPRODeck 蓝眼白龙样本的顶层卡字段为：`id, name, typeline, type, humanReadableCardType, frameType, desc, race, atk, def, level, attribute, archetype, ygoprodeck_url, card_sets, card_images, card_prices, misc_info`。
- ygocdb 蓝眼白龙样本确认 `cid=4007`、`id=89631139`、`faqcount=88`；FAQ 行包含 `fid, title, date, question, answer, refer`。
- YGOResources 顶层为 `cardData, cardId, faqData, qaIndex`，`cardData` 按 locale 分区。

### 构筑

- YGOPRODeck 样本：`deck_id=721844`，Kewl Tune，European WCQ 2026，Top 64；main/extra/side 分别为 40/15/15 个 passcode。
- Neuron 样本：复合键 `{cgid,dno}`，WCQ Spanish Nationals Winner 2026；解析出 main 22 个唯一牌项/40 张、extra 12 项/15 张、side 14 项/15 张。单项字段为 `zone, cid, name, quantity`。
- YDK 样本形状固定为 `#main`、`#extra`、`!side` 三段 passcode 列表；它能表示牌组，但不携带比赛、选手、名次或环境元数据。

### 环境与赛事

- Road of the King 样本环境为 OCG 2026.04，时间窗 2026-04-01 至 2026-06-30，聚合 185 场赛事、1084 副上位构筑和 11 个地区；主题行是 `{count, archetype, variants_text}`。
- KONAMI 赛事样本为 `300th Yu-Gi-Oh! Championship Series Dortmund 2026`，日期 `13-15 February 2026`，并有 city/country/event_type/source_url。

## ID 桥接

建议内部同时保留两个 ID，不用名称做 join：

```text
Project Ignis / YDK / YGOPRODeck
        passcode (例：89631139)
                 |
                 | YGOPRODeck misc_info.konami_id
                 | 或 ygocdb {id, cid}
                 v
KONAMI Card DB / Neuron / YGOResources
        cid (例：4007)
```

规范化 `cards` 表应以 `passcode` 为主键、`konami_cid` 为唯一可空键。任何只有 cid 的 Neuron 数据先进入 staging，完成桥接后再进入 benchmark 主表；无法桥接的记录保留原始引用并进入 quarantine，而不是按卡名模糊合并。

## 推荐的规范化数据层

建议拆成以下实体，具体 SQL 草案见 `schemas/canonical-data-model.sql`：

- `cards`：ID、类型和静态数值。
- `card_texts`：按 locale/version 保存名称、效果文本与灵摆文本。
- `card_prints`：卡包、编号、罕贵度、发行日期。
- `rulings`：FAQ/QA、引用卡、发布日期和来源。
- `banlists`：format、列表版本/生效日期、passcode、限制数。
- `engine_scripts`：passcode、脚本路径、hash、仓库 commit。
- `events`：官方事件身份、类型、时间和地点。
- `decks` / `deck_cards`：来源牌组、比赛/名次标签、main/extra/side 数量。
- `metagame_snapshots` / `metagame_archetypes`：环境时间窗和聚合分布。
- `raw_records`：原始 URL、抓取时间、内容 hash、解析器版本和许可备注。

## 对 benchmark 的直接影响

1. **卡牌理解与规则理解**可以立刻搭建：卡面文本来自 BabelCDB/YGOPRODeck/YGOResources，执行 oracle 来自 CardScripts/ygopro，引擎结果可以验证答案，而不是依赖人工主观评分。
2. **卡牌构筑**具备训练与评测数据起点：完整牌表来源至少有 YGOPRODeck Tournament 与 Neuron，禁限卡表来自 LFLists，环境先验来自 Road of the King。
3. **完整对战 agent**的数据瓶颈仍成立：目前确定的数据源主要是静态卡牌、规则、构筑和环境聚合，不是逐动作 duel log。对战评测应优先用 ygopro/EDOPro harness 自行生成可验证轨迹。
4. **数据集必须显式建模 provenance。** `official_event`、`official_card_text`、`curated_tournament_deck`、`user_published_deck`、`editorial_aggregate` 不能混为同一种 gold label。

## 文件与复现

- 总清单：`data/source_samples/manifest.json`
- 历史采集脚本：`scripts/legacy/windows/collect_source_samples.ps1`
- 历史 HTML 结构化脚本：`scripts/legacy/windows/derive_source_samples.ps1`

上述脚本保留用于已有样本的来源审计，尚未迁移为 WSL `ygo` 环境入口。
- 原始与派生样本：`data/source_samples/`
- 规范化 SQL 草案：`schemas/canonical-data-model.sql`

采集器按原始响应字节以 UTF-8 解码，避免 Windows PowerShell 5 对未声明/错误声明 charset 的响应产生乱码。HTML 派生只抽取当前页面中相对稳定的字段；生产 pipeline 仍需加入选择器回归测试、内容 hash、重试/限速、许可与 robots/terms 审查。
