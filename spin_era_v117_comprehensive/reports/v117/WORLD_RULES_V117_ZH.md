# V1.1.7 World职业闭环与轻量存档

本适配器使用独立格式 `SPIN_ERA_V1.1.7_CANDIDATE_1`，比赛规则为 `V1.1.7-CANDIDATE-1`。不迁移、不覆盖既有世界线。`world.WorldSession.create(..., game_ruleset='V1.1.7-CANDIDATE-1')` 由外层路由；也可以显式从 `world_v117` 导入。

每名球员每半月有15个抽象活动日，比赛、训练、休整共享。普通练赛至少消耗1日，同一球员下次练赛至少次日；正式赛事按完整赛事日数加0—3个旅行日扣费，不仅扣自己打过的场次。赛事完整窗口占用至结束日，之后练赛至少从次日开始。每阶段技术训练最多10日，其余为休整日：`competition_days + training_days + rest_days = 15`。比赛后只剩1日就只能完成正常训练的10%。半月不按真实天数放大，二月下半月与31日月份也使用15个抽象预算日，但比赛实际日期仍不得超出半月。

恢复使用非比赛日比例，训练日有日常恢复、休整模式有更大的恢复系数；`routine_recovery_eligible_days`不能再作为额外休整日叠加。调用者不得自行传入 `training_fraction/recovery_fraction`。年龄随阶段推进，不因少训练停走。体力成本取Game提供的实际估计工作量：每场每人 `min(18, 2 + 0.10*effort + movement_m/180)`，不再仅依靠总得分估计疲劳。疲劳达到90禁止新参赛；完整赛事中不因轮次疲劳增加回滚已完成赛程。伤病按确定性种子、疲劳和工作量抽样，概率上限6.5%；已有康复期禁止参赛。赛事伤病目前统一赛后结算，尚不支持中途伤退/退赛签表，这是明确保留的粗粒度限制。

默认普通俱乐部环境。起点每年12个抽象投入单位，年初未用余额累计最多24；场景可明确设置0—48的起始额度，必须留来源。国家级训练质量需已声明/挣得资格，或先执行 `invest_training(pid, id, units=3)` 购买有限高质量营地机会；这不是现实国家队身份。该方法使用3—12个单位，获得等量月数的营地资格，此后每半月国家级训练另耗1单位。前沿训练另需真实挣得的有限机会，每半月花3单位并消耗1次机会。不能无限免费调用前沿环境。

冠军有完整真实签表、Elo和S-PTS账本才可能触发成长机会。仅四人开赛或赛事名称显赫不够：胜者实际遇到对手赛前有效CA均值至少165，至少击败两名CA不低于自己8点的对手。达到这个可审计游戏阈值才解锁国家级训练质量资格、有限投入补充和前沿机会；不是现实国家队选拔或历史大赛实力认证。每年最多2个前沿奖励，冠军成长窗口同时受Training的滚动12个月最多2次约束。窗口只绑定本次实际使用至少8次的最多3项专项，挑战质量随对手实力计算，复盘质量随实际专项使用量计算。冠军不会立即增加任一技术、CA或软上限，后续选择对应专项训练才能兑现有限XP优势。普通弱场仍结算称号与该场景定义的积分，但无上述精英机会。

默认 `detail_level='summary'` 调用独立轻量Game，存聚合曝光、比分、工作量与hash，不保逐分逐板叙事。AI只能总结趋势，不能编造技术纪实。只有显式 `detail_level='full'` 才运行详细引擎；World内仍存签名compact receipt，完整日志暂存 `world.artifacts`，可通过 `world.export_artifacts(directory)` 外置；重新加载checkpoint后用 `world.attach_artifact(path)` 验证恢复。单独checkpoint足以延续生涯，不足以重新阅读未附带的逐板细节。应同时导出实际想保留的full artifacts。

轻量特殊域尚未通过跨引擎校准。正式 `run_event` 如有削球风格/战术族，或任何一面短颗粒、生胶、长胶、防弧，默认summary在参赛预检中明确拒绝，尚未打首场、扣时或入账。可明确改用 `detail_level='full'`，也可显式传 `allow_experimental_specialist_summary=True` 继续真实轻量引擎；系统不会隐式转full。显式实验赛仍会影响沙盒积分、冠军和后续成长证据，所以完整赛事收据永久标 `calibration_status='UNCALIBRATED'`、`experimental_scope='SPECIALIST_SUMMARY'`、许可值及涉及球员/胶皮，相关match_meta也带实验标记。`world.rankings()` 与完整卡的 `ranking_state` 均输出 `uncalibrated_specialist_summary` 和 `uncalibrated_specialist_summary_event_ids`，读榜者必须同时看到这些来源提示。把战术族写成attacker不能掩盖颗粒器材。详细正式赛、裸Game summary与练习赛仍可使用；练习赛不结算正式积分。

比赛仅投射当前有效43子值、G9、P6、CA、身体支撑限制和明确持拍手/器材/战术设定；PA、潜力档案、XP、训练银行、未来履历、积分与完整职业账本均不传给Game。每场输入hash也只覆盖这个局部快照，长期历史不会被反复发送到比赛进程。

交易仅克隆参与球员当前状态和小型索引；已完成账本不反复深拷贝/全量hash。每条新纪录写入hashchain，显式dump/load时验证整条链。训练阶段保留小型结算摘要和原收据hash，完整收据返回调用者但不写入永久世界events。Training去重ID、聚合年度数据和World结果账本仍随生涯线性增长；这是轻量化，不是无限期常数大小存档。四人64场、192次阶段结算的实测数据见 `world_stress_v117.json`，结果不用于证明总体成长校准。

新建checkpoint还保存 `ruleset_fingerprint`，固定文件集合写在 `world_v117.FINGERPRINT_FILES`：覆盖World、Game及新旧数值依赖、Training、Card、Area、共用schema、排名、预设库和2027/2028赛程模板；不含说明文档或实验脚本。load及deep检查逐项对照当前SHA，源码/关键数据变化即明确拒绝续跑，即使规则字符串相同、外层checksum已重签也不能静默换算法。应保留与存档配套的原工程包；将来微补丁须提供显式迁移流程，不能删改fingerprint来绕过。正常save/load保持原字节一致。

2027年末自动切换到2028年模板，未来赛程均标明合成规划。终点为2028-07-30，最后阶段结束后主角不得继续训练或比赛，尚落后的已载入NPC仅可依序结算追平。无需或不能以此机制自动生成未来历史人物。所有参赛者必须与主角处于同一阶段；训练先结算主角，再显式让载入NPC追平。未载入的整个世界仍不作自动演进。

验证命令：

```bash
python -m unittest discover -s tests -p 'test_world_v117.py' -v
python examples/stress_world_v117.py
python examples/stress_horizon_v117.py
```

`world_horizon_v117.json`进一步验证两名原创18岁球员从2006年2月到2028年奥运截止的完整长盘：每月两阶段、每季度健康允许才进行实际轻量练赛，每人每年国家级训练质量最多消费12投入单位，其余用俱乐部环境或休整；每个年末先dump/load验证，再从恢复对象继续下一年。它记录1080次球员阶段结算、完整年度趋势和终档体积；练赛无正式冠军机会，因此这个报告用于长期闭环和资源路径的诊断，不能当作最优冠军路径兑现PA的证明。

最小调用：

```python
import Card
from world_v117 import WorldSession
world = WorldSession.create([Card.make_ma18()], 2006, start_date='2006-02-01')
world.train_phase('ma_long_age18', {
    'month': 0, 'phase': 0,
    'technical': [
        {'group': 'read', 'specialize': ['self_read', 'choice']},
        {'group': 'bh', 'specialize': ['defense', 'placement']},
    ], 'body': 'stamina',
}, 'career:phase:0')
checkpoint = world.dump()
world = WorldSession.load(checkpoint)
```
