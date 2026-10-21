# 旋球年代｜V1.1.7 测试候选

本分支包含长期成长、身体支持后的技术表现、独立削球/颗粒战术、聚合比赛、
职业时间与资源约束，以及截止2028奥运会的有限时间线。

- [下载总包、四个分包和中文文档](downloads/v1.1.7-candidate)。
- [新聊天开幕文档](spin_era_v117_candidate/OPENING_V117_ZH.md)。
- [实际技术报告与未通过项](spin_era_v117_candidate/docs/V117_TECHNICAL_REPORT_ZH.md)。
- [源码与启动说明](spin_era_v117_candidate/README_V117_ZH.md)。
- [V1.1.6 HGR旧版](downloads/v1.1.6-hgr-candidate)与[原整合版](downloads/v1.1.6)继续保留。

Python3.11+，仅标准库。进入`spin_era_v117_candidate`执行：

```bash
python verify_package.py
python examples/start_v117.py --output saves/my_career
python examples/start_v117.py --output saves/month_demo --demo
```

重点比赛的逐板体验另加`--full-match`。普通比赛输出结果和聚合趋势。
新世界使用`world_v117.WorldSession`，存档绑定核心规则指纹；旧存档继续原规则。
本版本为测试候选，实验条件、成功范围与剩余偏差以技术报告为准。
