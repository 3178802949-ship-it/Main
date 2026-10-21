# 旋球年代 V1.1.7 测试候选

从 [中文开幕文档](OPENING_V117_ZH.md) 和 [当前版本说明](README_V117_ZH.md) 开始。
规则、实测结果与未通过项见 [设计说明](docs/V117_DESIGN_ZH.md) 和
[技术报告](docs/V117_TECHNICAL_REPORT_ZH.md)。

```bash
python verify_package.py
python examples/start_v117.py --output saves/my_career
python examples/start_v117.py --output saves/month_demo --demo
python run_v117_qa.py --output checks/my_qa
```

详细主场示例另加 `--full-match`。常规生涯使用 `world_v117.WorldSession`；
它统一管理训练、比赛、时间、负荷、资源、排名与存档。旧V1.1.6/HGR文档、
源码与实验为兼容性档案，不能当作本版本的新验收证据或重复领取的规则。
