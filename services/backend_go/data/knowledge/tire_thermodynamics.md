# Tire Thermodynamics — Knowledge Base

## Temperature Distribution Reading

A tire's contact patch temperature is measured at three points across its width: **inner**, **center**, and **outer** edges. The temperature distribution reveals how the tire is loaded:

- **Hot center, cooler edges**: Over-inflated. The tire crown bulges outward, concentrating the contact patch at center. Reduce pressure.
- **Hot edges, cooler center**: Under-inflated. The sidewalls flex excessively, loading the edges while the center lifts. Increase pressure.
- **Hot outer edge**: Insufficient negative camber for the lateral loads encountered. The tire rolls onto its outer shoulder in corners.
- **Hot inner edge**: Excessive negative camber. The tire leans inward too much, overloading the inner tread even on straights.

**Target**: Uniform temperature distribution across all three zones, with the inner edge ~5–10°C warmer than outer (accounting for negative camber in cornering).

## Pressure Effects on Grip

Tire pressure affects grip through the **contact patch size** and **deformation characteristics**:

- **Lower pressure** → larger contact patch → more mechanical grip, but:
  - Slower steering response (more sidewall flex)
  - Higher rolling resistance
  - Risk of bead unseating under extreme lateral load
  - Heat builds faster from hysteresis

- **Higher pressure** → smaller contact patch → less grip, but:
  - Crisper steering response
  - Lower rolling resistance
  - Better high-speed stability
  - Heat builds slower

**Typical rF2 operating window**: 160–200 kPa depending on compound and car class.

## Grip Fraction Interpretation

`Grip_Fract` (or grip utilization) represents how much of the tire's theoretical maximum grip is currently being used:

- **0.70–0.85**: Normal operating range. Car has grip margin available.
- **0.85–0.95**: Approaching limit. Driver is extracting good performance.
- **0.95–1.00**: At the absolute limit. Any perturbation causes loss of grip.
- **>1.00**: Physically impossible — indicates data scaling error.

**Per-axle interpretation**:
- Front grip fraction significantly higher than rear → car is front-limited (understeer tendency)
- Rear grip fraction significantly higher than front → car is rear-limited (oversteer tendency)

## Thermal Degradation

Tire performance degrades when temperatures exceed the compound's optimal window:

- **Cold (<70°C)**: Insufficient molecular activity in rubber compound. Grip significantly reduced.
- **Optimal (80–110°C)**: Compound at peak adhesion. Molecular chains flexing optimally.
- **Hot (>120°C)**: Thermal degradation begins. Compound softens excessively, blistering risk.
- **Critical (>140°C)**: Rapid surface degradation. Grip drops sharply; tire may grain or blister.

Temperature changes per lap indicate thermal stability:
- **<3°C/lap**: Stable thermal window
- **3–8°C/lap**: Marginal — approaching thermal limit
- **>8°C/lap**: Thermal instability — pressure or setup adjustment needed
