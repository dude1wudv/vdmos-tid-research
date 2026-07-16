File {
  Grid = "@MESH_LEAF@"
  Parameters = "sdevice.par"
  Plot = "@PREFIX@"
  Current = "@PREFIX@.plt"
  Output = "@PREFIX@.log"
}
Electrode {
  { Name="Gate" Voltage=0 }
  { Name="Emitter" Voltage=0 }
  { Name="@HIGH_CONTACT@" Voltage=0 }
}
Thermode {
  { Name="Gate" Temperature=@TEMPERATURE_K@ }
  { Name="Emitter" Temperature=@TEMPERATURE_K@ }
  { Name="@HIGH_CONTACT@" Temperature=@TEMPERATURE_K@ }
}
Physics {
  Temperature=@TEMPERATURE_K@
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
    Goal { Name=@HIGH_CONTACT@ Voltage=@TARGET_VOLTAGE_V@ }
  ) { Coupled { Poisson Electron Hole Temperature } }
  Save(FilePrefix="@RESTART_PREFIX@")
  Plot(FilePrefix="@PREFIX@_pre" NoOverwrite)
}