# 现代 Runtime v1：R0 最新二进制 Preflight（2026-08-15）

## 结论

最新 EDOPro adapter extension 已完成 R0 preflight。目标二进制 SHA-256 为 `2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc`；动态依赖全部可解析，Python 三个必要导出存在，`init_module`、TCG pool construct 与 OCG pool construct 均通过，两个 pool 均正常销毁，结束后没有残留 runtime 进程。

本轮严格没有调用 `reset()` 或 `step()`。因此它只证明“新二进制可初始化并构造/销毁两套 profile 的空环境池”，不证明新二进制的首次 observation、隐藏信息、合法动作、trace/replay、生命周期、吞吐、random eval 或完整对局正确。

旧 `4c9f4be7...` 二进制上取得的 reset 结论已被标记为 superseded，不能外推到当前 `2801283a...` 二进制。下一步需要单独授权 TCG/OCG reset smoke。

## 执行边界

| 项目 | 值 |
|---|---|
| 资源 | CPU-only；未使用 GPU、LLM 或 API |
| Conda 环境 | `ygo`，Python 3.10.20 |
| 执行阶段 | `init`、TCG `construct`、OCG `construct` |
| 明确未执行 | `reset`、`step`、dynamic hidden-information、trace/replay、lifecycle、throughput、random eval、full duel |
| 固定 Git commit | `30bbef0e8e6dbc723de01b0e7daeb664456e3211` |
| Config SHA-256 | `be1f0075e6d693072308e00c5ac4ac734c11b62b69f51d64b4553ad8a01f090c` |
| Asset manifest SHA-256 | `1758dc901ad1b3a4e339db833c0666ca94246920e780632bd37d16846a825cb6` |
| Frozen runtime snapshot SHA-256 | `2d84750b00cec5b30821d5b7cf6156b82a590311f3ac2c497a37727cfb61a5a8` |

运行时保留了用户已有的三份来源 HTML 未提交修改，因此 runner 如实记录 `git_dirty=true`；本轮 `tmp/` 产物被 `.gitignore` 忽略，不属于该状态原因。这不影响二进制、配置、资产 manifest、冻结 snapshot 与牌组输入哈希的绑定，但不满足“工作树完全干净”的 provenance 子条件；不得将本次结果表述为 clean-worktree execution。

## 二进制审计

| 检查 | 结果 |
|---|---|
| Extension 路径 | `tmp/build-edopro-modern/edopro_ygoenv.so` |
| SHA-256 | `2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc` |
| `ldd` | 解析 `libglog`、`libunwind`、`libstdc++`、`libm`、`libgcc_s`、`libc`、`libgflags`、`liblzma`、`libpthread`；无 `not found` |
| Python 导出 | `_EDOProEnvPool`、`_EDOProEnvSpec`、`init_module` 均存在 |

## Gate 结果

| Gate | Profile | 状态 | 耗时 | constructed | reset | stepped | destroyed |
|---|---|---|---:|---:|---:|---:|---:|
| `init` | - | passed | 0.246 s | 否 | 否 | 否 | 否 |
| `construct` | TCG | passed | 4.270 s | 是 | 否 | 否 | 是 |
| `construct` | OCG | passed | 1.919 s | 是 | 否 | 否 | 是 |

TCG profile 固定为 `tcg-kde-e-2026-05-18`，OCG profile 固定为 `ocg-jp-2026-07-01`。执行结束后的 `pgrep` 没有匹配 `edopro_ygoenv`，没有发现残留 runtime 进程。

## 证据与冻结策略

冻结输入 `snapshots/runtime-modern-v1-2026-07-20.json` 没有直接修改。该文件参与 R0 结果哈希；在运行后修改它会使刚刚生成的结果不能再与其 SHA 严格对应。

本次在 runtime snapshot 目录新增独立 evidence sidecar：

- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/r0-preflight-2026-08-15.json`

它固定记录新 extension 的 SHA、依赖/导出审计、R0 范围、正式结果路径、旧 reset 证据的 supersession 和下一授权边界。这样既更新当前 runtime 状态，又不篡改已经参与结果绑定的冻结输入。

## 下一步

后续状态（2026-08-15）：当前 SHA 的 TCG/OCG reset smoke 已在单独授权后通过，正式结果见 `docs/reports/runtime-modern-v1-reset-smoke-current-2026-08-15.md`。新的授权边界是 TCG/OCG 各一个合法 `step()`；在获得该授权前，不执行 `step` 或任何后续 Gate。

## 正式产物

- `results/runtime_modern_v1/r0_preflight_init_2026-08-15.json`
- `results/runtime_modern_v1/r0_preflight_construct_tcg_2026-08-15.json`
- `results/runtime_modern_v1/r0_preflight_construct_ocg_2026-08-15.json`
- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/r0-preflight-2026-08-15.json`
