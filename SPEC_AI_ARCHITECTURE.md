# SPEC — AI Architecture, Physics Grounding & Model Routing

> **Status**: Draft v2.0 — April 2026
> **Audience**: Implementing agent (`ai_architect`), developers
> **Prerequisite reading**: `services/backend_go/AGENTS.md` (current pipeline), `LLM_CONSTANTS.md`, `SETUP_CONSTANTS.md`

---

## Table of Contents

1. [Problem Statement & Goals](#1-problem-statement--goals)
2. [Physics Grounding Layer](#2-physics-grounding-layer)
3. [Multi-Agent Debate & Coherence Protocol](#3-multi-agent-debate--coherence-protocol)
4. [Model Routing Engine](#4-model-routing-engine)
5. [Benchmarking Strategy (rF2-Bench)](#5-benchmarking-strategy-rf2-bench)
6. [Frontend Changes — Read-Only Model Display](#6-frontend-changes--read-only-model-display)
7. [Implementation Roadmap](#7-implementation-roadmap)
8. [Research Pointers for Implementer](#8-research-pointers-for-implementer)

---

## 1. Problem Statement & Goals

### 1.1 Current Issues

The pipeline uses a **single Ollama model** (`llama3.2:latest`, 3B) for all 7+ agent roles. Known problems:

| Problem | Root Cause | Impact |
|---------|-----------|--------|
| **Hallucinated telemetry values** | LLM generates numbers not present in the input data | Incorrect recommendations |
| **Physics inversions** | LLM recommends "reduce rear wing to fix understeer" (physically backwards) | Dangerous setup changes |
| **Inter-agent contradictions** | Braking expert says "soften front", Cornering expert says "stiffen front" — Chief averages instead of resolving | Incoherent final output |
| **Model variance** | Switching from llama3.2 to qwen2.5 produces wildly different quality | No confidence in any single model |
| **Spanish quality variance** | Some models produce mojibake or awkward Spanish | Poor user experience |

### 1.2 Goals

1. **Physics accuracy ≥ 90%**: No recommendation violates known vehicle dynamics rules.
2. **Zero hallucinated values**: Every number in output traces to input telemetry data.
3. **Explicit contradiction resolution**: When agents disagree, the Chief must explain *why* one view prevails.
4. **Best-model-per-role**: Each agent role uses the model empirically proven best for that task.
5. **User sees results, not complexity**: Frontend hides model selection; shows only API Key input + read-only model info.

---

## 2. Physics Grounding Layer

### 2.1 Overview

Ollama models do not inherently understand vehicle dynamics. We must **inject** physics knowledge via three complementary strategies:

```
┌─────────────────────────────────────────────────────┐
│                    LLM Agent Call                     │
│                                                       │
│  ┌─────────────┐   ┌──────────────┐   ┌───────────┐ │
│  │ RAG Context  │ + │ Physics CoT  │ → │ LLM Output│ │
│  │ (injected    │   │ (structured  │   │           │ │
│  │  knowledge)  │   │  reasoning)  │   │           │ │
│  └─────────────┘   └──────────────┘   └─────┬─────┘ │
│                                              │       │
│                                  ┌───────────▼──────┐│
│                                  │ Symbolic Verifier ││
│                                  │ (physics_rules)   ││
│                                  └──────────┬───────┘│
│                                             │        │
│                              PASS ──────────┼── REJECT│
│                                             ▼        │
│                                     Final Output     │
└─────────────────────────────────────────────────────┘
```

### 2.2 Physics Rules File — `data/physics_rules.json`

A machine-readable ruleset encoding known causal relationships in vehicle dynamics. Each rule has an IF-condition, THEN-action, and physical justification. The rules are organized by domain.

**Schema:**

```json
{
  "version": "1.0",
  "domains": {
    "tire_pressure": [
      {
        "id": "TP-001",
        "if": "Tire_Temp_Center > Tire_Temp_Inner AND Tire_Temp_Center > Tire_Temp_Outer",
        "then": "REDUCE tire pressure (PressureSetting)",
        "direction": "decrease",
        "affected_params": ["PressureSetting"],
        "physics": "Excessive pressure concentrates contact patch at center; reduces total grip area and increases center wear."
      }
    ],
    "tire_camber": [...],
    "suspension": [...],
    "aerodynamics": [...],
    "braking": [...],
    "differential": [...],
    "balance": [...],
    "validation": [...]
  }
}
```

**Required rules — minimum 60 across all domains:**

#### A. Tire Physics (12+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| TP-001 | Tire_Temp_Center > Inner AND Center > Outer | Reduce pressure | Over-pressure concentrates contact patch center |
| TP-002 | Tire_Temp_Inner > Center AND Outer > Center | Increase pressure | Under-pressure bulges edges, center cold |
| TP-003 | Front tire temps consistently > rear | Rebalance load: lower front pressure OR increase rear pressure | Front overworked relative to rear |
| TC-001 | Tire_Temp_Outer > Inner (>10°C gap) | Increase negative camber | Outer edge overheating — insufficient camber for lateral loads |
| TC-002 | Tire_Temp_Inner >> Outer | Reduce negative camber magnitude | Excessive camber concentrates load on inner edge |
| TC-003 | Camber < -4.0° AND braking instability observed | Reduce camber magnitude | Extreme negative camber reduces straight-line contact patch |
| TS-001 | Grip_Fract_Front > 0.90 AND Grip_Fract_Rear < 0.75 | Balance setup toward rear | Front at saturation, rear underutilized — unstable state |
| TS-002 | Grip_Fract_Rear > 0.95 in acceleration zones | Reduce rear load or increase mechanical grip | Rear tires beyond saturation — traction loss risk |
| TS-003 | Grip_Fract < 0.70 sustained | Check for insufficient downforce or cold tire | Available grip not exploited — thermal or aero cause |
| TP-004 | Tire_Temp_Delta(LapN - Lap1) > 15°C, no track temp change | Pressure setting outside optimal window | Progressive heat buildup indicates thermal instability |
| TC-004 | Camber more negative by 1.5° AND Grip increases | Confirm new camber beneficial | Negative camber typically beneficial up to ~-3.5° |
| TS-004 | Grip_Fract > 1.05 | FLAG — data error | Physically impossible; indicates sensor/scaling issue |

#### B. Suspension (10+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| SU-001 | Ride_Height < 15mm (front) or < 20mm (rear) | Increase ride height 2–5mm | Risk of bottoming — chassis contact with surface |
| SU-002 | Ride_Height variation under braking > 5mm vs acceleration | Stiffen front spring or increase front slow bump damper | Excessive dive — weight transfer too aggressive |
| SU-003 | Body roll > 2.5° at G_Lat > 1.5g | Increase ARB stiffness (front or rear) | Excessive roll reduces aero efficiency and tire contact |
| SU-004 | Ride_Height_Front >> Rear (rake > 5mm) | Normalize rake (lower front or raise rear) | High rake increases rear load bias, promotes understeer |
| SU-005 | G_Force_Long high braking + large front height variation | Front springs too soft or bump damping insufficient | Braking load causes excessive compression |
| SU-D01 | Ride height oscillates ±5mm between corners | Increase rebound damping | Under-damped extension phase — suspension ringing |
| SU-D02 | G-force spike at entry, sharp ride height drop, slow recovery | Increase bump damping (slow) | Slow compression absorbs braking load poorly |
| SU-D03 | Damper rebound increased AND ride height becomes erratic | Decrease fast rebound; increase slow rebound (split) | Over-stiff rebound bounces suspension |
| SU-D04 | Grip_Fract drops after first lap AND ride height degradation | Increase slow bump damping | Track heat increases compliance; stiffer damping holds geometry |
| SU-006 | Spring_Rate increase 20% AND ride height increases >2mm | Verify — normally contradictory | Stiffer springs reduce compression; height should decrease |

#### C. Anti-Roll Bars & Balance (8+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| AB-001 | Understeer: Grip_Front > Grip_Rear at entry/mid | Soften front ARB OR stiffen rear ARB | Reduce front roll stiffness → more grip available front |
| AB-002 | Oversteer: Grip_Rear > Grip_Front at mid/exit | Soften rear ARB OR stiffen front ARB | Reduce rear roll stiffness → stabilize rear |
| AB-003 | Understeer entry → oversteer exit (same corner) | Damper tuning issue, not ARB alone | Transient vs steady-state imbalance |
| AB-004 | Understeer proportional to speed | Aerodynamic imbalance, not mechanical | Speed-dependent = aero-dominant cause |
| AB-005 | Body roll > 2.5° in fast corners | Increase ARB stiffness front or rear | Excessive roll reduces effective downforce |
| BL-001 | Exit oversteer (rear loose on throttle) | Stiffen rear spring OR increase diff lock | Rear unloads under acceleration |
| BL-002 | Exit understeer (car pushes on throttle) | Soften front spring OR soften front ARB | Front locked on exit; reduce front load to free rotation |
| BL-003 | Mid-corner understeer, low speed only | Soften front ARB or reduce diff preload | Low-speed understeer is mechanical, not aero |

#### D. Aerodynamics (8+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| AE-001 | Understeer in fast corners (>150 km/h) AND low rear wing | Increase rear wing 1–2° | More rear downforce shifts aero balance rearward |
| AE-002 | Oversteer at high speed, not at low speed | Reduce front wing OR increase rear wing | Speed-dependent oversteer = front-biased aero |
| AE-003 | Front_Downforce/Rear_Downforce > 55% front | Increase rear wing or reduce front wing | Aero balance should target ~50/50 for neutral handling |
| AE-004 | Top speed deficit on straight AND high wing angles | Reduce wing angles (both) cautiously | Drag penalty exceeding aero benefit on straights |
| AE-005 | Rear wing > +5° AND downforce measured < baseline | Possible wing stall — verify efficiency | Excessive angle can cause flow separation |
| AE-B01 | Understeer fast corners AND high rear wing already | Root cause is likely mechanical, not aero | Additional aero won't help if already near limit |
| AE-B02 | Aero balance shift AND ride height drops significantly | Verify spring capacity for added aero load | More downforce compresses suspension |
| AE-B03 | Wing change ≤1° AND speed impact <2% | Wing change justified — aero benefit exceeds drag cost | Marginal drag increase acceptable |

#### E. Braking (8+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| BR-001 | Brake_Temp_Front > 400°C AND Brake_Temp_Rear < 250°C | Shift brake bias rearward 2–5% | Front overheating, rear underutilized |
| BR-002 | G_Force_Lat spikes during braking zone | Rear instability under braking — check bias and rear springs | Combined lat+long load destabilizes rear |
| BR-003 | Brake_Temp_FL > FR by >50°C (single side) | FLAG — hardware issue, not setup | Asymmetric front temps = caliper or disc problem |
| BR-004 | G_Force_Long peak low AND all brake temps < 300°C | Insufficient brake pressure or duct cooling issue | Low decel + low temps = brakes not working hard enough |
| BR-D01 | Brake temps rise continuously without plateau | Increase brake duct setting | Insufficient cooling airflow |
| BR-D02 | Brake_Temp > 450°C AND deceleration decreasing | Increase duct setting until temp < 420°C | Brake fade threshold typically 400–450°C |
| BR-005 | Ride_Height front dive > 15mm under heavy braking | Front spring too soft for braking load | Excessive dive reduces front brake effectiveness |
| BR-006 | G_Force_Long pulsing (non-smooth deceleration) | Fine-tune brake bias ±2% | Pulsing = front/rear alternating lock |

#### F. Differential & Traction (5+ rules)

| ID | IF | THEN | Physics |
|----|-----|------|---------|
| DF-001 | RL/RR wheel speed delta > 10 rad/s in traction | Increase differential lock % | Inside wheel spinning — open diff losing torque |
| DF-002 | Snap oversteer at exit AND diff lock > 70% | Reduce differential lock 5–10% | Over-locked diff forces premature inside wheel slip |
| DF-003 | Traction G_Long < 0.5g consistently, no wheel lock | Increase diff lock 5–10% | Diff too open; not exploiting available traction |
| DF-004 | Diff lock increased AND steering becomes heavy | Flag — verify lock isn't excessive | High lock reduces cornering compliance |
| DF-005 | Corner exit understeer AND low diff lock | Increase diff lock cautiously | More coupling helps rotate car out of corners |

#### G. Validation / Anti-Hallucination Rules (10+ rules)

These rules **REJECT** common LLM physics inversions:

| ID | Pattern to Reject | Why It's Wrong |
|----|------------------|----------------|
| VC-001 | "Reduce rear wing to fix understeer" | Less rear downforce = LESS rear grip = MORE oversteer |
| VC-002 | "Increase front spring to improve traction on exit" | Front spring has no direct causal link to rear traction |
| VC-003 | "Soften brake bias for mid-corner balance" | Brake bias affects braking phase only, not steady-state |
| VC-004 | "Soften BOTH front AND rear ARB" | Symmetrical change doesn't fix balance — relative change needed |
| VC-005 | Value cites number not in telemetry input | Hallucinated data — auto-reject |
| VC-006 | Reason says "increase" but value decreases (or vice versa) | Internal coherence failure |
| VC-007 | "Reduce speed" or "brake earlier" | Not a setup recommendation — driving advice |
| VC-008 | "Increase front downforce to reduce oversteer" | More front downforce shifts balance forward, worsening oversteer |
| VC-009 | Parameter proposed is in fixed_params list | Locked parameter violation |
| VC-010 | Value in clicks/steps instead of physical units | Unit policy violation |

### 2.3 Symbolic Verification Layer (Post-Processing)

After each agent produces output, a Go function validates recommendations against `physics_rules.json`:

```go
// validateRecommendation checks a single setup change against the physics ruleset.
// Returns (isValid, violations).
func validateRecommendation(change SetupChange, rules []PhysicsRule, telemetryContext string) (bool, []string)
```

**Integration points in pipeline.go:**
1. After each **Domain Engineer** returns — validate before passing to Chief.
2. After the **Chief Engineer** returns — validate before post-processing.
3. **Rejection policy**: violated recommendations are stripped from output and logged. If >50% of an agent's output is rejected, flag the analysis as low-confidence.

### 2.4 RAG Knowledge Injection

Instead of relying solely on prompt-embedded rules, inject retrieved domain knowledge fragments into system prompts.

**Knowledge base structure:**
```
data/knowledge/
  tire_thermodynamics.md      # Tire temp reading, pressure effects, grip curve
  aerodynamic_balance.md      # Front/rear downforce, drag, balance effects
  suspension_geometry.md      # Spring rates, ride heights, damper tuning
  braking_systems.md          # Bias, duct cooling, trail braking physics
  differential_dynamics.md    # Lock %, traction, rotation trade-offs
  rf2_parameter_guide.md      # rFactor 2 specific: .svm format, click-to-physical mappings
```

**Injection method**: Simple file-based retrieval (no vector DB needed). Map domain engineer → knowledge files:

| Domain Engineer | Knowledge Files Injected |
|-----------------|--------------------------|
| Suspension & Corner Setup | `tire_thermodynamics.md`, `suspension_geometry.md` |
| Chassis & Balance | `suspension_geometry.md`, `braking_systems.md`, `differential_dynamics.md` |
| Aero & Speed | `aerodynamic_balance.md` |
| Powertrain & Traction | `differential_dynamics.md` |
| Chief Engineer | All files (condensed summary) |

### 2.5 Chain-of-Thought Physics Scaffolding

Add to every specialist and chief prompt a mandatory reasoning chain:

```
MANDATORY REASONING CHAIN (complete internally before each recommendation):
1. What telemetry symptom am I addressing? → cite exact values from data
2. What physical cause produces this symptom? → cite physics rule by ID
3. What parameter change addresses this cause? → name specific parameter
4. What direction must the change go? → increase/decrease with physics justification
5. Does this change conflict with any other recommendation? → check explicitly
6. What second-order effects might this change have? → acknowledge trade-offs
```

---

## 3. Multi-Agent Debate & Coherence Protocol

### 3.1 Architecture Decision: Domain Engineers

**Problem with the old pipeline** (1 driving + 4 telemetry experts + 14 section specialists + 1 chief = ~19 LLM calls):
- **Two-step abstraction loss**: Telemetry experts detect symptoms; section specialists propose fixes. The handoff loses information — the specialist doesn't know *why* a symptom was flagged, just that it was.
- **Context redundancy**: Each of the 14 specialists receives identical telemetry summary + insights (~3.5K tokens). That's 14× redundant context parsing.
- **Axle duplication**: FL, FR, RL, RR specialists work independently on near-identical physics problems. Post-processing (`enforceAxleSymmetry`) must reconcile them after the fact.
- **Contradiction amplification**: More independent agents = more opportunities for conflicting proposals with no in-context resolution.

**Solution**: **Merge telemetry analysis and setup proposal into 4 Domain Engineers** that each reason end-to-end: read telemetry → identify symptoms → propose setup changes for their assigned sections.

### 3.2 Revised Pipeline

```
Driving Analysis Agent (sequential)
         ↓
┌──────────────────────────────────────────────────────┐
│  PHASE 1 — Domain Engineers (4 parallel goroutines)   │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Suspension & Corner Setup Engineer               │ │
│  │ Sections: FRONTLEFT, FRONTRIGHT, REARLEFT,      │ │
│  │           REARRIGHT, TIRES                       │ │
│  │ Analyzes: tire temps, grip fractions, G-lateral, │ │
│  │           camber, spring rates, ride heights     │ │
│  │ ~25 parameters                                   │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Chassis & Balance Engineer                       │ │
│  │ Sections: SUSPENSION, GENERAL, CONTROLS          │ │
│  │ Analyzes: ARB balance, brake bias, brake temps,  │ │
│  │           diff lock, ride height delta, G-long   │ │
│  │ ~20 parameters                                   │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Aero & Speed Engineer                            │ │
│  │ Sections: FRONTWING, REARWING, BODYAERO,        │ │
│  │           AERODYNAMICS                           │ │
│  │ Analyzes: downforce balance, drag, speed-dep.    │ │
│  │           handling, ride height under aero load  │ │
│  │ ~12 parameters                                   │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Powertrain & Traction Engineer                   │ │
│  │ Sections: ENGINE, DRIVELINE                      │ │
│  │ Analyzes: throttle response, wheel spin, RPM,    │ │
│  │           differential behavior, traction G      │ │
│  │ ~10 parameters                                   │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│  PHASE 2 — Contradiction Detection (deterministic)    │
│  • Parse all 4 domain engineer outputs                │
│  • Compare parameter recommendations pairwise         │
│  • Flag: same param, opposite direction = CONFLICT    │
│  • Flag: coupled params with inconsistent intent      │
│  • NO LLM call — pure algorithmic comparison          │
└──────────────────────────┬───────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────┐
│  PHASE 3 — Chief Engineer with Conflict Brief         │
│  Input:                                               │
│    • All domain engineer reports                      │
│    • Explicit contradiction list with evidence         │
│    • Priority hierarchy: Safety > Drivability > Pace  │
│    • Full current setup for reference                 │
│  Task: Consolidate, resolve conflicts, final output   │
│  Must output `conflict_resolutions[]` array            │
└──────────────────────────┬───────────────────────────┘
                           ↓
Symbolic Verification (physics_rules.json, no LLM)
                           ↓
Post-processing (symmetry, coherence, reason hygiene)
```

**Total LLM calls: 6** (1 driving + 4 domain engineers + 1 chief)
**Wall clock: 3 durations** (driving → 4 domain parallel → chief)
**Token budget: ~25K** (vs ~75K with 14 specialists — 67% reduction)

### 3.3 Why This Architecture

| Dimension | Old (14 specialists) | New (4 domain engineers) |
|-----------|---------------------|--------------------------|
| **Physics reasoning** | Shallow per-section | End-to-end: symptom → cause → fix |
| **Context redundancy** | 14× identical telemetry | 4× targeted telemetry |
| **Cross-section coherence** | None (Chief reconciles post-hoc) | Built-in (one agent sees FL+FR+RL+RR) |
| **Contradiction risk** | High (14 independent proposals) | Low (4 focused domains, minimal overlap) |
| **Axle symmetry** | Enforced by post-processing | Reasoned by the agent itself |
| **LLM calls** | ~19 | **6** |
| **Token cost** | ~75K | **~25K** |
| **Wall clock** | 4 delays | **3 delays** |
| **7B model fit** | OK (narrow scope) | Better (focused but holistic) |

### 3.4 Domain Engineer Output Schema

Each domain engineer produces the same JSON structure:

```json
{
  "sections": [
    {
      "section": "FRONTLEFT",
      "items": [
        {
          "parameter": "CamberSetting",
          "new_value": "-2.5 deg",
          "reason": "de -3.0 deg a -2.5 deg: temperatura exterior 8°C mayor que interior indica exceso de camber negativo, reducir para distribuir carga más uniformemente [TC-001]"
        }
      ]
    },
    {
      "section": "FRONTRIGHT",
      "items": [...]
    }
  ],
  "findings_summary": "Resumen de hallazgos de telemetría relevantes a este dominio.",
  "confidence": 0.85
}
```

### 3.5 Domain Engineer Prompt Design

Each domain engineer prompt includes:

1. **Role definition**: "Eres el Ingeniero de Suspensión y Configuración de Esquinas. Tu dominio cubre..."
2. **Assigned sections** with complete current parameter values
3. **Relevant telemetry data** (only channels relevant to this domain, not all channels)
4. **Physics rules** (injected from `data/knowledge/*.md`)
5. **Chain-of-Thought scaffolding** (mandatory 6-step reasoning)
6. **Fixed parameters** (only those in assigned sections)
7. **Output schema** with strict JSON format

### 3.6 Contradiction Detection Algorithm (Phase 2 — Deterministic)

No LLM call — pure algorithmic comparison of domain engineer outputs:

```go
type Contradiction struct {
    ID               string   // "CF-001"
    Parameter        string   // "FrontSpringRate"
    Agent1           string   // "Suspension & Corner Setup"
    Proposal1        string   // "Soften front spring"
    Direction1       string   // "decrease"
    Agent2           string   // "Chassis & Balance"
    Proposal2        string   // "Stiffen front spring"
    Direction2       string   // "increase"
    Evidence1        string   // "Grip_Fract_FL=0.94, understeer detected"
    Evidence2        string   // "Ride_Height_Front drops 8mm under braking"
}
```

**Detection rules:**
1. **Direct opposition**: Same parameter, opposite direction (`increase` vs `decrease`).
2. **Coupled parameter conflict**: Parameter coupling matrix defines interactions (e.g., rear wing + rear ride height). If agents target coupled params with inconsistent intent, flag.

**Parameter coupling matrix:**

```json
{
  "RearWingSetting": ["RearRideHeightSetting", "RearSpringRate"],
  "FrontARBSetting": ["FrontSpringRate", "FrontRideHeightSetting"],
  "BrakeBiasSetting": ["FrontSpringRate", "RearSpringRate"],
  "DifferentialLockSetting": ["RearSpringRate", "RearARBSetting"]
}
```

**Note**: With only 4 domain engineers whose sections don't overlap, direct contradictions are rare. The coupling matrix catches indirect conflicts (e.g., Chassis engineer changes brake bias while Suspension engineer changes spring rates that affect braking stability).

### 3.7 Priority Hierarchy for Conflict Resolution

```
Priority 1: SAFETY
  - No snap oversteer, spins, or brake lock recommendations
  - Ride height above minimum thresholds
  - Brake temps below fade threshold

Priority 2: DRIVABILITY
  - Predictable handling (linear response)
  - Consistent behavior across laps

Priority 3: PACE
  - Faster lap times
  - Lower drag, higher corner speed
```

### 3.8 Chief Output Schema (Enhanced)

```json
{
  "full_setup": {
    "sections": [
      {
        "section": "SECTION_NAME",
        "items": [
          {
            "parameter": "exact_param_name",
            "new_value": "value_with_units",
            "reason": "de <old> a <new>: physics justification citing telemetry"
          }
        ]
      }
    ]
  },
  "conflict_resolutions": [
    {
      "conflict_id": "CF-001",
      "parameter": "FrontSpringRate",
      "adopted_from": "Suspension & Corner Setup",
      "rejected_from": "Chassis & Balance",
      "priority_applied": "DRIVABILITY",
      "explanation": "Understeer is dominant per grip analysis; ride height dive within safe limits (>15mm)."
    }
  ],
  "chief_reasoning": "Global strategy summary with telemetry references."
}
```

### 3.9 Optional Peer Review Phase

**Enable/disable**: `RF2_ENABLE_PEER_REVIEW=true|false` (default: `false`).

When enabled, adds 4 additional LLM calls between Phase 1 and Phase 2:

```
Phase 1.5 — Peer Review (4 parallel):
  Each domain engineer receives:
    • Their own report
    • Summary of other engineers' reports
    • Detected contradictions from Phase 2 (pre-run)
  Task: "Revise or defend your proposals given this additional context"
  Output: Updated report with confidence scores
  (Bounded: exactly 1 round, 30s timeout per agent)
```

**Total LLM calls with peer review**: 10 (1 + 4 + 4 peer + 1 chief)
**Wall clock with peer review**: 4 durations

**Recommendation**: Start with peer review disabled. Enable after benchmarking proves it improves physics accuracy ≥10%.

---

## 4. Model Routing Engine

### 4.1 Architecture

Replace the single `OLLAMA_MODEL` with a per-role model registry:

```go
type ModelConfig struct {
    Driving          string `env:"OLLAMA_MODEL_DRIVING"`
    Suspension       string `env:"OLLAMA_MODEL_SUSPENSION"`
    Chassis          string `env:"OLLAMA_MODEL_CHASSIS"`
    Aero             string `env:"OLLAMA_MODEL_AERO"`
    Powertrain       string `env:"OLLAMA_MODEL_POWERTRAIN"`
    Chief            string `env:"OLLAMA_MODEL_CHIEF"`
    Global           string `env:"OLLAMA_MODEL"` // fallback for any role
}

func (m *ModelConfig) ForRole(role string) string {
    // Role-specific → Global fallback
}
```

### 4.2 Per-Role Temperature Overrides

| Agent Role | Temperature | Rationale |
|-----------|-------------|-----------|
| Driving Coach | 0.4 | Slightly creative for empathetic coaching |
| Domain Engineers (all 4) | 0.2 | Low temp for precise numerical analysis + JSON |
| Chief Engineer | 0.3 | Conservative synthesis |

```bash
OLLAMA_TEMPERATURE_DRIVING=0.4
OLLAMA_TEMPERATURE_DOMAIN=0.2
OLLAMA_TEMPERATURE_CHIEF=0.3
```

### 4.3 Model Selection Criteria (Per Role)

| Agent Role | Required Capabilities | Recommended Category |
|-----------|----------------------|---------------------|
| **Driving Coach** | Strong Spanish fluency, narrative, empathy | Medium model (7B–14B), multilingual |
| **Suspension & Corner Setup** | Numerical reasoning, multi-section JSON, physics | Medium model (7B–14B), math-strong |
| **Chassis & Balance** | Physics reasoning, brake/diff/spring coupling | Medium model (7B–14B), reasoning |
| **Aero & Speed** | Downforce/drag trade-offs, speed-dependent analysis | Medium model (7B–14B), reasoning |
| **Powertrain & Traction** | Engine/diff analysis, traction physics | Medium model (7B–14B), instruction-following |
| **Chief Engineer** | Long context (12K+), synthesis, conflict resolution | Large model (70B+) |

### 4.4 Candidate Model Families (Ollama Cloud, April 2026)

| Family | Sizes | Key Strengths | Best For |
|--------|-------|---------------|----------|
| **Llama 3.x** | 8B, 70B | General purpose, reasoning, multilingual | Chief (70B), Specialists (8B) |
| **Qwen 2.5/3** | 1.5B–72B | Multilingual (23+ langs), math, 128K ctx | Driving (7B), Tyre/Braking (7B), Translation (1.5B) |
| **DeepSeek-R1/V3** | 7B–671B | CoT transparency, competitive reasoning | Chief (large), Experts (7B distill) |
| **Phi 4** | 14B | Excellent reasoning-to-size ratio | Specialists, Experts |
| **Mistral** | 7B–123B | Fast inference, instruction following, 128K ctx | Specialists (7B), Chief fallback |
| **Gemma 2/3** | 2B–27B | Efficient, instruction adherence | Translation (2B) |

### 4.5 Fallback Strategy

Each role has a 3-model fallback chain:

```go
var defaultFallbackChains = map[string][]string{
    "driving":     {"qwen2.5:7b", "llama3.1:8b", "mistral:7b"},
    "suspension":  {"qwen2.5:7b", "phi4:14b", "llama3.1:8b"},
    "chassis":     {"llama3.1:8b", "phi4:14b", "qwen2.5:7b"},
    "aero":        {"qwen2.5:7b", "llama3.1:8b", "mistral:7b"},
    "powertrain":  {"llama3.1:8b", "qwen2.5:7b", "mistral:7b"},
    "chief":       {"llama3.1:70b", "qwen2.5:72b", "mistral-large:123b"},
}
```

**Availability check**: `GET /api/tags` to Ollama before call; cache for 5 minutes.

### 4.6 Ollama Client Changes

```go
// GenerateWithRole calls Ollama with role-specific model and temperature.
func (c *Client) GenerateWithRole(ctx context.Context, role string, prompt string) (string, error) {
    model := c.Config.ForRole(role)
    temp := c.Config.TempForRole(role)
    return c.generateInternal(ctx, model, temp, prompt)
}
```

### 4.7 Runtime Config File — `config/model_routing.json`

```json
{
  "version": "1.0",
  "model_assignments": {
    "driving": {"model": "qwen2.5:7b", "temperature": 0.4},
    "suspension": {"model": "qwen2.5:7b", "temperature": 0.2},
    "chassis": {"model": "llama3.1:8b", "temperature": 0.2},
    "aero": {"model": "qwen2.5:7b", "temperature": 0.2},
    "powertrain": {"model": "llama3.1:8b", "temperature": 0.2},
    "chief": {"model": "llama3.1:70b", "temperature": 0.3}
  },
  "fallback_chains": {
    "driving": ["qwen2.5:7b", "llama3.1:8b", "mistral:7b"],
    "chief": ["llama3.1:70b", "qwen2.5:72b", "mistral-large:123b"]
  }
}
```

**Load priority**: `model_routing.json` → env vars → hardcoded defaults.

---

## 5. Benchmarking Strategy (rF2-Bench)

### 5.1 Overview

A domain-specific benchmark suite inspired by MT-Bench methodology, adapted for sim-racing telemetry analysis.

### 5.2 Golden Dataset

**Location**: `benchmarks/golden_dataset/`

**Size**: 50–80 test cases covering 10–15 distinct physics scenarios.

```
benchmarks/
  golden_dataset/
    scenarios/
      oversteer_entry.jsonl
      understeer_midcorner.jsonl
      thermal_degradation.jsonl
      brake_imbalance.jsonl
      bottoming_out.jsonl
      aero_imbalance.jsonl
      cold_tire_spin.jsonl
      driver_inconsistency.jsonl
      snap_oversteer_exit.jsonl
      differential_tuning.jsonl
    metadata.json
    judge_rubric.md
  scripts/
    run_benchmark.go
    evaluate_with_judge.go
    report_generator.go
  results/
```

**Test case schema (JSONL):**
```json
{
  "id": "rf2-001",
  "scenario": "brake_imbalance",
  "agent_role": "BrakingExpert",
  "difficulty": "medium",
  "telemetry_summary": "<full summary as agent would receive>",
  "session_stats": {"laps": 5, "best_lap": "1:32.445"},
  "setup_context": {"sections": [...]},
  "expected": {
    "key_findings": ["FL/FR brake temp asymmetry", "bias too far forward"],
    "acceptable_parameter_changes": {
      "BrakeBiasSetting": {"direction": "decrease", "range": [50, 58]}
    },
    "physics_rules_that_apply": ["BR-001", "BR-002"],
    "must_not_contain": ["reduce speed", "brake later", "invented_values"]
  }
}
```

### 5.3 Evaluation Rubric (Multi-Dimensional)

Each response scored 1–10 on 5 dimensions:

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| **Physics Accuracy** | 25% | Numbers trace to input? Rules not violated? Causality correct? |
| **JSON Schema** | 20% | Valid JSON? All fields present? Correct types? |
| **Spanish Quality** | 15% | Idiomatic? No mojibake? Appropriate register? |
| **Coherence & Logic** | 25% | No self-contradiction? Direction matches value? No hallucinations? |
| **Actionability** | 15% | Implementable in rF2? Valid ranges? Correct units? |

**Pass threshold**: ≥ 6.0 weighted average.

### 5.4 LLM-as-a-Judge Protocol

**Judge**: GPT-4o or Claude 3.5 Sonnet (via API). Must be stronger than candidates.

**Judge prompt:**
```
You are evaluating AI responses for a sim-racing telemetry system (rFactor 2).

TEST CASE: {test_case}
MODEL RESPONSE: {model_response}
GROUND TRUTH: {expected}
PHYSICS RULES: {applicable_rules}

Score 1–10 per dimension:
1. Physics Accuracy (25%): [score] — [justification]
2. JSON Schema (20%): [score] — [justification]
3. Spanish Quality (15%): [score] — [justification]
4. Coherence (25%): [score] — [justification]
5. Actionability (15%): [score] — [justification]

CRITICAL PENALTIES (auto-deduct 3 from Physics for each):
- Fabricated value not in input
- Physics inversion
- Self-contradictory recommendation

Overall: [weighted score]
Pass/Fail: [≥6.0 = Pass]
```

### 5.5 Benchmark Execution Workflow

```
For each candidate model M:
  For each test case T:
    1. Configure pipeline: M for role T.agent_role
    2. Run agent with T inputs
    3. Collect raw response
    4. Send (response, case, ground_truth) to Judge
    5. Collect scores
  Aggregate per dimension and overall
  Run each case 3× to measure variance
Generate comparison report
```

**Output example:**

| Model | Role | Physics | JSON | Spanish | Coherence | Action | **Overall** | Var |
|-------|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| qwen2.5:7b | Braking | 7.8 | 8.5 | 7.2 | 7.6 | 8.0 | **7.8** | ±0.4 |
| llama3.1:8b | Braking | 7.2 | 7.8 | 6.5 | 7.0 | 7.5 | **7.2** | ±0.6 |
| phi4:14b | Braking | 8.1 | 8.2 | 6.8 | 8.0 | 7.9 | **7.9** | ±0.3 |

### 5.6 Statistical Methodology

- **Runs per model-role pair**: 3 (variance measurement)
- **Confidence interval**: mean ± 1.96 × (std / √N) for 95% CI
- **Win rate (pairwise)**: Score delta > 0.5 = win. Binomial test for significance.
- **Min sample**: 10 cases per role × 3 runs = 30 evals per model-role pair

### 5.7 Cost Estimation

- **Per model, all roles**: ~100 Ollama generations + ~100 judge calls ≈ **$1–5**
- **Full benchmark (5 models)**: **$5–25**
- **Frequency**: Monthly or when new model released

---

## 6. Frontend Changes — Read-Only Model Display

### 6.1 Current State

Analysis tab (`apps/expo_app/app/(tabs)/analysis.tsx`) contains:
- Model chip selector (tappable)
- Manual model text input
- API Key input
- URL input

### 6.2 Required Changes

| Component | Current | Target |
|-----------|---------|--------|
| Model chip row | Interactive | **REMOVE** |
| Manual model input | Editable | **REMOVE** |
| API Key input | Editable | **KEEP** |
| URL input | Editable | **KEEP** |
| Model info display | N/A | **ADD** — read-only routing status |
| "Refrescar modelos" | Fetches model list | **RENAME** → "Test Connection" |

### 6.3 New Read-Only Component — `ModelRoutingInfo`

Displays active model per role, fetched from `GET /api/models/routing`:

```tsx
<View style={styles.modelRoutingCard}>
  <Text style={styles.cardTitle}>Modelos Activos</Text>
  {assignments.map(({role, label, model}) => (
    <View key={role} style={styles.routingRow}>
      <Text style={styles.roleLabel}>{label}</Text>
      <Text style={styles.modelTag}>{model}</Text>
    </View>
  ))}
</View>
```

### 6.4 New Backend Endpoint — `GET /api/models/routing`

```json
{
  "assignments": [
    {"role": "driving", "label": "Ingeniero de Conducción", "model": "qwen2.5:7b"},
    {"role": "suspension", "label": "Ing. Suspensión y Esquinas", "model": "qwen2.5:7b"},
    {"role": "chassis", "label": "Ing. Chasis y Equilibrio", "model": "llama3.1:8b"},
    {"role": "aero", "label": "Ing. Aerodinámica", "model": "qwen2.5:7b"},
    {"role": "powertrain", "label": "Ing. Tren Motriz", "model": "llama3.1:8b"},
    {"role": "chief", "label": "Ingeniero Jefe", "model": "llama3.1:70b"}
  ]
}
```

### 6.5 Store & API Changes

- **Remove from store**: `selectedModel`, `setSelectedModel`
- **Remove from Zustand partialize**: model persistence
- **Keep**: `ollamaApiKey`, `ollamaBaseUrl`, their setters
- **Add**: `modelRouting: ModelRoutingAssignment[] | null` (read-only)
- **Remove from `PUT /api/auth/config`**: `ollama_model` field
- **Remove from login restore**: `res.ollama_model`
- **Remove from analysis request**: `model`, `provider` fields
- **Keep in analysis request**: `ollama_base_url`, `ollama_api_key`

---

## 7. Implementation Roadmap

### Phase 1: Physics Grounding (data layer, no pipeline restructuring)
1. Create `data/physics_rules.json` with 60+ rules (all domains A–G above)
2. Create `data/knowledge/*.md` files (6 domain knowledge files)
3. Implement `validateRecommendation()` in Go
4. Wire validation into pipeline post-processing
5. Add Chain-of-Thought scaffolding constants

### Phase 2: Domain Engineers Architecture (pipeline restructuring)
1. Create 4 domain engineer prompts (Suspension, Chassis, Aero, Powertrain)
2. Refactor pipeline: replace 4 telemetry experts + 14 section specialists with 4 domain engineers
3. Implement contradiction detection (deterministic Phase 2)
4. Update Chief prompt for conflict resolution with `conflict_resolutions[]`
5. Inject RAG knowledge from `data/knowledge/*.md` into domain engineer prompts
6. Wire symbolic verification after domain engineers and after Chief
7. Add optional peer review phase with `RF2_ENABLE_PEER_REVIEW` config flag

### Phase 3: Model Routing Engine
1. Extend `config.Config` with `ModelConfig` per-role fields
2. Create `config/model_routing.json` schema and loader
3. Modify `ollama.Client` to accept per-call model + temperature
4. Update pipeline to use `GenerateWithRole()` for each call
5. Implement fallback chains with availability checking
6. Add `GET /api/models/routing` endpoint

### Phase 4: Frontend Changes
1. Remove model selector from Analysis tab
2. Remove `selectedModel` from store, request, auth config
3. Add `ModelRoutingInfo` read-only component
4. Wire to `GET /api/models/routing`
5. Rename "Refrescar modelos" → "Test Connection"

### Phase 5: Benchmarking Infrastructure
1. Create `benchmarks/golden_dataset/` with 50+ test cases
2. Implement benchmark orchestrator (`run_benchmark.go`)
3. Implement judge evaluator (`evaluate_with_judge.go`)
4. Implement report generator
5. Run initial benchmark across 5 candidate families
6. Populate `model_routing.json` with empirical winners

---

## 8. Research Pointers for Implementer

### 8.1 Physics Grounding

| Topic | Source | Purpose |
|-------|--------|---------|
| Vehicle dynamics fundamentals | *Race Car Vehicle Dynamics* — Milliken & Milliken | Canonical reference for all IF-THEN rules |
| rFactor 2 tire model | ISI rF2 physics docs, rF2 modding forums | rF2-specific brush tire model parameters |
| MoTeC telemetry interpretation | MoTeC i2 Pro user guide, community guides | Channel reading (Grip_Fract, G_Force, Brake_Temp) |
| Knowledge-grounded LLM | Lewis et al. 2020 "RAG for Knowledge-Intensive NLP" | Foundational RAG paper |
| Symbolic AI + LLM hybrid | Creswell et al. 2022 "Faithful Reasoning Using LLMs" | Chaining symbolic checks with LLM output |
| Chain-of-Thought prompting | Wei et al. 2022 "CoT Prompting Elicits Reasoning" | Foundational CoT technique |

### 8.2 Multi-Agent Debate

| Topic | Source | Purpose |
|-------|--------|---------|
| Multi-Agent Debate | Du et al. 2023 arXiv:2305.14325 | Core MAD paper |
| LLM self-critique | Madaan et al. 2023 "Self-Refine" | Self-revision technique |
| Framework patterns | AutoGen, CrewAI, LangGraph docs | Architecture patterns (not for direct use — we're in Go) |
| Confidence calibration | Kadavath et al. 2022 "LMs Know What They Know" | Interpreting LLM confidence scores |

### 8.3 Model Routing & Benchmarking

| Topic | Source | Purpose |
|-------|--------|---------|
| MT-Bench | Zheng et al. 2023 "Judging LLM-as-a-Judge" | Gold standard LLM evaluation methodology |
| Promptfoo | promptfoo.dev | Automated prompt + model evaluation |
| DeepEval | docs.confident-ai.com | LLM evaluation with metrics |
| Ollama Cloud API | ollama.com docs | Model availability, pricing, limits |
| Model comparison | HF Open LLM Leaderboard, LMSYS Arena | Public scores by model |
| Spanish LLM quality | Multilingual evaluation benchmarks, Aya | Spanish-specific model quality |

### 8.4 Frontend & API (Code Locations)

| What | Where | Action |
|------|-------|--------|
| Model selector UI | `apps/expo_app/app/(tabs)/analysis.tsx` lines 92–158 | Remove |
| Store model state | `apps/expo_app/src/store/useAppStore.ts` — `selectedModel` | Remove |
| API client model param | `apps/expo_app/src/api/client.ts` — `analyzePreparsed()` | Remove `model` from body |
| Auth config save | `services/backend_go/internal/auth/handlers.go` | Remove `ollama_model` |
| Analysis handler | `services/backend_go/internal/handlers/analysis.go` | Remove `model` from request |
| Pipeline orchestration | `services/backend_go/internal/agents/pipeline.go` | Replace 4 experts + 14 specialists with 4 domain engineers |
| Agent prompts | `services/backend_go/internal/agents/prompts.go` | Replace expert/specialist prompts with domain engineer prompts |
| Ollama client | `services/backend_go/internal/ollama/client.go` | Add per-call model/temp support via `GenerateWithRole()` |
| Physics rules | `services/backend_go/data/physics_rules.json` | Create (new file) |
| Knowledge base | `services/backend_go/data/knowledge/*.md` | Create (6 new files) |
| Validation logic | `services/backend_go/internal/agents/validation.go` | Create (new file) |
| Contradiction detection | `services/backend_go/internal/agents/contradictions.go` | Create (new file) |
