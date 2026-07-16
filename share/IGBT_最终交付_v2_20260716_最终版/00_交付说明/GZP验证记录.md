# 最终 IGBT GZP 验证记录

- 包内文件：`../01_IGBT可继续仿真工程/IGBT_SEB_20260714_Final_Continuation.gzp`。
- SHA-256：`30a49adba4b5e50b823e39d98f84915f4a02462044c33269f1280831bd0ffa2c`
- 大小：`10494473 bytes`
- 内部身份：`IGBT_SEB_20260714_Final_Continuation / 7-case IGBT continuation Workbench project`。
- 验证等级：`PACK_UNPACK_WORKBENCH_OPEN_SVISUAL_VIEW_EXTRACT`。
- 直接证据：gzip EOF 与 tar 结构 PASS；全新目录 `swbunpack` = PASS；Workbench W-2024.09 可编辑打开 = PASS；SVisual 查看 = PASS；SVisual 提取 = PASS。
- 打包后 SDevice 重跑：`NOT_RERUN_AFTER_PACKAGING`。

**关系声明：**该工程通过内嵌 7 案 run index、package manifest 和冻结产物哈希绑定 20260714 IGBT 正式事实源。它包含结构、热 restart、HeavyIon、查看和提取节点，可作为后续获授权仿真的起点；本次交付收口没有额外启动 SDevice，因此不把“可继续”写成打包后已重跑。
