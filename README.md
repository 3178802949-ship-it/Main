# 旋球年代｜V1.1.6 HGR 技术补丁候选

当前分支提供左右手几何、双面胶皮与专业削球增量补丁；保持原能力公式和旧存档规则。

- [下载目录](downloads/v1.1.6-hgr-candidate)：候选总包、开幕文档、技术报告与包装验证。
- [源码与运行说明](spin_era_hgr_candidate/README_ZH.md)。
- [审计与最小实施方案](spin_era_hgr_candidate/docs/HGR_AUDIT_PLAN_ZH.md)。
- [最终技术报告](spin_era_hgr_candidate/docs/HGR_TECHNICAL_REPORT_ZH.md)：机制、差异、兼容、实测结果与风险。
- [固定种子对照](spin_era_hgr_candidate/reports/hgr_patch/REGRESSION_REPORT_ZH.md)：4组×32种子×新旧=256场BO7。
- [旧版下载](downloads/v1.1.6)：保留原整合包。

Python3.11+，仅标准库：进入源码目录执行`python verify_package.py`、`python self_test.py`。新规则必须显式使用Game.PATCH_RULESET；缺省调用和旧存档继续旧算法。

154项检查通过，34个受保护基线文件保持原字节，新旧完整演示及续跑一致。该状态不是现实历史胜率或总体竞技平衡认证。完整边界以技术报告为准。
