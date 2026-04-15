# Differential Dynamics — Knowledge Base

## Differential Lock Percentage

The limited-slip differential controls **how much torque is shared** between left and right driven wheels:

### Lock Percentage Effects
- **0% (open diff)**: Wheels rotate independently. Maximum cornering compliance, but all torque goes to the wheel with least grip (inside wheel spins freely).
- **100% (locked/spool)**: Both wheels forced to same speed. Maximum traction in a straight line, but car resists turning (understeer on power).
- **Typical range**: 20–70% depending on car type and circuit.

### Low Lock (0–30%)
- Best for: Tight circuits with many slow corners
- Advantages: Easy rotation, smooth corner exit, predictable
- Disadvantages: Poor traction out of slow corners, inside wheel may spin uselessly

### Medium Lock (30–55%)
- Best for: Most circuits, balanced approach
- Advantages: Good compromise between traction and rotation
- Disadvantages: May need fine-tuning per corner type

### High Lock (55–80%)
- Best for: High-speed circuits, wet conditions (equalize grip)
- Advantages: Maximum traction, stable under acceleration
- Disadvantages: Heavy steering on exit, can cause snap oversteer if rear breaks away

### Very High Lock (>80%)
- Generally too aggressive for dry conditions
- Car fights the driver in corners
- Risk of sudden oversteer when rear eventually lets go

## Differential Preload

Preload is the **minimum locking torque** applied even with no drive torque:

- **Higher preload**: Diff begins to lock earlier during acceleration → smoother torque delivery, can stabilize car under trailing throttle
- **Lower preload**: More responsive to small inputs, more rotation on corner entry under trailing throttle
- **Trade-off**: High preload = more stability but less agility

## Diagnostic Patterns

### Wheel Speed Delta
- **RL/RR speed difference >10 rad/s** under acceleration: Diff too open. Inside wheel spinning.
- **RL/RR near-identical speeds in slow corners**: Diff too locked. Car pushing (understeer).

### Corner Exit Behavior
- **Snap oversteer on exit** with high diff lock: Over-locked. Inside wheel suddenly losing grip as car straightens.
- **Lazy rotation on exit** with low diff lock: Under-locked. Outside wheel doing all the work; car won't rotate.
- **Understeer on power** (car pushes wide): Can be diff OR springs/ARBs. Check diff first — increase lock slightly; if no improvement, it's mechanical.

### Steering Feel
- Steering becomes noticeably heavy after diff lock increase: Lock is excessive. The diff is fighting the steering geometry.
- Steering feels inconsistent between left/right turns: Possible diff or alignment asymmetry.

## Traction Analysis

- **Traction G_Long < 0.5g consistently**: Poor acceleration. Either diff is too open, or rear mechanical grip is insufficient.
- **Wheel spin events**: Monitor rear wheel speeds during acceleration zones. Persistent inner-wheel spin → increase lock.
- **No wheel spin but slow**: Both wheels at grip limit → need more mechanical grip (springs, camber) rather than diff adjustment.
