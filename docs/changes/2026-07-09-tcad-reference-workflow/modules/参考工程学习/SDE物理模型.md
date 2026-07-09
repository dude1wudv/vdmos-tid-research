上级：[[_参考工程学习]]
下级：无
依赖：[[工程包识别]]
---

# SDE 物理模型

参考工程中的 SDE 模型包括：

- Silicon 区域：`sub`、`epi`、`pbody`。
- Oxide 区域：`gox1`、`gox2`。
- PolySi 栅：`gatepoly`。
- Aluminum 源极金属：`A1`、`A2`。
- 接触：`gate`、`source`、`drain`。
- 掺杂：衬底、外延、P-body、P+、N+、多晶硅。
- 网格：全局区域 + Oxide/Silicon 界面加密。

新芯片建模时优先复用这个结构拆法，但尺寸、掺杂和 `AreaFactor` 必须按新芯片文档重定。