# 《旋球年代》V1.1.7 综合版｜使用说明

这是本轮收束的赛事与长期生涯工作基准，规则为 `V1.1.7-COMPREHENSIVE-1`。总包包含Game、Card、Training、Area四个模块、统一World、证据叙述、来源记录、测试、完整开局卡与存档。旧文件保留以复查原基线；内部`v118`文件名只表示增量实现层，公开版本仍是V1.1.7综合版。

## 交给新的聊天

把**完整总包ZIP**与**OPENING_COMPREHENSIVE_ZH.md**一起上传，并发送：

> 按开幕文档加载本包，先验证PACKAGE_MANIFEST，再恢复examples/comprehensive_demo_output/START_WORLD_COMPREHENSIVE.json。先展示当前公开卡、日期、疲劳和可行动作，等待我选择本期训练或比赛。调用程序实际结算后再叙述，不提前推进时间。若无法执行Python，请明确说明，先只讨论方案。

随包起点是2006年2月1日的“马龙式18岁测试卡”，不是现实生涯重放。`COMPLETE_CARD_COMPREHENSIVE.json`为完整公开卡；`DEMO_*`是另存的一月示范结果，不应替换尚未行动的START。

## 本地运行

需要Python 3.11或更高，全部依赖标准库。在解压后的工程根目录执行：

```bash
python verify_package.py
python self_test.py
python examples/start_comprehensive.py --output saves/my_first_career
```

最后一条只创建新起点；如需运行一月示范，加`--demo --full-match`。输出目录须为空，避免覆盖旧存档。自动复验：`python run_comprehensive_qa.py --output checks/my_qa`。

```python
from pathlib import Path
from simulator import WorldSession, Card, Game, Training, Area
w = WorldSession.load(Path('examples/comprehensive_demo_output/START_WORLD_COMPREHENSIVE.json').read_text(encoding='utf-8'))
print(w.card('ma_long_age18'))
print(w.consistency_check(deep=True))
```

本版新增源码与冻结旧依赖通过规则指纹绑定。旧存档继续使用原工程；不能改format或指纹“升级”。源代码和数值数据不应在生涯进行中随手修改。

## 四模块各做什么

| 模块 | 职责与本版入口 |
| --- | --- |
| Game | 对抗、合法动作选择、球风小幅先验、逐板/聚合日志；`Game.play_match` |
| Card | 43技术/P6/G9/CA、排名账本、公开球风、后台人设；`Card.normalize/public_view/narrative_view` |
| Training | 月内两阶段、两技术大类与一体能、专精、一般训练、连续XP、年龄/伤病；`Training.initialize/settle_phase` |
| Area | 时代主题、人物快照、赛历模板、报名和2028终点、来源日期；`Area.context_for_date/calendar_for_year` |

独立分包用于检查或接入；持续生涯只通过World提交。不要先调用底层加XP，再用World领取一次。Area就是早先口述的“时代”模块，本版沿用工程名称。

## 对局、训练与叙述

每月两阶段，每阶段可特训两技术大类和一体能大类；每个技术大类可选两个子项专精，代价为额外疲劳。未选子项保留一般训练及卓越成长机会。比赛、训练、休息共享时间，不允许凭对话多领一次。

球风是偏好，不是能力；后台性格只为叙述参考。公开人物的性格目前均标为模拟写作设定，无已核实采访。突破/冠军给有期限的专项学习窗口，不直接赠送CA/G或冠军战力。PA是窄带生涯潜能评估；自然老化降低身体支持与当前发挥，不自动扣PA。持久大伤另有潜能损伤收据。

summary用于赛果和聚合趋势，不生成不存在的逐板纪实。主场细节模拟应明确选full，全文外置并保存哈希；缺少全文就退回聚合叙述。`w.narrate_match`、`w.narrate_training`只读已结算证据，文学扩写也须遵守此范围。

## 交付边界

时间截止2028-07-30；2027/2028赛历是模拟模板，不是已核实官方赛历。削球/颗粒的正式summary对局仍未完成校准，默认保护会拦截，显式实验后留有UNCALIBRATED旗标。完整NPC人口自动演进、团体赛执行和共享世界并发不在本版验收内。

研究可读范围与失败记录见`docs/V118_RESEARCH_ZH.md`；作者摘要不是训练或PA系数的实证证明。最终结果见`reports/comprehensive/`，旧`reports/v118`保留为开发过程记录，不当作新增验收证据。
