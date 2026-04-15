# rFactor 2 Parameter Guide — Knowledge Base

## .svm File Format

rFactor 2 vehicle setups use the `.svm` (Setup Vehicle Modifier) file format:

- Plain text, INI-style sections: `[SectionName]`
- Parameters as `Key=Value` with optional `//comment`
- Some parameters are **read-only** (commented out); these represent hardware constraints that cannot be changed in-game.
- Values may use click indices internally, but external tools should present **physical units**.

## Section Names (Internal)

The following section names are used in `.svm` files and throughout the pipeline:

| Section | Description | Typical Parameters |
|---------|-------------|-------------------|
| FRONTLEFT | Front left corner | CamberSetting, PressureSetting, SpringRate, RideHeightSetting, SlowBumpSetting, SlowReboundSetting, FastBumpSetting, FastReboundSetting, ToeSetting |
| FRONTRIGHT | Front right corner | Same as FRONTLEFT (axle pair) |
| REARLEFT | Rear left corner | Same as FRONTLEFT with rear-specific ranges |
| REARRIGHT | Rear right corner | Same as REARLEFT (axle pair) |
| FRONTWING | Front aerodynamic surfaces | FlapSetting |
| REARWING | Rear aerodynamic surfaces | FlapSetting |
| SUSPENSION | Chassis-level suspension | FrontAntiRollBarSetting, RearAntiRollBarSetting, FrontHeaveSpringRate, RearHeaveSpringRate |
| GENERAL | General vehicle settings | BrakeBiasSetting, BrakeDuctSetting, FuelSetting |
| CONTROLS | Driver controls | DiffLockSetting, DiffPreloadSetting, TractionControlSetting |
| BODYAERO | Body aerodynamic settings | FrontBodyHeightSetting, RearBodyHeightSetting |
| ENGINE | Engine parameters | BoostSetting, EngineMixtureSetting |
| DRIVELINE | Drivetrain | GearRatios, FinalDriveRatio |
| TIRES | Tire selection | CompoundSetting |
| AERODYNAMICS | General aero | Various aero-related settings |

## Value Format: Physical Units Policy

All setup recommendations must use **physical units**, never click indices:

| Parameter Type | Unit | Example |
|---------------|------|---------|
| Pressure | kPa | `172.4 kPa` |
| Camber | deg | `-3.2 deg` |
| Toe | deg | `0.10 deg` |
| Spring rate | N/mm | `145 N/mm` |
| Ride height | mm | `25 mm` |
| Damper (bump/rebound) | N/m/s | `4500 N/m/s` |
| ARB | N/mm | `120 N/mm` |
| Wing angle | deg | `6.5 deg` |
| Brake bias | % | `57.5%` |
| Diff lock | % | `45%` |
| Fuel | L | `60 L` |

## Clean Value Extraction

rF2 `.svm` values may contain compound formats:
- `223//N/mm` → the value after `//` is the unit annotation. Physical value is `223 N/mm`.
- `3.5 deg` → simple value with unit suffix.
- `15` → bare numeric, unit inferred from parameter name.

The `CleanValue()` function splits on `//` and uses the right part when it contains unit information.

## Axle Symmetry Convention

For axle pairs (FL/FR, RL/RR):
- Parameters should be **symmetric by default** (same value left and right)
- Asymmetry is only justified by:
  - Track with predominantly one-direction corners
  - Telemetry showing consistent left/right imbalance
  - Wind direction effects on oval tracks
- Post-processing enforces symmetry unless telemetry justifies the difference

## Fixed (Locked) Parameters

Some parameters are locked by the user and must not be modified:
- Loaded from `fixed_params.json` or user preferences
- Excluded from specialist context before analysis
- Any recommendation on a locked param is filtered in post-processing
- Common locked params: FuelSetting, CompoundSetting, GearRatios
