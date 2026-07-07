用 academic-research-suite + pdf 精读下面这篇论文。

输入：{paper_path}

请输出到对应 `papers/*.md` 的 Analysis 区域，结构固定为：

1. 论文定位：器件背景 / TID 经典机理 / VDMOS TID 实验 / 模型方法
2. 器件类型：VDMOS、trench MOSFET、MOS capacitor、CMOS、其他
3. 辐照实验：辐照源、总剂量、剂量率、偏置条件、温度、退火条件
4. 测量指标：Vth、Id-Vg、leakage、mobility、subthreshold swing、Ron、breakdown
5. 机理归因：oxide trapped charge、interface traps、border traps、STI/field oxide/LOCOS、annealing
6. 关键图表：列出最值得复看的图号/表号和原因
7. 可复现实验流程：按步骤重构
8. 对 VDMOS 总剂量效应研究的价值：可借鉴点 + 局限
9. 术语表：中英对照
10. 可信度与待核查项
