# Understanding 双人标注协议 v0.1

## 目的

Understanding pilot 用于验证模型是否真正理解卡片发动条件、cost、target、once-per-turn、结算操作与限制，而不是仅凭卡名或常见 combo 记忆作答。第一轮目标是 30 个完成双人独立标注与裁决的样本；CardScripts 只能生成候选标签，不能替代人工 Gold。

人工工作记录使用 `understanding-annotation` contract，模型评测输入使用通用 `benchmark-record` contract。两者必须分离：候选题、标注者身份、分歧和裁决理由不能直接暴露给被测模型。

## 文件与状态

正式标注数据只允许放在：

```text
data/benchmark/understanding/
```

支持 `.json` 和 `.jsonl`。E0 不再扫描 `data/benchmarks/understanding/` 或 `data/understanding/` 等别名目录，避免同一题被重复计数。

每条记录只有三个合法状态：

| 状态 | 含义 | 是否计入 E0 30 题 |
|---|---|---:|
| `candidate` | 已有问题、冻结文本与证据，尚未完成双标 | 否 |
| `double_annotated` | 至少两位不同 annotator 独立提交，尚未裁决 | 否 |
| `adjudicated` | 双标完成，裁决者给出最终六字段 Gold | 是 |

E0 会拒绝重复 `record_id`、同题重复 `annotator_id`、引用不存在的 evidence source、schema 不合法或跨字段语义矛盾的记录。

## 六个语义字段

每个字段由 `status`、受控 `labels` 和原文 `source_spans` 构成。`source_spans` 用于复核，不参与标注一致率；一致率比较 `status`、排序后的 `labels` 和 OPT `scope`。

### Activation condition

标注效果能够进入可发动/可触发状态的前提，不把发动后才执行的操作误写为条件。

受控标签：状态、事件、位置、时点、阶段、回合玩家要求，以及 mandatory/optional。

### Cost

只标注发动时支付且即使效果被无效也不会退还的代价。不要仅凭 CardScripts 的 `SetCost` callback 判定；必须结合文本、规则与裁定。

受控标签包括 LP payment、discard、tribute/release、banish、send to Graveyard、detach、reveal 和 return to Deck。

### Target

区分“发动时明确取对象”与“结算时选择”。文本中出现“choose/select”不自动等于规则意义上的 target。

受控标签区分 targets card/player/zone、selects without targeting 和 selects at resolution。

### Once-per-turn scope

除 `status` 与 `labels` 外必须选择 scope：

- `none`：不存在 OPT；
- `soft_card_copy`：每张/当前这张卡的软 OPT；
- `hard_card_name`：同名卡共享的硬 OPT；
- `effect_instance`：特定效果实例限制；
- `duel`：整场决斗限制；
- `other`：需在 rationale 中解释。

### Resolution operation

标注效果成功结算时执行的核心状态变化，例如 draw、search、add to hand、special summon、destroy、banish、negate、send、set、shuffle 或区域返回。

### Restriction

标注效果施加或自身携带的行动限制，例如发动、召唤、攻击、额外卡组、素材、区域或 lingering restriction。不要把 cost 或发动条件重复标成 restriction。

## 证据要求

每题至少包含一份可哈希证据，优先级如下：

1. 冻结环境对应的官方卡片文本；
2. 官方规则书、规则更新或 FAQ/裁定；
3. CardScripts，仅作为候选与引擎实现证据；
4. 专家标注与裁决记录。

每份 evidence 必须记录 URI、本地内容 SHA-256、获取时间和 evidence level。annotation 中引用的 `evidence_source_ids` 必须真实存在于该记录。

## 独立标注与裁决

两位标注者在提交前不能查看对方的 value 或 rationale。两份 annotation 都必须设置 `independent=true`。自由文本 rationale 可以不同；E0 只在六个受控语义字段上计算字段级 exact agreement。

目标一致率为至少 90%。低于该阈值时不能通过补写 Gold 绕过，应先分析分歧、修订标签定义，再重新标注受影响样本。

裁决者检查原文、规则和双方理由，填写最终 `gold`、`disputed_fields` 与裁决 rationale。只有 `status=adjudicated` 且六字段完整的记录计入 E0。

## 验证命令

```bash
conda activate ygo
python -m experiments.validate_benchmark_artifact \
  --kind understanding-annotation \
  data/benchmark/understanding/pilot.jsonl

python -m experiments.run_e0_data_qualification
```

E0 正式结果会记录所有 Understanding 输入文件的 SHA-256。修改任何题目、标注或裁决都会改变实验输入清单，必须重新运行资格审计。

## 从标注到 Benchmark

裁决完成后再生成不含 annotator 身份、分歧和裁决过程的 `benchmark-record`：

- `input`：模型可见的卡片文本、规则上下文和问题；
- `target`：裁决后的结构化六字段；
- `provenance`：官方文本、规则与标注证据 hash；
- `verifier`：`human_consensus` 或结合规则/引擎的 `composite`；
- `visibility`：明确公开字段与测试时不可见字段；
- `split`：按 IID、composition OOD、temporal 或 name-masked 规则冻结。

第一轮先完成 30 题标注可靠性 pilot。达到一致率后再扩充，不先生成数百条未经验证的数据。

