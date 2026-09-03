# YGO-Bench v1 环境范围：TCG + OCG

更新日期：2026-07-22

## 决策

YGO-Bench v1 先只覆盖纸牌环境的 **TCG 与 OCG**。Master Duel 和 Duel Links 不进入 v1 数据集、主实验或总榜；它们需要独立的卡池、禁限表语义、模式与客户端规则，过早混入会让能力差异和环境差异无法区分。

TCG/OCG 也不能被合并成一个宽泛的 `YGO` format。每条样本必须绑定完整 snapshot；主结果按 snapshot 分开报告。

## 两个首批快照

| Snapshot | Regulation | Region | Mode | Banlist |
|---|---|---|---|---|
| `tcg-kde-e-2026-05-18` | TCG | KDE-E | Advanced BO3 | 2026.05 TCG，2026-05-18 生效 |
| `ocg-jp-2026-07-01` | OCG | JP | Ranking Duel BO3 | 2026.07 OCG，2026-07-01 生效 |

两者固定相同的 ygopro-core、CardScripts、BabelCDB 与 LFLists commit，以便把差异主要限制在 regulation、card pool 与 banlist。正式赛事牌组仍要补充 event-specific `card_pool_cutoff`，不能把当前聚合卡池误当成历史卡池。

## Benchmark 设计

### 1. 单环境主任务

- Understanding：分别在 TCG/OCG 合法状态上生成 CardRule、LegalSet、ResolveDelta 与 counterfactual 样本。
- Deck Building：牌组只能与同 snapshot 的禁限表、卡池和赛事 meta 比较。
- Gameplay Strategy：同一局、同一对手与同一 deck pool 内只使用一个 snapshot。

主表给出 `TCG score` 和 `OCG score`，不默认求平均。需要汇总时报告 macro average，并同时保留两个分项，避免样本量较大的环境支配结论。

### 2. 跨环境迁移任务

跨环境不是额外能力，而是三类能力上的 adaptation slice：

- `CrossRegulationLegality`：同一牌表在 TCG/OCG 下分别找出违规并修复。
- `DeckMigration`：给定源环境牌表与目标 snapshot，做最小合法修复，再评估协同与 rollout utility 是否保持。
- `RuleCardPoolGrounding`：判断一张卡在给定地区与日期是否可用，不允许只凭卡名记忆。
- `LeaveOneRegulationOut`：在一个 regulation 上开发提示或 agent，在另一个 regulation 上测试，测量迁移损失。

迁移结果单独成表，不与单环境能力分数混在一起。

## 数据切分

- 所有 deck、event、decision point 和 counterfactual group 带 `snapshot_id`。
- 同一赛事及其近重复牌表不得跨 train/test。
- `test_temporal` 在每个 regulation 内按禁限表或发售日期切分。
- `test_cross_regulation` 的源与目标快照必须显式记录；不得用目标环境赛事牌表做 retrieval。
- TCG 与 OCG 的同名卡文本、裁定或发售状态存在差异时，保留 locale/source/version，不做静默覆盖。

## 当前实现边界

本地 D1 validator 目前能检查：Main/Extra/Side 数量、全牌组 copy limit、CDB 卡池 availability bit 与缺失卡号。它还不能证明 event-specific 历史卡池完整，因此 `card_pool_cutoff = null` 的结果只能作为当前快照审计，不作为历史赛事 legality gold。

官方页面是禁限表权威来源；仓库内 LFList 是固定 commit 与 hash 的可执行镜像。OCG 官方页面为动态页面，正式发布数据时必须额外归档页面日期或官方公告。

## v1 成功标准

1. TCG 与 OCG 都通过 E0 replay、hidden-information 和 legal-action 验证。
2. 每个主任务在两个 snapshot 都有足够样本，而不是只把一个环境当少量附录。
3. 至少一个微观能力指标能解释两个环境内的 Full Duel 表现。
4. 跨环境实验能区分“记错禁限表/卡池”与“策略本身迁移失败”。

## 暂不纳入

- Master Duel Ranked/WCS；
- Duel Links Speed/Rush、角色与 Skill；
- World Championship 混合禁限表；
- GOAT、Traditional、Rush Duel 与其他历史/特殊赛制。

这些环境可以在 v1 schema 和数据管线稳定后作为独立 track 加入，不能共享未经验证的 legality 或 gameplay leaderboard。
