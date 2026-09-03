# 现代 Runtime v1：TCG/OCG Reset Smoke 报告（2026-08-09）

> 状态：**superseded（2026-08-15）**。本文 reset 结果绑定 extension SHA-256 `4c9f4be724ad5ae093f6e518f564273bafb57c50888fb61d535daeb27e8ce35d`。当前 runtime config 指向的新 extension SHA-256 为 `2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc`，两者不同；因此本文不能证明新二进制的 reset 正确性。新二进制仅完成 init/construct R0 preflight，见 `docs/reports/runtime-modern-v1-r0-preflight-2026-08-15.md`。必须在新 SHA 上重新完成 TCG/OCG reset smoke 后，才能恢复 reset-level runtime claim。

## 结论

用户授权的 TCG/OCG reset smoke 均已通过。当前现代 runtime 能够使用冻结的 2026 TCG 与 OCG 牌组创建 duel，完成首次 `reset()`，生成结构合法且不泄露私有卡牌身份的 observation，并正常销毁环境池。

这使 runtime foundation 的五个 Gate（init、TCG/OCG construct、TCG/OCG reset）全部通过，但不等于完整策略环境已经 ready。本轮没有执行 `step()`、动态 hidden-information audit、trace/replay、100 次生命周期、吞吐、32 局 random eval 或完整对局，因此 `engine_ready` 继续保持 `false`。

## 执行配置

| 项目 | TCG | OCG |
|---|---|---|
| Environment snapshot | `tcg-kde-e-2026-05-18` | `ocg-jp-2026-07-01` |
| 固定牌组 | European WCQ 2026 Kewl Tune Top 64 | Japan Championship 2026 Kewl Tune Top 16 |
| 对局配置 | 同牌组 mirror | 同牌组 mirror |
| Seed | `20260808` | `20260809` |
| num_envs / batch / threads | 1 / 1 / 1 | 1 / 1 / 1 |
| 执行范围 | 一次 `reset()`，不执行 action | 一次 `reset()`，不执行 action |
| GPU / LLM / API | 未使用 | 未使用 |

实际命令：

```bash
conda activate ygo
python -m experiments.run_modern_runtime_gate --stage reset --profile tcg
python -m experiments.run_modern_runtime_gate --stage reset --profile ocg
```

## 固定输入

| 项目 | 值 |
|---|---|
| Git commit | `fde9fe0cfcef2acd57ca7e1dac8e33f9476ee489` |
| ygopro-core | `0764db0c75b3d1d574880d365aa3695ab1f13b43` |
| CardScripts | `aeb606ccfa9c1bf1b6a52970ab90053d760bc24e` |
| BabelCDB | `ba612a7a2961098e978893b2a2c8600e317d2e61` |
| extension SHA-256 | `4c9f4be724ad5ae093f6e518f564273bafb57c50888fb61d535daeb27e8ce35d` |
| runtime snapshot SHA-256 | `2d84750b00cec5b30821d5b7cf6156b82a590311f3ac2c497a37727cfb61a5a8` |
| asset manifest SHA-256 | `1758dc901ad1b3a4e339db833c0666ca94246920e780632bd37d16846a825cb6` |
| config SHA-256 | `be1f0075e6d693072308e00c5ac4ac734c11b62b69f51d64b4553ad8a01f090c` |
| Python / platform | 3.10.20 / WSL2 Linux 5.15.167.4 |

runtime snapshot 文件本身仍记录 `adapter_initialized_smoke_pending`，因为它是所有 Gate 结果参与哈希的冻结输入。直接修改该字段会使 init、construct 和 reset 证据全部失效。当前运行状态由本报告、固定场景状态与机器 Gate 结果表达为 `reset_smoke_verified_followup_gates_pending`。

## 结果

| 指标 | TCG | OCG |
|---|---:|---:|
| 状态 | passed | passed |
| 耗时 | 2.480 s | 2.047 s |
| 合法动作数 | 3 | 8 |
| to_play | 1 | 0 |
| 可见 card rows | 24 | 20 |
| 最大 observation card ID | 14,407 | 14,407 |
| 己方主卡组 rows | 35 | 35 |
| 己方主卡组身份泄露 | 0 | 0 |
| 己方主卡组详情泄露 | 0 | 0 |
| 己方手牌 rows | 5 | 5 |
| 己方手牌身份缺失 | 0 | 0 |
| 对手私有区 rows | 51 | 55 |
| 对手私有区身份泄露 | 0 | 0 |
| 对手私有区详情泄露 | 0 | 0 |
| 对手私有区顺序泄露 | 0 | 0 |
| pool 正常销毁 | 是 | 是 |

两边 observation 均严格满足：

- `cards_`: `[1, 150, 40]`, `uint8`
- `global_`: `[1, 9]`, `uint8`
- `actions_`: `[1, 64, 30]`, `uint8`
- `h_actions_`: `[1, 32, 30]`, `uint8`

最大 observation card ID 没有超过冻结 `code_list.txt` 的 14,605 个条目。两份结果均记录 `git_dirty=false`、`pool_reset=true`、`pool_stepped=false` 和 `pool_destroyed=true`。

本次结果是在 tournament corpus v0.1 与 environment snapshot 分层元数据提交后重新生成。两副 runtime primary 牌组、runtime config、extension、asset manifest 和 runtime snapshot 的 hash 均未改变；重新验证用于把正式 Gate 证据锚定到当前干净提交，而不是推断旧结果仍然有效。

## 隐藏信息结论

本轮已经完成 reset observation 的隐藏信息与 identity-grounding 检查：

- 己方洗牌后主卡组只保留位置/数量信息，不暴露卡牌 ID 或效果详情；
- 己方起手五张卡均能映射到冻结 observation card ID；
- 对手手牌、主卡组与 Extra Deck 不暴露身份、详情或可恢复顺序；
- reset 状态没有对手盖卡，因此盖卡计数为 0，这一分支仍由合成单元测试覆盖。

这个结论只适用于首次 reset。执行动作、连锁、展示、检索、随机除外或临时可见状态后，hidden-information policy 是否仍正确，需要单独的动态 Gate。

## 执行异常与解释

第一次使用 `python experiments/run_modern_runtime_gate.py` 时在 Python import 阶段因模块搜索路径不包含仓库根目录而失败，未导入 runtime、未创建 pool、未调用 reset、未生成结果。正式执行改用模块入口 `python -m experiments.run_modern_runtime_gate`。实现没有加入 `sys.path` 兜底。

正式进程末尾输出旧 Gym 包的弃用提示。当前 pool 通过 Gymnasium 接口运行，提示没有改变返回值或 Gate 判定；后续应把移除上游 Gym import 作为普通依赖清理，而不是本次结果 blocker。

## 当前边界与下一步

仍待单独评估和授权的 runtime Gate：

1. TCG/OCG 各执行一个经过验证的合法动作，检查 response/message parsing 与状态变化；
2. 在动作、连锁与公开卡牌变化后做动态 hidden-information/identity-grounding audit；
3. trace/replay action 与状态 hash 一致性；
4. 连续创建/销毁 100 次无崩溃或资源生命周期错误；
5. 测量并恢复到目标吞吐（约 1,000 steps/s）；
6. TCG/OCG 各 32 局 random eval。

在这些 Gate 通过前，不运行本地 7B、frontier API 或完整 Agent 对局。

## 正式产物

- `results/runtime_modern_v1/gate_reset_tcg.json`
- `results/runtime_modern_v1/gate_reset_ocg.json`
- `docs/reports/runtime-modern-v1-reset-smoke-2026-08-09.md`
