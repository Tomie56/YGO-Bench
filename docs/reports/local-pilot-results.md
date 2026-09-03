# 本地可运行实验：首轮 Pilot 结果

运行时间：2026-07-22T10:56:52.283694+00:00

运行环境：Windows + CPU；本轮未下载模型权重，也未运行 ygopro engine。

## 结论

1. U1 的词法基线表现高度不均衡：count-limit 与 condition callback 可被表面措辞较好预测，cost 居中，target callback 的 recall 很低。单纯的 once-per-turn/if/when 识别可能过于简单，而 Lua callback 也不能直接当作完整语义 gold。
2. D1 现在按 TCG/OCG snapshot 分开审计。历史 ygo-agent 牌组在两个当前环境都存在明显的 regulation、card-pool 或时间错配，不能合并成一个“YGO 合法率”。
3. D2 的 leave-one-deck-out 训练候选覆盖率为 64.10%。这意味着小牌组池中的大量主题卡在其他牌组从未出现，masked completion 首先受数据覆盖限制。
4. 当前本地 CPU pipeline 已经能复现数据加载、snapshot legality、leave-one-deck-out 和结构代理评分；下一步需要 WSL/engine 才能生成真正的 LegalSet、ResolveDelta 与策略 rollout 标签。

## U1：卡片文本到脚本 Callback 词法基线

样本：13334 张同时具有英文文本和 official Lua script 的卡。

| 标签 | 正例率 | Precision | Recall | F1 | Accuracy |
|---|---|---|---|---|---|
| count_limit_callback | 0.5806 | 0.9628 | 0.8887 | 0.9242 | 0.9154 |
| cost_callback | 0.3517 | 0.7007 | 0.6974 | 0.699 | 0.7888 |
| target_callback | 0.9033 | 0.9886 | 0.4121 | 0.5817 | 0.4647 |
| condition_callback | 0.6639 | 0.7844 | 0.9335 | 0.8525 | 0.7855 |

注意：`SetTarget` 是引擎 target callback，不等于 PSCT 中一定存在语义上的“取对象”；该实验用于评估自动标签可行性，不是最终 Card Understanding benchmark。

## D1：TCG/OCG 牌组合法性审计

| Snapshot | Regulation | 牌组数 | 通过 | 未通过 | 违规类型 |
|---|---|---|---|---|---|
| tcg-kde-e-2026-05-18 | TCG | 31 | 1 | 30 | {"copy_limit": 130, "missing_card_id": 3} |
| ocg-jp-2026-07-01 | OCG | 31 | 0 | 31 | {"copy_limit": 157, "missing_card_id": 3} |

逐牌组兼容模式：`{"TCG": 1, "none": 30}`。这里的 `none` 表示牌组不通过任一所选 snapshot，环境名组合表示通过对应 snapshot。

这些牌组来自较早版本的 ygo-agent。结果测量的是 regulation/card-pool/temporal mismatch 和 importer 需求，而不是原作者构筑质量。BabelCDB 的 `datas.ot` 只提供聚合的 OCG/TCG availability bit；在 `card_pool_cutoff` 尚未固定时，它不能证明某张卡在历史赛事日期已经发售。

## D2：Leave-One-Deck-Out 卡片补全

- 牌组数：31
- 查询数：688
- 目标卡在其他牌组出现的查询：441
- 训练候选覆盖率：64.10%

| Baseline | All H@1 | All H@5 | All MRR | Seen H@1 | Seen H@5 | Seen MRR |
|---|---|---|---|---|---|---|
| popularity | 0.1163 | 0.2137 | 0.1618 | 0.1814 | 0.3333 | 0.2525 |
| cooccurrence | 0.1294 | 0.2689 | 0.2004 | 0.2018 | 0.4195 | 0.3126 |
| nearest | 0.1235 | 0.2427 | 0.1861 | 0.1927 | 0.3787 | 0.2903 |

`All` 包含训练牌组中完全没出现过的目标卡；`Seen` 只评估候选池中出现过的目标。正式 DeckMeta 数据必须使用更大的同环境赛事牌组池，并按赛事和近重复牌组分组切分。

## 生成文件

- `results/local_pilot/metrics.json`
- `results/local_pilot/u1_text_script_proxy.csv`
- `results/local_pilot/d1_deck_legality.csv`
- `results/local_pilot/d2_leave_one_deck_out.csv`

## 下一步

1. 安装 WSL2/Ubuntu，跑 E0 双 bot 固定 seed 对局。
2. 从首条 trace 生成 20 个 decision points 和 10 个 counterfactual groups。
3. 分别收集至少 50 副同一 TCG snapshot 与 50 副同一 OCG snapshot 的 tournament decks，重跑 D1/D2，再加入本地 7B/14B 或 API LLM baseline。
