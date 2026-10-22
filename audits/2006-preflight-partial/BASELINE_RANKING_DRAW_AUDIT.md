# V1.18基线：排名、资格与签表只读审计

状态：`TESTED_BASELINE_ONLY_NEW_HANDOFF_NOT_READ`。本报告检查已发布基线`5efc9c6449617a415668896abecf37a8e0ad24ad`下的`spin_era_v1_18`。新上传完整2004—2006 ZIP因32MiB工具传输上限尚未读取；不能把以下结果称为其`SOURCE_MANIFEST.json`核验或2006年终存档认证。

未修改原始引擎；仅运行2006年2月的合成人物、合成赛事探针，未运行任何2004—2006锁定比赛或2007正式赛事。

## 优先修复的已证实问题

### P0：任意event_id可绕过疲劳资格并永久延迟伤病

`world_extensions_v1_18.py:142`把任何非空`event_id`传成`_check_actor(..., in_event=True)`。`world_v1_18.py:368`只在`not in_event`时检查疲劳上限。`world_extensions_v1_18.py:166`随后把伤病检查替换为`deferred_to=event_id`，但公开`settle_match`（194—203行）没有验证该ID是否属于已授权、在进行的赛事上下文。

实际探针：两名合成球员疲劳95；同一份由真实引擎生成的BO3收据，未传赛事ID时被拒绝；传`PHANTOM-DOES-NOT-EXIST`即成功结算，双方伤病均推迟给不存在的赛事，`consistency_check(deep=True)`仍返回有效。证据`ranking_draw/PHANTOM_EVENT_PROBE.json`。

最小修复方向：公共提交不能自行指定内部特权。使用显式在进行赛事登记/内部作用域，将跳过赛前疲劳与推迟伤病限制于实际受控生命周期；所有已延期检查在赛事完成时必须恰好兑现一次，深检拒绝悬空延期。旧封存记录不重算伤病。

相关缺口：`run_group`（`world_extensions_v1_18.py:289`）给每场传同一赛事ID，但结束时只存表及回执，没有类似`run_event`的赛后`_injury_chance`汇总结算。因此循环赛的延期伤病也未闭合。这个结论来自真实调用栈；尚未用大样本评估其生涯影响。

### P1：历史替换可产生同一球员两次入签

`Game/competition_v1_18.py:50`的`historical_replacement`检查输入名单唯一，但不检查新`player_id`是否已在名单，也不检查替换后名单唯一。

实际探针：输入`[a,b]`，申请新增`a`、`seed=0`，替换低位`b`后返回`[a,a]`。这直接违反“全分区不重复球员”。证据`ranking_draw/PROBE_RESULTS.json`。适合在独立候选副本加非空身份、禁止已参赛身份和输出唯一性检查；对合法输入保持同seed同签位，不触碰历史结果。

### P1：青年类别缺少统一年龄/提名资格闸门

`run_group`只检查人数、类别、健康和时钟，不调用`Area.check_entry`，也不需要年龄组或协会提名收据。公开`settle_match`同样允许直接选择`kind='youth_singles'`。两名30岁合成卡可以完成青年BO3循环组，青年Elo也被更新，深检有效。见`ranking_draw/PROBE_RESULTS.json`。

`Area/__init__.py:276`的既有`check_entry`是结构预检，文档已明确不认证配额/排名资格。它按比赛首日实岁或出生年份近似比较`min_age/max_age`（约302—324行），没有赛事专属的“在某年1月1日出生之后”截止日期规则。缺历史规程时不能擅自选择一种年龄口径作为2006开罗官方规则。

最小修复方向：新正式比赛要求显式年龄级别、cutoff模式/日期、协会、提名/资格状态；未知官方资格返回`UNVERIFIED`并阻断正式报名，另留显式假设沙盒入口。练习赛不受正式年龄组限制。不要追溯拒绝已锁定旧赛果。

## 已存在的排名机制及缺失部分

- `Card/__init__.py:323`的`RankingBook`分别保存成年/青年Elo以及成年/青年/团体赛事积分。`settle_match`拒绝重复match_id；World外层同收据重交则返回`already_applied`，这两层职责没有混淆。
- `runtime/ranking_v112.py:1`明确称独立内部提案，`Card/__init__.py:405`也输出`INTERNAL_S_PTS_NOT_OFFICIAL_HISTORICAL_ITTF`；现有代码并未把S-PTS宣称为ITTF官方历史排名。
- 唯一公开`world_ranking`（`Card/__init__.py:382`）仅调用成年`leaderboard`，后者只合计`player.results`。青年400分冠军写入`youth_points`后，该查询仍显示0 S-PTS；这是“青年榜接口缺失”，不是已经拥有青年榜且算错为0。`world.card`只附青年Elo，不能据此推出青年世界第几。
- 当前成年内部榜采用365日窗、最佳8站、到期删除而非连续衰减（`runtime/ranking_v112.py:65`）。同一event_id同一球员不可重复记分（55行），但同一站跨周系列身份、强制站与协会完整池没有重建。
- 榜单不存出生日期/年龄组，因此不会按年龄退出青年榜。`eligible_ids`由调用者提供；`complete_pool=True`只代表声明完整池，不是官方认证。
- 世界卡的`ranking_state`输出完整性范围和内部积分口径，做法应保留。新增青年榜应在独立的版本化投影里完成，使用相同唯一事件账而不是再发一份赛果积分。

## 签表与赛事生命周期

`world_v1_18.py:532`的`run_event`仅处理2/4/8/…128人完整单败淘汰赛，拒绝团体（544行）、非2次幂和重复球员（539行）。`rng.shuffle(draw)`（589—591行）不保护种子、不检查同国回避，也无空签/轮空语义。后续轮次由真实胜者继承，路径唯一这一点存在，但函数会一次性把整项赛事跑完（594—607行）。

因此它是“已标SIMULATED的完整沙盒赛事运行器”，不是用户现在要求的真实资格/种子签表恢复器，也不能直接用于“每胜一场展示下一位对手并等待授权”。应另加可恢复的逐场赛事状态机，存固定槽位、资格证据、种子位置、轮空、已完成节点、下一场待授权节点；仍让已批准单场通过既有原子结算入口。

`run_group`使用轮转表产生不同配对，`group_table`拒绝重复/外来配对并锁定BO，`qualifiers`在出线边界仍同分时拒绝凭ID晋级。其返回明确声明模拟规则、非认证历史规程。当前小表排序不是所有年代赛事官方规程的替代品；新赛事应显式给出可核验的tiebreak规则。

`historical_replacement`只允许指定层级的非确认种子/深轮次低位槽位，方向保守；但所谓`EVIDENCE_QUALIFIED_ALTERNATIVE_BRANCH`依赖调用者自报`evidence_status`与非空source_refs，函数没有读取或认证引用内容。不要把这一状态写成“官方已核验”。

## 尚缺的历史输入

1. 新总包根`CODEX_MASTER_PROMPT.md`、`SOURCE_MANIFEST.json`及每个原文件实际字节。
2. 2005逐场收据和分支身份，以核对14-9+15-8=29-17与旧档29-18、2006总账83-32之间的一场负场差；不能凭算术创造一场比赛。
3. 权威2006开罗第一版决赛原始日志及废弃三版收据/完整后效应，方可核对650板、seed200612170717、XP、伤病、H2H及回撤。
4. 2006赛事当年男子原型的报名名单、年龄截止条款、协会配额/提名、种子排名截点、完整签表和同国回避规程的可靠原件或可访问来源。
5. 全部NPC同站结果及模拟青年积分表，方能算覆盖范围明确的模拟年终青年榜。开罗银牌应有积分口径，但不能仅加主角后宣布精确世界名次。
6. 2006七月完整43子项/P6 XP结存，及之后每阶段收据；若只有三月卡桥接，必须保留unknown而不是伪装完整续玩档。

本次未获取新的官方外部历史来源。用户粘贴的要求及三年概述属于任务约束/待核对线索，不是本报告已读过的逐场原始证据。

## 已运行命令

`python /workspace/audits/full_history_2006/ranking_draw/probe_baseline.py`成功，保存`PROBE_RESULTS.json`与`PROBE_RUN.txt`。它实际复现三项行为并记录9个依赖源码SHA256。另一次合成疲劳95假赛事探针保存`PHANTOM_EVENT_PROBE.json`。这些是缺陷复现证据，不是修复后通过或历史校准测试。

## 独立候选补丁完成情况

`patches/draw_identity/`已提供原/新源码、SHA绑定默认dry-run应用器、真实unified diff及8项通过的单元测试，含50种子合法行为对照。状态仍为`TESTED_BASELINE_PATCH_NOT_APPLIED_TO_UNREAD_HANDOFF`。原引擎未改，新总包未读取，尚不能宣布迁移到2006完整世界。
