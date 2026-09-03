# 脚本目录

## WSL 入口

- `build_ygoenv_local.sh`：在已激活的 Conda `ygo` 环境中编译旧版 ygoenv 扩展。
- `build_edopro_ygoenv.sh`：将固定的现代 EDOPro core 与 ygo-agent adapter 编译到 `tmp/build-edopro-modern/`；通过 `patch_edopro_adapter.py` 生成经过严格匹配的 overlay，不改写第三方源码快照。
- `prepare_modern_runtime_assets.py`：从固定 BabelCDB 生成完整 `code_list.txt`，并审计 CardScripts 与固定 TCG/OCG 牌组后写出正式资产 manifest。
- `setup_wsl_miniconda.sh`：首次安装 WSL Miniconda 的引导脚本，不是日常实验入口。

现代 Runtime 的非对局验证命令：

```bash
conda activate ygo
python scripts/prepare_modern_runtime_assets.py
bash scripts/build_edopro_ygoenv.sh
python -m unittest discover -s tests -v
python -m experiments.run_modern_runtime_gate --stage init
python -m experiments.run_modern_runtime_gate --stage construct --profile tcg
python -m experiments.run_modern_runtime_gate --stage construct --profile ocg
```

上述 Gate 只初始化模块或构造环境池，不调用 `reset()`/`step()`，不能替代 runtime smoke。

首次 reset smoke 仅在用户明确授权后运行：

```bash
python -m experiments.run_modern_runtime_gate --stage reset --profile tcg
python -m experiments.run_modern_runtime_gate --stage reset --profile ocg
```

首次合法动作 Gate 同样必须获得单独授权后运行：

```bash
python -m experiments.run_modern_runtime_gate --stage step --profile tcg
python -m experiments.run_modern_runtime_gate --stage step --profile ocg
```

该阶段在 `reset()` 返回的 exposed legal actions 中选择索引 0，执行一次
`step()` 并验证 Gymnasium 返回、observation、card ID、reward 和终止状态。它仍不
等于完整对局、hidden-information、replay、生命周期或吞吐 Gate。

## 历史 Windows 脚本

`legacy/windows/` 保存首轮数据源采样与覆盖率审计所用的 PowerShell 脚本。它们依赖 Windows PowerShell 和 `sqlite3.exe`，不符合当前“全部命令在 WSL 中运行”的约束，因此只用于追溯既有数据，不作为新的实验入口。

迁移这些脚本时，应使用 WSL `ygo` 环境中的 Python 标准库或现有依赖，并以 `data/source_samples/` 和 `data/coverage/local-coverage.json` 做 schema 回归检查。
