# 《旋球年代》V1.1.7 综合版

本分支为有限时代生涯模拟的综合工作基准。新增球风偏好、明确为模拟设定的后台人设、时代来源日期约束、可审计叙述和PA/伤病口径，保留四模块与统一结算。尚非正式1.0或历史认证。

- [下载总包、四个分包与交接文档](downloads/v1.1.7-comprehensive/README_DOWNLOAD_ZH.md)
- [完整总包ZIP](downloads/v1.1.7-comprehensive/Spin_Era_V1_1_7_Comprehensive.zip)
- [新聊天开幕文档](spin_era_v117_comprehensive/OPENING_COMPREHENSIVE_ZH.md)
- [玩家与AI说明](spin_era_v117_comprehensive/README_COMPREHENSIVE_ZH.md)
- [Q&A与保留问题](spin_era_v117_comprehensive/docs/COMPREHENSIVE_QA_ZH.md)
- [本版实际QA](spin_era_v117_comprehensive/reports/comprehensive/qa/COMPREHENSIVE_QA.json)
- [分发件干净解压检查](downloads/v1.1.7-comprehensive/COMPREHENSIVE_PACKAGING_VERIFICATION.json)

网页版下载：打开ZIP后点右上角 **Download raw file** 下载箭头。总包已经包含四模块，普通用户只需总包ZIP和开幕文档。

351项行为检查通过，100条条件成长曲线、128场风格对照、96份叙述审计完成。两名原创角色从2006年推进至2028年，完成1080次阶段结算、89场聚合练习与23次载入续跑检查。四个独立分包和总包均在干净解压后实测。

良好条件48/48达到峰值CA距PA≤10，有限资源场景仍不保证；冠军窗口局部XP有效，但本组未提高最终峰CA。专业削球/颗粒正式summary仍未校准，默认保护保留。3篇作者摘要已读，训练等体育原文和人物采访未核实，性格仅为模拟写作设定。详情和原始证据均随包。

Python3.11+标准库。进入`spin_era_v117_comprehensive`：

```bash
python verify_package.py
python self_test.py
python examples/start_comprehensive.py --output saves/new_career
```

公开入口：`from simulator import WorldSession, Card, Game, Training, Area, Narrative`。内部v118文件名是增量实现标记，公开版本仍V1.1.7综合版。存档绑定源码与数据指纹，不静默升级旧世界。

[此前V1.1.7候选](downloads/v1.1.7-candidate)、[HGR候选](downloads/v1.1.6-hgr-candidate)及其源码继续保留，旧世界按原规则续接。
