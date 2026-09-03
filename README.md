# yugioh-bench

面向大语言模型智能体的游戏王 benchmark 研究项目。

当前阶段是 idea validation 与最小实验设计，核心文档：

- [文档索引](docs/README.md)
- [研究方案](docs/reports/yugioh-bench-idea.md)
- [完整实验计划](docs/reports/experiment-plan-v1.md)
- [实验执行计划](docs/reports/experiment-execution-plan.md)
- [当前实验路线图](docs/reports/experiment-roadmap-2026-08-06.md)
- [下一阶段实验计划](docs/reports/next-experiment-plan.md)
- [TCG + OCG 环境范围](docs/reports/tcg-ocg-scope.md)
- [两周最小试验规格](docs/reports/pilot-spec.md)
- [本地 Pilot 结果](docs/reports/local-pilot-results.md)
- [参考资料与版本](references/SOURCES.md)

本项目当前采用的工作假设是：先做 benchmark + dataset + failure/transfer analysis，不先做新 agent 方法；先证明理解、构筑与实战策略的分层指标能解释完整对局表现，再扩展到新的 YGOAgent 方法。

v1 只覆盖纸牌 TCG 与 OCG，两个环境分别绑定可复现 snapshot 并分开报告。Master Duel 与 Duel Links 暂不纳入。

开发、测试和训练统一在 WSL `Ubuntu-22.04` 的 Conda `ygo` 环境中进行。完整协作约束见 [AGENTS.md](AGENTS.md)。

当前环境依赖记录在 [environment.yml](environment.yml)。第三方源码必须先按 [来源清单](references/SOURCES.md) 恢复到固定版本，再从项目根目录创建环境。

## 项目主页与互动审阅

仓库包含可部署到 GitHub Pages 的项目主页和静态互动审阅器。公开审阅器的结果只保存在当前浏览器中，支持 JSONL 导入和导出，不会直接写入正式 Gold。

从项目根目录生成站点：

```bash
python -m scripts.build_public_site
python -m scripts.check_public_site --site site
python -m http.server 8766 --directory site
```

打开 `http://localhost:8766/` 查看项目主页，打开 `http://localhost:8766/review/` 进入审阅器。`site/` 只包含公开页面和合成题面，不包含整套卡图、原始抓取、`docs/internal/` 或本机绝对路径。

首次同步 GitHub 前不能直接推送当前本地历史；需要先按公开 allowlist 生成干净历史，避免已提交过的内部材料出现在公开仓库历史中。

## 许可证与第三方材料

YGO-Bench 的原创代码与文档采用 [Apache License 2.0](LICENSE)。游戏王相关商标、卡图、卡片文本及其他第三方材料不包含在该授权中，其权利归各自权利人所有。项目与 Konami Digital Entertainment 无隶属、背书或赞助关系。详细说明见 [NOTICE](NOTICE)，数据与软件来源见 [来源清单](references/SOURCES.md)。
