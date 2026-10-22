# V1.18回滚与逐步补丁

原始2004检查点保存在`data/v1_18/handoff2004/WORLD_2005_OPENING_ORIGINAL.json`，SHA256为`7418d87ab217b5423842a225de9298c0ef8a680945ff329132c5a7aca70d2ce5`。原引擎ZIP SHA256为`e1498d5cb658359f1361fd7459a7b6641b64eb2efc4ff2351efa22e813e50f1d`。

要完全回到原版，在独立目录解压未修改的V1.1.7综合版，再用其WorldSession读取原检查点。不能直接在本版中换成旧入口加载，因为公共门面已经更新且旧格式绑定原代码指纹。不要覆盖原件，不把V1.18的新XP、H2H或NPC推演结果写回旧世界。

迁移命令：`python examples/start_v1_18.py --from-2004 --output saves/new_v1_18`。脚本输出原件副本、迁移核对表、新起点和完整公开卡，默认不推进2005。再次输入已迁移状态不会重新授奖；不同对账输入会报冲突。

同一代码版本内可逐步更新配置：

```python
w.apply_patch('P005_OPT_IN_ANTI_SHUTOUT', enabled=True)
w.apply_patch('P005_OPT_IN_ANTI_SHUTOUT', enabled=False)
w.apply_patch('P006_PHYSICAL_FATIGUE', enabled=False)  # 仅兼容对照
```

结构补丁P001—P004不能在V1.18格式里关闭。可选开关不改变过去赛果；重复同配置返回already_applied。关闭身体修复和反扑时，Game的旧BO7比较可复现原版比分、逐分与曝光/负荷；这不表示新World可伪装为旧格式。

以后增加代码补丁，应登记新ID和依赖、保留父检查点与父指纹，提供明确源版本到目标版本的转换及dry-run，再运行回归。当前适配器只承诺已实现的V1.1.7综合版→V1.18路径，不承诺任意未来源码可自动兼容旧存档。

保存用`w.save(path)`；覆盖须显式`overwrite=True`，会保留有效`.bak`。恢复备份须显式`WorldSession.load_file(path,recover_backup=True)`，避免无提示倒退世界时间。
