# 对战状态审计渲染器：首个可审核样本

## 结论

我们现在可以把引擎提供给 Agent 的某一时刻观测，渲染成一张可直接审阅的规则桌面图，同时生成一份逐卡、逐动作的 JSON 审计清单。它不是新的游戏客户端，不参与对局控制，也不替 Agent 做规则、策略或动作推理；显示内容完全来自现有 observation 和 visibility provenance。

这解决了一个很实际的审核问题：在做策略任务、链式响应和 Agent 消融以前，可以先确认模型到底看到了什么，尤其确认手牌、卡组、盖卡等隐藏区域没有在可视化过程中泄露身份。

## 图中包含什么

渲染器采用垂直俯视场地：对手在上方、当前玩家在下方，两个共享 Extra Monster Zone 固定放在中央，并分别与主怪兽区第 2、第 4 列对齐。没有纵深透视，也没有可交互控件。对手手牌位于对手场地区域上方，当前玩家手牌位于当前玩家场地区域下方。渲染器显示：

- 双方 LP、回合数和阶段；
- 双方手牌、卡组、墓地、除外区和额外卡组，作为各自半场的实体卡槽或卡堆显示，并标注数量；
- 双方相向的主怪兽区和魔法陷阱区，以及位于两方主怪兽区之间的两个共享额外怪兽区；
- Agent 可见的公开卡图；卡图通过 `observation card ID -> frozen code_list -> passcode -> 本地 JPEG` 映射得到；
- 隐藏手牌、对手盖卡等统一显示为卡背；
- 当前玩家可选的合法动作及其目标摘要。动作编号与环境 action index 一致，从 `0` 开始且只显示一次；`Select place` 和 `Select disable field` 会按 core 的 `cmd_place2id` 原表解码为具体区域，并保留 `m1`、`s1`、`om1` 等原始区域规格，便于人工回查。

怪兽卡不通过旋转区分归属。对手控制的怪兽使用红色边框，当前玩家控制的怪兽使用蓝色边框；这一规则同时适用于 Main Monster Zone 和 Extra Monster Zone，且只作用于怪兽，不作用于手牌、卡组、墓地或魔法陷阱。

页面右侧是固定高度的已发生事件面板。调用方必须显式传入事件文字，以及可选的公开 passcode；渲染器不会从当前状态猜测历史。公开事件可显示缩小卡面，身份不可见的事件只能显示缩小卡背。页面最多显示最近 12 条，较早事件只记录省略数量且不会溢出面板。若隐藏事件携带 passcode，渲染器立即报错。

正式输出有三份：静态 `.html` 用于保留可检查的布局和本地卡图引用，Edge 生成的 `.png` 用于人眼审阅，同名 `.audit.json` 用于程序化检查。后者记录每张显示卡的区域、控制者、可见性来源和是否隐藏，并记录合法动作列表。SVG 不再是输出格式。

所有单张卡槽，包括 Deck、墓地、除外、Extra Deck、手牌、主怪兽区、魔法陷阱区和 Extra Monster Zone，均使用固定的 `59:86` 游戏王实体卡纵横比。两个 EMZ 位于金色的中央共享带，不归属任一玩家。

视觉层以卡图为主，完整卡名和 provenance 保留在 JSON 审计清单中。手牌最多以两行、每行十张的固定尺寸压叠方式展示，因此 10--20 张手牌仍逐张可见；超过 20 张才使用明确的剩余数量标记。

## 隐私与正确性边界

渲染器把可见性来源当作强制约束，而不是显示建议。对于 `hidden_private` 和 `opponent_facedown`，状态中只要出现非零 observation card ID，渲染立即报错，不生成图片。隐藏卡在 JSON 中的 `name`、`card_code` 和 `observation_card_id` 均为 `null`。

它还要求完整提供 `card_visibility_`、`num_options` 和 `to_play`。因此不会把缺少动作数、轮次或可见性信息的半截状态伪装成完整的 Agent 视图。

## 已验证的真实样本

使用固定 TCG runtime-primary 牌组，在 reset 后执行此前已授权的第 0 个合法动作，生成了一个样本：

- HTML：`tmp/audit_renderer_example/tcg_step_state.html`
- PNG：`tmp/audit_renderer_example/tcg_step_state.png`
- 审计清单：`tmp/audit_renderer_example/tcg_step_state.audit.json`
- 原始捕获：`tmp/audit_renderer_example/tcg_step_state.npz`

该样本绑定当前 extension SHA256：

`2801283a6627405f0a8bc92db0cc007b6e75055d5115b31fb3b72ca56cec90cc`

静态检查结果如下：

| 检查项 | 结果 |
| --- | --- |
| HTML 是否生成、PNG 是否由 Edge 生成 | 通过 |
| 捕获文件是否需要 pickle | 否 |
| 隐藏卡数量 | 86 |
| 隐藏卡身份泄露 | 0 |
| 当前合法动作数 | 5 |
| 合法动作语义 | 将卡放入我方魔法与陷阱区 1--5（`s1`--`s5`） |
| 对局池是否销毁 | 是 |

该状态处于 `MSG_SELECT_PLACE` 中间响应窗口，因此这五项是区域选择，而不是五个新的高层出牌动作。原始 `actions_` 的 place ID 为 `8`--`12`；按当前 core 固定映射，它们恰好对应 `s1`--`s5`。这只是审计器的受控示例，不增加 runtime 的正式策略实验结论，也不替代后续 trace/replay、完整隐藏信息审计和多局对战验证。

另有一张仅用于布局审核的合成预览：`tmp/audit_renderer_example/ownership-history-layout-preview.png`。它展示红/蓝怪兽边框、对手占用 EMZ 和右侧事件记录，但不是引擎实验结果。

## 多步对局的当前限制

为观察非空对局状态，尝试过 CPU-only 的 TCG 多步合法动作采样。固定选择动作 `0` 的最小探针连续完成 8 步且正常销毁对局池；但随机动作采样和独立的 40 步固定动作采样，都会在更后续的动作路径触发 `lua_longjmp` 并由 Python 进程中止。检查时 WSL 仍有约 14 GiB 可用内存、无 swap 使用且没有引擎残留进程，因此不能把它归因于硬件资源不足。

结论是：当前可以可靠审阅已验证的 reset/单步真实状态，但不能把完整多步对局称为稳定可用。下一步应定位 native/Lua 的具体失败动作和调用链；在此之前，不应运行大规模随机对局或将其作为策略 Benchmark 结果。

## 当前限制与下一步

卡图是纯展示层，来自本地冻结缓存 `data/card_images/runtime-modern-v1-2026-07-20/full/`。目前 14,586 个 passcode 有真实 JPEG；两个公开图片源均缺失的 19 个特殊 passcode 不会伪装为真实卡图，公开可见时将以文字卡框显示。无论是否有卡图，隐藏卡都不会生成 passcode、卡名或图片 URL。

渲染器已具备支持 Understanding 与策略数据审核的最小能力。下一项研究工作仍应按既定顺序转向 Understanding 题目：先构造 30 道候选题并完成双人独立标注，而不是继续扩张引擎功能。
