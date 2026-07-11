# IGBT 与 MOSFET 高场位置对比仿真计划

  ## 摘要

  创建单一 plan-docs 计划文档：

  docs/changes/2026-07-10-igbt-mosfet-field-comparison/01-对
  比仿真计划.md

  目标是先完成当前 IGBT 四温度基线，再建立仅改变底部集电区极
  性的 MOSFET 对照，比较两类器件的最大电场、最大总电流密度及
  其到栅氧化层的距离。计划同时覆盖可复算数据包、实验报告图和
  PPT 精简图，不预设“MOSFET 不适合大功率”为必然结论。

  ## 模型与实验矩阵

  - IGBT 使用当前 /home/tcad/STDB/VDMOS_TID_IGBT，完成后冻结
    实际运行 deck 和网格。

  - MOSFET 项目命名为 /home/tcad/STDB/VDMOS_TID_MOSFET，从已
    验证 IGBT 工程复制：
      - 保留沟槽、栅氧、n+ emitter/source、p-body、440 µm n-
        drift、5 µm n-buffer、网格和接触位置。

      - 仅将底部 0.5 µm、5e19 cm^-3 p+ collector 改为同浓度
        n+ drain。

      - Collector 接触改名为 Drain，其他物理模型和求解参数保
        持一致。

  - 两类器件统一运行 -30、25、50、70 °C，即 243.15、298.15、
    323.15、343.15 K。

  - 每个温度先扫描 0–4.5 kV；若未获得 BV，后续按 500 V 递增
    上限，最多扩展至 6 kV。

  - 比较口径：
      1. 相同应力：4.5 kV。
      2. 归一化应力：各器件、各温度自身 90% BV。
      3. 若 6 kV 内仍无击穿拐点，标记 BV_NOT_FOUND，不生成虚
         构的 90% BV 数据。

  ## 数据与图像产物

  - 每个 case 保存实际 .cmd、mesh/final .tdr、.plt、.log 和
    参数快照；运行副本归档至 /home/tcad/codex_runs/
    igbt_mosfet_compare_<timestamp>/。

  - 用 Sentaurus Visual Tcl 批量导出，GUI 只负责最终抽查；
    IGBT/MOSFET 使用相同坐标范围、色标、视角和图片尺寸。

  - 汇总 CSV 固定字段：
      - device、temp_c、bias_mode、voltage_v、bv_v、status
      - e_max_v_cm、e_x_um、e_y_um、
        e_distance_to_gate_oxide_um

      - j_max_a_cm2、j_x_um、j_y_um、
        j_distance_to_gate_oxide_um

      - tmax_k、run_dir、tdr_file、log_file

      5. 从栅氧界面进入漂移区的电场和电流密度线剖面。
      6. 峰值到栅氧距离的温度折线图/柱状图。
      7. 必要时附 avalanche generation 和 lattice
         temperature 诊断图。

  - PPT 版只保留 25 °C 结构图、4.5 kV 对比图、90% BV 对比
    图、距离汇总图和一页结论；其余温度放附录。

  ## 执行顺序与验收

  1. 完成并冻结 IGBT 四温度运行，确认所有 case 的日志、BV 曲
     线和最终 .tdr 可读。

  2. 从冻结的 IGBT 工程生成 MOSFET 对照，只修改底部极性和接
     触命名。

  3. 先跑 25 °C MOSFET 网格和 4.5 kV smoke case；通过后展开
     四温度矩阵。

  4. 执行独立 BV 提取，再生成 4.5 kV 与 90% BV 两套场分布。
  5. 批量提取峰值坐标，并计算到最近 R.Si/R.Gox
     界面的欧氏距离。

  6. 核对 CSV、曲线、图像与原始 .tdr/.log 能相互追溯。
  7. 只有在两种比较口径下均显示稳定、可重复的距离差异时，才
     支持结构性结论；否则报告为“当前模型未验证该假设”或“差异
     仅在特定温度/偏置成立”。

  ## 假设与边界

  - 这是同尺寸、同漂移区的受控 TCAD 对照，不代表所有 IGBT 与
    所有 MOSFET。

  - 本轮不加入 TID、重离子、界面陷阱或工艺统计。
  - “大功率适用性”不能仅由一个峰值距离决定；最终结论同时报告
    BV、峰值场、峰值电流密度和位置，不延伸到成本、开关损耗或
    实际封装能力。

  - 按 Ponytail 最小化处理：只生成一个计划文档；微观模块树和
    workflow 交接包等真正开始批量执行时再补。