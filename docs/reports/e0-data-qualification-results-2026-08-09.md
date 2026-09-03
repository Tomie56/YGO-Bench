# E0 数据资格复验结果（2026-08-09）

## 结论

E0 总 Gate 仍未通过，因此当前不能开始本地 7B 或 frontier API 的正式 Benchmark 实验。

本次复验消除了上一轮的 provenance 缺陷：TCG 与 OCG 两副固定赛事牌组的结构解析、原始 YGOPRODeck HTML 重解析、牌表一致性和 provenance 完整率现在均为 100%。当前失败原因已经收敛为两项真实数据缺口：每环境只有 1/10 副资格牌组，Understanding 双人标注为 0/30。

本次还在重跑前冻结了 TCG/OCG 官方规则证据。TCG snapshot 绑定 Rulebook v9.01、2021 Rules Update 与 KDE-E Tournament Policy v2.5；OCG snapshot 绑定 2026 年 7 月禁限表与 Japan Championship 2026 规则。根据赛事规则，OCG 卡池截止日已由先前记录的 2026-07-18 修正为 2026-07-17。两个 snapshot 的 `open_fields` 均已清空。

随后新增了正式 `understanding-annotation` contract 并再次重跑 E0。现在只有 schema 合法、两位不同标注者独立提交且完成裁决的记录才计入 30 题；候选题和双标未裁决记录只单独计数。自由文本 rationale 与 source span 不参与 agreement，CardScripts callback 仍不能替代人工标签。

## 实验配置

| 项目 | 值 |
|---|---|
| Experiment ID | `E0-data-qualification-v0.1` |
| Git commit | `3249a69a980e57d607addbd99223ff67ac3f8a1b` |
| Git dirty | `false` |
| WSL / Conda | `Ubuntu-22.04` / `ygo` |
| Python | 3.10.20 |
| 资源 | CPU-only；无 GPU、LLM 或 API |
| 随机种子 | 无随机过程，`null` |
| TCG snapshot | `tcg-kde-e-2026-05-18` |
| OCG snapshot | `ocg-jp-2026-07-01` |
| 命令 | `python -m experiments.run_e0_data_qualification --output results/e0_data_qualification/metrics.json` |

正式结果记录了审计脚本、两个 snapshot、两份固定牌组 JSON 和两份原始赛事 HTML 的 SHA-256。原始 HTML 现在属于显式输入，不能在不改变实验输入 hash 的情况下被替换。

本次 snapshot hash 已随官方规则证据与 OCG 卡池截止日修正而更新；E0 结果是在上述 Git commit 的干净工作树中重新生成，不沿用旧 snapshot 的资格结论。

## Understanding Gate

| 指标 | 实际值 | 目标 | 状态 |
|---|---:|---:|---|
| 正式裁决 Gold | 0 | 30 | 未通过 |
| 候选记录 | 0 | - | 尚未开始 |
| 双人独立标注样本 | 0 | 30 | 未通过 |
| 六字段完整 Gold | 0 | 30 | 未通过 |
| 字段级一致率 | 不可计算 | >= 90% | 未通过 |

CardScripts callback 仍只能作为候选标签，不能替代 activation condition、cost、target、once-per-turn scope、resolution operation 和 restriction 的双人复核 Gold。

## Deck Gate

| Snapshot | 记录数 | 数量目标 | Parser | 原始重解析 | Provenance | 状态 |
|---|---:|---:|---:|---:|---:|---|
| TCG | 1 | 10 | 100% | 100% | 100% | 数量未通过 |
| OCG | 1 | 10 | 100% | 100% | 100% | 数量未通过 |

两份记录都已包含 `event_date`、`placement`、牌组 URL、官方赛事 URL、原始文件路径、SHA-256、`retrieved_at` 和 `evidence_level`。牌组卡号、数量和 Main/Extra/Side 区段与原始页面完全一致。

## 对论文实验的含义

现在可以确定，已有两份牌组是合格的 schema/provenance 样例，但不能用两个个例评价构筑能力。继续接模型只会测出个例记忆、格式和 prompt 适配，无法支持 TCG/OCG 环境能力结论。

进入首轮模型实验前仍需：

1. 补充 TCG 与 OCG 各 9 副同 snapshot、事件可核验的完整赛事牌组；
2. 建立 30 个 Understanding 候选，并由两位标注者独立完成六字段标注；
3. 达到字段级一致率至少 90%，否则先修订标注协议；
4. 重跑本 E0 Gate，只有总结果通过后再冻结本地模型与 API 配置。

本轮没有运行 runtime smoke、策略场景、模型推理或完整对局。

## 正式产物

- `results/e0_data_qualification/metrics.json`
- `experiments/run_e0_data_qualification.py`
- `docs/reports/benchmark-experiment-protocol-v0.1.md`
