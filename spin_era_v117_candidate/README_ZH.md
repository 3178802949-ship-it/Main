# 旋球年代｜V1.1.6 HGR 技术补丁候选

增加左右手绝对几何、双面胶皮条件动作、专业正反手削球与移动/攻削转换。基础P6/G9/CA/PA、临场波动、心理与训练成长公式保持，旧规则显式兼容。

Python 3.11+，仅标准库。新聊天先读OPENING_ZH.md和docs/HGR_TECHNICAL_REPORT_ZH.md。

```bash
python verify_package.py
python self_test.py
python examples/start_hgr.py --output saves/new_hgr
```

`--demo`额外执行真实BO7和两阶段训练。新规则须显式`Game.play_match(...,ruleset=Game.PATCH_RULESET)`或`WorldSession.create(...,game_ruleset=Game.PATCH_RULESET)`。旧调用缺省仍走旧规则，旧存档保持原format与回放结果；不静默升级。

复验：`python examples/run_hgr_qa.py`，新结果写checks/hgr_qa，发行证据在reports/HGR_QA.json。旧84项验收/100场/72职业实验保存在原reports位置，仅作为旧基线证据。

本轮预定256场同卡同种子旧/新对照见reports/hgr_patch/REGRESSION.json；完整技术报告含定义、实际结果、差异、兼容与风险，审计方案见docs/HGR_AUDIT_PLAN_ZH.md。数据变更与受保护文件见reports/HGR_SOURCE_CHANGES.json及HGR_BASELINE_MANIFEST.json。

重跑对照：`python examples/benchmark_specialist_patch.py --seeds 32 --workers 4 --output checks/new_regression`，输出须为空以免覆盖证据。重新封包：`python build_hgr_package.py --output /tmp/hgr-package`。

370预设没有可靠持拍手/双面胶皮记录，unknown不猜；回归装备是声明的实验假设。2013许昕缺年度卡，用2012旧基线且不补成长；Joo原CA标签与既有公式不一致在报告单列，原43/P6不改。不得把样本胜率作为现实历史胜率。

完整原始V1.1.6数据、示例存档与旧报告保留；本版候选只在独立目录/分支开发。原有build_packages.py仅为旧版四模块发行参考，新候选请用build_hgr_package.py。
