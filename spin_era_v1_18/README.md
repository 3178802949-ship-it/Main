# 《旋球年代》V1.18 综合修订版

先读 [README_V1_18_ZH.md](README_V1_18_ZH.md)，新聊天使用 [OPENING_V1_18_ZH.md](OPENING_V1_18_ZH.md)。
公开入口：`from simulator import WorldSession, Card, Game, Training, Area, Narrative`。

本轮修复共享时钟、比赛事务、正式XP、奖励兑换、BO3/5/7及小组规则，并加入可关闭的反扑实验与身体疲劳修复。2004原件、23场赛果、CA150/PA191保持，继承状态另建2005新分支。

规则：`V1.18-1`。旧`v118`文件属于冻结V1.1.7依赖，新实现为`v1_18`。请勿按相近文件名混用接口。
Python3.11+，只需标准库。校验：`python verify_package.py`；测试：`python self_test.py`。
验收、模型限制和回滚见 [设计与QA](docs/v1_18/DESIGN_AND_QA_ZH.md) 与 [回滚说明](docs/v1_18/ROLLBACK.md)。
