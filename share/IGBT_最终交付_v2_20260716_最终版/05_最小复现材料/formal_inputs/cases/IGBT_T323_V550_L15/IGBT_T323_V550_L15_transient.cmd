File {
  Grid = "igbt_baseline_msh.tdr"
  Parameters = "sdevice.par"
  Plot = "IGBT_T323_V550_L15_tr"
  Current = "IGBT_T323_V550_L15_tr.plt"
  Output = "IGBT_T323_V550_L15_tr.log"
}
Electrode {
  { Name="Gate" Voltage=0 }
  { Name="Emitter" Voltage=0 }
  { Name="Collector" Voltage=0 }
}
Thermode {
  { Name="Gate" Temperature=323.15 }
  { Name="Emitter" Temperature=323.15 }
  { Name="Collector" Temperature=323.15 }
}
Physics {
  Temperature=323.15
  EffectiveIntrinsicDensity(BandGapNarrowing(Slotboom))
  Thermodynamic
  AnalyticTEP
  HeavyIon(
    StartPoint=(0 3.5) Direction=(1 0) Length=50 Time=1e-10
    LET_f=0.1555 Wt_hi=0.1 Gaussian PicoCoulomb
  )
}
Physics(Material="Silicon") {
  Mobility(DopingDep HighFieldSaturation)
  Recombination(SRH(DopingDependence TempDependence) Auger Avalanche(Lackner))
}
Plot {
  eDensity hDensity
  eMobility hMobility
  TotalCurrent/Vector eCurrent/Vector hCurrent/Vector
  ElectricField/Vector Potential SpaceCharge
  Temperature JouleHeat TotalHeat
  HeavyIonGeneration HeavyIonChargeDensity
  AvalancheGeneration eAvalancheGeneration hAvalancheGeneration
  Doping DonorConcentration AcceptorConcentration
}
Math {
  Extrapolate Transient=BE Notdamped=50 Iterations=25 ExitOnFailure
  Digits=5 ErrRef(electron)=1e10 ErrRef(hole)=1e10
  BreakCriteria { LatticeTemperature(MaxVal=2500) }
}
Solve {
  Load(FilePrefix="IGBT_T323_V550_L15_restart")
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_pre" NoOverwrite)
  NewCurrentPrefix="IGBT_T323_V550_L15_tr_transient_"
  Transient(InitialTime=0 FinalTime=9.2e-11 InitialStep=1e-13 Increment=1.5 Decrement=2 MinStep=1e-17 MaxStep=1e-11) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_092ps" NoOverwrite)
  Transient(InitialTime=9.2e-11 FinalTime=9.4e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_094ps" NoOverwrite)
  Transient(InitialTime=9.4e-11 FinalTime=9.6e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_096ps" NoOverwrite)
  Transient(InitialTime=9.6e-11 FinalTime=9.7e-11 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_097ps" NoOverwrite)
  Transient(InitialTime=9.7e-11 FinalTime=9.8e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_098ps" NoOverwrite)
  Transient(InitialTime=9.8e-11 FinalTime=9.9e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_099ps" NoOverwrite)
  Transient(InitialTime=9.9e-11 FinalTime=9.95e-11 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_099p5ps" NoOverwrite)
  Transient(InitialTime=9.95e-11 FinalTime=1e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_100ps" NoOverwrite)
  Transient(InitialTime=1e-10 FinalTime=1.002e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_100p2ps" NoOverwrite)
  Transient(InitialTime=1.002e-10 FinalTime=1.005e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_100p5ps" NoOverwrite)
  Transient(InitialTime=1.005e-10 FinalTime=1.01e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_101ps" NoOverwrite)
  Transient(InitialTime=1.01e-10 FinalTime=1.02e-10 InitialStep=2e-13 Increment=1.0 Decrement=2 MinStep=1e-17 MaxStep=2e-13) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_102ps" NoOverwrite)
  Transient(InitialTime=1.02e-10 FinalTime=1.03e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_103ps" NoOverwrite)
  Transient(InitialTime=1.03e-10 FinalTime=1.04e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_104ps" NoOverwrite)
  Transient(InitialTime=1.04e-10 FinalTime=1.06e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_106ps" NoOverwrite)
  Transient(InitialTime=1.06e-10 FinalTime=1.08e-10 InitialStep=1e-12 Increment=1.4 Decrement=2 MinStep=1e-17 MaxStep=1e-12) {
    Coupled { Poisson Electron Hole Temperature }
  }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_audit_108ps" NoOverwrite)
  Transient(
    InitialTime=1.08e-10 FinalTime=2.1e-9
    InitialStep=2e-13 Increment=1.4 Decrement=2
    MinStep=1e-17 MaxStep=1e-10
  ) { Coupled { Poisson Electron Hole Temperature } }
  Plot(FilePrefix="IGBT_T323_V550_L15_tr_at2p1ns" NoOverwrite)
}
