# 实际源码入口图｜可读的V1.18基线

不是新上传2004—2006包的认证地图。源码根为前轮发布spin_era_v1_18。

```mermaid
flowchart TD
  A[simulator.py公开入口] --> W[world_v1_18.WorldSession]
  W --> X[world_extensions_v1_18.WorldExtensions]
  W --> T[Training/v1_18.py正式XP与奖励]
  T --> TC[Training/v118.py冻结半月核心]
  TC --> C[runtime/career_v118.py身体支持与年龄]
  X --> G[Game/v1_18.py卡投影与子进程]
  G --> GW[Game/worker_v1_18.py]
  GW --> F[Game/engine_v1_18.py逐板]
  GW --> L[Game/light_v1_18.py逐分聚合]
  X --> R[Card/__init__.py RankingBook]
  W --> A2[Area/v1_18.py赛历]
```

- 世界比赛输入：world_v1_18.py:307的_match_card；身体支持由Training.performance_card给出。
- 外部结算：world_extensions_v1_18.py:194的settle_match；内部总账事务在:132的_settle_inplace。实际起始行以源码rg为准，补丁后可能移动。
- 旧签表整场运行：world_v1_18.py:532的run_event；不是逐轮待授权会话。
- 小组：world_extensions_v1_18.py:289的run_group；积分与H2H经统一事务，原版组末伤病延期未收口。
- 计分验证：Game/formats_v1_18.py；身份签位替换与小组表：Game/competition_v1_18.py。
- 公开榜：Card/__init__.py:382的world_ranking，当前只计算adult，不可调用它假称青年年终榜。

详细数值链与实际探针见BASELINE_MATCH_STATE_AUDIT.md、BASELINE_GROWTH_AUDIT.md。轻量模式没有逐板事实，不应用其聚合输出编造指定球路。
