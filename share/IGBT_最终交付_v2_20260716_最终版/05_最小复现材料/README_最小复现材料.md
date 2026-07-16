# 最小复现材料

本目录只提供 7 个 IGBT 主案的小型输入、只读汇总脚本和自动核心租约包装器；不含 MOSFET 主输入、重复的 GZP、TDR/PLT/SAV、完整日志、许可证或凭据。最终 GZP 位于 `../01_IGBT可继续仿真工程/`。

## 已验证的只读复算

```powershell
python scripts\summarize_igbt_mosfet_seb_campaign.py
python scripts\validate_ai_tcad_paper_materials.py
```

仓库侧 `package_igbt_delivery_v2.py` 复制已验证的最终 GZP 和小型脱敏材料，不构建 GZP、不调用 SDevice。随包提供的 `scripts/verify_delivery_v2.py` 执行 ZIP CRC、解压后二次哈希、清单、相对链接与包内 GZP 结构核验。

## 获授权 VM 上的继续运行

1. 先按 `../01_IGBT可继续仿真工程/README_可继续仿真工程.md` 解包并核对 GZP 身份；
2. 将 `scripts/run_igbt_seb_case_脱敏.ps1` 复制到仓库 `scripts/`，并通过参数显式提供授权的 `-VmUserHost`、`-RemoteRunRoot`、`-SentaurusRoot`、`-LocalRunRoot`；
3. 用 `-Threads 1` 和 `-CorePolicyPath` 启动新的独立 attempt；网格、DC restart、瞬态必须串行。

本材料不授权分发 Synopsys 软件或受限产物。MOSFET 仅在 03 附录提供；低 LET 仅 diagnostic_only/MESH_SENSITIVE；650 V redesign 仍 PENDING。
