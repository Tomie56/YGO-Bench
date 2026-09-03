# 正式实验前 Readiness 审计（2026-08-09）

> 状态更新：本报告绑定提交 `d04d76a` 与旧 extension。后续发现旧 adapter 暴露当前玩家主卡组洗牌顺序，修复后的 binary 已使本报告对应的 canonical readiness 结果失效。当前状态与重验要求见《现代 Runtime v1 主卡组隐藏信息修复（2026-08-09）》；本报告保留为历史审计记录。

## 一句话结论

YGO-Bench 的数据契约、模型适配、确定性评分、TCG/OCG 官方环境快照和现代 runtime reset 基础已经就绪，但正式模型实验仍不应开始。当前仅剩两个明确 blocker：E0 数据资格未达到样本量与双人标注要求，以及现代 runtime 的 reset 之后 Gate 尚未验证。

审计状态为 `not_ready`。这不是底层失败，而是对研究结论边界的主动约束：当前可以继续建设数据和 Gate runner，不能把已通过的 reset smoke 写成完整策略环境已经可用。

## 审计配置

| 项目 | 值 |
|---|---|
| Readiness ID | `pre-experiment-readiness-v0.1` |
| Git commit | `d04d76af9c3f674d31972f1a016ad4cda0ee2394` |
| Git dirty | `false` |
| WSL / Conda | `Ubuntu-22.04` / `ygo` |
| Python | 3.10.20 |
| 资源 | CPU-only；无 GPU、LLM 或 API |
| 配置 | `configs/pre-experiment-readiness-v0.1.json` |
| 正式结果 | `results/readiness/pre_experiment_v0.1.json` |

审计记录配置、脚本、schema、snapshot、runtime 结果、E0 结果和核心实现的 SHA-256；正式结果由干净工作树生成。

## 当前状态

| 模块 | 状态 | 结论依据 |
|---|---|---|
| WSL/Conda 环境 | 通过 | 发行版、环境名、Python 与必需包均匹配 |
| 数据契约 | 通过 | benchmark record、model output、evaluation result、runtime/environment snapshot 与 fixed scenario 均通过 schema 校验 |
| 模型与评分基础设施 | 通过 | provider-neutral adapter、严格输出校验和确定性 scorer 可导入且版本固定 |
| TCG/OCG 环境快照 | 通过 | 官方规则、赛事政策、禁限表和事件规则证据已冻结，两个 snapshot 均无 `open_fields` |
| Runtime foundation | 通过 | init、TCG/OCG construct、TCG/OCG reset 均有正式通过记录 |
| Runtime engine | 未通过 | reset 之后的 legal action、隐藏信息、重放、生命周期、吞吐与 random eval 尚未完成 |
| E0 数据资格 | 未通过 | Understanding 0/30；TCG 与 OCG 赛事牌组均为 1/10 |
| 论文协议 | 通过 | 三层 Benchmark、实验路线与评价边界已有版本化文档 |

## 已关闭的问题

1. TCG snapshot 已绑定 Rulebook v9.01、2021 Rules Update 和 KDE-E Tournament Policy v2.5。
2. OCG snapshot 已绑定 2026 年 7 月禁限表和 Japan Championship 2026 规则；卡池截止日根据赛事规则修正为 2026-07-17。
3. 两个 snapshot 的待定字段均已清空，可作为论文数据的环境版本依据。
4. TCG/OCG 固定牌组均能初始化并完成一次 reset；结果保持 `pool_reset=true`、`pool_destroyed=true`，且 observation 与 card ID 校验通过。
5. E0 中两份已有赛事牌组的结构解析、原始 HTML 复解析和 provenance 完整率均为 100%。

## 仍需完成的 Gate

### 数据 Gate

- 建立 30 个 Understanding pilot 样本，完成两位标注者独立六字段标注；字段级一致率目标至少 90%。
- TCG 与 OCG 各再补 9 副同 snapshot、赛事和名次可核验的完整牌组，使每个环境达到 10 副。
- 重跑 E0；只有总 Gate 通过，才冻结本地 7B 与 frontier API 的正式配置。

### Runtime Gate

- TCG/OCG 各验证一次合法 action 的实际执行，而不只是读取 action 输出。
- 验证双方 observation 不泄露隐藏信息。
- 验证 trace/replay 的状态 hash 一致。
- 每个环境连续创建与销毁 100 次，确认不触发崩溃或资源生命周期错误。
- 验证吞吐并达到预设阈值，再运行每环境 32 局 random eval。

上述各项仍属于 smoke 或运行时实验，需在执行前单独说明目标、配置、资源、产物和判定标准，并获得明确授权。本轮没有执行这些 Gate，也没有运行 LLM、API 或完整对局。

## 对论文实验的直接含义

静态 Benchmark 的软件接口已经足以接入多种 API 或本地模型，但测试数据尚未达到最小资格，因此现在运行模型不会产生可发表的比较。动态 Benchmark 已证明现代卡表与固定牌组能够进入引擎初始状态，但尚不能支持策略能力或完整对局结论。

下一步应并行推进两件事：补齐 E0 的 Understanding 与构筑数据，以及逐项实现并申请执行 reset 之后的 runtime Gate。二者都通过后，才进入本地 7B、frontier API、harness 消融和小规模 Full Duel。
