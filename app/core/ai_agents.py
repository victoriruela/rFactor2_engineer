import json
import re
import subprocess
import time
import os
import requests
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

# --- CONFIGURACIÓN OLLAMA ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_TAG = os.getenv("OLLAMA_MODEL", "llama3.2:latest")


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
Eres un ingeniero de pista experto en rFactor 2. Analiza los datos de telemetría VUELTA A VUELTA y CURVA A CURVA para evaluar la técnica de conducción del piloto. Responde en CASTELLANO.

IMPORTANTE: Tu análisis debe centrarse EXCLUSIVAMENTE en la conducción (frenada, trazada, uso del acelerador, marchas, etc.).
PROHIBIDO sugerir cambios en el setup del coche. Tu trabajo es decir al piloto qué está haciendo mal y cómo mejorar su técnica, no qué cambiar en el coche.

DATOS DE TELEMETRÍA:
{telemetry_summary}

ESTADÍSTICAS DE SESIÓN:
{session_stats}

ANÁLISIS REQUERIDO:
1. Examina los datos punto a punto para identificar el comportamiento en las CURVAS. Compara cómo el piloto toma la misma curva en diferentes vueltas usando la columna "Lap Distance" para ubicarte.
2. Identifica problemas específicos en curvas (frenadas tardías, falta de velocidad de paso por curva, aceleraciones bruscas que causan sobreviraje, etc.)
3. Compara la EVOLUCIÓN: ¿mejora o empeora el rendimiento en sectores específicos del circuito?
4. Identifica patrones: ¿el desgaste o temperatura afectan al rendimiento en las últimas vueltas por la forma de conducir?

Escribe EXACTAMENTE 5 puntos de mejora DE CONDUCCIÓN. Cada punto debe ser ÚNICO y diferente a los demás.
Formato obligatorio para cada punto:
- Vuelta N (Distancia Xm): [análisis de curva con valores numéricos REALES de conducción] → [acción correctiva específica de CONDUCCIÓN]

Reglas ESTRICTAS:
- USA valores numéricos REALES de los datos (velocidad, frenada %, throttle %, RPM, G Force, etc.)
- Céntrate en COMPARAR curvas entre vueltas.
- PROHIBIDO repetir ideas.
- PROHIBIDO sugerir cambios de setup (presiones, muelles, alerones, etc.).
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

PARÁMETROS FIJOS (REGLA CRÍTICA):
Los siguientes parámetros NO pueden ser modificados bajo ninguna circunstancia: {fixed_params_prompt}
DEBES tener en cuenta sus valores actuales para tu análisis global, pero TIENES PROHIBIDO proponer un nuevo valor para ellos. Si crees que uno de estos parámetros es la causa del problema, menciónalo en el análisis de otros parámetros, pero no sugieras cambiarlo.

IMPORTANTE:
- Solo propón cambios en los parámetros que REALMENTE necesiten ser modificados.
- Si un parámetro está bien configurado según la telemetría, NO lo incluyas en la respuesta.
- Puedes proponer cambios en todos, algunos o NINGUNO de los parámetros.
- Si no hay cambios necesarios en ningún parámetro, devuelve un JSON con "items" vacío y un campo "summary" explicando por qué.

Reglas:
1. Cada "reason" DEBE ser una explicación técnica EXTREMADAMENTE DETALLADA (mínimo 2-3 frases), citando valores numéricos REALES y comparando el comportamiento en curvas entre vueltas.
2. Explica el mecanismo físico: CÓMO el cambio de ese parámetro específico solucionará el problema de telemetría detectado.
3. Responde SIEMPRE en CASTELLANO.
4. Devuelve ÚNICAMENTE JSON puro.
5. RESTRICCIONES DE VALORES:
   - Parámetros DISCRETOS (solo valores enteros): FuelSetting, BrakeDuctSetting, RadiatorSetting, BoostSetting, RevLimitSetting, EngineBrakeSetting. Solo puedes proponer valores enteros (ej: de 5 a 6, NUNCA de 5 a 5.5).
   - Parámetros CONTINUOS (permiten decimales): CamberSetting, ToeSetting, PressureSetting, SpringSetting, PackerSetting, SlowBumpSetting, SlowReboundSetting, FastBumpSetting, FastReboundSetting, RideHeightSetting, y similares.
   - NO propongas cambiar la cantidad de combustible (FuelSetting) salvo que haya un problema claro de peso.
   - Los valores propuestos deben ser REALISTAS y proporcionados al problema detectado.

JSON puro:
{{
  "items": [
    {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica muy detallada, citando curvas (Lap Distance), vueltas y valores numéricos reales de telemetría. Explica el porqué técnico del cambio." }}
  ],
  "summary": "Resumen técnico de los cambios propuestos o justificación detallada de por qué no se necesitan cambios"
}}
"""

CHIEF_ENGINEER_PROMPT = """
Eres el Ingeniero Jefe de Competición de un equipo de rFactor 2. Tu responsabilidad es CONSOLIDAR el setup completo.
Recibes informes de ingenieros especialistas para cada sección del coche.

CIRCUITO: {circuit_name}

DATOS DE TELEMETRÍA COMPLETOS:
{telemetry_summary}

SETUP ACTUAL COMPLETO:
{current_setup}

Informes de los especialistas:
{specialist_reports}

{memory_context}

TU ROL COMO INGENIERO JEFE (REGLAS DE ORO):
1. SER PERMISIVO: Los especialistas son expertos en su área. Tu labor NO es filtrar por sistema, sino ELIMINAR O MODIFICAR SOLO aquello que sea incoherente, peligroso o contradictorio. Si una propuesta de un especialista tiene sentido técnico basado en la telemetría, DEBES incluirla.
2. RESPETAR LAS EXPLICACIONES:
   - Si aceptas el cambio de un especialista SIN modificar el valor propuesto, DEBES usar la explicación (reason) íntegra del especialista, o ampliarla. No la resumas.
   - Si modificas el valor o descartas una propuesta, DEBES dar una explicación (reason) detallada de por qué tu decisión es mejor para el balance global del coche.
3. VISIÓN GLOBAL Y COHERENCIA: Verifica que los cambios no se contradigan entre ejes (delantero/trasero) o secciones.
4. SIMETRÍA:
   - Mantén simetría (FRONTLEFT ≈ FRONTRIGHT, etc.) a menos que la telemetría (G Force Lat, temperaturas asimétricas) justifique claramente una asimetría por el diseño del circuito.
5. EXPLICACIONES DETALLADAS: El piloto necesita entender el "porqué". Evita frases cortas. Cita siempre valores de telemetría.
6. PARÁMETROS FIJOS (REGLA CRÍTICA):
   Los siguientes parámetros han sido fijados por el piloto y NO PUEDEN ser modificados: {fixed_params_prompt}
   Si un especialista ha propuesto un cambio para uno de estos parámetros, DEBES descartar esa propuesta específica, pero puedes usar su razonamiento para ajustar otros parámetros relacionados que NO estén fijos.
7. IMPORTANTE: El nombre de la sección en el JSON ("name") DEBE ser el nombre interno (ej: "FRONTLEFT", "SUSPENSION").

JSON puro:
{{
  "full_setup": {{
    "sections": [
      {{
        "name": "FRONTLEFT",
        "items": [
          {{ "parameter": "CamberSetting", "new_value": "-3.2", "reason": "COPIA AQUÍ LA RAZÓN DEL ESPECIALISTA SI NO MODIFICAS EL VALOR, O EXPLICA TU CAMBIO DETALLADAMENTE..." }}
        ]
      }}
    ]
  }},
  "chief_reasoning": "Resumen global de la estrategia de setup adoptada y correcciones importantes realizadas a las propuestas de los especialistas."
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


def _extract_numeric(val_str):
    """Extrae el primer valor numérico de un string como '223 N/mm' -> 223.0, '-3 °' -> -3.0"""
    val_str = str(val_str).strip()
    m = re.match(r'^([+-]?\d+\.?\d*)', val_str)
    if m:
        return float(m.group(1))
    return None


def _compute_change_pct(current_clean, new_clean):
    """Calcula el porcentaje de cambio entre valor actual y nuevo.
    Devuelve string como '(+12.5%)' o '(-5.0%)' o None si no se puede calcular."""
    curr_num = _extract_numeric(current_clean)
    new_num = _extract_numeric(new_clean)
    if curr_num is None or new_num is None:
        return None
    if curr_num == new_num:
        return None
    if curr_num == 0:
        return "(nuevo)" if new_num != 0 else None
    pct = ((new_num - curr_num) / abs(curr_num)) * 100
    sign = "+" if pct > 0 else ""
    return f"({sign}{pct:.1f}%)"


# Secciones relacionadas con neumáticos/suspensión que deben analizarse juntas
TIRE_SUSP_SECTIONS = {"FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT", "SUSPENSION"}


class AIAngineer:
    def __init__(self):
        self.llm = None
        self.output_parser = StrOutputParser()
        self.mapping_path = "app/core/param_mapping.json"
        self.mapping = self._load_mapping()
        # Memoria del ingeniero jefe: historial de decisiones
        self.chief_memory = []
        self._telemetry_cache = ""
        self._agent_reports_cache = []

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
            parts = val_str.split("//", 1)
            if len(parts) > 1:
                return parts[1].strip()
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
                if "sections" not in self.mapping:
                    self.mapping["sections"] = {}
                if "parameters" not in self.mapping:
                    self.mapping["parameters"] = {}
                self.mapping["sections"].update(translation.get("sections", {}))
                self.mapping["parameters"].update(translation.get("parameters", {}))
                self._save_mapping()

    def _build_current_setup_summary(self, setup_data):
        """Construye un resumen del setup actual completo para el ingeniero jefe."""
        lines = []
        for section_name, section_data in setup_data.items():
            if section_name.upper() in ("BASIC", "LEFTFENDER", "RIGHTFENDER"):
                continue
            filtered = {k: self._clean_value(v) for k, v in section_data.items()
                       if not (k.startswith('Gear') and 'Setting' in k)}
            if filtered:
                lines.append(f"\n[{section_name}]")
                for k, v in filtered.items():
                    lines.append(f"  {k} = {v}")
        return "\n".join(lines)

    def _format_full_setup(self, all_reco_map, setup_data):
        """Formatea las recomendaciones finales con porcentajes de cambio."""
        full_setup_recommendations = {"sections": []}

        for section_name, orig_section_data in setup_data.items():
            if section_name.upper() in ("BASIC", "LEFTFENDER", "RIGHTFENDER"):
                continue

            friendly_section = self._get_friendly_name(section_name, 'section')
            items = []

            reco_dict = all_reco_map.get(section_name, {})
            if not reco_dict:
                for k, v in all_reco_map.items():
                    if k.lower() == friendly_section.lower() or k.lower() == section_name.lower():
                        reco_dict = v
                        break
                if not reco_dict:
                    for k, v in all_reco_map.items():
                        if section_name.lower() in k.lower() or k.lower() in section_name.lower():
                            reco_dict = v
                            break

            for param_key, current_val in orig_section_data.items():
                if param_key.startswith("Gear") and "Setting" in param_key:
                    continue

                friendly_param = self._get_friendly_name(param_key)

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
                    reason = re.sub(r'\b\d+//', '', reason)

                    # Calcular porcentaje de cambio
                    pct = _compute_change_pct(clean_curr, reco_val)
                    display_new = f"{reco_val} {pct}" if pct else reco_val
                else:
                    display_new = clean_curr
                    reason = "Sin cambios requeridos."

                items.append({
                    "parameter": friendly_param,
                    "current": clean_curr,
                    "new": display_new,
                    "reason": reason,
                    "section_key": section_name,
                    "param_key": param_key
                })

            if items:
                full_setup_recommendations["sections"].append({
                    "name": friendly_section,
                    "section_key": section_name,
                    "items": items
                })

        return full_setup_recommendations

    async def analyze(self, telemetry_summary, setup_data, circuit_name="Desconocido", session_stats=None, model_tag=None, fixed_params=None, driving_telemetry_summary=None):
        if self.llm is None or (model_tag and getattr(self, '_current_model', None) != model_tag):
            print("Inicializando LLM...")
            self._init_llm(model_tag)

        # Preparar prompt de parámetros fijos
        fixed_list = fixed_params or []
        if fixed_list:
            friendly_fixed = [self._get_friendly_name(p) for p in fixed_list]
            fixed_params_prompt = ", ".join([f"{f} ({p})" for f, p in zip(friendly_fixed, fixed_list)])
        else:
            fixed_params_prompt = "Ninguno."

        # Limpiar memoria del ingeniero jefe para nueva sesión de análisis
        self.chief_memory = []
        self._telemetry_cache = telemetry_summary
        self._agent_reports_cache = []

        # 1. Actualizar mapeos si hay nuevos parámetros
        await self.update_mappings(setup_data)

        # 2. Análisis de Conducción
        # Usar resumen filtrado (solo canales de técnica de pilotaje) si está disponible
        driving_input = driving_telemetry_summary if driving_telemetry_summary is not None else telemetry_summary
        driving_prompt = PromptTemplate.from_template(DRIVING_PROMPT)
        driving_chain = driving_prompt | self.llm | self.output_parser
        try:
            driving_analysis = await driving_chain.ainvoke({
                "telemetry_summary": driving_input,
                "session_stats": json.dumps(session_stats or {}, indent=2)
            })
            print(f"[DEBUG driving_analysis] {repr(driving_analysis[:300])}")
        except Exception as e:
            print(f"Error en driving_chain: {e}")
            driving_analysis = "No se pudo obtener el análisis de conducción."

        # 3. Análisis de Setup por secciones (un agente por cada sección)
        specialist_reports = []

        for section_name, section_data in setup_data.items():
            if section_name.upper() in ("BASIC", "LEFTFENDER", "RIGHTFENDER"):
                continue

            filtered_data = {k: v for k, v in section_data.items() if not (k.startswith('Gear') and 'Setting' in k)}
            if not filtered_data:
                continue

            cleaned_data = {k: self._clean_value(v) for k, v in filtered_data.items()}

            friendly_section = self._get_friendly_name(section_name, 'section')
            report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                "section_name": friendly_section,
                "telemetry_summary": telemetry_summary,
                "section_data": json.dumps(cleaned_data, indent=2),
                "context_data": "N/A",
                "circuit_name": circuit_name,
                "fixed_params_prompt": fixed_params_prompt
            })
            if report:
                print(f"[DEBUG {section_name}_report] {repr(str(report)[:300])}")
                specialist_reports.append({"name": section_name, "items": report.get("items", [])})

        # Preparar resumen del setup actual para el ingeniero jefe
        current_setup_summary = self._build_current_setup_summary(setup_data)

        # Ingeniero Jefe (paso final de consolidación)
        chief_engineer_report = await self._get_json_from_llm(CHIEF_ENGINEER_PROMPT, {
            "specialist_reports": json.dumps(specialist_reports, indent=2),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name,
            "current_setup": current_setup_summary,
            "memory_context": "N/A",
            "fixed_params_prompt": fixed_params_prompt
        })
        print(f"[DEBUG chief_engineer_report] {repr(str(chief_engineer_report)[:300])}")

        # Guardar razonamiento del jefe en memoria (con contexto completo)
        chief_reasoning = ""
        if chief_engineer_report:
            chief_reasoning = chief_engineer_report.get("chief_reasoning", "")
            self._agent_reports_cache = specialist_reports
            self.chief_memory.append({
                "action": "análisis_inicial",
                "reasoning": chief_reasoning,
                "agent_reports": json.dumps(specialist_reports, indent=2, default=str),
                "timestamp": time.strftime("%H:%M:%S")
            })

        # 4. Formatear respuesta para el frontal
        all_reco_map = {}

        # Solo usamos las recomendaciones del ingeniero jefe (tiene la última palabra)
        if chief_engineer_report and "full_setup" in chief_engineer_report:
            chief_sections = chief_engineer_report["full_setup"].get("sections", [])
            for c_section in chief_sections:
                s_name = c_section.get("name", "")
                if not s_name:
                    continue
                # Asegurar que el nombre de la sección sea el interno (mapeado de vuelta si el LLM usó el amigable)
                internal_name = s_name
                # Intento de corrección si el LLM ignoró el prompt y envió el nombre amigable
                inv_sections = {v: k for k, v in self.mapping.get("sections", {}).items()}
                if s_name in inv_sections:
                    internal_name = inv_sections[s_name]

                if internal_name not in all_reco_map:
                    all_reco_map[internal_name] = {}

                for item in c_section.get("items", []):
                    p_name = item.get("parameter", "")
                    # Intento de corrección si el LLM usó el nombre amigable del parámetro
                    internal_p_name = p_name
                    inv_params = {v: k for k, v in self.mapping.get("parameters", {}).items()}
                    if p_name in inv_params:
                        internal_p_name = inv_params[p_name]

                    all_reco_map[internal_name][internal_p_name] = item
        else:
            # Fallback: usar informes de especialistas si el jefe no respondió
            for s_report in specialist_reports:
                s_name = s_report.get("name", "")
                if s_name not in all_reco_map:
                    all_reco_map[s_name] = {}
                for item in s_report.get("items", []):
                    p_name = item.get("parameter", "")
                    all_reco_map[s_name][p_name] = item

        full_setup_recommendations = self._format_full_setup(all_reco_map, setup_data)

        return {
            "driving_analysis": driving_analysis,
            "setup_analysis": "Análisis completo realizado por el equipo de ingenieros de pista. Se han evaluado todos los canales de telemetría curva a curva.",
            "full_setup": full_setup_recommendations,
            "agent_reports": specialist_reports,
            "chief_reasoning": chief_reasoning
        }
