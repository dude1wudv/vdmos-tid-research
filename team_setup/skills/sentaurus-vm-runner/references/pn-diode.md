# PN diode reference

## Source case

Official case:

```text
/usr/synopsys/sentaurus/W-2024.09/tcad/W-2024.09/Applications_Library/GettingStarted/sdevice/3Ddiode_demo
```

Files of interest:

- `sde_dvs.cmd`: creates a 1 x 1 x 10 silicon cuboid, top/bottom contacts, Gaussian boron/phosphorus profiles, and `n@node@_msh.tdr` mesh.
- `sdevice_des.cmd`: Workbench-tokenized deck. For direct CLI runs, replace `@tdr@`, `@plot@`, `@tdrdat@`, `@log@`, `@bias@`, and `@previous@` or generate plain `forward.cmd` / `reverse.cmd` decks.
- `svisual_vis.tcl`: plots `top InnerVoltage` vs `top TotalCurrent` from `.plt`.

## Direct-run sequence

```bash
export PATH=/usr/synopsys/sentaurus/W-2024.09/bin:/usr/synopsys/scl/scl2023/linux64/bin:$PATH
sde -e -l sde_direct.cmd
sdevice forward.cmd
sdevice reverse.cmd
```

Expected outputs:

- Mesh: `n1_msh.tdr`
- Forward IV: `forward.plt`, `forward.tdr`, `forward_stdout.log`
- Reverse IV: `reverse.plt`, `reverse.tdr`, `reverse_stdout.log`
- Summary: `SUMMARY.txt`

Known final points from the first successful run on this VM:

```text
Forward top total current at 10 V: 2.628E-02 A
Reverse top total current at -1000 V outer bias: -8.987E-05 A
```

## License recovery

Symptom:

```text
The desired vendor daemon is down.
Feature: SK_swb_all
FlexNet Licensing error:-97,121
```

Recovery:

```bash
export PATH=/usr/synopsys/scl/scl2023/linux64/bin:$PATH
lmutil lmreread -c /usr/synopsys/scl/scl2023/synopsys.dat
lmutil lmstat -a -c 27000@sentaurus | head -80
```

A healthy status includes:

```text
snpslmd: UP
```