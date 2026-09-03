# 现代 Runtime v1：当前二进制 TCG/OCG Reset Smoke（2026-08-15）

## 结论

当前 EDOPro adapter extension（SHA-256 `2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc`）已通过 TCG 与 OCG 各一次 reset smoke。两种 profile 均能创建 duel、完成首次 `reset()`、返回结构合法的 observation、通过 reset-level identity-grounding 与隐藏信息审计，并正常销毁环境池。

这使当前二进制的 runtime foundation 五项基础 Gate 全部有直接证据：init、TCG construct、OCG construct、TCG reset、OCG reset。旧 extension SHA `4c9f4be7...` 上的 reset 结论仍仅保留为历史记录；当前 reset-level claim 只由本报告和本轮 JSON 结果支持。

`engine_ready` 仍然是 `false`。本轮没有执行 `step()`，因此不证明 response/message parsing、状态转移、动态可见性、trace/replay、一百次生命周期、吞吐、random eval 或完整对局正确。

## 执行配置

| 项目 | TCG | OCG |
|---|---|---|
| Environment snapshot | `tcg-kde-e-2026-05-18` | `ocg-jp-2026-07-01` |
| 固定牌组 | European WCQ 2026 Kewl Tune Top 64 | Japan Championship 2026 Kewl Tune Top 16 |
| 对局配置 | 同牌组 mirror | 同牌组 mirror |
| Seed | `20260808` | `20260809` |
| 执行范围 | 一次 `reset()`，不执行 action | 一次 `reset()`，不执行 action |
| GPU / LLM / API | 未使用 | 未使用 |

运行于 WSL `Ubuntu-22.04` 的 `ygo` Conda 环境，Python 3.10.20。结果绑定：Git commit `6c21f9039b3360100907172d341ae89aab8654b7`、config SHA-256 `be1f0075e6d693072308e00c5ac4ac734c11b62b69f51d64b4553ad8a01f090c`、asset manifest SHA-256 `1758dc901ad1b3a4e339db833c0666ca94246920e780632bd37d16846a825cb6` 与 frozen runtime snapshot SHA-256 `2d84750b00cec5b30821d5b7cf6156b82a590311f3ac2c497a37727cfb61a5a8`。

运行时保留了用户已有的三份来源 HTML 未提交修改，因此结果 JSON 如实记录 `git_dirty=true`。这不影响被记录的输入哈希与 extension SHA，但不满足“工作树完全干净”的 provenance 子条件。

## 结果

| 指标 | TCG | OCG |
|---|---:|---:|
| 状态 | passed | passed |
| 耗时 | 2.364 s | 1.999 s |
| 合法动作数 | 3 | 8 |
| `to_play` | 1 | 0 |
| 可见 card rows | 24 | 20 |
| 最大 observation card ID | 14,407 | 14,407 |
| 己方主卡组 rows | 35 | 35 |
| 己方主卡组身份/详情泄露 | 0 / 0 | 0 / 0 |
| 己方手牌 rows / 身份缺失 | 5 / 0 | 5 / 0 |
| 对手私有区 rows | 51 | 55 |
| 对手私有区身份/详情/顺序泄露 | 0 / 0 / 0 | 0 / 0 / 0 |
| 对手盖卡身份/详情泄露 | 0 / 0 | 0 / 0 |
| pool 正常销毁 | 是 | 是 |

两边 observation 都符合冻结 spec：`cards_` 为 `[1, 150, 40]`、`global_` 为 `[1, 9]`、`actions_` 为 `[1, 64, 30]`、`h_actions_` 为 `[1, 32, 30]`，全部为 `uint8`。14,407 小于冻结 `code_list.txt` 的 14,605 条目数。

## 隐藏信息结论

本轮仅审计首次 reset observation：

- 己方洗牌后主卡组不暴露 card ID 或效果详情；
- 己方起手五张卡都有稳定 observation card ID；
- 对手手牌、主卡组与 Extra Deck 不暴露身份、详情或可恢复顺序；
- 首次 reset 没有对手盖卡，因此盖卡泄露计数为零，但这不是动态盖卡路径的证据。

这不能替代执行动作、连锁、展示、检索或临时可见状态之后的动态 hidden-information audit。

## 证据与后续边界

本轮的 runtime evidence sidecar 为：

- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/reset-smoke-2026-08-15.json`

冻结 `snapshots/runtime-modern-v1-2026-07-20.json` 未在运行后被改写，以保持结果 JSON 记录的 snapshot SHA 可复现。该 sidecar 与 R0 evidence 一起表达当前二进制状态。

后续状态（2026-08-15）：当前 SHA 的 TCG/OCG 单步 Gate 已在单独授权后通过，正式结果见 `docs/reports/runtime-modern-v1-single-step-2026-08-15.md`。新的授权边界是动态 hidden-information coverage Gate；获得该授权前，不执行任何后续 runtime Gate，也不接入本地模型或 API。

## 正式产物

- `results/runtime_modern_v1/reset_smoke_tcg_2026-08-15.json`
- `results/runtime_modern_v1/reset_smoke_ocg_2026-08-15.json`
- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/reset-smoke-2026-08-15.json`
