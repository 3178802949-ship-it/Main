# 源码审计、独立补丁与精简试验｜PARTIAL

本包不是2006年末可继续游玩的新版整合包。新完整历史ZIP超过工具32MiB传输上限，尚未读取根任务书、SOURCE_MANIFEST及新历史。先看INPUT_UPLOAD_GUIDE_ZH.md补齐材料。

已实际完成的源验证、两项独立源码补丁、测试和1000训练路径实验见WHAT_IS_DONE.md与TEST_REPORT.md。原引擎549文件未改；两个补丁的独立组合副本通过原377项回归，另16项补丁测试通过。没有运行2007正式比赛，也没有重抽开罗决赛。

WORLDLINE_CANON.json与START_2007_PRESEASON.json均是restorable=false的缺口诊断，严禁当存档加载。历年负场差一尚未凭收据解决，完整43项/P6/XP/伤病缺失，不造数据填满。

lightweight/result中的1.32MB ZIP是EXPERIMENTAL旧V1.18分发试验，起点仍2005-01-01、未整合2006历史，也未包含本次候选补丁。只证明分离证据可大幅精简，不推荐用它代替当前年末存档。原始全量档案必须保留。

补丁只对明确匹配旧SHA的独立副本应用，默认dry-run。应用后指纹改变，旧检查点按设计拒绝；必须在真实历史可读后写显式迁移适配器。不要手改指纹，也不要把修复后的候选冒充旧封存引擎。

RELEASE_MANIFEST_SHA256.json校验本阶段交付文件，不能替代尚未读取的用户原SOURCE_MANIFEST。
