# 现代 Runtime v1：Pre-smoke Gate 报告（2026-08-09）

> 后续状态：TCG/OCG reset smoke 已通过。正式结果见 `docs/reports/runtime-modern-v1-reset-smoke-2026-08-09.md`。本文保留为执行 smoke 前的历史 Gate 记录。

## 结论

`runtime-modern-v1-2026-07-20` 已完成现代 BabelCDB、CardScripts、公共 Lua 脚本目录、稳定 `code_list.txt` 和固定 TCG/OCG 牌组到 ygo-agent EDOPro adapter 的接线，并通过以下非对局 Gate：

1. 固定资产生成与覆盖审计；
2. 现代 EDOPro 扩展编译、动态依赖和 Python 导出检查；
3. `init_module` 初始化；
4. TCG 与 OCG profile 的环境池构造和空环境销毁。

当前状态为 `adapter_initialized_smoke_pending`。本轮没有调用 `reset()` 或 `step()`，尚未创建 duel，也没有验证合法动作、状态观测、完整对局、隐藏信息、replay、重复生命周期或吞吐。因此固定牌组中的 `runtime_adapter_ready=false` 和 `engine_ready=false` 继续保持。

## 固定输入

| 组件 | 固定版本或规模 |
|---|---|
| ygopro-core | `0764db0c75b3d1d574880d365aa3695ab1f13b43` |
| CardScripts | `aeb606ccfa9c1bf1b6a52970ab90053d760bc24e` |
| BabelCDB | `ba612a7a2961098e978893b2a2c8600e317d2e61` |
| LFLists | `64ebb3bb88c3a941bc1b504a408407251eff6501` |
| BabelCDB 正 card ID | 14,605 |
| `official/c*.lua` | 13,420 |
| 公共根目录 Lua | 25 |
| code list 顺序 | `datas.id` 升序，observation ID 从 1 开始，`uint16` |

`code_list.txt` SHA256：

```text
ad2283d28e812cd2f779e216963ea4afea286be831b5d4a12449e5fa5ece7812
```

资产 manifest SHA256：

```text
1758dc901ad1b3a4e339db833c0666ca94246920e780632bd37d16846a825cb6
```

## 固定牌组与脚本覆盖

| Profile | Environment snapshot | 固定牌组 | 唯一卡 | 有效脚本覆盖 |
|---|---|---|---:|---:|
| TCG | `tcg-kde-e-2026-05-18` | European WCQ 2026 Kewl Tune Top 64 | 38 | 38/38 |
| OCG | `ocg-jp-2026-07-01` | Japan Championship 2026 Kewl Tune Top 16 | 41 | 41/41 |

有效脚本覆盖允许三种情况：同 ID 的直接脚本、BabelCDB alias 对应脚本，以及按设计无需脚本的通常怪兽或 Token。OCG 牌组中的 `Harpie's Feather Duster` 通过 alias `18144507 -> 18144506` 加载脚本；`PSY-Frame Driver` 是无需 Lua 的通常怪兽。

公共入口 `constant.lua`、`utility.lua` 与固定牌组脚本合计形成 48 个唯一入口；递归静态依赖审计解析到 72 个脚本和 24 条静态加载边。唯一的特殊布局是 `proc_unofficial.lua -> unofficial/proc_unofficial.lua`，已在 adapter 中显式路由。另记录 1 个动态 `Duel.LoadScript(code)` 调用，不将其伪装成静态已解析依赖。

当前 pre-smoke 配置使用同 profile 镜像对战，防止 TCG 与 OCG 牌组在基础设施 Gate 中被直接混用。两个 profile 都使用 adapter 固定的 `DUEL_MODE_MR5`。禁限表、卡池截止和牌组合法性由版本化 snapshot/deck verifier 检查，不由 core 在开局时重新验证。

## Adapter 接线

构建过程不修改 `references/ygo-agent` 的冻结源码。`scripts/patch_edopro_adapter.py` 对源码执行 20 个必须恰好匹配一次的变换，生成 `tmp/` overlay。变换覆盖：

- EDOPro core API v11 的指针参数；
- 显式 CardScripts 根目录参数；
- 公共 Lua 与 `official/c*.lua` 的路径路由；
- `utility.lua` 所需 `unofficial/proc_unofficial.lua` 的显式路由；
- BabelCDB alias 脚本路由；
- CDB、code list、牌组和公共脚本的 fail-fast 检查；
- 以一次 JOIN 预加载 BabelCDB 全部 14,605 张卡，保证 Token、脚本生成卡和后续固定牌组也能进入 cardReader 与 observation；
- `uint16` observation card ID 容量与重复 ID 检查；
- duel/player 指针初始化；
- Reset、终局、析构和 replay 文件句柄的资源清理。

最终扩展：`tmp/build-edopro-modern/edopro_ygoenv.so`。

```text
SHA256 d475b6fd9a2284b0090e42e2cbc834c919f52ab3cdc150c4454779989b67c2ab
```

所有动态库依赖均可解析，Python 导出 `_EDOProEnvPool`、`_EDOProEnvSpec` 和 `init_module`。SQLiteCpp 头文件产生已知预处理警告，LTO 提示串行执行；二者没有导致编译或链接失败。

逐卡 SQL 原型虽然能覆盖全库，但 `init_module` 需要 17.37 秒。改为一次 JOIN 后，同一输入的初始化降至约 0.50 秒，`/usr/bin/time -v` 峰值内存约 44.0 MiB；最终正式 Gate 内部计时为 0.384 秒。该优化改变的是初始化缓存方式，不改变 code list 或对局规则。

## 正式 Gate 结果

| Gate | Profile | 结果 | 耗时 | `pool_reset` |
|---|---|---|---:|---:|
| Module initialization | - | 通过 | 0.384 s | false |
| Pool construction | TCG | 通过 | 1.996 s | false |
| Pool construction | OCG | 通过 | 2.435 s | false |

三项结果均记录：

- Git commit：`90325ceaa204f81a823cca7718dc5b68140bbd8f`；
- `git_dirty=false`；
- Python 3.10.20；
- WSL2 Ubuntu-22.04；
- config SHA256：`be1f0075e6d693072308e00c5ac4ac734c11b62b69f51d64b4553ad8a01f090c`；
- runtime snapshot SHA256：`e8214477b7371997965fb303a4a245a977860b2ebb76dc72729f8eaa1277f5ee`。

环境池构造会触发 ygo-agent 对旧 `gym` 包的弃用提示；当前实际构造的是其 Gymnasium pool wrapper。该提示没有导致 Gate 失败，但应作为后续依赖维护事项记录，不能静默隐藏。

## 首次 Runtime Smoke 申请配置

下一步需要首次调用 `reset()`，分别验证 TCG 与 OCG profile 能否创建 duel、加载公共 Lua/卡片脚本并返回首个合法 observation。建议配置如下：

`experiments/run_modern_runtime_gate.py --stage reset` 已实现 observation key/shape/dtype、合法动作数量、当前玩家和 card ID 范围检查，并有纯数组单元测试；该阶段尚未实际执行。

| 项目 | 配置 |
|---|---|
| 资源 | CPU-only；不使用 GPU、LLM 或 API |
| Profile | TCG、OCG 各一次 |
| 环境数/线程 | 1 / 1 |
| 牌组 | 各自固定牌组镜像对战 |
| Seed | TCG `20260808`；OCG `20260809` |
| 动作 | 只执行一次 reset；暂不跑完整局 |
| 预计耗时 | 每个 profile 少于 1 分钟 |
| 产物 | `results/runtime_modern_v1/gate_reset_tcg.json`、`gate_reset_ocg.json` 和原始 stderr 日志 |

通过标准：

1. 无 CDB、公共 Lua、卡片 Lua 或牌组缺失错误；
2. reset 返回 shape、dtype 与 spec 一致的有限 observation；
3. `1 <= num_options <= max_options`，每个可见 card ID 均能映射到 code list；
4. 销毁环境后进程正常退出，无 SIGABRT、double free 或重复关闭；
5. 结果完整记录 commit、输入 hash、profile、snapshot、seed、耗时和异常输出。

该 smoke 通过后，才能继续 legal-action execution、hidden-information、trace/replay、100 次生命周期、吞吐和每环境 32 局 random eval Gate。

## 产物

- `results/runtime_modern_v1/gate_init.json`
- `results/runtime_modern_v1/gate_construct_tcg.json`
- `results/runtime_modern_v1/gate_construct_ocg.json`
- `configs/runtime-modern-v1-2026-07-20.json`
- `data/runtime_snapshots/runtime-modern-v1-2026-07-20/manifest.json`
- `experiments/run_modern_runtime_gate.py`
