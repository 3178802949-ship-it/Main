# 2004—2006历史交接｜源码预审与独立补丁（PARTIAL）

新上传完整历史ZIP超过当前工具32MiB传输上限，尚未读取其根任务书、SOURCE_MANIFEST及新2005—2006原件。本分支不是已恢复2006年末的新版游戏，也没有推进2007正式赛事。

- [下一批材料如何上传](audits/2006-preflight-partial/INPUT_UPLOAD_GUIDE_ZH.md)
- [阶段审计、补丁与实验总包（约1.74MB）](downloads/2006-preflight-partial/Spin_Era_2006_Preflight_Audit_PATCHES_PARTIAL.zip)
- [已完成与未完成](audits/2006-preflight-partial/WHAT_IS_DONE.md)
- [测试报告](audits/2006-preflight-partial/TEST_REPORT.md)
- [源码与账本冲突](audits/2006-preflight-partial/AUDIT_SOURCE_AND_CONFLICTS.md)
- [补丁差异](audits/2006-preflight-partial/PATCH_DIFF.md)
- [1000条合成训练路径的实际结果](audits/2006-preflight-partial/BASELINE_GROWTH_AUDIT.md)
- [轻量化实验](audits/2006-preflight-partial/lightweight/LIGHTWEIGHT_PROBE.md)

已验证此前V1.18的549文件SHA，377项原测试通过。签位身份与赛事上下文/组末伤病候选补丁在独立副本合并后377项回归再次通过，另16项补丁测试通过。原源码未改。

1000条合成训练核心路径完成，但不包含实际2006主角卡或World伤病/退出。轻量运行实验从27.6MB降至1.32MB，规则与同种子结果保持一致；该EXPERIMENTAL旧基线包仍为2005起点，不能代替当前年末存档。

开罗首版3:4负松平健太为用户锁定结果；未用重赛验证。2005/2006负场差一、完整43/P6/XP与伤病状态仍待原件。两个年末/开局JSON只是restorable=false缺口诊断。

此前[V1.18完整发布](downloads/v1.18/README_DOWNLOAD_ZH.md)保留；此分支仅保存预审材料，不冒充已完成的新历史整合版。
