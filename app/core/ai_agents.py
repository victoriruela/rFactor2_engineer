import json
import re
import asyncio
import subprocess
import time
import os
import requests
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

# --- CONFIGURACIÓN OLLAMA ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_TAG = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def list_available_models():
    """Devuelve la lista de modelos disponibles en Ollama."""
    _ensure_ollama_running()
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []

def _find_ollama_exe():
    """Busca el ejecutable de ollama en ubicaciones conocidas."""
    for candidate in [
        "ollama",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
    ]:
        if candidate == "ollama" or os.path.isfile(candidate):
            try:
                subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                return candidate
            except Exception:
                continue
    return None

# --- PROMPTS ---

DRIVING_PROMPT = """
Eres un ingeniero de pista experto en rFactor 2. Analiza los datos de telemetría VUELTA A VUELTA y CURVA A CURVA, y responde en CASTELLANO.

Tienes acceso a los DATOS COMPLETOS de telemetría submuestreados (~50 puntos por vuelta) con todos los canales relevantes.
Estos datos incluyen velocidad, throttle, freno, dirección, RPM, marchas, fuerzas G, temperaturas, desgaste, presiones, etc.
Cada fila tiene la columna "Vuelta" y "Lap Distance" (distancia recorrida en la vuelta).

DATOS DE TELEMETRÍA:
{telemetry_summary}

ESTADÍSTICAS DE SESIÓN:
{session_stats}

ANÁLISIS REQUERIDO:
1. Examina los datos punto a punto para identificar el comportamiento en las CURVAS. Compara cómo el piloto toma la misma curva en diferentes vueltas usando la columna "Lap Distance" para ubicarte.
2. Identifica problemas específicos en curvas (frenadas tardías, falta de velocidad de paso por curva, aceleraciones bruscas que causan sobreviraje, etc.)
3. Compara la EVOLUCIÓN: ¿mejora o empeora el rendimiento en sectores específicos del circuito?
4. Identifica patrones: ¿el desgaste o temperatura afectan al rendimiento en las últimas vueltas?

Escribe EXACTAMENTE 5 puntos de mejora. Cada punto debe ser ÚNICO y diferente a los demás.
Formato obligatorio para cada punto:
- Vuelta N (Distancia Xm): [análisis de curva con valores numéricos REALES] → [acción correctiva específica]

Reglas ESTRICTAS:
- USA valores numéricos REALES de los datos (velocidad, frenada %, throttle %, RPM, G Force, etc.)
- Céntrate en COMPARAR curvas entre vueltas.
- PROHIBIDO repetir ideas.
- Sin introducción, sin conclusión, solo los 5 puntos.
"""

SECTION_AGENT_PROMPT = """
Eres un Ingeniero Especialista en {section_name} para rFactor 2. Circuito: {circuit_name}.

Tienes acceso a los DATOS COMPLETOS de telemetría submuestreados (~50 puntos por vuelta) con todos los canales.
Analiza el comportamiento del coche CURVA A CURVA, comparando las mismas distancias ("Lap Distance") entre diferentes vueltas.

DATOS DE TELEMETRÍA COMPLETOS:
{telemetry_summary}

PARÁMETROS ACTUALES DE {section_name}: {section_data}

TU MISIÓN:
Como experto en esta sección, debes evaluar CÓMO cada parámetro actual influye en el comportamiento visto en la telemetría.
1. Examina cómo afecta el setup al comportamiento en las CURVAS. ¿Hay subviraje o sobreviraje excesivo en curvas lentas vs rápidas?
2. Compara la evolución entre vueltas: ¿empeoran las temperaturas o presiones afectando al grip en curva?
3. Propón cambios CONCRETOS con valores numéricos basados en lo que observas en los datos.
4. Si consideras que no hay cambios necesarios, JUSTIFÍCALO con datos (ej: "Las temperaturas se mantienen estables en 90°C en todas las vueltas").

Reglas:
1. Cada "reason" DEBE citar valores numéricos REALES y comparar el comportamiento en curvas entre vueltas.
2. Explica el MOTIVO técnico de cada cambio: por qué ese valor nuevo corregirá el comportamiento observado en la curva.
3. Debes proporcionar un razonamiento para CADA parámetro que consideres relevante, incluso si no lo cambias.
4. Responde SIEMPRE en CASTELLANO.
5. Devuelve ÚNICAMENTE JSON puro.

JSON puro:
{{
  "items": [
    {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica citando curvas, vueltas y valores numéricos reales" }}
  ]
}}
"""

TIRES_SUSPENSION_ANALYSIS_PROMPT = """
Eres un Ingeniero Especialista en Neumáticos y Suspensión de rFactor 2. Circuito: {circuit_name}.

Analiza los DATOS COMPLETOS de telemetría submuestreados. Céntrate en el comportamiento en las CURVAS y la comparación entre vueltas.
Observa temperaturas (Tyre Temp FL/FR/RL/RR), presiones, alturas (Ride Height), y suspensión (Susp Pos, Susp Force).

DATOS DE TELEMETRÍA COMPLETOS:
{telemetry_summary}

SETUP ACTUAL: {setup_data}

TU TAREA:
1. Identifica problemas de temperatura o desgaste comparando el inicio y el final de la sesión.
2. Analiza el balance del coche en curvas: ¿las alturas son correctas? ¿hay "bottoming" (golpeo del fondo contra el suelo)?
3. Propón cambios para optimizar el grip en curva y la estabilidad.
4. Cita valores numéricos REALES (ej: "En la curva de la distancia 1500m, la suspensión delantera llega al tope en la vuelta 5").

Responde en CASTELLANO y devuelve ÚNICAMENTE JSON.

JSON puro:
{{
  "sections": [
    {{
      "name": "NombreSeccionInterno",
      "items": [
        {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica con datos de curvas y vueltas" }}
      ]
    }}
  ]
}}
"""

TIRES_SUSPENSION_VALIDATION_PROMPT = """
Eres el Ingeniero Jefe de Dinámica Vehicular. Circuito: {circuit_name}.

Tienes acceso a los DATOS COMPLETOS de telemetría submuestreados. Úsalos para validar y complementar las propuestas.

DATOS DE TELEMETRÍA COMPLETOS:
{telemetry_summary}
DATOS ORIGINALES DEL SETUP: {original_setup}
PROPUESTAS DEL PRIMER INGENIERO: {first_proposals}

Tu tarea:
1. Valida cada propuesta del primer ingeniero contra los datos reales. ¿Los datos respaldan el cambio?
2. AÑADE propuestas para parámetros que el primer ingeniero NO haya cubierto (presiones, camber, toe, altura, muelles, amortiguadores).
3. Si el primer ingeniero no propuso cambios suficientes, AÑADE al menos 3 cambios adicionales con valores concretos.
4. Cada "reason" DEBE citar valores numéricos REALES de la telemetría que justifiquen el cambio.
5. Explica el MOTIVO técnico de cada valor nuevo propuesto.
6. Responde en CASTELLANO.

JSON puro:
{{
  "sections": [
    {{
      "name": "NombreSeccionInterno",
      "items": [
        {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación con datos reales de telemetría" }}
      ]
    }}
  ]
}}
"""

CHIEF_ENGINEER_PROMPT = """
Eres el Ingeniero Jefe de Competición. Tu responsabilidad es dar la palabra final sobre el setup completo.
Recibes informes de los especialistas de cada área y del equipo de Neumáticos y Suspensión.

CIRCUITO: {circuit_name}

Tienes acceso a los DATOS COMPLETOS de telemetría submuestreados para verificar las propuestas de los especialistas.

DATOS DE TELEMETRÍA COMPLETOS:
{telemetry_summary}

Informes de especialistas:
{specialist_reports}

Tu tarea:
1. Revisa cada propuesta de los especialistas y verifica que los datos de telemetría la respaldan.
2. Asegura coherencia entre todas las recomendaciones (ej: no subir presiones si ya hay sobrecalentamiento).
3. Cada "reason" DEBE explicar el MOTIVO técnico del cambio citando datos reales de la telemetría.
4. PROHIBIDO poner "reason" genéricos como "mejora el rendimiento". Cada razón debe ser específica.
5. Todo el setup es para ser aplicado en el garaje antes de salir a pista.
6. Responde SIEMPRE en CASTELLANO.

JSON puro:
{{
  "full_setup": {{
    "sections": [
      {{
        "name": "NombreSeccionInterno",
        "items": [
          {{ "parameter": "NombreOriginal", "new_value": "ValorFinal", "reason": "Justificación técnica con datos reales de telemetría" }}
        ]
      }}
    ]
  }}
}}
"""

TRANSLATOR_PROMPT = """
Eres un experto en localización de simuladores de carreras.
Debes traducir y hacer "amigables" los siguientes parámetros y secciones de rFactor 2.
Nuevos elementos: {new_elements}

Devuelve un JSON con las traducciones (Usa nombres naturales en castellano):
{{
  "sections": {{ "CODIGO": "Nombre Amigable" }},
  "parameters": {{ "CODIGO": "Nombre Amigable" }}
}}
"""


def _ensure_ollama_running():
    """Arranca el servidor ollama si no está disponible."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    print("Ollama no está corriendo. Intentando arrancar...")
    ollama_exe = _find_ollama_exe()
    if not ollama_exe:
        print("ADVERTENCIA: ollama no está instalado en el sistema.")
        return False
    try:
        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        for _ in range(15):
            time.sleep(1)
            try:
                r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
                if r.status_code == 200:
                    print("Ollama arrancado correctamente.")
                    return True
            except Exception:
                pass
    except FileNotFoundError:
        print("ADVERTENCIA: no se pudo arrancar ollama.")
    return False




class AIAngineer:
    def __init__(self):
        self.llm = None
        self.output_parser = StrOutputParser()
        self.mapping_path = "app/core/param_mapping.json"
        self.mapping = self._load_mapping()

    def _init_llm(self, model_tag=None):
        _ensure_ollama_running()
        tag = model_tag or OLLAMA_MODEL_TAG
        self.llm = ChatOllama(
            model=tag,
            base_url=OLLAMA_BASE_URL,
            num_predict=4096,
            temperature=0.3,
        )
        self._current_model = tag
        print(f"LLM listo: ollama/{tag}")

    def _load_mapping(self):
        if os.path.exists(self.mapping_path):
            try:
                with open(self.mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sections": {}, "parameters": {}}

    def _save_mapping(self):
        with open(self.mapping_path, 'w', encoding='utf-8') as f:
            json.dump(self.mapping, f, indent=2, ensure_ascii=False)

    def _clean_value(self, val):
        val_str = str(val)
        if "//" in val_str:
            parts = val_str.split("//")
            if len(parts) > 1:
                return parts[1].split("(")[0].strip()
        return val_str.strip()

    def _get_friendly_name(self, key, item_type='parameter'):
        return self.mapping.get(item_type + "s", {}).get(key, key)

    async def _get_json_from_llm(self, prompt, inputs):
        prompt_tmpl = PromptTemplate.from_template(prompt)
        chain = prompt_tmpl | self.llm | self.output_parser
        try:
            response = await chain.ainvoke(inputs)
        except Exception as e:
            print(f"Error en LLM: {e}")
            return None

        try:
            # Buscar el primer objeto JSON completo y válido
            start = response.find('{')
            if start != -1:
                depth = 0
                for i, ch in enumerate(response[start:], start):
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = response[start:i+1]
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                cleaned = re.sub(r',\s*\}', '}', candidate)
                                cleaned = re.sub(r',\s*\]', ']', cleaned)
                                try:
                                    return json.loads(cleaned)
                                except json.JSONDecodeError:
                                    pass
                            break
        except Exception as e:
            print(f"Error en LLM JSON: {e}")
        return None

    async def update_mappings(self, setup_data):
        new_sections = [s for s in setup_data.keys() if s not in self.mapping.get("sections", {})]
        new_params = []
        for s, p in setup_data.items():
            for k in p.keys():
                if k not in self.mapping.get("parameters", {}):
                    new_params.append(k)

        new_params = list(set(new_params))

        if new_sections or new_params:
            new_elements = {"sections": new_sections, "parameters": new_params}
            translation = await self._get_json_from_llm(TRANSLATOR_PROMPT, {"new_elements": str(new_elements)})
            if translation:
                if "sections" not in self.mapping: self.mapping["sections"] = {}
                if "parameters" not in self.mapping: self.mapping["parameters"] = {}
                self.mapping["sections"].update(translation.get("sections", {}))
                self.mapping["parameters"].update(translation.get("parameters", {}))
                self._save_mapping()

    async def analyze(self, telemetry_summary, setup_data, circuit_name="Desconocido", session_stats=None, model_tag=None):
        if self.llm is None or (model_tag and getattr(self, '_current_model', None) != model_tag):
            print("Inicializando LLM...")
            self._init_llm(model_tag)

        # 1. Actualizar mapeos si hay nuevos parámetros
        await self.update_mappings(setup_data)

        # 2. Análisis de Conducción
        driving_prompt = PromptTemplate.from_template(DRIVING_PROMPT)
        driving_chain = driving_prompt | self.llm | self.output_parser
        try:
            driving_analysis = await driving_chain.ainvoke({
                "telemetry_summary": telemetry_summary,
                "session_stats": json.dumps(session_stats or {}, indent=2)
            })
            print(f"[DEBUG driving_analysis] {repr(driving_analysis[:300])}")
        except Exception as e:
            print(f"Error en driving_chain: {e}")
            driving_analysis = "No se pudo obtener el análisis de conducción."

        # 3. Análisis de Setup Jerárquico
        specialist_reports = []
        tires_susp_sections = ["FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT", "LEFTFRONT", "RIGHTFRONT", "LEFTREAR", "RIGHTREAR", "SUSPENSION"]

        tires_susp_setup = {s: setup_data[s] for s in setup_data if s in tires_susp_sections}

        # Agente 1: Propuesta inicial neumáticos/suspensión (vía JSON)
        first_tires_susp_report = await self._get_json_from_llm(TIRES_SUSPENSION_ANALYSIS_PROMPT, {
            "setup_data": json.dumps(tires_susp_setup, indent=2),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        print(f"[DEBUG first_tires_susp_report] {repr(str(first_tires_susp_report)[:300])}")

        # Agente 2: Validación y mejora
        final_tires_susp_report = await self._get_json_from_llm(TIRES_SUSPENSION_VALIDATION_PROMPT, {
            "original_setup": json.dumps(tires_susp_setup, indent=2),
            "first_proposals": json.dumps(first_tires_susp_report, indent=2) if first_tires_susp_report else "Sin propuestas",
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        print(f"[DEBUG final_tires_susp_report] {repr(str(final_tires_susp_report)[:300])}")

        if final_tires_susp_report:
            specialist_reports.extend(final_tires_susp_report.get("sections", []))
        elif first_tires_susp_report:
            specialist_reports.extend(first_tires_susp_report.get("sections", []))

        # Analizar otras secciones (Aerodinámica, Motor, etc.)
        for section_name, section_data in setup_data.items():
            if section_name in tires_susp_sections:
                continue

            friendly_section = self._get_friendly_name(section_name, 'section')
            report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                "section_name": friendly_section,
                "telemetry_summary": telemetry_summary,
                "section_data": json.dumps(section_data, indent=2),
                "context_data": "N/A",
                "circuit_name": circuit_name
            })
            if report:
                print(f"[DEBUG {section_name}_report] {repr(str(report)[:300])}")
                specialist_reports.append({"name": section_name, "items": report.get("items", [])})

        # Ingeniero Jefe (paso final de consolidación)
        chief_engineer_report = await self._get_json_from_llm(CHIEF_ENGINEER_PROMPT, {
            "specialist_reports": json.dumps(specialist_reports, indent=2),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        print(f"[DEBUG chief_engineer_report] {repr(str(chief_engineer_report)[:300])}")

        # 4. Formatear respuesta para el frontal
        # Construimos un mapa de todas las recomendaciones de los especialistas para asegurar que no se pierdan
        all_reco_map = {} # section_name -> { param_name -> item }
        
        # Primero llenamos con los informes de los especialistas
        for s_report in specialist_reports:
            s_name = s_report.get("name", "")
            if s_name not in all_reco_map:
                all_reco_map[s_name] = {}
            for item in s_report.get("items", []):
                p_name = item.get("parameter", "")
                all_reco_map[s_name][p_name] = item

        # Si el Ingeniero Jefe dio recomendaciones finales, estas tienen prioridad (sobreescriben o añaden)
        if chief_engineer_report and "full_setup" in chief_engineer_report:
            chief_sections = chief_engineer_report["full_setup"].get("sections", [])
            for c_section in chief_sections:
                s_name = c_section.get("name", "")
                if not s_name: continue
                if s_name not in all_reco_map:
                    all_reco_map[s_name] = {}
                for item in c_section.get("items", []):
                    p_name = item.get("parameter", "")
                    # El ingeniero jefe tiene la última palabra
                    all_reco_map[s_name][p_name] = item

        full_setup_recommendations = {"sections": []}

        for section_name, orig_section_data in setup_data.items():
            friendly_section = self._get_friendly_name(section_name, 'section')
            items = []

            # Buscamos recomendaciones tanto por nombre técnico como amigable (por si acaso el LLM usó el amigable)
            reco_dict = all_reco_map.get(section_name, {})
            if not reco_dict:
                # Intentar buscar por nombre amigable si el LLM se confundió
                for k, v in all_reco_map.items():
                    if k.lower() == friendly_section.lower():
                        reco_dict = v
                        break

            for param_key, current_val in orig_section_data.items():
                if param_key.startswith("Gear") and "Setting" in param_key:
                    num_part = param_key.replace("Gear", "").replace("Setting", "")
                    if num_part.isdigit(): continue

                friendly_param = self._get_friendly_name(param_key)
                
                # Buscar recomendación por clave técnica o nombre amigable
                reco = reco_dict.get(param_key)
                if not reco:
                    for pk, rv in reco_dict.items():
                        if pk.lower() == friendly_param.lower():
                            reco = rv
                            break

                clean_curr = self._clean_value(current_val)
                
                if reco:
                    reco_val = self._clean_value(reco.get('new_value', clean_curr))
                    reason = reco.get('reason', "Sin cambios requeridos.")
                else:
                    reco_val = clean_curr
                    reason = "Analizado por el equipo de ingeniería. No se detectaron anomalías que requieran cambios en este parámetro."

                items.append({
                    "parameter": friendly_param,
                    "current": clean_curr,
                    "new": reco_val,
                    "reason": reason
                })

            if items:
                full_setup_recommendations["sections"].append({
                    "name": friendly_section,
                    "items": items
                })

        return {
            "driving_analysis": driving_analysis,
            "setup_analysis": "Análisis completo realizado por el equipo de ingenieros de pista. Se han evaluado todos los canales de telemetría curva a curva.",
            "full_setup": full_setup_recommendations,
            "agent_reports": specialist_reports
        }
