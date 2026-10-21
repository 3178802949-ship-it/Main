# 旋球年代｜V1.1.6 HGR 技术补丁候选开幕文档

本包增加左右手几何、双面胶皮与专业削球机制。先读README和docs/HGR_TECHNICAL_REPORT_ZH.md，再读原有docs/AI_HANDOFF_ZH.md的通用训练与叙述规则。两者涉及新机制/规则启用时以本文件为准。

## 启动与版本

1. 解压根目录执行 `python verify_package.py` 和 `python self_test.py`。完整复验执行 `python examples/run_hgr_qa.py`，读取新生成的`checks/hgr_qa/HGR_QA.json`；发行证据保留在`reports/HGR_QA.json`。没有Python执行能力时不能声称已结算。
2. 有存档就先WorldSession.load并执行consistency_check，不重开。旧format与旧比赛规则继续旧算法，不能改旧payload或重写封存赛果；新format为`SPIN_ERA_V1.1.6_HGR_CANDIDATE_1`，固定game_ruleset=`V1.1.6-HGR-CANDIDATE-1`。
3. 新建补丁生涯必须显式 `WorldSession.create(cards, year, game_ruleset=Game.PATCH_RULESET, ...)`。直接调用Game时也显式`ruleset=Game.PATCH_RULESET`。缺省继续旧算法，这是兼容策略，不代表补丁已启用。
4. 先为原创球员建立完整43技术/P6/发展档案；持拍手、握拍、双面胶皮分别记录。规范持拍手`hand='left'/'right'`；胶皮`rubbers={'fh':'inverted','bh':'long_pips'}`。握拍单独记录，不能由胶皮猜持拍手。缺失就unknown，不按姓名补造。
5. 本轮预设均缺持拍手/胶皮史料。想要完整几何对抗须先向用户确认原创配置，或显式标为沙盒假设；不能把实验配置写回认证人物档案。anti_spin只以`experimental_anti_spin=True`显式试验启用。

## 可运行示例

`python examples/start_hgr.py --output saves/new_hgr`创建干净合成开局。

`python examples/start_hgr.py --demo --output saves/demo_hgr`额外执行一场BO7练习和两阶段训练/陪练追平。示例装备与左右手均为预先声明的合成配置，不是现实运动员史实。`examples/hgr_demo_output/START_WORLD_HGR.json`为干净开局；`DEMO_WORLD_HGR.json`仅为流程演示，不记入新玩家履历。

## 结算与叙述

- 每月两次训练、两技术大类+一体能、双子项专精疲劳、一般卓越、XP和许可规则完全沿用原Training。
- 比赛只通过Game/World公开入口调用。双方/NPC须同步到主世界半月；完整赛事/Elo/S-PTS各按原事件账本一次结算，练习不领奖励。九大赛仍一般处理。
- 正手/反手位从实际坐标、持拍手和当时站位映射；必须区分台面落点、接触侧、斜直线、追身和移动。unknown字段不得叙述成已确认的左/右手对位。
- 从日志的action_family、stroke_side、technique_path、rubber、spin_strength、geometry、movement和到位/失误记录写技术叙述；不能从胜负反推不存在的神球或旋转误判。
- 削球质量仍按原技术子项计算。专业标签/左手/长胶本身不提供固定能力加成。新动作合法并不意味着成功，削球没有直接必胜抽签。
- 只有实际可观察击球记录用于对手弱点与策略推断；不能读对手隐藏当天G作为角色已知。文学与宏观叙述可以补充氛围，不得凭叙事生成属性、冠军或积分。
- 每阶段consistency_check，展示能力/XP/许可/疲劳/伤病/排名范围，dump并交付完整存档。跨年calendar_refresh_required先切换赛历；不足完整池只报告样本排名。

## 边界

这是技术补丁候选，未认证真实历史胜率。2013许昕对照使用2012旧快照基线，朱世赫独立实验卡按既有公式重算派生聚合；两版输入完全相同。原始历史快照、封存比赛和旧存档不被补丁改写。真实赛历、人口稀有率、历史级潜能兑现和NPC全自动职业演进仍未完成。
