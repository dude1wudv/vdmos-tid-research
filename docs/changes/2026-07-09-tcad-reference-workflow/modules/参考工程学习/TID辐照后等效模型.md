上级：[[_参考工程学习]]
下级：无
依赖：[[辐照前仿真]]
---

# TID 辐照后等效模型

参考工程用 Oxide/Silicon 界面陷阱模型表达 TID 效应：

```text
FixedCharge Conc = Not
Acceptor Conc    = Nit
```

经验含义：

- `Not`：固定正电荷，主要导致 n 型 VDMOS 阈值负漂移。
- `Nit`：Acceptor 型界面陷阱，可表现为补偿、亚阈/迁移率退化代理。

已归档的匹配点：`post_fit` 使用 `Not=2.7e11`、`Nit=1.4e11`，得到 `Vth≈1.333 V`。

高陷阱/高固定电荷 case 建议使用增强求解策略：先 Poisson/Coupled 稳态，再进入偏置 ramp 和 gate sweep。