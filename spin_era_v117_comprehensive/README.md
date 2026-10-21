# 《旋球年代》V1.1.7 综合版

**交接入口：[OPENING_COMPREHENSIVE_ZH.md](OPENING_COMPREHENSIVE_ZH.md)**  
使用说明：[README_COMPREHENSIVE_ZH.md](README_COMPREHENSIVE_ZH.md) · 常见问题：[docs/COMPREHENSIVE_QA_ZH.md](docs/COMPREHENSIVE_QA_ZH.md)

此版为有限时代生涯模拟的工作基准，规则 `V1.1.7-COMPREHENSIVE-1`，不是历史认证或正式1.0。
公开接口为 `from simulator import WorldSession, Card, Game, Training, Area, Narrative`。
内部 `v118` 文件名是本轮增量开发层的标记，不代表另发V1.1.8。
旧源码、旧测试、旧世界格式和原始数据保留；请勿把旧README、开幕文档或默认模块当作本版入口。

仅需Python 3.11+标准库。先校验：`python verify_package.py`。完整行为回归：`python self_test.py`。
