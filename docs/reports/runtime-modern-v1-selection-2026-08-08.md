# 现代 Runtime 版本选择与资产覆盖复核（2026-08-08）

> 2026-08-09 状态更新：现代资产现已通过 `init_module` 与 TCG/OCG 环境池构造验证，runtime snapshot 状态更新为 `adapter_initialized_smoke_pending`。这两类 Gate 均未调用 `reset()` 或 `step()`，因此 `runtime_adapter_ready=false`、`engine_ready=false` 仍保持不变。完整的 clean-commit Gate 证据将在独立的 pre-smoke 报告中记录。

## 结论

项目不追随滚动最新版，而是将 2026-07-20 已下载并固定的 EDOPro 现代资产定义为 `runtime-modern-v1-2026-07-20`：

- 规则引擎采用 `edo9300/ygopro-core` 的现代 `OCG_*` API；
- 卡片效果采用同一时点的 ProjectIgnis/CardScripts；
- 卡牌数据库采用 ProjectIgnis/BabelCDB；
- 禁限表采用 ProjectIgnis/LFLists；
- 默认卡池只纳入资产截止日之前已正式发行的卡，不默认纳入 prerelease/unofficial 卡。

该组合的源码和数据资产已经就绪，并能完整覆盖当前固定的 TCG 38 张唯一卡和 OCG 41 张唯一卡。2026-08-08 已确认 ygo-agent 自带一个现代 `edopro` adapter，并完成冻结 core API v11 所需的最小兼容补丁；扩展已经可以编译和动态加载。当前状态更新为 `adapter_buildable_engine_pending`，仍不能解释为已经可以运行完整对局。

## 固定版本

| 组件 | 来源 | Commit | Commit 日期 |
|---|---|---|---|
| Engine | `edo9300/ygopro-core` | `0764db0c75b3d1d574880d365aa3695ab1f13b43` | 2026-06-21 |
| CardScripts | `ProjectIgnis/CardScripts` | `aeb606ccfa9c1bf1b6a52970ab90053d760bc24e` | 2026-07-19 |
| BabelCDB | `ProjectIgnis/BabelCDB` | `ba612a7a2961098e978893b2a2c8600e317d2e61` | 2026-07-19 |
| LFLists | `ProjectIgnis/LFLists` | `64ebb3bb88c3a941bc1b504a408407251eff6501` | 2026-07-17 |

统一清单：`snapshots/runtime-modern-v1-2026-07-20.json`。

需要纠正此前的一处来源表述：`references/ygopro-core/` 是 `edo9300/ygopro-core` 的 EDOPro 现代 fork，不是旧的 `Fluorohydride/ygopro-core`。旧 core 仍保留在 `references/build-deps/ygopro-core/`，供已验证的 2024 ygoenv runtime 复现使用。

## 三种时间不能混用

| 时间 | 含义 |
|---|---|
| Runtime asset cutoff：2026-07-20 | 固定 core、CardScripts、CDB 和 LFLists 的可复现边界 |
| Banlist effective date | 各环境实际使用的禁限表生效日 |
| Card pool cutoff | 该环境允许进入任务的卡片发行边界 |

当前 TCG 环境使用 2026-05-18 禁限表，卡池截止 2026-07-11；OCG 环境使用 2026-07-01 禁限表，卡池截止 2026-07-18。后续即使更新 runtime，也不能据此自动改变历史环境的禁限表或卡池。

## 覆盖复核

修正后的脚本覆盖判断不再要求每个 passcode 都存在同名 Lua 文件，而是识别：

1. 同 passcode 的直接脚本；
2. 通过 BabelCDB `alias` 复用的脚本；
3. 通常怪兽和 Token 等按设计无需脚本的卡。

| 环境 | 唯一卡 | CDB | 有效脚本覆盖 | 现代资产状态 |
|---|---:|---:|---:|---|
| TCG KDE-E | 38 | 38/38 | 38/38 | `modern_assets_ready=true` |
| OCG JP | 41 | 41/41 | 41/41 | `modern_assets_ready=true` |

此前报告的两张“缺脚本”均是假 blocker：

- `PSY-Frame Driver`（49036338）是通常怪兽，不需要 Lua 脚本；
- `Harpie's Feather Duster`（18144507）alias 到 18144506，`c18144506.lua` 已存在。

旧 ygoenv runtime 的 CDB/脚本覆盖仍约为 61%，该结果没有被覆盖或改写。现代资产和旧 runtime 的检查现在明确分开。

## Adapter 编译进展

第三方 ygo-agent 同时包含旧 `ygopro` adapter 和现代 `edopro` adapter。现代 adapter 已经使用：

```text
OCG_CreateDuel / OCG_DuelProcess / OCG_DuelGetMessage / OCG_DuelSetResponse
```

冻结的 EDOPro core API v11 将四类结构体参数改为 `const *`。项目通过 `patches/ygo-agent/edopro-core-v11-api.patch` 修正四处调用，并由 `scripts/build_edopro_ygoenv.sh` 在 `tmp/` overlay 中应用，不改写固定的第三方源码快照。

编译验证结果：

- 环境：WSL `Ubuntu-22.04`、Conda `ygo`、Python 3.10.20；
- 输入：16 个现代 core C++ 源文件、7 个 SQLiteCpp 源文件；
- 输出：`tmp/build-edopro-modern/edopro_ygoenv.so`；
- 本次最终产物 SHA256：`8243fc06bd94ab9689f054c033a54fd4318f3c490f8429efb0166be21244ac48`（release 构建包含 LTO 与 `-march=native`，该哈希标识本次本机产物，不作为跨机器确定性构建承诺）；
- 动态依赖：全部可解析；
- Python 加载：通过，导出 `_EDOProEnvSpec`、`_EDOProEnvPool` 和 `init_module`。

构建输出中的 SQLiteCpp 预处理警告来自固定第三方依赖；另有 LTO 串行化提示。两者均未导致编译或链接失败。

## 当前真正的 Blocker

adapter 的“可编译、可加载、可初始化、可构造环境池”已经得到证明，但它尚未调用 duel reset，也没有完成合法动作、隐藏信息、重放、生命周期、吞吐和 random eval Gate。因此两套场景继续保持：

```text
runtime_adapter_ready=false
engine_ready=false
```

完整 BabelCDB、公共 CardScripts 根目录、`official/c*.lua`、alias 脚本、稳定 `code_list.txt` 和两副固定牌组均已接入。下一项验证是首次 duel reset 与首个合法 observation。

TCG/OCG profile 当前分别绑定不同环境 snapshot 和固定牌组，但 adapter 的 duel flags 均为 `DUEL_MODE_MR5`。禁限表、卡池截止与牌组合法性由 snapshot/deck verifier 负责，不由 core 在开局时重新检查。因此不能把两个 profile 表述为两套不同的引擎规则实现；它们是同一现代规则引擎上的两个版本化实验环境。

## 本轮没有执行的工作

- 没有覆盖或删除 2024 runtime；
- 没有拉取滚动最新版；
- 没有运行 random eval、smoke、LLM、API 或 Full Duel；
- 没有声称当前牌组已经可以在 ygoenv 中执行。

下一步应先规划并经用户确认一次不进行对局的 `init_module`/环境创建验证，明确现代脚本根目录、公共 Lua 依赖、CDB 和固定牌组的接线方式；随后才进入 runtime smoke 与完整 Gate，并保持 2024 与 modern-v1 两套 runtime 可切换。
