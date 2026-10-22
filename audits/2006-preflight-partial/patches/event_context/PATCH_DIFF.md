# V1.18基线：赛事上下文与小组伤病结算补丁

状态：**TESTED_BASELINE_PATCH_NOT_APPLIED_TO_UNREAD_HANDOFF**。

本目录是基于已发布V1.18源码的独立、已测试补丁，不是2006年末恢复档。新上传的2004—2006完整ZIP因32MiB传输限制尚未读取，不能据此声称已经核验其中的新引擎或修复其全部世界线。

## 实际缺陷与修复

1. 原`world_extensions_v1_18.py:194`公开`settle_match`接受任意`event_id`。下游`_settle_inplace`把非空ID视为正在参赛，绕过疲劳预检，并把伤病检定延期到该ID。原代码未验证该赛事存在；实际合成测试中，疲劳95的双方在普通提交被拒绝，而指定不存在的赛事后却成功入账，伤病永久延期，deep check仍通过。
2. 原`run_group`逐场都传内部赛事ID以延期伤病，却没有在循环结束时兑现健康检定。

补丁只改`world_extensions_v1_18.py`：

- 外部`settle_match`明确拒绝任何非None的赛事上下文，错误为`EXTERNAL_EVENT_CONTEXT_FORBIDDEN`。赛事权限只属于内部`run_event`/`run_group`原子事务；不能凭一个字符串获取。
- `run_group`在所有赛果完成后、提交前，对每名参赛者恰好调用一次原有`_injury_chance`，使用本组实际日志累积effort，并把回执放入`completed_group.post_event_health`。
- 若最终健康结算失败，整个组别的赛果、积分、疲劳、XP、健康与外置日志都不提交。未更改伤病概率系数。

逐场`MatchSettlement`保留其`deferred_to`记录，最终通过对应组事件的`post_event_health`解析；不会回写并重新封存原始比赛收据。

## 实测

- 5项实际公开API测试全部通过：虚假赛事和已存在事件都不能被外部借用、拒绝后状态逐字不变、正常外部提交及重复幂等、每名组赛参与者仅一次健康结算与实际effort、健康结算异常全事务回滚。
- 3项安全应用测试通过：默认dry-run不写、显式应用及重复幂等/原件备份、错误基线拒绝且不写、已知原始源码路径拒绝写入。这里同一测试可覆盖多个断言，合计仍为3项。
- 另在独立候选副本同时应用本补丁和相邻`draw_identity`补丁，原377项测试全部通过，用时68.371秒。没有把复跑计作新增377项测试。
- 候选指纹为`33642d261576746aad922b07a254c13d176de52f36a90dba96c11194841f0f06`。原始2005检查点在候选中按设计拒绝载入，报`WORLD_RULESET_FINGERPRINT_MISMATCH`；未通过改指纹或旧检查点绕过。
- 所有比赛均为合成身份；没有重赛封存历史，也没有运行2007正式赛事。

证据：`TEST_RESULTS.txt`、`APPLY_HELPER_TESTS.txt`、`COMBINED_BASELINE_REGRESSION.txt`、`COMBINED_FINGERPRINT_CHECK.json`、`TEST_REPORT.json`。`BEFORE_PHANTOM_EVENT_PROBE.json`来自本轮对未改动基线的实际复现。

## 应用、迁移与回滚

保持原始引擎只读，在独立候选目录执行：

```bash
python apply_patch.py --candidate-engine /path/to/candidate
python apply_patch.py --candidate-engine /path/to/candidate --apply
```

第一条仅dry-run；第二条才写入，且必须匹配`PATCH_MANIFEST.json`基线SHA256。重复应用返回`already_applied`。脚本生成原件备份，并原子替换单个源码文件。`run_validation.py`可从显式基线路径在临时目录重建并测试；`--full-regression`运行原377项测试，`--combined-draw-patch-dir`可同时验证抽签身份补丁。

代码改变后原分发清单与规则指纹应当失效，须由正式发布流程重建清单并提供已审计的版本迁移。**此补丁没有生成或伪造2006年末检查点，也未自动迁移旧存档。** 尚未读取新包前不推荐玩家直接对正在使用的世界线应用。

回滚时恢复候选的`world_extensions_v1_18.py.before_event_context_patch`；若同时用了抽签补丁，也恢复其原始文件。恢复原版本引擎后才使用该版本原始检查点；不把新账本倒塞进旧格式。

## 仍未解决

该补丁不新增年龄资格、官方提名、种子/轮空/同国回避或逐轮授权，不改变整场赛事自动跑完的既有API；这些属于另行审计的缺口。它也不把内部青年Elo当官方排名，不补造2005—2006历史数据。
