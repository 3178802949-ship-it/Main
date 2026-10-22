# 《旋球年代》V1.18｜玩家与维护说明

本版以V1.1.7综合版为代码基线，实施共享时钟、独立比赛事务、43专项正式经验、奖励兑换和赛制修订。公开规则为`V1.18-1`；内部旧`v118`文件不是本版入口，新增模块名为`v1_18`。Python3.11+标准库即可运行。

## 开始或续接

新聊天上传总包ZIP和`OPENING_V1_18_ZH.md`，要求其先校验文件，再恢复随包起点。没有Python执行能力时，只能阅读、规划和写明确虚构的段落，不能声称已经结算。

```bash
python verify_package.py
python self_test.py
python examples/start_v1_18.py --from-2004 --output saves/my_2005
```

输出目录必须为空。命令只生成继承起点和迁移核对表，不触发2005赛事。随包`examples/v1_18_opening/START_WORLD_V1_18.json`是可直接恢复的2005-01-01起点；原始检查点与迁移预览并列保留。普通原创测试起点可省略`--from-2004`，使用马龙式18岁测试卡；加`--demo`才会另存一次示范训练结果。

```python
from pathlib import Path
from simulator import WorldSession
w = WorldSession.load_file('examples/v1_18_opening/START_WORLD_V1_18.json')
print(w.card(w.data['main_player_id']))
print(w.consistency_check(deep=True))
w.save('saves/2005_start.json')
```

`save`默认不覆盖；显式`overwrite=True`采用原子替换并保留上个有效版本`.bak`。损坏时只有显式`load_file(path, recover_backup=True)`才使用备份，不悄悄倒退生涯。

## 四模块与统一入口

| 模块 | 本版作用 |
| --- | --- |
| Game | 详细/轻量BO3、BO5、BO7；合法动作、球风、身体疲劳；可选反扑；日志重放 |
| Card | 当前43/P6/G9/CA、排名账本、12轴球风与后台性格 |
| Training | 两阶段训练、正式XP银行、同一成本/许可/软上限管道、有限奖励 |
| Area | 有限时代主题、赛历和参赛检查、明确模拟赛制与来源日期 |
| World | 所有比赛、训练、日程、疲劳、伤病、H2H、排名和经验的统一提交 |

持续生涯只通过World行动。`Game.play_match`只产生比赛收据，随后可交给`w.settle_match`统一入账；`w.play_practice`、`w.run_event`和`w.run_group`已包含结算，不能再领一次底层XP。

```python
# 例：需两个当前已激活、同期且健康的球员。
# raw = w.play_practice(a, b, 'unique-match-id', 118001, best_of=5, detail_level='full')
# receipt = w.match_settlement('unique-match-id')
```

主角关闭一个半月后，NPC通过相同Training管道自动结算到同一时钟，正常训练上限同为10天；跨年资源也为所有激活球员一次性滚动，保留到账记录；NPC计划可用`queue_npc_plan`预先指定。缺完整卡的历史身份不能直接比赛；已有锁定卡可用`activate_player_snapshot`带到当前日期，明确标为沿用能力的评估，不重新抽取能力。

## 从2004继承了什么

2004的14胜9负、CA150/PA191/P6/43值和原始文件保留。23场旧赛果进入新分支账本并重建H2H；5份详细日志保持原世界ID/哈希，经专门接口挂接。旧疲劳不倒扣，缺失的官方积分不凭空补造。早期青年内部积分保留其部分记录身份，2005新增比赛从新账本继续计算。

旧使用量按明示的100次使用兑1XP规则对账，累计26.34XP已接入正式银行（包含波兰连胜兑换）；不直接兑换永久技术点，因此开局CA仍150。重复汇总文件不再次相加。`stable.consistency`在本版明示映射到`stable.sustain`，旧奖励原文不改。雅典2张观赛凭证永久保留，可按本版规则兑换。

NPC的2005状态通过记录过的模型追赶生成，原2004对手卡仍封存。未保存完整属性的资格赛对手只进入身份库，禁止把姓名自动补成高手卡。

## 赛制与负荷

BO3/5/7分别先赢2/3/4局；每局11分、净胜2分，10平后每分换发球。决胜局5分换边采用对称场地、规范化几何坐标，不给某一端隐藏能力加成。赛制主要改变总局数、负荷、调整机会和短赛随机性，单项技术不按赛制加点。

小组由统一best_of和显式排序规则处理。多方同分先建立相互交锋小表；无法解决的出线边界需补充明确规则，不能用稳定ID顺序冒充体育裁决。2004欧青赛混合赛制保留，不反向重算旧小组。

## 已知限制

极端全维能力差距仍会产生过高确定性的强弱结果；小幅反扑不等于解决了底层胜率曲线。专业削球/颗粒正式summary继续受校准保护，需明确选full或显式实验许可。时代赛历是来源分级的模板，完整真实历史签表与官方排名未完成认证。

官方规则原站本轮返回403，记录见`reports/v1_18/RULE_SOURCE_ACCESS.json`。基本赛制按规则知识实现并做程序校验；具体赛事使用哪种赛制仍需其真实规程证据。训练与生理系数仍是游戏设计参数。
