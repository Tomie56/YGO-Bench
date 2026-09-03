# TCG/OCG 赛事牌组 Corpus v0.1 报告（2026-08-09）

## 结论

第一版构筑与环境理解数据底座已从每环境 1 副牌组扩充为 TCG/OCG 各 10 副，共 20 副真实赛事牌组。20 副牌组均具备可复核的赛事来源、原始页面、完整 Main/Extra/Side 卡号、固定环境 snapshot 和静态卡表覆盖，可进入静态 Benchmark 的后续样本构造。

这不表示 20 副牌组都能直接进入完整对局。当前现代 runtime 的 CDB 与 CardScripts 对 OCG 10/10、TCG 8/10 牌组覆盖完整；另外两副 TCG Branded 牌组保留为静态数据，但不能作为动态引擎场景。动态 Gate 仍只绑定已经通过 reset 的两副 Kewl Tune runtime primary。

## 数据范围

| 环境 | 赛事 | 日期 | 牌组数 | 静态可用 | 现代资产完整 | Runtime primary |
|---|---|---:|---:|---:|---:|---:|
| TCG | European WCQ 2026 | 2026-07-11 | 10 | 10 | 8 | 1 |
| OCG | Japan Championship 2026 | 2026-07-18 | 10 | 10 | 10 | 1 |
| 合计 | 2 场赛事 | - | 20 | 20 | 18 | 2 |

牌组覆盖冠军、亚军、Top 4、Top 8、Top 16 和 Top 64，并包含 Kewl Tune、Mitsurugi、Branded、Elfnote、Invoked、LAD Ritual、Toon、Maliss、Sky Striker、Lunalight 等构筑。v0.1 的目标是建立数据资格和 schema，不声称已经形成对环境分布无偏的统计样本。

## 来源与可追溯性

`data/source_samples/ygoprodeck_tournament/corpus-v0.1.json` 是唯一 corpus 输入 manifest。它对每条记录固定：

- TCG/OCG 环境和对应 snapshot；
- 赛事名称、日期、赛事页 URL 与官方赛事交叉引用；
- 牌组页 URL、本地原始 HTML、抓取时间和 SHA-256；
- 页面中预期的 category、tournament 字段；
- 是否为动态 runtime primary。

freezer 不接受 manifest 外的隐式页面，也不在 hash、路径、category 或 tournament 不一致时继续生成。E0 deck audit 会从原始 HTML 重新解析牌组名称、作者、名次及三个 deck zone，避免只验证派生 JSON 自身。

## 静态与动态资格分离

`static_benchmark_ready` 表示牌组可以用于构筑与环境理解任务：卡号能被 snapshot 卡表解释、来源完整、三个 zone 可解析，且没有当前 snapshot 禁限违规。

`modern_assets_ready` 进一步要求现代 CDB 和 CardScripts 足以执行牌组中的所有有效果脚本卡。它是动态引擎场景的必要条件，但不是静态 Benchmark 的前提。

两副 TCG Branded 牌组包含当前 runtime 尚未完整支持的 TCG 独占卡。数据层保留真实赛事事实并将其标记为不可执行，没有删除卡、替换卡或用兼容逻辑掩盖缺口。

## Card Catalog 分层

基础 BabelCDB 尚未包含 Chaos Origins 的全部卡。snapshot 现显式支持：

1. 基础 `cards.cdb`；
2. 按顺序合并的 release CDB，本版加入 `release-cori.cdb`；
3. 只用于静态 card ID/name 解释的补充元数据，TCG 本版冻结卡号 `80843006` 的 YGOPRODeck API 响应。

补充元数据不会自动生成 Lua 脚本，也不会让牌组获得 `modern_assets_ready`。因此静态数据完整性和动态可执行性仍保持可审计的边界。

## 验证结果

- 完整单元测试：47/47 通过；
- corpus 数量：TCG 10、OCG 10；
- runtime primary：每个 snapshot 恰好 1 副；
- 静态卡表覆盖：20/20；
- 现代 CDB + CardScripts 覆盖：18/20；
- 正式动态 scenario：2 个，均绑定既有 Kewl Tune primary；
- 本阶段未运行新的 step、完整对局、LLM、API 或 GPU 实验。

## 当前限制

v0.1 只覆盖两场 2026 年赛事，适合用于 schema、provenance 和最小构筑任务 pilot，不足以估计跨月份、跨赛制和跨原型的泛化能力。下一版数据设计需要按时间和赛事分组划分 train/dev/test，防止同一赛事或同源牌组变体跨 split 泄漏；同时需要把任务样本与原始牌表分开版本化，避免把“收集到牌组”误写成“已经完成 Benchmark”。
