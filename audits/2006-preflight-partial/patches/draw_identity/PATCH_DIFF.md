# V1.18历史签位替换身份补丁

状态：TESTED_BASELINE_PATCH_NOT_APPLIED_TO_UNREAD_HANDOFF。仅适用于基线源码SHA256精确匹配的独立副本，不修改原V1.18或2004—2006锁定历史。

修复：拒绝空/非法新身份、非法原名单身份、已在签表中的新身份，并检查替换后不重复。合法输入的随机候选集合、排序、选位、seed和输出结构保持不变。50个seed对照逐值相同；不代表50场比赛校准。

```diff
--- a/Game/competition_v1_18.py
+++ b/Game/competition_v1_18.py
@@ -52,7 +52,11 @@
 
 def historical_replacement(entries,player_id,*,seed,qualification_tier,source_refs=()):
     """Only replace a supplied low slot. Never invent real attendance."""
-    if not entries or len({x.get('player_id') for x in entries})!=len(entries):raise ValueError('unique supplied entries required')
+    if not isinstance(player_id,str) or not player_id.strip():raise ValueError('nonempty replacement player identity required')
+    if not isinstance(entries,(list,tuple)) or not entries or any(not isinstance(x,dict) for x in entries):raise ValueError('unique supplied entries required')
+    entry_ids=[x.get('player_id') for x in entries]
+    if any(not isinstance(pid,str) or not pid.strip() for pid in entry_ids) or len(set(entry_ids))!=len(entries):raise ValueError('unique supplied entries required')
+    if player_id in entry_ids:raise ValueError('REPLACEMENT_PLAYER_ALREADY_ENTERED')
     eligible=[x for x in entries if x.get('qualification_tier')==qualification_tier and not x.get('confirmed_seed') and not x.get('confirmed_deep_run')]
     if not eligible:raise ValueError('NO_EVIDENCE_COMPATIBLE_LOW_SLOT')
     chosen=random.Random(seed).choice(sorted(eligible,key=lambda x:x['player_id']))
@@ -60,6 +64,7 @@
     for x in draw:
         if x['player_id']==chosen['player_id']:
             x.update(player_id=player_id,replaces=chosen['player_id'],classification='SIMULATED_REPLACEMENT')
+    if len({x['player_id'] for x in draw})!=len(draw):raise ValueError('DUPLICATE_REPLACEMENT_DRAW_IDENTITY')
     verified=bool(source_refs) and all(x.get('evidence_status')=='VERIFIED_ATTENDANCE_AND_SLOT' for x in entries)
     return dict(draw=draw,removed_player_id=chosen['player_id'],seed=seed,source_refs=list(source_refs),
         status='EVIDENCE_QUALIFIED_ALTERNATIVE_BRANCH' if verified else 'HYPOTHETICAL',
```

默认dry-run：

```bash
python apply_draw_identity_patch.py --engine-dir /path/to/separate/engine
python apply_draw_identity_patch.py --engine-dir /path/to/separate/engine --apply
python test_draw_identity_patch.py
```

应用器校验原/补丁源码SHA256、拒绝已知原引擎路径及指向原路径的符号链接、错误基线不写文件，重复应用返回ALREADY_APPLIED。只原子替换一个源码文件。

此补丁会改变规则指纹。它不是存档迁移器，不得为了加载旧World手工篡改存档指纹。应由主发布流程在独立版本中实现显式迁移后再续玩；新交接包尚未读取，禁止直接宣称已适配它。回滚时恢复原引擎及应用前完整存档配对，不能把修改后新账倒塞进旧引擎。ORIGINAL_competition_v1_18.py为逐字节基线备份。

已运行8项单元测试：原缺陷复现、补丁拒绝、50种子有效行为不变、输入不变、非法身份拒绝、dry-run/应用/幂等、错基线拒绝、原引擎写保护。没有重赛历史对局或2007正式比赛。
