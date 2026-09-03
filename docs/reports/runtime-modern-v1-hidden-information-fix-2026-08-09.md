# 现代 Runtime v1 主卡组隐藏信息修复（2026-08-09）

## 结论

现代 EDOPro adapter 原先会在 observation 中编码当前行动玩家自己主卡组的完整卡片身份和洗牌后顺序。这不是单纯的特征设计差异，而是会直接污染策略 Benchmark 的隐藏信息泄漏。该问题已经在 tracked adapter transform 中修复，新 extension 已完成编译、链接和 Python 导出验证；由于 binary 变化，原 TCG/OCG reset 结果已失效，必须重新验证后才能恢复 `runtime_adapter_ready=true`。

本轮没有运行 reset、step、hidden-information trace、完整对局、LLM 或 API。

## 问题与影响

adapter 的 observation 将当前玩家和对手的卡片分别放在固定的 card row 区域。旧实现会查询并完整编码当前玩家主卡组中的每张卡，因此模型不仅知道自己的构筑，还能知道洗牌后的顶牌顺序。

这会使模型在抽卡规划、是否投入资源、是否检索、是否接受风险等决策中使用现实玩家不可见的信息。若不先修复，后续 Full Duel、局部策略和 harness 消融都无法支持“LLM/Agent 是否能成为优秀玩家”的结论。

## 修复语义

1. 当前玩家自己的主卡组默认只保留卡片数量、区域和动作映射，不写入 card ID、属性、种族、等级、攻防或类型。
2. 当当前合法选择明确包含自己主卡组中的候选卡时，仅这些候选可暂时显示身份，以支持检索、选择和长组合决策。
3. `MSG_CONFIRM_CARDS` 等规则消息明确公开的卡片可以显示。
4. “某张对手盖卡可以被选择为 target”不等于身份公开；对手盖卡不会因为出现在合法 action 中而泄漏身份。
5. 对手主卡组、手牌和额外卡组继续使用 count-only 编码；对手盖伏场上卡继续隐藏身份和细节。

reset validator 同步增加了严格审计：自己的主卡组不能有身份或细节泄漏，自己的手牌必须可 grounding，对手私有区域和盖卡不能暴露身份、序列或细节。

## 构建环境修复

原构建脚本使用 Ubuntu 22.04 默认 GCC 11.4.0 单进程编译全部源文件。此次构建先后在三个不同源文件、三个不同优化 pass 中发生 GCC internal compiler error；同时 WSL 内核记录 9p `FS-Cache: Duplicate cookie`、`Operation canceled` 和 journal 非正常关闭。可用内存仍有约 14 GiB，因此不是内存耗尽。

正式 build profile 现固定为：

| 项目 | 值 |
|---|---|
| Compiler | `g++-12 12.3.0` |
| C++ standard | C++17 |
| Optimization | `-O2 -march=native` |
| Strategy | 52 个 translation units 分离编译后统一 shared link |
| Lua | 固定 Lua 5.4.8，以 C++ 编译并静态链接 |
| Output | `tmp/build-edopro-modern/edopro_ygoenv.so` |
| SHA-256 | `4c9f4be724ad5ae093f6e518f564273bafb57c50888fb61d535daeb27e8ce35d` |

构建脚本会拒绝非 GCC 12.x，不增加自动 fallback 或重试。最终 `ldd` 不依赖系统 Lua，Python 导出 `_EDOProEnvPool`、`_EDOProEnvSpec` 和 `init_module` 均验证通过。

## 当前状态

- Runtime snapshot：`adapter_initialized_smoke_pending`
- Adapter status：`init_and_pool_construct_verified`
- TCG/OCG `runtime_adapter_ready`：`true`
- TCG/OCG `engine_ready`：`false`
- 当前 canonical init/construct JSON：已从最终 snapshot 状态重新生成并通过
- 当前 canonical reset/readiness JSON：reset 等待授权重验；readiness 将在当前 Gate 结果提交后重新生成
- 非 smoke 测试：41/41 通过
- 当前 readiness：`not_ready`；init/TCG construct/OCG construct passed，TCG/OCG reset pending
- 当前 readiness commit：`4d790f8af633c2012dadfd9808459da09f700364`
- 当前 readiness 结果：`results/readiness/pre_experiment_v0.1.json`

当前 readiness 还确认 `understanding-annotation` contract 与中文双标协议均已纳入正式前置材料并通过完整性检查；E0 使用严格版双标/裁决计数，当前 adjudicated Gold 仍为 0/30。

历史 reset 报告仍保留，并明确绑定旧 extension hash；它只能说明旧 binary 曾完成 reset，不能证明当前修复后的 binary 已通过。

## 下一步 Gate

1. 已在干净提交 `378a621` 完成 preflight：init 0.359 秒、TCG construct 2.393 秒、OCG construct 2.322 秒；两个 pool 均成功销毁，未调用 reset。
2. 已从最终状态提交 `6dc11b8` 重新生成正式 Gate：init 0.302 秒、TCG construct 2.432 秒、OCG construct 1.780 秒，均 `git_dirty=false`，两个 pool 均成功销毁。
3. 单独申请 TCG/OCG reset re-verification。新的 reset Gate 必须同时通过 observation contract、card ID 边界和 reset hidden-information audit。
4. reset 通过后再申请 legal-action step smoke。
5. 完整 hidden-information trace 仍需覆盖多步状态、搜索候选、确认公开和对手盖卡 target 等窗口，不能由 reset-only 审计替代。
