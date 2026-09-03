# E0 数据资格实验结果（2026-08-07）

> 后续状态：provenance 修正后的复验结果见 `docs/reports/e0-data-qualification-results-2026-08-09.md`。本文保留为首次 E0 Gate 的历史记录。

## 1. 结论

E0 数据资格 Gate **未通过**，当前不应开始把本地 7B 或远程 API 的输出解释为正式 Benchmark 结果。

本次实验同时确认了一个积极结果：现有 TCG/OCG 两副固定赛事牌组都能从保存的 YGOPRODeck 原始 HTML 成功重解析，牌组区段、卡片 ID 和数量与冻结记录完全一致。因此当前问题不是解析器失效，而是正式样本量、来源字段和理解层人工 Gold 尚未达到实验协议要求。

## 2. 实验目标与配置

目标：执行 `benchmark-experiment-protocol-v0.1.md` 中的 E0 数据资格测试，判断 Understanding 与 Deck 数据是否允许进入模型 Pilot。

| 配置 | 值 |
|---|---|
| 发行版 | WSL `Ubuntu-22.04` |
| Conda 环境 | `ygo` |
| Python | 3.10.20 |
| 资源 | CPU only；无 GPU、无 API |
| 随机性 | 无；`random_seed=null` |
| TCG snapshot | `tcg-kde-e-2026-05-18` |
| OCG snapshot | `ocg-jp-2026-07-01` |
| 运行命令 | `python experiments/run_e0_data_qualification.py --output results/e0_data_qualification/metrics.json` |
| 代码版本 | `77bea68f0219710d30a9a0932ef9ae434dc4be64`；审计脚本 hash 已写入指标文件 |

输入 snapshot、固定牌组记录和审计脚本的 SHA-256 均保存在结果 JSON 中。最终运行从已提交且干净的代码状态启动，指标记录 `git_dirty=false`。

## 3. Understanding Gate

| 指标 | 实际值 | 目标 | 结果 |
|---|---:|---:|---|
| 正式理解样本 | 0 | 30 | 未通过 |
| 双人独立标注样本 | 0 | 30 | 未通过 |
| 六字段完整 Gold | 0 | 30 | 未通过 |
| 字段级一致率 | 不可计算 | >= 90% | 未通过 |

当前已有 13,334 张卡的文本到 Lua callback 代理标签，但它们属于候选或弱监督，不能替代 activation condition、cost、target、OPT scope、resolution operation 和 restriction 的人工/规则 Gold。本次审计没有把 Lua callback 数量伪装成已标注理解样本。

## 4. Deck Gate

| Snapshot | 正式牌组 | 目标 | 记录解析 | 原始 HTML 重解析一致 | provenance 完整 | 结果 |
|---|---:|---:|---:|---:|---:|---|
| TCG | 1 | 10 | 100% | 100% | 0% | 未通过 |
| OCG | 1 | 10 | 100% | 100% | 0% | 未通过 |

两副牌组均满足：

- 固定记录 JSON 可解析；
- Main/Extra/Side 数量符合对应 snapshot 规则；
- 原始 HTML 的三个嵌入牌组数组能够重新解析；
- 重解析出的卡片 ID 多重集合与冻结记录完全相同；
- 原始 HTML 内容 hash 与记录一致。

两副牌组均缺少：

- `source.retrieved_at`；
- `source.evidence_level`。

因此解析 Gate 通过，但每环境至少 10 副牌组的数量 Gate 和 provenance Gate 均未通过。

## 5. 对实验主线的影响

这次结果阻止了一个会污染论文结论的错误顺序：如果现在直接跑本地 7B，理解层没有正式 Gold，构筑层每环境只有一副牌组，模型分数主要反映格式和个例，不能代表 TCG/OCG 能力。

可以继续开展的数据工程是：

1. 建立 30 题 Understanding 标注候选集和明确的双人标注结构；
2. 给现有两副牌组补齐抓取时间和证据等级；
3. 补采 TCG/OCG 各 9 副满足同 snapshot 的赛事牌组；
4. 重跑 E0，只有数据 Gate 通过后才冻结第一个 M1 本地模型 Pilot。

策略层仍受 runtime-2026 Gate 约束，本轮没有运行 random eval、策略场景或 Full Duel。

## 6. 产物

- 审计入口：`experiments/run_e0_data_qualification.py`
- 机器可读指标：`results/e0_data_qualification/metrics.json`
- 实验协议：`docs/reports/benchmark-experiment-protocol-v0.1.md`

本轮没有使用 GPU、API 或模型推理，也没有产生训练数据。
