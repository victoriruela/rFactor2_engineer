# Braking Systems — Knowledge Base

## Brake Bias

Brake bias determines the **distribution of braking force** between front and rear axles:

- **Forward bias (>55% front)**: Front brakes do more work. Safer — produces understeer under braking. Risk: front lock-up, excessive front temperature.
- **Rearward bias (<50% front)**: Rear brakes do more work. Faster (less understeer) but risky — rear lock-up causes spin.
- **Typical range**: 52–62% front depending on car weight distribution and downforce.

### Bias Adjustment Rules
- Front brake temps >400°C AND rear <250°C → shift bias rearward 2–5%
- Rear lock-up under braking → shift bias forward
- Turn-in understeer initiated by braking → shift bias rearward (less front lock → front can steer)
- Straight-line stability under braking is poor → shift bias forward (stabilize rear)

### Important Limitation
Brake bias affects **ONLY the braking phase**. It has NO direct effect on:
- Mid-corner balance (that's springs/ARBs/aero)
- Corner exit behavior (that's springs/diff/throttle map)
- Steady-state handling

## Brake Temperature Management

### Temperature Zones
- **<200°C**: Under-temperature. Brake friction material not at operating temp. Reduced braking efficiency.
- **200–380°C**: Optimal operating window. Maximum friction coefficient.
- **380–450°C**: Hot but functional. Friction begins to decrease. Monitor carefully.
- **>450°C**: Brake fade. Friction material degrades rapidly. Performance drops nonlinearly.

### Brake Duct Cooling
Brake ducts direct airflow to the braking system for cooling:
- **Larger duct opening**: More airflow → cooler brakes, but increased drag
- **Smaller duct opening**: Less drag, but risk of overheating
- **Typical strategy**: Start with moderate ducts, increase only if temps exceed 420°C

### Temperature Asymmetry
- Left/right temp difference >50°C on same axle → NOT a setup issue. Indicates hardware problem (caliper, disc, pad).
- Front/rear temp difference → brake bias issue (adjustable via setup)

## Trail Braking

Trail braking is the technique of carrying brake pressure into the corner entry:
- Transfers weight forward → more front grip for turn-in
- Keeps rear tires light → car rotates more easily
- **Setup interaction**: Cars that are too stiff in front pitch (high front spring/damper) penalize trail braking by limiting weight transfer
- **Brake bias interaction**: More forward bias helps trail braking stability but can cause front lock under heavy initial braking

## Braking G-Force Analysis

- **Peak deceleration**: Healthy range 1.5–3.5g depending on car class
- **Low peak G with low brake temps**: Brakes not working hard enough (pressure/duct issue)
- **Pulsing G-force**: Front/rear wheels alternating between locking and rolling. Indicates bias needs fine-tuning.
- **G-force drops with high temps**: Classic brake fade. Increase duct cooling.
