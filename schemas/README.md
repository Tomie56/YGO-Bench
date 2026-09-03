# YGO-Bench contracts

`schemas/` 固定第一轮实验的机器可读边界。新增的三个运行时契约是：

- `benchmark-record.schema.json`：理解、构筑和策略三层样本；
- `model-output.schema.json`：本地模型、API 模型与非 LLM baseline 的统一输出；
- `evaluation-result.schema.json`：逐样本评分、错误归因和成本记录。
- `understanding-annotation.schema.json`：候选题、两位独立标注和裁决 Gold 的工作流记录；它不是模型输入。

已有的 environment snapshot、runtime snapshot 与 fixed scenario schema 也由同一
入口校验。它们负责固定 TCG/OCG 规则环境和现代引擎资产，不与模型输出混用。
`runtime-gate-protocol.schema.json` 进一步冻结动态 Gate 的 action policy、规模、
可见性 provenance 编码、随机种子偏移、产物命名和通过阈值。

当前版本为 `0.1.0`。`examples/` 只用于契约测试，不属于 Benchmark 数据。

验证命令：

```bash
conda activate ygo
python -m experiments.validate_benchmark_artifact \
  --kind benchmark-record schemas/examples/benchmark-record.json
```

解析失败、未知字段、layer/task 错配以及必要审计字段缺失都会直接失败。API
provider 的原始响应不能直接进入 scorer，必须先转换为 `model-output` 契约。
Understanding 候选题和半成品标注必须先通过 `understanding-annotation` 契约；只有
`status=adjudicated` 的记录才能转换为正式 `benchmark-record` 并计入 E0 Gold 数量。
