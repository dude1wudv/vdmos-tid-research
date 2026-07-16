File {
  Grid = "igbt_baseline_msh.tdr"
  Parameters = "sdevice.par"
  Plot = "IGBT_T298_V575_L15_dc"
  Current = "IGBT_T298_V575_L15_dc.plt"
  Output = "IGBT_T298_V575_L15_dc.log"
}
Electrode {
  { Name="Gate" Voltage=0 }
  { Name="Emitter" Voltage=0 }
  { Name="Collector" Voltage=0 }
}
Thermode {
  { Name="Gate" Temperature=298.15 }
  { Name="Emitter" Temperature=298.15 }
  { Name="Collector" Temperature=298.15 }
}
Physics {
  Temperature=298.15
  EffectiveIntrinsicDensity(BandGapNarrowing(Slotboom))
  Thermodynamic
  AnalyticTEP
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
  AvalancheGeneration eAvalancheGeneration hAvalancheGeneration
  Doping DonorConcentration AcceptorConcentration
}
Math {
  Extrapolate Notdamped=50 Iterations=25 ExitOnFailure
  Digits=5 ErrRef(electron)=1e10 ErrRef(hole)=1e10
}
Solve {
  Poisson
  Coupled { Poisson Electron Hole }
  Quasistationary(
    InitialStep=1e-3 Increment=1.5 Decrement=2
    MinStep=1e-9 MaxStep=0.05
    Goal { Name=Collector Voltage=575 }
  ) { Coupled { Poisson Electron Hole Temperature } }
  Save(FilePrefix="IGBT_T298_V575_L15_restart")
  Plot(FilePrefix="IGBT_T298_V575_L15_dc_pre" NoOverwrite)
}
