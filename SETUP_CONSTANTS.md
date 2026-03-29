# Setup Constants

## Setup Sections

### Analyzed Sections
Sections processed by specialist agents (all except those in "Skipped"):

`GENERAL`, `FRONTWING`, `REARWING`, `BODYAERO`, `SUSPENSION`, `CONTROLS`, `ENGINE`, `DRIVELINE`, `FRONTLEFT`, `FRONTRIGHT`, `REARLEFT`, `REARRIGHT`, `AERODYNAMICS`, `TIRES`

### Skipped Sections
Always excluded from analysis:

`BASIC`, `LEFTFENDER`, `RIGHTFENDER`

### Tire/Suspension Group
Sections analyzed as related for cross-reference:

`FRONTLEFT`, `FRONTRIGHT`, `REARLEFT`, `REARRIGHT`, `SUSPENSION`

## Parameter Types

### Discrete (Integer-Only) Parameters
Only integer values allowed when recommending changes:

`FuelSetting`, `BrakeDuctSetting`, `RadiatorSetting`, `BoostSetting`, `RevLimitSetting`, `EngineBrakeSetting`

### Continuous (Decimal-Allowed) Parameters
Float values permitted:

`CamberSetting`, `ToeSetting`, `PressureSetting`, `SpringSetting`, `PackerSetting`, `SlowBumpSetting`, `SlowReboundSetting`, `FastBumpSetting`, `FastReboundSetting`, `RideHeightSetting`

### Gear Parameters (Excluded from Analysis)
Parameters starting with `Gear` and containing `Setting` are filtered out of all agent analysis.

## Fixed Parameters (Default Set)

These parameters are excluded from AI modification recommendations by default. The user can change this list at runtime via the Streamlit UI. Current defaults in `app/core/fixed_params.json`:

```
PressureSetting, Ride, Pitstop3Setting, ReverseSetting, RevLimitSetting,
Gearing, ElectricMotorMapSetting, FinalDriveSetting, BrakePadSetting,
RearWheelTrackSetting, Push2PassMapSetting, EngineBoostSetting,
Pitstop2Setting, FrontTireCompoundSetting, Custom, RearTireCompoundSetting,
CGRightSetting, FrontWheelTrackSetting, CGRearSetting, RatioSetSetting,
EngineMixtureSetting, Balance, RegenerationMapSetting, FuelSetting,
Pitstop1Setting, NumPitstopsSetting, Downforce
```

## Telemetry Channel Priority

Columns used for AI analysis, in priority order (first 100 used if available):

```
Lap Number, Lap Distance, Ground Speed, Throttle Pos, Brake Pos,
Steering, Engine RPM, Gear, G Force Lat, G Force Long,
Fuel Level, Tyre Wear FL/FR/RL/RR, Tyre Pressure FL/FR/RL/RR,
Tyre Temp {FL/FR/RL/RR} {Inner/Centre/Outer},
Ride Height FL/FR/RL/RR, Susp Pos FL/FR/RL/RR,
Grip Fract FL/FR/RL/RR, Tyre Load FL/FR/RL/RR,
Front Downforce, Rear Downforce, Drag,
Brake Temp FL/FR/RL/RR, Body Pitch, Body Roll,
Camber FL/FR/RL/RR, Min Corner Speed, Max Straight Speed, Delta Best
```
