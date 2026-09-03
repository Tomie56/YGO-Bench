# 构筑 Benchmark 静态牌组审阅页

## 定位

构筑页是 YGO-Bench 的静态审阅与展示终端，不是牌组编辑器。它读取冻结的 YDK 文件，展示 Main Deck、Extra Deck 和 Side Deck，并输出机器可读的牌组清单。页面本身不增加、删除或替换卡牌，也不替模型完成禁限合法性、缺卡补全或选卡判断。

## 输入与输出

输入为标准 YDK 的 `#main`、`#extra`、`!side` 三个分区，以及冻结 CDB 和本地卡图目录。卡图直接使用 passcode 命名的本地 JPEG；若某个 passcode 没有图片，则显示带卡名的文字卡框，不伪造图片。

输出包括：

- 静态 HTML：保留完整网格、卡图引用与可检查结构；
- Edge PNG：用于人工审阅和论文展示；
- `.deck.json`：记录输入 YDK/CDB 哈希、三区卡数、逐卡顺序、copy number、卡名和图片可用性。

## 页面结构

页面参考密集牌组总览的基本结构：顶部显示牌组名和 Main/Extra/Side/Unique 计数；Main Deck 使用十列卡图网格；Extra Deck 与 Side Deck 分别使用独立色带和十列网格。页面不显示没有 Gold 来源的稀有度、卡包或编辑状态。

这套表示可以直接用于以下构筑任务的输入或结果审核：

- 禁限表与卡池条件下的牌组合法性检查；
- 从不完整牌组中补全缺卡；
- Main/Extra/Side 的最小修复；
- side-deck 调整；
- TCG/OCG 环境迁移；
- 候选卡选择结果展示。

## 首个真实样本

首个完整样本使用 European WCQ 2026 的 Kewl Tune Top 8 牌组：

- 输入：`data/fixed_snapshots/tcg-kde-e-2026-05-18/decks/european-wcq-2026-kewl-tune-top8-alex-biemans.ydk`
- HTML：`tmp/deck_renderer_example/european-wcq-2026-kewl-tune-top8-alex-biemans.html`
- PNG：`tmp/deck_renderer_example/european-wcq-2026-kewl-tune-top8-alex-biemans.png`
- 清单：`tmp/deck_renderer_example/european-wcq-2026-kewl-tune-top8-alex-biemans.deck.json`

该样本为 Main 40、Extra 15、Side 15，38 种不同卡牌；60 张卡均有本地卡图。它只证明静态展示与审计链路可用，不构成模型构筑能力结果。
