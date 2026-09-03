# YGO-Turns 数据源审计

## 一句话结论

`Rifa456/YGO-Turns` 是目前找到的最有价值的人类赛事状态数据之一，已经完整冻结且许可清楚；但它属于 2008 年前的 pre-MR1 历史环境，只包含回合结束状态而没有动作日志，并存在槽位截断与两处冲突主键，因此只能先进入历史策略与状态评估 pilot，不能直接作为现代 TCG/OCG Agent 决策 Gold。

## 1. 冻结结果

| 项目 | 结果 |
| --- | --- |
| 上游 | `Rifa456/YGO-Turns` |
| Hugging Face revision | `1661a60c2bf1a093e110d81825edcf63acda2611` |
| 数据文件 | `ygo-turns.parquet` |
| 文件大小 | 1,740,463 bytes |
| SHA-256 | `9c5a79931336e854f87d63cdcd62357d80c77a15c5e25edfdbed986d551b3077` |
| 许可证 | CC BY 4.0 |
| 本地路径 | `data/question_sources/raw/ygo-turns/` |
| 下载方式 | 固定 revision、原子写入、大小与哈希校验 |

上游主域在当前 WSL 网络中不可达，固定快照通过 `hf-mirror.com` 下载。下载器不依赖 latest 分支，后续能够复现同一字节内容。

## 2. 数据实际规模

Parquet footer 与实际字段审计得到：

| 指标 | 实际值 |
| --- | ---: |
| 回合状态行 | 23,280 |
| 特征列 | 241 |
| 赛事 match | 684 |
| duel | 1,792 |
| turn 0 行 | 1,792 |
| 单局最大状态数 | 73 |
| 非连续回合序列 | 0 局 |
| 非空卡名词表 | 525 |

`turn_number=0` 在每局恰好出现一次，应作为初始状态记录，而不是非法回合号。规范 duel 主键必须使用 `(match_id, duel_number)`，状态主键使用 `(match_id, duel_number, turn_number)`。

## 3. Schema

数据是一个扁平、双方对称的状态表：

| 字段组 | 代表字段 | 类型与含义 |
| --- | --- | --- |
| 索引 | `match_id`, `duel_number`, `turn_number` | `int64/int32`，定位状态序列 |
| 标签 | `is_p1_turn`, `p1_won` | `int8`，当前行动方与最终胜负 |
| 生命值 | `p1_life_points`, `p2_life_points` | `int64` |
| 怪兽区 | `p1_monster_zone_0_*` | 名称、ATK、DEF、里侧、指示物、表示形式 |
| 魔陷区 | `p1_spell_zone_0_*` | 名称、里侧、指示物 |
| 场地区 | `p1_field_spell_zone_*` | 名称、指示物 |
| 手牌 | `p1_hand_size`, `p1_hand_0..9` | 总数与最多 10 个卡名槽 |
| 牌库 | `p1_deck_size`, `p1_deck_top_0..4` | 总数与牌库顶 5 张 |
| 墓地 | `p1_gy_size`, `p1_gy_0..14` | 总数与最多 15 个卡名槽 |
| 除外 | `p1_banished_size`, `p1_banished_0..4` | 总数与最多 5 个卡名槽 |
| 额外 | `p1_extra_size`, `p1_extra_0..14` | 总数与最多 15 个卡名槽 |
| 装备 | `p1_monster_zone_0_equip_*` | 每个怪兽区记录装备数量和最多 2 个卡名 |

双方字段以 `p1_`、`p2_` 镜像。卡片身份只保存英文名称，没有 passcode、KONAMI cid 或稳定 replay 内部 ID；接入现有卡表时必须通过冻结名称映射，并人工处理旧卡名与 errata。

## 4. 数据质量发现

### 4.1 文档与文件不一致

数据卡写 Parquet 使用 ZSTD，实际 footer 显示所有列均为 SNAPPY。这不影响读取，但说明发布说明不能代替机器审计。

数据卡报告 P1 胜率 55.7%。配套 EDA 脚本实际计算的是所有状态行上 `p1_won` 的均值，精确值为 55.717%；它会让长对局获得更大权重。按每局只计一次时，P1 胜率是 59.375%。后续报告必须写明加权口径。

### 4.2 冲突主键

以下两个状态主键各出现两次，且重复行不是完全相同副本，每组有 56 列不同：

- `(match_id=221, duel_number=3, turn_number=5)`
- `(match_id=222, duel_number=3, turn_number=5)`

这些记录不能通过“保留第一条”静默处理。进入任何派生集前应整体隔离这两个 duel，或取得上游 replay 后重新裁决。

### 4.3 状态槽位截断

实际 size 超过固定身份槽位的 player-zone observation 数量如下：

| 区域 | 身份槽位 | 实际最大 size | 超限 observation |
| --- | ---: | ---: | ---: |
| 手牌 | 10 | 21 | 1,880 |
| 墓地 | 15 | 42 | 4,401 |
| 除外 | 5 | 24 | 1,254 |
| 额外卡组 | 15 | 15 | 0 |

因此 size 字段是完整计数，但对应卡片身份在不少状态中不完整。牌库也只提供顶 5 张，并不是逐状态的完整牌库顺序。需要完整卡片集合的任务必须排除超限样本，或显式标为截断状态。

### 4.4 隐藏信息

原始表同时包含双方手牌身份与双方牌库顶 5 张，共有 15 个对手私有身份列。这是离线重建的全知状态，不是玩家或 Agent 合法可见的 observation。

任何 Agent 输入必须经过视角化投影：隐藏对手手牌、牌库顶、盖卡身份和其他不可见信息。原始私有字段只能作为信念校准或离线标签，不能直接送入模型。

## 5. 对 YGO-Bench 的用途

| 任务 | 判断 | 原因 |
| --- | --- | --- |
| 历史状态价值判断 | 可用 | 有连续状态与最终胜负，可按 match 切分 |
| 隐藏信息信念校准 | 有条件可用 | 必须先生成合法 observation，raw 私有字段只作 latent truth |
| 状态序列一致性 | 可用 | 1,792 局序列连续，可测状态跟踪 |
| Replay 决策点 | 不可直接用 | 没有逐动作、候选动作、时间戳或 replay URL |
| Chain/响应时点 | 不可用 | 只有回合末快照，缺少 chain 内事件 |
| 现代 TCG/OCG 策略 | 不可作为主结果 | 数据属于 pre-MR1，规则与卡池过旧 |
| Full Duel Agent | 不可用 | 没有可交互环境或动作 oracle |

推荐把它定义为 `historical_pre_mr1_state_value` 辅助集，而不是并入现代 `ReplayDecision` 主测试集。它最有价值的作用是验证数据管线、视角化和 match-level split，并提供一个真实人类赛事的历史对照。

## 6. 接入前的最低处理要求

1. 按 `match_id` 划分 train/dev/test，禁止同一 match 的 turn 泄漏到不同 split。
2. 隔离两个冲突 duel，不做静默去重。
3. 对需要完整身份的任务排除手牌、墓地或除外区超限状态。
4. 创建 player-relative observation，严格遮蔽对手私有区域。
5. 将英文卡名桥接到 passcode，并保存映射版本与未匹配列表。
6. 所有结果显式标记 `ruleset=pre_mr1`，不得外推到当前 TCG/OCG。
7. 评估胜率时区分 snapshot-weighted 与 duel-weighted 两种口径。

## 7. 当前判断

完整冻结是正确的：文件小、来源明确、许可允许研究与再利用，而且它证明了 DuelingBook replay 与赛事牌表能够被重建为结构化状态数据。但它没有解决现代策略 Bench 最难的问题，即“在给定合法 observation 与候选动作时，人类专家为什么选择这一动作”。最值得继续向作者询问的是原始 replay/event 序列、来源 URL、赛事日期与 rating、牌组标签，以及能否提供现代格式数据。

来源：

- https://huggingface.co/datasets/Rifa456/YGO-Turns
- https://github.com/rifa-456/YGO-Turns
