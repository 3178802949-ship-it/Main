# 《旋球年代》V1.18

本版将球员时钟、比赛入账与奖励兑换接入统一生涯事务，补齐BO3/BO5/BO7、日程约束、身体疲劳输出、观赛与赛事奖励、原子保存和可审计补丁。保留2004原档，提供2005继承起点。

- [下载总包、四个分包与交接文档](downloads/v1.18/README_DOWNLOAD_ZH.md)
- [完整总包ZIP](downloads/v1.18/Spin_Era_V1_18_Integrated.zip)
- [新聊天开幕文档](downloads/v1.18/OPENING_V1_18_ZH.md)
- [设计评价、奖励范围和保留问题](downloads/v1.18/DESIGN_AND_QA_ZH.md)
- [功能QA](downloads/v1.18/V1_18_QA.json) · [分发件解包验收](downloads/v1.18/V1_18_PACKAGING_VERIFICATION.json)

GitHub网页版打开ZIP后，点右上角 **Download raw file** 下载箭头。通常只需总包和开幕文档，一起上传新聊天。

377项功能测试全部通过，44,000场实际比赛压力测试完成。另有长期推进至2028年的World续接测试。2005开局仍是CA150、PA191、疲劳0、2004年14胜9负；23场旧赛果没有重赛，26.34XP进入银行，两张观赛凭证待兑换。

反扑实验默认关闭；身体疲劳修复默认开启。极端能力差距、专业打法轻量校准及高潜力兑现仍有报告中列明的限制，不作为现实概率认证。

Python3.11+，仅标准库：

```bash
cd spin_era_v1_18
python verify_package.py
python self_test.py
python examples/start_v1_18.py --from-2004 --output saves/new
```

公开入口：`from simulator import WorldSession, Card, Game, Training, Area, Narrative`。存档绑定规则和来源指纹；源代码升级使用迁移适配器，不手改指纹。

此前[V1.1.7综合版](downloads/v1.1.7-comprehensive/README_DOWNLOAD_ZH.md)及其源码保持可用，回滚遵循[说明](downloads/v1.18/ROLLBACK.md)。
