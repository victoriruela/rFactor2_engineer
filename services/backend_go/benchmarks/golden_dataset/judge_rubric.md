# rF2-Bench — Rúbrica de Evaluación (Judge Rubric)

## Propósito

Este documento define los criterios de evaluación que usa el **LLM-as-a-Judge** para puntuar las respuestas de los Domain Engineers del pipeline rFactor2 Engineer contra el golden dataset.

---

## Sistema de Puntuación

Cada caso se evalúa en **5 dimensiones**. La nota final es la media ponderada. Umbral de aprobación: **≥ 6.0**.

| Dimensión | Peso | Escala |
|-----------|------|--------|
| Precisión Física | 25% | 0–10 |
| Conformidad JSON | 20% | 0–10 |
| Calidad Española | 15% | 0–10 |
| Coherencia y Lógica | 25% | 0–10 |
| Accionabilidad | 15% | 0–10 |

---

## Dimensión 1 — Precisión Física (25%)

**Qué evaluar**: ¿El agente aplica correctamente las leyes físicas del dominio del motorsport?

| Puntos | Criterio |
|--------|----------|
| 9–10 | Todas las recomendaciones de parámetros son físicamente coherentes. Se citan explícitamente las reglas de física aplicables. Los rangos numéricos están dentro de los límites reales de ajuste. |
| 7–8 | La mayoría de recomendaciones son correctas. Puede haber un parámetro con dirección imprecisa pero no catastrófica. |
| 5–6 | Al menos una recomendación corrige la dirección del problema aunque el criterio sea incompleto. |
| 3–4 | Mezcla de recomendaciones correctas e incorrectas. Al menos una inversión física presente. |
| 1–2 | La mayoría de recomendaciones están mal (ej. "aumentar ala trasera para subviraje de alta velocidad"). |
| 0 | Recomendaciones que empeorarían activamente la situación observada en telemetría. |

**Penalizaciones automáticas (aplican sobre la nota final)**:
- `-3.0` por cada **inversión física catastrófica** (ej. subir presión para enfriar neumático)
- `-2.0` por cada **valor inventado** sin base en telemetría ni setup_context
- `-2.0` por **autocontradicción** (recomienda A en un párrafo y ¬A en otro)

---

## Dimensión 2 — Conformidad JSON (20%)

**Qué evaluar**: ¿La respuesta devuelve JSON válido con la estructura de `SectionReport[]` esperada?

| Puntos | Criterio |
|--------|----------|
| 10 | JSON perfectamente válido. Todos los campos presentes: `section`, `items[{parameter, old_value, new_value, reason, change_pct}]`, `summary`. |
| 8–9 | JSON válido. Falta un campo opcional (ej. `change_pct` vacío) pero los obligatorios están. |
| 5–7 | JSON mayormente válido pero con errores menores (trailing comma, campo extra inesperado). |
| 2–4 | JSON malformado pero recuperable con `extractJSON()`. Faltan campos críticos. |
| 0–1 | Sin JSON o JSON irrecuperable. Solo texto libre. |

**Nota**: el runner usa `extractJSON()` antes de evaluar — si el JSON es recuperable cuenta como válido para esta dimensión.

---

## Dimensión 3 — Calidad Española (15%)

**Qué evaluar**: ¿El contenido está correctamente escrito en español castellano, con terminología técnica apropiada?

| Puntos | Criterio |
|--------|----------|
| 9–10 | Español fluido y preciso. Terminología técnica de motorsport correcta (ej. "subviraje", "horquilla", "ride height"). Sin mezcla de idiomas. |
| 7–8 | Español mayormente correcto. Algún anglicismo innecesario o término impreciso. |
| 5–6 | Respuesta en español pero con errores gramaticales notables o terminología incorrecta. |
| 3–4 | Mezcla de español e inglés o español deficiente. |
| 0–2 | Respuesta predominantemente en inglés o idioma incorrecto. |

---

## Dimensión 4 — Coherencia y Lógica (25%)

**Qué evaluar**: ¿El razonamiento sigue una cadena lógica desde los datos de telemetría hasta las recomendaciones?

| Puntos | Criterio |
|--------|----------|
| 9–10 | Razonamiento explícito y trazable: "la telemetría muestra X → por tanto el problema es Y → se corrige con Z". Los `reason` de cada item explican el porqué con valores numéricos de la telemetría. |
| 7–8 | Razonamiento presente pero parcialmente implícito. Conclusiones correctas aunque la cadena no sea completamente explícita. |
| 5–6 | Razonamiento superficial. Las conclusiones son razonables pero no hay evidencia de que se usaron los datos de telemetría. |
| 3–4 | Recomendaciones arbitrarias o genéricas no justificadas. |
| 0–2 | Sin razonamiento visible. Respuesta que podría aplicarse a cualquier sesión sin leer la telemetría. |

---

## Dimensión 5 — Accionabilidad (15%)

**Qué evaluar**: ¿Las recomendaciones son concretas y ejecutables por el piloto/ingeniero sin ambigüedad?

| Puntos | Criterio |
|--------|----------|
| 9–10 | Cada cambio tiene valor concreto (ej. "reducir BrakeBias de 56% a 53%") o rango acotado. Los `new_value` incluyen unidades. |
| 7–8 | La mayoría de cambios son concretos. Alguno es genérico ("reducir un poco"). |
| 5–6 | Cambios identificados correctamente pero sin valores ni rangos. |
| 3–4 | Recomendaciones vagas ("ajustar el diferencial"). |
| 0–2 | Sin cambios específicos o cambios imposibles de ejecutar. |

---

## Verificaciones de must_contain y must_not_contain

Estas son binarias (pass/fail) y afectan la nota final:

| Verificación | Efecto |
|-------------|--------|
| `must_mention` faltante | `-0.5` por cada término faltante (máximo `-2.0`) |
| `must_not_contain` presente | `-2.0` por cada violación |

---

## Prompt del Judge

El judge externo (LLM) recibe este prompt para evaluar cada caso:

```
Eres un experto en ingeniería de automovilismo y evaluador de sistemas LLM para análisis de telemetría de sim-racing (rFactor2).

Tu tarea: evaluar la respuesta de un Agente Domain Engineer según la rúbrica rF2-Bench.

--- ESCENARIO ---
{scenario_description}

--- TELEMETRÍA ENTREGADA AL AGENTE ---
{telemetry_summary}

--- SETUP CONTEXT ---
{setup_context}

--- RESPUESTA DEL AGENTE ---
{agent_response}

--- Expected (referencia) ---
{expected}

--- INSTRUCCIONES ---
Evalúa la respuesta en 5 dimensiones de 0 a 10 con una justificación de 1-2 frases por dimensión.
Aplica penalizaciones automáticas donde corresponda.
Devuelve SOLO el siguiente JSON (sin markdown, sin texto extra):

{
  "scores": {
    "physics_accuracy": <0-10>,
    "json_schema": <0-10>,
    "spanish_quality": <0-10>,
    "coherence_logic": <0-10>,
    "actionability": <0-10>
  },
  "penalties": [
    {"type": "physical_inversion|invented_value|self_contradiction|must_not_contain|must_mention", "detail": "...", "deduction": <float>}
  ],
  "weighted_score": <float>,
  "pass": <true|false>,
  "summary": "<1-2 frases en español resumiendo los puntos fuertes y débiles>"
}
```

---

## Pesos para el weighted_score

```
weighted_score = (
  physics_accuracy * 0.25 +
  json_schema      * 0.20 +
  spanish_quality  * 0.15 +
  coherence_logic  * 0.25 +
  actionability    * 0.15
) - sum(penalties[].deduction)

pass = weighted_score >= 6.0
```
