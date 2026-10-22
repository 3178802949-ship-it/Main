# V1.18模块边界

```mermaid
flowchart TD
  A[原始检查点与外部回执] --> B[migration_v1_18: 源校验与新世界线]
  B --> W[simulator.WorldSession]
  W --> C[Card: 43/P6/G9/CA与身份]
  W --> E[Area: 时代/赛历/赛制声明]
  W --> G[Game: 独立进程比赛]
  G --> R[带输入快照与哈希的收据]
  R --> S[World统一MatchSettlement事务]
  S --> X[Training: 共用XP/成本/许可/上限]
  S --> H[日期/疲劳/伤病/H2H/积分]
  W --> N[Narrative: 只读事实与后台写作提示]
  W --> P[原子存档与可选外置全文]
```

`WorldExtensions._settle_inplace`是唯一现代比赛入账管。直接收据走`settle_match`，自带模拟的练习/赛事/小组也调用同一管。训练不直接读取文学叙述加点；观赛和奖励必须有已知来源或已登记凭证。

CA由冻结的`card_training_v112.compute_card`及身体支持后的表现值汇总，不在逐分模型中直接指定赢家。比赛学习的挑战估计可以参考对手CA；这与把CA直接变成单分胜率是不同用途。

`Game/formats_v1_18`统一11分、净胜2分、先赢局数和服务次序；`competition_v1_18`处理小表和签位证据。两种比赛引擎共享技术与战术依赖，summary仍是聚合近似，不能伪装成逐板全文。

数值训练核心沿用冻结V1.1.7；`Training/v1_18`添加来源去重、比赛XP、奖励预算与银行守恒检查。旧模块标识保留用于追溯，所有新生涯调用公开`simulator`入口。
