# 现代 Runtime v1：当前二进制单步 Gate（2026-08-15）

## 结论

当前 extension（SHA-256 `2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc`）已通过 TCG 与 OCG 各一个合法 action 的单步 Gate。两边均从首次 reset 开始，验证 action index `0` 位于合法动作范围，再执行该动作；状态哈希发生变化，post-step observation 结构合法，单状态动态 hidden-information/identity-grounding 检查通过，环境池正常销毁。

这证明当前 adapter 能完成基础的 action encoding、response/message parsing 与一次状态转移，但不能证明其能在长对局中持续处理连锁、展示、检索、打断或隐藏信息变化。`engine_ready` 继续保持 `false`。

## 范围与配置

| 项目 | 值 |
|---|---|
| Gate 协议 | `runtime-modern-gates-v0.1`，固定 `action_index=0` |
| Profile | TCG `tcg-kde-e-2026-05-18`；OCG `ocg-jp-2026-07-01` |
| 执行内容 | 每个 profile：一次 reset + 一个合法 step |
| 明确未执行 | dynamic coverage、trace/replay、lifecycle、throughput、random eval、完整对局、GPU、LLM、API |
| Git commit | `860f071eaa7b88f51b1593ac6f5f609282040993` |
| 工作区状态 | `git_dirty=true`，因保留用户已有的 3 个来源 HTML 修改 |

## 结果

| 指标 | TCG | OCG |
|---|---:|---:|
| 状态 | passed | passed |
| 总耗时 | 1.925 s | 1.585 s |
| reset 前合法动作数 | 3 | 8 |
| 执行动作 | 0 | 0 |
| step 后合法动作数 | 5 | 5 |
| state changed | 是 | 是 |
| terminal / truncated | 否 / 否 | 否 / 否 |
| 最大学习 card ID | 14,407 | 14,407 |
| post-step 动态 hidden-information | passed | passed |
| confirmed reveal rows | 0 | 0 |
| pool 正常销毁 | 是 | 是 |

两边的 pre/post observation SHA-256 均不相同，因而并非“动作被静默忽略”。post-step observation 的 `cards_`、`global_`、`actions_` 与 `h_actions_` shape/dtype 均匹配冻结 spec；动态审计确认私有行没有 identity、详情或顺序泄露，并且可见行没有缺失 identity。

## 限制

本次每个环境只有一个 post-step state，且 `confirmed_reveal_rows=0`、`selectable_own_deck_rows=0`。因此它没有覆盖展示、检索或可选择卡组卡等最容易出错的动态可见性分支。不能把本轮的单状态通过表述为“动态隐藏信息已经全面验证”。

## 后续边界

下一项需单独授权的检查是动态 hidden-information coverage Gate：在受限动作轨迹中审计至少 100 个状态、至少 100 个私有区行，并要求至少一次 confirmed reveal。该 Gate 通过前，不进入 trace/replay、生命周期、吞吐、32 局 random eval、模型/API 或完整 Agent 对局。

## 正式产物

- `results/runtime_modern_v1/step_gate_tcg_2026-08-15.json`
- `results/runtime_modern_v1/step_gate_ocg_2026-08-15.json`
- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/step-gate-2026-08-15.json`
