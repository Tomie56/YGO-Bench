# Understanding 与构筑 Pilot 首批候选数据报告

## 一句话结论

已经生成第一批可供人工审阅的 YGO-Bench 候选数据：30 道 Understanding 候选题和 60 道构筑候选题均通过正式 schema 验证。Understanding 仍没有专家 Gold，不能用于报告模型准确率；构筑题的结构与禁限违规具有冻结 snapshot 下的机器 Gold，但开放式构筑质量仍不在本批任务的 claim 内。

## 1. 在线题源调查

### 1.1 KONAMI Judge Program

KONAMI 的 Rulings Comprehension Level 1（RC-1）测试明确用于考查基础游戏机制与卡片交互，并以 80% 为通过线。它证明了“卡片文本 + 具体交互 + 规则判断”是一种被官方采用的能力测量形式。

RC-1 适合作为能力分类参考，不适合作为直接数据源。本项目没有登录、抓取、复制或重新发布真实考试题。YGO-Bench 使用公开官方规则和卡片页面重新编写原创题目，从而保留测试范式，同时避免题目泄漏、许可不明和版本不可追溯的问题。

来源：

- https://www.yugioh-card.com/en/judges/judge-faq/
- https://www.yugioh-card.com/en/play/fast-effect-timing/
- https://www.yugioh-card.com/en/play/psct/

### 1.2 社区规则题与问答

网上存在 Testmoz、论坛问答、视频“规则难题”和非官方翻译题库。这些材料可以帮助发现高分歧概念，例如 Damage Step、错过时点、连续魔法离场和效果无效，但不适合直接进入正式 Benchmark：

- 很多题目没有明确作者许可；
- 题目可能绑定旧规则或旧卡片文本；
- 答案通常只有一句结论，缺少可哈希的规则证据；
- 社区共识不能自动升级为官方裁定 Gold。

因此社区题只作为“候选难点发现器”，正式题目必须重新表述，并绑定官方卡片文本、规则页以及独立专家标注。

### 1.3 Project Ignis Puzzles

Project Ignis 维护了 EDOPro 的 canonical puzzle collection，许可证为 AGPL-3.0-or-later。其 Lua 文件通过 `Debug.ReloadFieldBegin`、`Debug.AddCard`、`Debug.PreEquip`、`Debug.PreSummon` 和 `aux.BeginPuzzle()` 固定双方 LP、卡片位置、表示形式与一回合目标。这种表示与 `ygopro-core` 的规则状态天然接近，是目前最有希望转为动态 Benchmark 的公开题源。

本次将仓库 commit `1177a180dd237da7f9703c846d533c2116ca1439` 浅克隆到 `tmp/`，仅做静态审计：

| 项目 | 数量 |
| --- | ---: |
| Lua 文件 | 459 |
| Rush Duel | 219 |
| 使用 `Debug.AddCard` | 459 |
| 使用 `Debug.ReloadFieldBegin/End` | 459 |
| 使用 `aux.BeginPuzzle()` | 455 |
| 当前冻结 CDB 与 CardScripts 均覆盖 | 68 |
| 排除 Rush 后的静态资产完整候选 | 66 |
| 包含自定义 `Effect.CreateEffect` | 24 |

“66 个静态资产完整候选”只表示卡号和 CardScript 文件存在，不表示它们已经能在当前 ygoenv adapter 中执行。它们还需要：

1. 排除 Duel Links、旧 Master Rule、Tag Duel 等规则差异；
2. 检查 puzzle 内自定义 Effect 是否改变正式卡片规则；
3. 获得或重新验证解答轨迹；
4. 给当前 runtime 增加 puzzle state loader；
5. 通过多步稳定性、隐藏信息和 trace/replay Gate。

因此本轮没有将 Puzzle 数据写入正式策略集，也没有调用 core 执行 puzzle。

来源：https://github.com/ProjectIgnis/Puzzles

## 2. Understanding Pilot

### 2.1 官方证据冻结

选择了 12 张具有代表性的卡，覆盖 condition、cost、target、once-per-turn、条件结算、延迟处理和 lingering restriction：

- Ash Blossom & Joyous Spring
- Called by the Grave
- Infinite Impermanence
- Effect Veiler
- Pot of Prosperity
- Ghost Ogre & Snow Rabbit
- Droll & Lock Bird
- Ghost Belle & Haunted Mansion
- Bystial Magnamhut
- Crossout Designator
- Triple Tactics Talent
- S:P Little Knight

每张卡同时冻结 KONAMI Card Database 的 TCG English 和 OCG English-Asia 页面，共 24 份官方页面。另冻结 Fast Effect Timing 与 PSCT 页面。每个页面均保存原始 HTML、解析后的卡名与卡片文本、KONAMI CID、passcode、抓取时间和 SHA-256。

CardScripts 只作为候选与引擎实现证据，不能替代规则 Gold。BabelCDB 中个别文本包含“unofficial OCG functionality”提示，因此生成器不使用 BabelCDB 文本作为官方卡片文本，而只使用刚冻结并核验的 KONAMI 页面。

### 2.2 30 题组成

| 类型 | 数量 | TCG | OCG |
| --- | ---: | ---: | ---: |
| CardSemantics | 12 | 6 | 6 |
| RuleAndTiming | 10 | 5 | 5 |
| Counterfactual | 8 | 4 | 4 |
| 合计 | 30 | 15 | 15 |

反事实部分包含四组最小变量变化，每组两题：

- Infinite Impermanence：己方控制 0 张卡与 1 张卡；
- Effect Veiler：对手 Main Phase 与 End Phase；
- Ash Blossom：从 Main Deck 加入手牌与从 GY 加入手牌；
- Bystial Magnamhut：对手是否控制怪兽。

题目不是简单询问“这张卡做什么”，而是要求分辨具体语义边界或结算结果。例如：

- Called by the Grave 作为 Chain Link 3 处理已丢弃的 Ash Blossom；
- Infinite Impermanence 在结算前离场时，怪兽无效与同列无效是否分别适用；
- Droll & Lock Bird 面对 Chain 中非最后发生的加手事件；
- S:P Little Knight 暂时除外后的 End Phase 返回。

### 2.3 当前资格

文件：`data/benchmark/understanding/pilot-candidates-v0.1.jsonl`

- 记录数：30；
- SHA-256：`eeb9f3666b84ae0b438d8a0a5de79fbf734c2778bda8419accb6cc02be122b2b`；
- schema：`understanding-annotation`；
- 状态：30/30 均为 `candidate`；
- annotations：空；
- Gold：空；
- adjudication：空。

这意味着题目已经可供人工审阅和双标，但不能用于正式模型排名。特别是 RuleAndTiming 题需要专家确认场景假设是否充分，避免题目因为未声明状态而产生多个答案。

## 3. 构筑 Pilot

### 3.1 数据与任务生成

输入为已冻结的 20 副真实赛事牌组：TCG 10 副、OCG 10 副。每副牌组生成三条记录：

1. 原始牌组合法性审计；
2. 受控损坏后的错误定位；
3. 同一损坏的最小修复。

受控变换完全确定，不使用随机数：

- Main Deck 恰好 40 张：删除固定位置的一张卡，制造 Main Deck 39 张的唯一结构违规；
- Main Deck 大于 40 张：将固定位置的一张卡替换为 Pot of Greed。Pot of Greed 在冻结 TCG 与 OCG 禁限表中均为 0，区段数量保持不变，只产生一项禁限违规。

生成器验证以下不变量：

- 20 副来源牌组在对应 snapshot 下均合法；
- 每个受控损坏恰好产生一项违规；
- 每个最小修复只需要一次编辑；
- 应用严格逆变换后，逐区段列表与原始牌组完全一致；
- 修复后 snapshot validator 返回无违规。

### 3.2 评价边界

构筑修复同时保留两种评价：

- `legality`：任意一次编辑后满足 snapshot 约束的方案均可获得合法性分；
- `source_recovery`：只有精确恢复被隐藏的原赛事牌组变换，才获得来源恢复分。

这一拆分很重要。对于 39 张 Main Deck，加入许多不同卡都可能重新合法；如果只用原牌组卡作为唯一 exact-match Gold，会把合理但不同的修复错误地判为零分。当前 Pilot 的 G1 claim 仅覆盖硬约束和已知受控逆变换，不覆盖开放式“这套牌战略上最好加入什么”。

### 3.3 当前资格

文件：`data/benchmark/deck/pilot-candidates-v0.1.jsonl`

- 记录数：60；
- TCG/OCG：30/30；
- 原始合法性审计：20；
- 损坏错误定位：20；
- 最小修复：20；
- SHA-256：`077f0f58d281676e960d16f8229db782d0b15b83821c59a9136735ae6d0b1c18`；
- schema：`benchmark-record`；
- verifier：snapshot validator，G1。

## 4. 验证结果

本轮仅使用 CPU 与网络，没有使用 GPU、模型 API、reset、step、smoke 或完整对局。

通过的检查包括：

- 10 项 contract 回归测试；
- 3 项 Understanding source/config 测试；
- 3 项构筑生成不变量测试；
- 30/30 Understanding 正式 contract 验证；
- 60/60 构筑正式 contract 验证。

连续验证多条记录时发现 `load_schema()` 重复编译同一 JSON Schema 会触发当前 `jsonschema/referencing` 依赖组合的内部错误。现已缓存经过 meta-schema 检查的 schema；每条 record 仍逐条执行 Draft 2020-12 验证。新增 50 次连续验证回归测试后通过。

## 5. 现在能得出的结论与不能得出的结论

可以说：

- 静态 Understanding 与构筑数据管线已经首次产出真实候选样本；
- 题目、官方文本、规则、CardScript、赛事牌组和 snapshot 之间可以追溯；
- 构筑硬约束任务已经具备机器可验证 Gold；
- Project Ignis Puzzle 是动态题目的可行候选底座。

不能说：

- 30 道 Understanding 已经是 Gold；
- 模型已经在 YGO-Bench 上完成评测；
- 66 个 Puzzle 已经可以通过当前 runtime 执行；
- 构筑题已经测量了开放式战略构筑能力；
- 当前数据量足以支持完整 TCG/OCG 泛化结论。

## 6. 建议的下一检查点

下一步先做人工题目审阅，而不是立即调用模型：

1. 由一位熟悉规则的审阅者检查 30 题的状态描述是否充分，并标记“保留、修改、删除”；
2. 先从每类抽 3 题，共 9 题做双人独立标注试跑，确认六字段 contract 是否适合 RuleAndTiming 场景；
3. 修订题目后再完成 30/30 双标与裁决；
4. 构筑侧人工查看 6 个样本，确认输入表示和 legality/source-recovery 双指标符合预期；
5. Puzzle 另开检查点，只做 5 个候选的规则版本与 loader 可行性审计，不直接运行 66 个场景。
