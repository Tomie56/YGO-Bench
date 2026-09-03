# 数据资产扩展报告（2026-09-03）

本轮目标是扩大 YGO-Bench 的静态与动态候选资产，不提前运行 LLM、GPU 或对局 smoke，也不把外部来源的答案直接当作 Gold。所有新增数据都保留来源路径、URL（如有）、抓取时间、原始响应哈希或源文件哈希。

## 本轮新增规模

| 资产 | 数量 | 当前用途 | 是否已是 Gold |
| --- | ---: | --- | --- |
| YGOPRODeck 赛事牌组候选 | 480 副 | 静态构筑候选；其中 171 副的卡号全部存在当前 BabelCDB，可进一步做动态构筑预检 | 否，需许可与环境复核 |
| 裁定 QA 候选 | 30,893 条 | 卡牌语义、规则与时点理解候选 | 否，来源答案未经过我们的专家双标 |
| 裁定测试 fixture | 66 条 | 规则/反事实候选与回归参考 | 否，需核对版本与证据 |
| BoardGame StackExchange 问题 | 283 条 | 社区难点发现与理解题候选 | 否，社区内容仅作候选 |
| ProjectIgnis puzzle Lua | 459 个 | 动态残局候选，供 loader/版本审计 | 否，规则环境混杂 |
| yugi-bench-v1 solution trace | 已归档 | 暂不纳入当前动态候选池，等待后续 action-schema 重放审计 | 当前不使用 |

候选清单统一索引位于 `data/benchmark/source-candidates-v0.2/manifest.json`。静态和动态清单采用 gzip JSONL，便于后续 loader 流式读取。

## 赛事牌组来源

通过 YGOPRODeck 公开 `getDecks.php` 接口的 `tournament=1` 过滤器抓取 200 页（约 4,000 条原始记录），每页约 20 条。原始页面响应保存在 `data/source_samples/ygoprodeck_tournament/api-candidates-v0.2/raw_pages/`，规范化候选保存在 `tournament-candidates.jsonl`。

规范化字段包括 `deck_num`、牌组名称、提交用户、赛事名称、名次、选手、参赛人数、format、Main/Extra/Side 卡号数组、牌组页面 URL 和抓取时间。接口返回中仍有普通 Meta/Genesys 社区牌组，因此只有同时存在赛事名称、名次和选手字段的记录才进入候选清单。

480 副候选覆盖多个赛事与 format，包括 TCG、OCG、Worlds 及 Genesys；它们不是当前 20 副人工交叉核验 corpus 的替代品。YGOPRODeck 的公开 API 文档允许批量读取卡片/牌组数据，但本轮仍将牌组记录标为 `candidate_only_license_review_required`，正式发布前需要确认站点条款和再分发边界。

## 静态理解候选

`ocg-ruling-assistant` 的 30,893 条 QA 已解压为候选索引，保留问题、来源答案、问题卡号、相关卡号、关键词、状态和 source URL。它适合按 `questionCardIds`、规则关键词和题型抽样，不能直接作为 Gold：

1. 其中 24,975 条是 `card-faq`，5,918 条是 `qa`，来源语言和裁定时点并不统一。
2. 来源项目虽然是 MIT，但数据中引用了官方 FAQ 和其他公开资料，最终数据集仍需逐条确认版权、版本和答案证据。
3. 外部答案只能作为候选答案或检索证据；正式理解集仍要求两位熟悉游戏王规则的标注者独立标注并裁决。

另加入 66 条已有 fixture case 和 283 条 StackExchange 问题。StackExchange 条目保留 CC BY-SA 4.0 标记、题目链接、分数和回答数量；它们用于发现高价值难点，不直接进入测试 Gold。

## 动态策略候选

ProjectIgnis 的 459 个 Lua 脚本已生成逐文件清单，记录脚本哈希、目录类别、字节数、`aux.BeginPuzzle()` 和 solution marker。该仓库包含 World Championship、Miscellaneous、Duel Links、旧主机游戏和教程等多种规则环境，不能假定全部兼容现代 TCG/OCG runtime。下一步应按目录和脚本依赖分层，先筛出现代 ocgcore 可加载的子集。

yugi-bench-v1 的 89 条 solution trace 保留在原始来源目录，但按当前决定暂不纳入动态候选索引。等我们的 action schema 和 replay 兼容性审计完成后，再单独决定是否恢复；本轮动态候选只包含 ProjectIgnis 脚本。

## 当前结论与下一步

本轮已经解决“候选题太少”的资产问题，但没有把候选规模误写成有效 Gold。下一步按以下顺序推进：

1. 静态侧按规则关键词、卡号覆盖、来源版本和重复问题对 31,242 条候选去重分层，抽取一批供人工审阅器集中标注。
2. 构筑侧对 480 副赛事候选运行纯数据 verifier，分离 TCG/OCG/Genesys/Worlds，检查卡池、禁限表和 Main/Extra/Side 约束。
3. 动态侧先对 ProjectIgnis 目录做环境筛选，再用当前 runtime 对小批候选执行 loader-only preflight；这不是 smoke 或完整对局实验。
4. 暂不处理 yugi-bench trace；只有在明确恢复决定后，才进行 schema 转换和 replay hash 审计。
5. 由人工完成 Understanding pilot 的 Gold；候选数量扩展不替代双标和裁决。
