# TCG/OCG 固定 Snapshot Pilot（2026-08-04）

> 2026-08-08 复核：本报告中的约 56%–58% 脚本覆盖指旧 ygoenv runtime。现代 2026-07-20 CardScripts 经过 alias 与无需脚本卡修正后，TCG/OCG 当前固定牌组均为 100% 有效脚本覆盖。两套场景仍为 `engine_ready=false`，但 blocker 已收敛为现代 `OCG_*` API adapter 尚未接入。详见 `docs/reports/runtime-modern-v1-selection-2026-08-08.md`。

## 结论

已为 TCG 与 OCG 各冻结一副 2026 赛事牌组和一个确定性开局场景。两副牌均为 40 主牌、15 额外、15 side，对应禁限表违规数为 0，BabelCDB 卡片覆盖率为 100%。

它们现在适合进入构筑与卡牌理解数据实验，但还不能进入 ygoenv 策略对局实验：当前 ygoenv runtime 仍是 2024 卡池，牌表数据库覆盖约 60%，Lua script 覆盖约 56%–58%。生成的场景因此明确标记为 `engine_ready=false`。

## 固定资产

| 环境 | 固定牌组 | 赛事 | 禁限表 | runtime CDB | runtime scripts | 策略场景 |
|---|---|---|---:|---:|---:|---|
| TCG KDE-E | Kewl Tune Top 64 | European WCQ 2026, 2026-07-11 | 0 违规 | 23/38 | 22/38 | blocked |
| OCG JP | Kewl Tune Top 16 | Japan Championship 2026, 2026-07-18 | 0 违规 | 25/41 | 23/41 | blocked |

统一 manifest：`data/fixed_snapshots/manifest.json`

每个环境目录包含：

- 结构化 JSON 牌表，带卡名、passcode、数量、来源 hash 与覆盖检查；
- 可供 ygopro/ygoenv 使用的 `.ydk`；
- 一个固定 deck、engine seed、action seed 的 `seeded_full_duel_start` 场景；
- 精确的缺卡与缺脚本 blocker 列表。

## 来源链

TCG：KONAMI 的 European WCQ 赛事页确认赛事日期与 Advanced Constructed 环境；YGOPRODeck 赛事牌表页提供 passcode 列表。

OCG：KONAMI 的日本选手权页面确认 2026-07-18 赛事结果与环境，官方 2026-07-01 禁限表固定 regulation；YGOPRODeck 同赛事牌表页提供 passcode 列表。

原始页面保存在 `data/source_samples/ygoprodeck_tournament/`，结构化产物保留原始 HTML 的 SHA-256。第三方牌表与官方赛事页是双来源，不把第三方 tournament 标签单独当作官方证明。

## 能力实验路由

| 能力 | 当前是否可开始 | 可做内容 |
|---|---|---|
| 理解 | 是 | 卡片文本问答、条件/cost/target/OPT 标签、TCG/OCG 可用性差异 |
| 构筑 | 是 | 禁限合法性、卡位补全、side-deck 选择、跨环境迁移 |
| 策略 | 否 | runtime 卡池与脚本未对齐，固定场景不能可靠执行 |

因此不应立即运行 API 或本地对局 agent。先将当前 BabelCDB 与 CardScripts 接入 ygoenv runtime，再对两个固定场景执行加载、合法动作、终局、隐藏信息和 replay 五项 gate。

## 复现

```powershell
D:\anaconda3\python.exe experiments\freeze_tcg_ocg_snapshots.py
```

该命令会重新生成两副 JSON/YDK、场景文件和覆盖 manifest。
