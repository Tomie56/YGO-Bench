# 现代 Runtime Gate Protocol v0.1（2026-08-09）

## 结论

现代 runtime 的后续验证已从一组松散的结果文件名升级为机器可校验的 Gate protocol。该 protocol 固定 TCG/OCG 共 12 个 Gate 的动作策略、随机种子、执行规模、产物名称和通过阈值，并要求 readiness 同时校验 runtime 输入 hash、Gate protocol hash 与实际覆盖量。

本报告描述实验设计和已完成的非 smoke 验证，不报告尚未运行的动态实验结果。当前只证明 contract、runner 与 native transform 可以静态生成并通过合成测试；新 extension 构建及任何 runtime Gate 必须另行记录。

## Gate 矩阵

| Gate | 每个环境的配置 | 核心判定 |
|---|---|---|
| Legal step | 单环境，固定 action index 0 | 动作在合法集合内、动作特征非空、状态变化、输出合法 |
| Dynamic hidden information | 单环境，PCG64，最多 2,000 transitions | 无未证明的私有 identity/detail/sequence；至少 100 个状态、100 条私有行、1 条 confirmed reveal |
| Trace/replay | 单环境，最多 400 transitions | 动作、完整 runtime state hash、终局 flags 全部一致 |
| Lifecycle | 单环境，100 次 construct/reset/destroy | 完成 100 次、0 crash、每次释放 pool |
| Throughput | 16 env / 16 threads / batch 16 | 512 warmup 后计时 8,192 transitions，至少 1,000 steps/s |
| Random eval | 单环境，32 局 | 完成 32 局、0 crash、单局不超过 10,000 steps |

以上六类 Gate 分别对 TCG 与 OCG 运行。任何结果只有在 `git_dirty=false`，且 runtime config、extension、asset manifest、runtime snapshot 和 Gate protocol hash 与当前输入一致时才有效。

## 动态隐藏信息

reset 时可以严格要求对手 hand/deck/extra 不出现 card ID，但行动后存在合法例外：确认展示、检索展示或当前从自己主卡组选择卡片时，身份可以短暂可见。因此动态 verifier 使用 native 输出的逐卡 provenance：

| Code | 含义 | Identity 规则 |
|---:|---|---|
| 0 | padding | 必须为空 |
| 1 | hidden private | 必须隐藏 identity、详情和私有顺序 |
| 2 | owner visible | 必须有 identity |
| 3 | public field | 必须有 identity |
| 4 | confirmed reveal | 必须有 identity，并计入动态覆盖 |
| 5 | selectable own deck | 必须有 identity，仅限当前合法选择 |
| 6 | opponent facedown | 必须隐藏 identity 与详情 |

verifier 还检查 provenance 与 owner、location 和 position 的一致性。一条 hand/deck/extra 私有卡只有 `hidden_private` 或 `confirmed_reveal` 两种合法状态；不能因为同一区域另一张卡被展示而公开整区。

## Replay 证据

trace/replay 不只比较动作列表。每一步的 hash 包含：

- `cards_`、`global_`、`actions_`、`h_actions_`；
- `card_visibility_`；
- `num_options`、`to_play`、`is_selfplay`、`win_reason`。

原始轨迹与 fresh pool replay 的动作、step 前后 hash 和终局 flags 必须逐项相同。只比较最终胜负或 observation 子集不能通过 Gate。

## Readiness 防伪条件

readiness 不根据文件存在性判定通过。每份结果还必须满足：

- `gate_id`、profile 和 `gate_kind` 正确；
- `gate_protocol_id` 与 SHA-256 正确；
- 结果内嵌的 Gate 配置与冻结 protocol 完全一致；
- runtime 四类输入 hash 一致；
- runtime 已初始化、pool 已销毁；
- 实际 steps、episodes、cycles、coverage 或 throughput 达到 protocol 阈值。

## 当前状态与下一步

当前 33 个 adapter transform 能从冻结 upstream header 唯一生成，53 项非 smoke 测试通过。尚未执行新 binary build、init、construct、reset、step 或任何完整对局。

下一步先重编译 extension并只做加载验证；然后在干净提交上运行不调用 reset 的 init/construct preflight。因为 extension hash 会变化，现有 reset 证据将自动失效，必须在报告中标为 superseded，并重新申请 reset smoke 授权。
