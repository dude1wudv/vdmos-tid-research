# Total Ionizing Dose Effects in MOS Oxides and Devices Reading Notes

## Bibliographic Info

- **Title:** Total Ionizing Dose Effects in MOS Oxides and Devices
- **Authors:** T. R. Oldham; F. B. McLean
- **Venue:** IEEE Transactions on Nuclear Science, Vol. 50, No. 3
- **Date:** June 2003
- **DOI:** 10.1109/TNS.2003.812927
- **Local PDF:** `01_seed_papers/02_tid_foundation/Oldham_McLean_2003_Total_Ionizing_Dose_Effects_in_MOS.pdf`

## One-line Takeaway

This review explains TID effects in MOS systems as a chain of oxide charge generation, recombination, hole transport, trapping/detrapping, and interface-trap formation, then connects these mechanisms to device/circuit failure and hardness assurance.

## Section Notes

### 2026-07-07 — Abstract, Introduction, and start of Overview

**Focus:** Establish what problem the paper is solving and the four-process framework used to understand MOS TID response.

**Paper says:** Ionizing radiation affects MOS oxides through charge generation, transport, trapping/detrapping, and interface-trap formation. In an n-channel MOSFET, radiation-induced positive trapped charge in the gate oxide can shift threshold voltage enough that the transistor cannot turn off at zero gate bias, i.e. it goes depletion mode.

**Key structure:** The paper frames the apparently complex radiation response as separable components with different time scales, electric-field dependence, temperature dependence, and processing dependence.

**Evidence:** p. 483, Abstract, Introduction, Fig. 1 discussion; p. 483-484, Overview.

**Follow-up:** Read the four physical processes in the Overview carefully before diving into equations and generation/yield details.

## Concepts / Terms

- **TID (Total Ionizing Dose):** Accumulated ionizing-radiation exposure; in MOS oxides it mainly matters because deposited energy creates electron-hole pairs and downstream trapped/interface charge.
- **Threshold-voltage shift:** Change in gate voltage required to turn a MOS transistor on/off; central observable for MOS radiation damage.
- **Depletion-mode failure:** For the nMOS example here, trapped oxide charge shifts threshold so much that the device remains on even at zero applied gate voltage.
- **Gate oxide / SiO2:** Radiation-sensitive insulating layer in MOS structures.

## Questions & Answers

## Methods / Evidence

- The first two pages are review/schematic rather than new experimental data. Fig. 1 illustrates device-level failure; Fig. 2/3 provide a conceptual process/time framework.

## Figures & Tables

- **Fig. 1:** Normal n-channel MOSFET vs. post-irradiation device with trapped positive oxide charge causing threshold shift.
- **Fig. 2:** MOS energy-band schematic showing the major radiation-response processes.
- **Fig. 3:** Schematic time-dependent post-irradiation threshold-voltage recovery, linking time regions to physical mechanisms.

## Open Questions

- How do oxide thickness, electric field, temperature, and processing separately affect each mechanism?
- In VDMOS/power MOS contexts, which parts map directly to gate oxide vs. field oxide / isolation oxide damage?

## Running Glossary

- **NSREC:** Nuclear and Space Radiation Effects Conference.
- **CMOS:** Complementary MOS technology.
- **Si/SiO2 interface:** Boundary where interface traps form and strongly affect threshold voltage.


### 2026-07-07 — Overview 收尾与初始产额框架

**Focus:** 理解四个 TID 物理过程如何控制阈值电压随时间变化，并进入电子-空穴对产生能与初始空穴产额。

**Paper says:** MOS TID response includes: electron-hole pair generation/recombination, hole transport to the Si/SiO2 interface, long-lived hole trapping near the interface, and radiation-induced interface-trap buildup. Electron-hole pair generation energy sets the initial charge-pair density per dose, but initial recombination quickly reduces the surviving hole population.

**Answer / interpretation:** 初始空穴产额不是固定常数，而取决于电场和辐射 LET。电场帮助分离电子/空穴，提高幸存空穴比例；LET 越高，电荷对越密，复合越强，幸存空穴比例可能越低。

**Evidence:** p. 484-485, Overview, III.A, III.B opening.

**Follow-up:** 继续读 III.B 的 geminate recombination 和 columnar recombination，两者分别对应低线密度和高线密度辐射情形。
