# YGO-Bench 两周最小试验规格

> 注：本文件保留为最早的规则/时点 pilot。覆盖理解、构筑、实战策略与完整统计协议的当前版本见 `docs/reports/experiment-plan-v1.md`；执行时以后者为准。

## 目标

用最小工程量回答一个决定项目去留的问题：

> 引擎生成的规则/时点诊断分数，能否区分当前 LLM，并比普通静态卡牌问答更好地预测同模型的真实对局质量？

这个 pilot 不追求完整 leaderboard，也不做 self-evolution。

## 范围

- 规则环境：锁定一个 `ygopro-core` commit、一个 Master Rule/banlist 快照。
- 卡组：2 个固定、复杂度不同且 WindBot 有稳定 executor 的卡组。
- 局面来源：WindBot 对局的确定性 seed + action prefix；必要时用 debug script 构造边界状态。
- 模型：3 个能力档位，每个模型固定推理预算与温度。
- 条件：`legal-actions shown` 与 `legal-actions hidden` 两种 harness。

## 数据

先构建 200 个经过引擎验证的 decision points：

| 类型 | 数量 | 标签 |
|---|---:|---|
| 合法动作/发动条件 | 60 | 完整 legal-action set |
| 连锁响应与发动时点 | 60 | 最佳响应窗口、合法 chain candidates |
| 效果结算/下一状态 | 40 | canonical state delta/hash |
| 2-5 步战术线 | 40 | 成功条件、最短/低资源动作线 |

至少一半样本组成 counterfactual pairs：只改变一个状态变量，例如一回合一次标志、卡位占用、墓地资源、chain link、是否已被无效、可见手牌或召唤次数，使正确答案发生翻转。

## 接口

候选 canonical observation：

```json
{
  "ruleset": "snapshot-id",
  "turn": 3,
  "phase": "MAIN1",
  "priority_player": 0,
  "public_state": {},
  "private_state": {},
  "known_opponent_information": {},
  "chain": [],
  "history": [],
  "legal_actions": []
}
```

动作必须使用稳定 ID，不以卡名字符串做唯一匹配。引擎保留完整隐藏状态，agent adapter 只能读取属于当前玩家的 observation。

## 指标

- `Legal Set F1`：模型判断的合法动作集合与引擎集合的 F1。
- `Execution Success`：提交动作可被引擎无重试执行的比例。
- `State Delta Exact Match`：效果结算后的结构化状态变化完全一致率。
- `Counterfactual Consistency`：在最小状态变化后，模型是否相应翻转判断。
- `Response Quality`：错过关键响应、过早交互、无效交互的比例。
- `Tactical Success`：在动作/资源上限内达到目标的比例。
- `Cost`：token、模型调用、延迟和估算美元成本。

## 基线

- 随机合法动作。
- WindBot deck executor。
- ReAct LLM，结构化 observation + legal actions。
- 同一 ReAct LLM，不提供 legal actions。
- 规则检索增强 ReAct，检索范围只含当前 snapshot 的规则/卡片文本。

## 成功门槛

满足下列三项即可进入完整 benchmark 开发：

1. 三个模型在至少两个核心指标上形成稳定且置信区间可分的差异。
2. counterfactual consistency 显著低于普通 IID 准确率，证明 benchmark 揭示了记忆之外的状态依赖推理缺口。
3. 诊断分数与 50-100 局固定对手对局中的关键错误率/胜率方向一致。

若只看到卡名记忆或 harness parser 差异，应先改数据与接口，不扩展完整 tournament。

## 两周排期

| 时间 | 交付物 |
|---|---|
| Day 1-3 | headless core 启动、双 bot 对局、协议日志与隐藏信息单测 |
| Day 4-5 | canonical observation/action schema、确定性 replay-prefix 重放 |
| Day 6-8 | 200 个局面与 counterfactual 生成器、engine verifier |
| Day 9-10 | 3 个模型 x 2 个 harness 条件跑通 |
| Day 11-12 | 50-100 局固定对手对局与错误归因 |
| Day 13-14 | 统计、人工抽查、go/no-go 报告 |

## 必须先写的测试

- 同 seed + 同 action prefix 得到相同 canonical state hash。
- 玩家 observation 不含对手手牌、卡组顺序和盖卡身份。
- 每个暴露的 legal action 均能被引擎执行。
- counterfactual 修改只改变声明的变量与预期标签。
- first/second player 和 retry/fallback 不会被错误计入模型能力。
