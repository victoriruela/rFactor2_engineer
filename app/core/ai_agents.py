import json
import re
import subprocess
import time
import os
import logging
import unicodedata
import requests
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

# --- CONFIGURACIÓN OLLAMA ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_TAG = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
JIMMY_API_URL = os.getenv("JIMMY_API_URL", "https://chatjimmy.ai/api/chat")
JIMMY_MODEL_TAG = "llama3.1-8B"
JIMMY_STATS_RE = re.compile(r"<\|stats\|>.*?<\|/stats\|>", re.DOTALL)
JIMMY_RUNTIME_CONFIG_PATH = "app/core/jimmy_runtime_config.v1.json"
# Jimmy llama3.1-8B has ~8K token context; keep total prompt well under that.
# Full prompt = template (~1.5K chars) + telemetry + section_data + fixed_params.
JIMMY_MAX_TELEMETRY_CHARS = 4_000
logger = logging.getLogger(__name__)


def list_available_models(base_url=None, api_key=None):
    """Devuelve la lista de modelos disponibles en Ollama (local o remoto).

    Args:
        base_url: URL base de Ollama. Si es None usa OLLAMA_BASE_URL del env.
        api_key: Bearer token para autenticación (Ollama Cloud u otro endpoint remoto).
    """
    effective_url = base_url or OLLAMA_BASE_URL
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if not base_url:  # solo auto-arrancar si se usa el Ollama local del backend
        _ensure_ollama_running()
    try:
        r = requests.get(f"{effective_url}/api/tags", headers=headers, timeout=5)
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
Eres un ingeniero de pista experto en rFactor 2. Analiza los datos de telemetría para evaluar la técnica de conducción del piloto. Responde en CASTELLANO.

IMPORTANTE: Tu análisis debe centrarse EXCLUSIVAMENTE en la conducción (frenada, trazada, uso del acelerador, marchas, etc.).
PROHIBIDO sugerir cambios en el setup del coche. Tu trabajo es decir al piloto qué está haciendo mal y cómo mejorar su técnica, no qué cambiar en el coche.

DATOS DE TELEMETRÍA:
{telemetry_summary}

ESTADÍSTICAS DE SESIÓN:
{session_stats}

METODOLOGÍA OBLIGATORIA — Análisis POR CURVA, comparando ENTRE VUELTAS:
1. Usa los datos de "Lap Distance" para identificar las CURVAS principales del circuito. Los rangos de distancia son para TU análisis interno — NO los incluyas en la salida.
2. Numera las curvas secuencialmente: Curva 1, Curva 2, Curva 3... y describe brevemente el tipo (horquilla, chicane, ese rápida, curva lenta de derechas, etc.).
3. Para CADA curva, COMPARA el comportamiento del piloto ENTRE DIFERENTES VUELTAS: ¿frena más tarde en unas que en otras? ¿La velocidad de paso varía? ¿Hay sobreviraje por aceleración brusca?
4. Detecta PATRONES REPETITIVOS: si el piloto comete el mismo error en la misma curva en varias vueltas, es un patrón que debe corregir. Si mejora progresivamente, destácalo.
5. Identifica si el desgaste, la temperatura de neumáticos o el combustible afectan la conducción en las últimas vueltas.

Escribe EXACTAMENTE 5 puntos de mejora DE CONDUCCIÓN. Cada punto debe referirse a una CURVA CONCRETA del circuito.
Formato obligatorio para cada punto:

**Curva N** (tipo de curva): [Patrón detectado comparando vueltas: cita valores numéricos REALES de velocidad, frenada %, throttle %, RPM, G Force de cada vuelta comparada] → [Acción correctiva específica de CONDUCCIÓN]

Ejemplo:
**Curva 3** (horquilla lenta de derechas): En la vuelta 2 el piloto frena al 85% y pasa a 78 km/h, pero en las vueltas 5 y 7 frena solo al 62% y entra a 94 km/h, perdiendo el vértice y saliendo abierto → Frenar más progresivamente antes del vértice, manteniendo al menos 75% de frenada hasta los 82 km/h para clavar el apex.

Reglas ESTRICTAS:
- USA valores numéricos REALES de los datos (velocidad, frenada %, throttle %, RPM, G Force, etc.)
- Cada punto debe COMPARAR la misma curva en AL MENOS 2-3 vueltas diferentes.
- NO incluyas rangos de metros/distancia en el título de la curva. Los datos de Lap Distance son para tu análisis interno.
- PROHIBIDO hacer un análisis "por vuelta" (vuelta 1, vuelta 2...). El análisis es "por curva" comparando vueltas.
- PROHIBIDO repetir ideas o curvas.
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

REGLA DE SIMETRÍA (OBLIGATORIA):
Si esta sección corresponde a un neumático o rueda de un lado (izquierdo/derecho), los valores que propongas DEBEN ser IDÉNTICOS al otro lado del mismo eje, SALVO que la telemetría muestre una asimetría clara (G Force lateral, temperaturas asimétricas, desgaste desigual) causada por el trazado del circuito. Si propones un valor asimétrico, DEBES justificarlo explícitamente con datos de telemetría.
Ejemplo: si propones CamberSetting=-3.2 para FRONTLEFT, debes proponer CamberSetting=-3.2 también para FRONTRIGHT, a menos que los datos demuestren que el circuito requiere asimetría.

PARÁMETROS FIJOS (REGLA CRÍTICA):
Los siguientes parámetros NO pueden ser modificados bajo ninguna circunstancia: {fixed_params_prompt}
DEBES tener en cuenta sus valores actuales para tu análisis global, pero TIENES PROHIBIDO proponer un nuevo valor para ellos. Si crees que uno de estos parámetros es la causa del problema, menciónalo en el análisis de otros parámetros, pero no sugieras cambiarlo.

IMPORTANTE:
- Solo propón cambios en los parámetros que REALMENTE necesiten ser modificados.
- Si un parámetro está bien configurado según la telemetría, NO lo incluyas en "items". Es perfectamente válido y esperado que algunos o todos los parámetros estén bien configurados.
- Puedes proponer cambios en todos, algunos o NINGUNO de los parámetros.
- Si no hay cambios necesarios en ningún parámetro, devuelve un JSON con "items" vacío y un campo "summary" explicando POR QUÉ los valores actuales son correctos para este circuito y esta telemetría.
- En el "summary", menciona brevemente qué parámetros revisaste y por qué están bien o por qué propones cambiarlos.

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

1. REVISAR HOLÍSTICAMENTE: Analiza TODAS las propuestas de los especialistas en el contexto de la telemetría completa y el setup actual. Tu trabajo es:
   a) APROBAR cambios que tengan sentido técnico y sean coherentes con la telemetría.
   b) RECHAZAR cambios que sean redundantes (si otro cambio ya resuelve el mismo problema, puede que no haga falta tocar más valores — salvo que ambos cambios sean necesarios conjuntamente).
   c) CORREGIR cambios con errores técnicos (ej: un especialista que sugiere bajar el alerón trasero para reducir subviraje — esto es INCORRECTO porque reducir carga trasera AUMENTA el subviraje. Debes detectar y corregir estos errores).
   d) ACEPTAR que algunos parámetros pueden estar ya bien configurados y NO necesitar cambios. Esto es perfectamente válido.

2. PROPIEDAD DE LAS EXPLICACIONES (REGLA CRÍTICA):
   - Si ACEPTAS un cambio de un especialista SIN modificar el valor: COPIA la explicación (reason) ÍNTEGRA del especialista. No la resumas ni reformules.
   - Si MODIFICAS un valor o RECHAZAS una propuesta: escribe TU PROPIA explicación detallada, citando datos de telemetría y explicando el mecanismo físico.

3. SIMETRÍA POR EJE:
   - Mantén simetría (FRONTLEFT ≈ FRONTRIGHT, REARLEFT ≈ REARRIGHT) a menos que la telemetría (G Force lateral, temperaturas asimétricas, desgaste desigual) justifique claramente una asimetría por el diseño del circuito.
   - Si un especialista propone valores diferentes entre lados del mismo eje SIN justificación telimétrica explícita, IGUALA ambos lados al valor más razonable y explica por qué.

4. COHERENCIA FÍSICA: Verifica que cada cambio propuesto produce el efecto descrito. Ejemplos de errores comunes que DEBES detectar:
   - Reducir alerón trasero NO reduce subviraje (lo aumenta al quitar carga trasera)
   - Endurecer suspensión trasera NO mejora tracción (la empeora)
   - Aumentar camber negativo más allá de cierto punto REDUCE grip en recta
   Cuando detectes un error así, corrige el valor O la dirección del cambio.

5. EXPLICACIONES DETALLADAS: El piloto necesita entender el "porqué" de cada decisión. Cita valores de telemetría. Evita frases genéricas.

6. PARÁMETROS FIJOS (REGLA CRÍTICA):
   Los siguientes parámetros han sido fijados por el piloto y NO PUEDEN ser modificados: {fixed_params_prompt}
   Si un especialista ha propuesto un cambio para uno de estos parámetros, DESCARTA esa propuesta, pero puedes usar su razonamiento para ajustar otros parámetros relacionados no fijos.

7. IMPORTANTE: El nombre de la sección en el JSON ("name") DEBE ser el nombre interno (ej: "FRONTLEFT", "SUSPENSION").

8. RAZONAMIENTO GLOBAL OBLIGATORIO: El campo "chief_reasoning" es OBLIGATORIO siempre. Debe contener:
   - Tu valoración global de la telemetría y el setup.
   - Para cada propuesta de cada especialista: si la apruebas, si la modificas, o si la rechazas, y POR QUÉ.
   - Si NO modificas nada de lo que proponen los especialistas, explica por qué todas las propuestas son correctas.
   - Si algún parámetro ya está bien y no necesita cambios, menciónalo también.

JSON puro:
{{
  "full_setup": {{
    "sections": [
      {{
        "name": "FRONTLEFT",
        "items": [
          {{ "parameter": "CamberSetting", "new_value": "-3.2", "reason": "COPIA AQUÍ LA RAZÓN ÍNTEGRA DEL ESPECIALISTA SI ACEPTAS SIN CAMBIOS, O ESCRIBE TU PROPIA EXPLICACIÓN DETALLADA SI MODIFICAS O CORRIGES..." }}
        ]
      }}
    ]
  }},
  "chief_reasoning": "OBLIGATORIO: Valoración global de la telemetría y el setup. Para cada sección: qué propuestas aceptas, cuáles modificas, cuáles rechazas, y por qué. Cita datos de telemetría."
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
        self.jimmy_runtime_config = self._load_jimmy_runtime_config()
        # Memoria del ingeniero jefe: historial de decisiones
        self.chief_memory = []
        self._telemetry_cache = ""
        self._agent_reports_cache = []

    def _log_event(self, level, event, **fields):
        serialized_fields = " ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in fields.items())
        msg = f"ai_pipeline event={event}"
        if serialized_fields:
            msg = f"{msg} {serialized_fields}"
        logger.log(level, msg)

    def _load_jimmy_runtime_config(self):
        default_cfg = {
            "selectedModel": JIMMY_MODEL_TAG,
            "prompt": {"systemPrompt": ""},
            "sampling": {"topK": 8, "temperature": 0.0},
            "parseCleanup": {
                "stripStatsTags": True,
                "stripOuterQuotes": True,
                "trimWhitespace": True,
                "extractFirstJsonObject": True,
                "removeTrailingCommasBeforeParse": True,
            },
            "fallbackPolicy": {
                "maxRetriesPerStage": 1,
                "failureSignal": {
                    "degraded": True,
                    "reasonField": "fallback_reason",
                },
            },
        }
        try:
            if not os.path.exists(JIMMY_RUNTIME_CONFIG_PATH):
                return default_cfg
            with open(JIMMY_RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            merged = default_cfg.copy()
            for key in ("prompt", "sampling", "parseCleanup", "fallbackPolicy"):
                merged[key] = {**default_cfg.get(key, {}), **loaded.get(key, {})}
            for key, value in loaded.items():
                if key not in merged:
                    merged[key] = value
            return merged
        except Exception as e:
            print(f"Advertencia: no se pudo cargar runtime Jimmy ({e}). Usando defaults.")
            return default_cfg

    def _jimmy_parse_cleanup_cfg(self):
        return self.jimmy_runtime_config.get("parseCleanup", {})

    def _jimmy_fallback_cfg(self):
        return self.jimmy_runtime_config.get("fallbackPolicy", {})

    def _jimmy_max_retries(self):
        cfg = self._jimmy_fallback_cfg()
        retries = cfg.get("maxRetriesPerStage", 1)
        try:
            return max(0, int(retries))
        except Exception:
            return 1

    def _sanitize_jimmy_text(self, text):
        cleaned = "" if text is None else str(text)
        cleanup_cfg = self._jimmy_parse_cleanup_cfg()
        if cleanup_cfg.get("stripStatsTags", True):
            cleaned = JIMMY_STATS_RE.sub("", cleaned)
        if cleanup_cfg.get("trimWhitespace", True):
            cleaned = cleaned.strip()
        if cleanup_cfg.get("stripOuterQuotes", True):
            if len(cleaned) >= 2 and cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1].strip()
        return cleaned

    def _extract_json_candidate(self, response_text):
        cleanup_cfg = self._jimmy_parse_cleanup_cfg()
        raw = "" if response_text is None else str(response_text)
        if cleanup_cfg.get("trimWhitespace", True):
            raw = raw.strip()

        if cleanup_cfg.get("extractFirstJsonObject", True):
            start = raw.find('{')
            if start == -1:
                return None
            depth = 0
            for i, ch in enumerate(raw[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return raw[start:i + 1]
            return None
        return raw

    def _parse_json_candidate(self, candidate):
        if candidate is None:
            return None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            cleanup_cfg = self._jimmy_parse_cleanup_cfg()
            if not cleanup_cfg.get("removeTrailingCommasBeforeParse", True):
                return None
            cleaned = re.sub(r',\s*\}', '}', candidate)
            cleaned = re.sub(r',\s*\]', ']', cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None

    async def _get_text_from_llm(self, prompt, inputs, min_len=1):
        provider = getattr(self, "_provider", "ollama")
        attempts = 1
        if provider == "jimmy":
            attempts = self._jimmy_max_retries() + 1

        for attempt in range(1, attempts + 1):
            try:
                response = await self._call_llm_text(prompt, inputs)
            except Exception as e:
                self._log_event(
                    logging.WARNING,
                    "llm_text_attempt_error",
                    provider=provider,
                    attempt=attempt,
                    attempts=attempts,
                    error=str(e),
                )
                continue

            cleaned = response.strip() if isinstance(response, str) else ""
            if len(cleaned) >= max(1, int(min_len)):
                if attempt > 1:
                    self._log_event(
                        logging.INFO,
                        "llm_text_retry_recovered",
                        provider=provider,
                        attempt=attempt,
                        attempts=attempts,
                    )
                return cleaned
            self._log_event(
                logging.WARNING,
                "llm_text_attempt_too_short",
                provider=provider,
                attempt=attempt,
                attempts=attempts,
                min_len=max(1, int(min_len)),
                actual_len=len(cleaned),
            )

        self._log_event(
            logging.WARNING,
            "llm_text_exhausted",
            provider=provider,
            attempts=attempts,
        )
        return None

    def _init_llm(self, model_tag=None, provider="ollama", custom_base_url=None, custom_api_key=None):
        provider_key = (provider or "ollama").lower()
        if provider_key == "jimmy":
            self.llm = None
            self._provider = "jimmy"
            self._current_model = self.jimmy_runtime_config.get("selectedModel", JIMMY_MODEL_TAG)
            print(f"LLM listo: jimmy/{self._current_model}")
            return

        if provider_key != "ollama":
            raise ValueError(f"Proveedor LLM no soportado: {provider}")

        effective_url = custom_base_url or OLLAMA_BASE_URL
        # Solo intentar arrancar Ollama local si no hay URL personalizada
        if not custom_base_url:
            _ensure_ollama_running()

        tag = model_tag or OLLAMA_MODEL_TAG
        ollama_kwargs = {
            "model": tag,
            "base_url": effective_url,
            "num_predict": 4096,
            "temperature": 0.3,
        }
        if custom_api_key:
            ollama_kwargs["client_kwargs"] = {"headers": {"Authorization": f"Bearer {custom_api_key}"}}
            ollama_kwargs["async_client_kwargs"] = {"headers": {"Authorization": f"Bearer {custom_api_key}"}}
        self.llm = ChatOllama(**ollama_kwargs)
        self._provider = "ollama"
        self._current_model = tag
        self._custom_base_url = effective_url
        self._custom_api_key = custom_api_key
        print(f"LLM listo: ollama/{tag} @ {effective_url}")

    def _build_prompt_text(self, prompt, inputs):
        prompt_tmpl = PromptTemplate.from_template(prompt)
        return prompt_tmpl.format(**inputs)

    def _call_jimmy_api(self, prompt_text):
        sampling_cfg = self.jimmy_runtime_config.get("sampling", {})
        prompt_cfg = self.jimmy_runtime_config.get("prompt", {})
        response = requests.post(
            JIMMY_API_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Referer": "https://chatjimmy.ai/",
                "Origin": "https://chatjimmy.ai",
            },
            json={
                "messages": [{"role": "user", "content": prompt_text}],
                "chatOptions": {
                    "selectedModel": self.jimmy_runtime_config.get("selectedModel", JIMMY_MODEL_TAG),
                    "systemPrompt": prompt_cfg.get("systemPrompt", ""),
                    "topK": sampling_cfg.get("topK", 8),
                    "temperature": sampling_cfg.get("temperature", 0.0),
                },
                "attachment": None,
            },
            timeout=90,
        )
        response.raise_for_status()
        return self._sanitize_jimmy_text(response.text)

    async def _call_llm_text(self, prompt, inputs):
        provider = getattr(self, "_provider", "ollama")
        if provider == "jimmy":
            prompt_text = self._build_prompt_text(prompt, inputs)
            return self._call_jimmy_api(prompt_text)

        prompt_tmpl = PromptTemplate.from_template(prompt)
        chain = prompt_tmpl | self.llm | self.output_parser
        return await chain.ainvoke(inputs)

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

    async def _get_json_from_llm(self, prompt, inputs, validate_fn=None):
        provider = getattr(self, "_provider", "ollama")
        attempts = 1
        if provider == "jimmy":
            attempts = self._jimmy_max_retries() + 1

        for attempt in range(1, attempts + 1):
            try:
                response = await self._call_llm_text(prompt, inputs)
            except Exception as e:
                self._log_event(
                    logging.WARNING,
                    "llm_json_attempt_error",
                    provider=provider,
                    attempt=attempt,
                    attempts=attempts,
                    error=str(e),
                )
                continue

            try:
                candidate = self._extract_json_candidate(response)
                parsed = self._parse_json_candidate(candidate)
                if parsed is None:
                    self._log_event(
                        logging.WARNING,
                        "llm_json_not_parseable",
                        provider=provider,
                        attempt=attempt,
                        attempts=attempts,
                    )
                    continue
                if validate_fn and not validate_fn(parsed):
                    self._log_event(
                        logging.WARNING,
                        "llm_json_invalid_contract",
                        provider=provider,
                        attempt=attempt,
                        attempts=attempts,
                    )
                    continue
                if attempt > 1:
                    self._log_event(
                        logging.INFO,
                        "llm_json_retry_recovered",
                        provider=provider,
                        attempt=attempt,
                        attempts=attempts,
                    )
                return parsed
            except Exception as e:
                self._log_event(
                    logging.WARNING,
                    "llm_json_attempt_exception",
                    provider=provider,
                    attempt=attempt,
                    attempts=attempts,
                    error=str(e),
                )

        self._log_event(
            logging.WARNING,
            "llm_json_exhausted",
            provider=provider,
            attempts=attempts,
        )
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

    def _normalize_specialist_report(self, report):
        """Normaliza variaciones de esquema JSON de especialistas (especialmente Jimmy)."""
        if not isinstance(report, dict):
            return {"items": [], "summary": ""}

        summary = report.get("summary") or report.get("resumen") or ""
        summary = str(summary).strip()

        raw_items = None
        for key in ("items", "recommendations", "recomendaciones", "changes", "cambios", "proposals"):
            candidate = report.get(key)
            if candidate is not None:
                raw_items = candidate
                break

        if raw_items is None:
            raw_items = []
        elif isinstance(raw_items, dict):
            raw_items = [raw_items]
        elif not isinstance(raw_items, list):
            raw_items = []

        normalized_items = []
        for item in raw_items:
            normalized = self._normalize_recommendation_item(item)
            if normalized:
                normalized_items.append(normalized)

        return {
            "items": normalized_items,
            "summary": summary,
        }

    @staticmethod
    def _normalize_token(text):
        if text is None:
            return ""
        normalized = unicodedata.normalize("NFKD", str(text))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"[^a-zA-Z0-9]+", "", normalized).lower()
        return normalized

    def _normalize_recommendation_item(self, item):
        """Normaliza un item de recomendación (especialista o chief) con claves alternativas."""
        if not isinstance(item, dict):
            return None

        parameter = (
            item.get("parameter")
            or item.get("parametro")
            or item.get("name")
            or item.get("key")
            or item.get("param")
        )
        new_value = (
            item.get("new_value")
            or item.get("newValue")
            or item.get("nuevo_valor")
            or item.get("nuevoValor")
            or item.get("new")
            or item.get("value")
            or item.get("valor")
        )
        reason = (
            item.get("reason")
            or item.get("razon")
            or item.get("motivo")
            or item.get("justificacion")
            or ""
        )

        if parameter is None or new_value is None:
            return None

        return {
            "parameter": str(parameter).strip(),
            "new_value": str(new_value).strip(),
            "reason": str(reason).strip(),
        }

    @staticmethod
    def _looks_like_internal_text(text):
        low = str(text or "").strip().lower()
        if not low:
            return True

        markers = (
            "copia aqui",
            "copia aquí",
            "escribe tu propia",
            "obligatorio:",
            "json puro",
            "chartinstance",
            "minimalist",
            "assistant",
            "_goals",
            "telimétrica",
        )
        return any(marker in low for marker in markers)

    def _sanitize_reason_text(self, reason_text, fallback_text):
        reason = re.sub(r"\s+", " ", str(reason_text or "")).strip()
        if self._looks_like_internal_text(reason):
            return fallback_text
        return reason

    def _build_fallback_chief_reasoning(self, specialist_reports):
        section_count = len(specialist_reports or [])
        item_count = 0
        no_change_sections = 0
        for report in specialist_reports or []:
            items = report.get("items", []) if isinstance(report, dict) else []
            if not items:
                no_change_sections += 1
            item_count += len(items) if isinstance(items, list) else 0

        return (
            "Consolidacion del Ingeniero Jefe: se revisaron "
            f"{section_count} secciones y {item_count} propuestas de cambio. "
            "Se mantienen los cambios tecnicamente coherentes y se descartan textos internos no validos. "
            f"Secciones sin cambios necesarios: {no_change_sections}."
        )

    @staticmethod
    def _has_asymmetry_justification(reason_text):
        text = str(reason_text or "").lower()
        markers = (
            "asimetr",
            "g force lat",
            "g-force lat",
            "temperatur",
            "desgaste",
            "lado interior",
            "lado exterior",
            "trazado",
            "circuito",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _pick_more_conservative_value(current_left, current_right, value_left, value_right):
        curr_l = _extract_numeric(current_left)
        curr_r = _extract_numeric(current_right)
        val_l = _extract_numeric(value_left)
        val_r = _extract_numeric(value_right)

        if None in (curr_l, curr_r, val_l, val_r):
            return value_left

        delta_if_left = abs(curr_l - val_l) + abs(curr_r - val_l)
        delta_if_right = abs(curr_l - val_r) + abs(curr_r - val_r)
        return value_left if delta_if_left <= delta_if_right else value_right

    def _enforce_axle_symmetry(self, all_reco_map, setup_data):
        """Armoniza valores izquierda/derecha por eje cuando no hay justificación explícita de asimetría."""
        axle_pairs = [("FRONTLEFT", "FRONTRIGHT"), ("REARLEFT", "REARRIGHT")]
        suffix = " Ajuste del Ingeniero Jefe: se armoniza por simetría de eje al no existir justificación explícita de asimetría en telemetría."

        for left_sec, right_sec in axle_pairs:
            left_reco = all_reco_map.get(left_sec, {})
            right_reco = all_reco_map.get(right_sec, {})
            if not left_reco and not right_reco:
                continue

            if left_sec not in all_reco_map:
                all_reco_map[left_sec] = {}
                left_reco = all_reco_map[left_sec]
            if right_sec not in all_reco_map:
                all_reco_map[right_sec] = {}
                right_reco = all_reco_map[right_sec]

            left_setup = setup_data.get(left_sec, {})
            right_setup = setup_data.get(right_sec, {})
            param_keys = set(left_reco.keys()) | set(right_reco.keys())

            for param_key in param_keys:
                left_item = left_reco.get(param_key)
                right_item = right_reco.get(param_key)

                if left_item and right_item:
                    left_val = self._clean_value(left_item.get("new_value", ""))
                    right_val = self._clean_value(right_item.get("new_value", ""))
                    if left_val == right_val:
                        continue

                    reason_text = f"{left_item.get('reason', '')} {right_item.get('reason', '')}".strip()
                    if self._has_asymmetry_justification(reason_text):
                        continue

                    chosen = self._pick_more_conservative_value(
                        self._clean_value(left_setup.get(param_key, "")),
                        self._clean_value(right_setup.get(param_key, "")),
                        left_val,
                        right_val,
                    )
                    left_item["new_value"] = chosen
                    right_item["new_value"] = chosen
                    left_item["reason"] = f"{left_item.get('reason', '').strip()}{suffix}".strip()
                    right_item["reason"] = f"{right_item.get('reason', '').strip()}{suffix}".strip()
                    continue

                source_item = left_item or right_item
                if not source_item:
                    continue

                if self._has_asymmetry_justification(source_item.get("reason", "")):
                    continue

                mirrored = {
                    "parameter": source_item.get("parameter", param_key),
                    "new_value": self._clean_value(source_item.get("new_value", "")),
                    "reason": f"{source_item.get('reason', '').strip()}{suffix}".strip(),
                }

                if left_item is None:
                    left_reco[param_key] = dict(mirrored)
                if right_item is None:
                    right_reco[param_key] = dict(mirrored)

    def _build_setup_agent_reports(self, all_reco_map, specialist_reports=None):
        """Construye reportes de agentes alineados con el setup final consolidado."""
        # Indexar summaries de especialistas por nombre de sección
        specialist_summaries = {}
        for sr in (specialist_reports or []):
            s_name = sr.get("name", "")
            if s_name and sr.get("summary", "").strip():
                specialist_summaries[s_name] = self._sanitize_reason_text(
                    sr["summary"].strip(),
                    f"Analisis consolidado para {self._get_friendly_name(s_name, 'section')}."
                )

        reports = []
        for section_key, items_map in all_reco_map.items():
            if not items_map:
                continue

            normalized_items = []
            for param_key, item in items_map.items():
                normalized = self._normalize_recommendation_item(item)
                if not normalized:
                    continue
                normalized_items.append(
                    {
                        "parameter": self._get_friendly_name(param_key),
                        "new_value": self._clean_value(normalized.get("new_value", "")),
                        "reason": self._sanitize_reason_text(
                            normalized.get("reason", ""),
                            "Cambio consolidado por el Ingeniero Jefe en base a telemetria y coherencia global."
                        ),
                    }
                )

            if not normalized_items:
                continue

            # Usar el summary del especialista si existe, o uno genérico
            summary = specialist_summaries.get(
                section_key,
                f"Valores consolidados para {self._get_friendly_name(section_key, 'section')}."
            )

            reports.append(
                {
                    "name": section_key,
                    "friendly_name": self._get_friendly_name(section_key, "section"),
                    "summary": summary,
                    "items": normalized_items,
                }
            )

        return reports

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
                    reason = self._sanitize_reason_text(
                        reco.get('reason', "Sin cambios requeridos."),
                        "Cambio validado por el Ingeniero Jefe segun telemetria y equilibrio global del setup."
                    )
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

            # Solo incluir secciones que tengan al menos un cambio propuesto
            has_changes = any(
                str(it.get('current', '')) != str(it.get('new', ''))
                for it in items
            )
            if items and has_changes:
                full_setup_recommendations["sections"].append({
                    "name": friendly_section,
                    "section_key": section_name,
                    "items": items
                })

        return full_setup_recommendations

    async def analyze(self, telemetry_summary, setup_data, circuit_name="Desconocido", session_stats=None, model_tag=None, fixed_params=None, driving_telemetry_summary=None, provider="ollama", ollama_base_url=None, ollama_api_key=None):
        provider_key = (provider or "ollama").lower()
        current_provider = getattr(self, "_provider", None)
        needs_init = current_provider != provider_key

        if provider_key == "ollama":
            if self.llm is None:
                needs_init = True
            if model_tag and getattr(self, "_current_model", None) != model_tag:
                needs_init = True
            if ollama_base_url != getattr(self, "_custom_base_url", None):
                needs_init = True
            if ollama_api_key != getattr(self, "_custom_api_key", None):
                needs_init = True

        if needs_init:
            print("Inicializando LLM...")
            self._init_llm(model_tag, provider=provider_key, custom_base_url=ollama_base_url, custom_api_key=ollama_api_key)

        self._log_event(
            logging.INFO,
            "analysis_started",
            provider=provider_key,
            model=getattr(self, "_current_model", model_tag),
            circuit=circuit_name,
            setup_sections=len(setup_data or {}),
        )

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
        fallback_reasons = []

        # 1. Actualizar mapeos si hay nuevos parámetros
        await self.update_mappings(setup_data)

        # Provider-aware telemetry truncation: Jimmy's small context needs much shorter input.
        if provider_key == "jimmy" and len(telemetry_summary) > JIMMY_MAX_TELEMETRY_CHARS:
            ai_telemetry = telemetry_summary[:JIMMY_MAX_TELEMETRY_CHARS] + "\n... [datos truncados para ajuste de contexto LLM]"
        else:
            ai_telemetry = telemetry_summary

        self._log_event(
            logging.INFO,
            "telemetry_sizes",
            original_len=len(telemetry_summary),
            ai_len=len(ai_telemetry),
            provider=provider_key,
        )

        # 2. Análisis de Conducción
        # Usar resumen filtrado (solo canales de técnica de pilotaje) si está disponible
        driving_input = driving_telemetry_summary if driving_telemetry_summary is not None else telemetry_summary
        if provider_key == "jimmy" and len(driving_input) > JIMMY_MAX_TELEMETRY_CHARS:
            driving_input = driving_input[:JIMMY_MAX_TELEMETRY_CHARS] + "\n... [datos truncados]"
        try:
            driving_analysis = await self._get_text_from_llm(DRIVING_PROMPT, {
                "telemetry_summary": driving_input,
                "session_stats": json.dumps(session_stats or {}, indent=2)
            }, min_len=10)
            if not driving_analysis:
                raise ValueError("driving_analysis_empty_or_too_short")
            self._log_event(
                logging.INFO,
                "stage_driving_completed",
                ok=True,
                text_len=len(driving_analysis),
            )
        except Exception as e:
            self._log_event(
                logging.WARNING,
                "stage_driving_completed",
                ok=False,
                error=str(e),
            )
            driving_analysis = "No se pudo obtener el análisis de conducción."
            fallback_reasons.append("driving_analysis_empty_or_too_short")

        # 3. Análisis de Setup por secciones (un agente por cada sección)
        specialist_reports = []
        specialist_sections_attempted = 0

        for section_name, section_data in setup_data.items():
            if section_name.upper() in ("BASIC", "LEFTFENDER", "RIGHTFENDER"):
                continue

            filtered_data = {k: v for k, v in section_data.items() if not (k.startswith('Gear') and 'Setting' in k)}
            if not filtered_data:
                continue

            specialist_sections_attempted += 1

            cleaned_data = {k: self._clean_value(v) for k, v in filtered_data.items()}

            friendly_section = self._get_friendly_name(section_name, 'section')
            report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                "section_name": friendly_section,
                "telemetry_summary": ai_telemetry,
                "section_data": json.dumps(cleaned_data, indent=2),
                "context_data": "N/A",
                "circuit_name": circuit_name,
                "fixed_params_prompt": fixed_params_prompt
            })
            if report:
                normalized_report = self._normalize_specialist_report(report)
                specialist_reports.append(
                    {
                        "name": section_name,
                        "friendly_name": self._get_friendly_name(section_name, 'section'),
                        "items": normalized_report.get("items", []),
                        "summary": normalized_report.get("summary", ""),
                    }
                )

        specialist_items = sum(
            len(r.get("items", [])) for r in specialist_reports if isinstance(r.get("items", []), list)
        )
        specialist_reasons = 0
        for report in specialist_reports:
            items = report.get("items", [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and str(item.get("reason", "")).strip():
                    specialist_reasons += 1
        self._log_event(
            logging.INFO,
            "stage_specialists_completed",
            attempted=specialist_sections_attempted,
            reports=len(specialist_reports),
            items=specialist_items,
            reasons=specialist_reasons,
        )

        # Preparar resumen del setup actual para el ingeniero jefe
        current_setup_summary = self._build_current_setup_summary(setup_data)

        # Ingeniero Jefe (paso final de consolidación)
        chief_engineer_report = await self._get_json_from_llm(CHIEF_ENGINEER_PROMPT, {
            "specialist_reports": json.dumps(specialist_reports, indent=2),
            "telemetry_summary": ai_telemetry,
            "circuit_name": circuit_name,
            "current_setup": current_setup_summary,
            "memory_context": "N/A",
            "fixed_params_prompt": fixed_params_prompt
        }, validate_fn=lambda data: isinstance(data, dict) and isinstance(data.get("full_setup", {}).get("sections", None), list))
        chief_sections_count = 0
        chief_reasoning_len = 0
        if chief_engineer_report:
            chief_sections_count = len(chief_engineer_report.get("full_setup", {}).get("sections", []))
            chief_reasoning_len = len((chief_engineer_report.get("chief_reasoning") or "").strip())
        self._log_event(
            logging.INFO,
            "stage_chief_completed",
            ok=bool(chief_engineer_report),
            sections=chief_sections_count,
            reasoning_len=chief_reasoning_len,
        )

        # Guardar razonamiento del jefe en memoria (con contexto completo)
        chief_reasoning = ""
        if chief_engineer_report:
            chief_reasoning = self._sanitize_reason_text(
                chief_engineer_report.get("chief_reasoning", ""),
                self._build_fallback_chief_reasoning(specialist_reports),
            )
            self._agent_reports_cache = specialist_reports
            self.chief_memory.append({
                "action": "análisis_inicial",
                "reasoning": chief_reasoning,
                "agent_reports": json.dumps(specialist_reports, indent=2, default=str),
                "timestamp": time.strftime("%H:%M:%S")
            })
        else:
            chief_reasoning = self._build_fallback_chief_reasoning(specialist_reports)

        # 4. Formatear respuesta para el frontal
        all_reco_map = {}
        specialist_map = {}
        chief_map = {}

        inv_params = {v: k for k, v in self.mapping.get("parameters", {}).items()}

        # Base determinista: propuestas de especialistas (se preservan por defecto)
        for s_report in specialist_reports:
            s_name = s_report.get("name", "")
            if not s_name:
                continue
            specialist_map.setdefault(s_name, {})
            for item in s_report.get("items", []):
                normalized_item = self._normalize_recommendation_item(item)
                if not normalized_item:
                    continue

                p_name = normalized_item.get("parameter", "")
                internal_p_name = inv_params.get(p_name, p_name)
                summary_fallback = (s_report.get("summary") or "").strip()
                fallback_reason = summary_fallback or "Cambio propuesto por especialista y validado en consolidacion."
                normalized_item["reason"] = self._sanitize_reason_text(
                    normalized_item.get("reason", ""),
                    fallback_reason,
                )
                specialist_map[s_name][internal_p_name] = normalized_item

        # Override del jefe: solo reemplaza/ajusta parametros que si devolvio.
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

                if internal_name not in chief_map:
                    chief_map[internal_name] = {}

                for item in c_section.get("items", []):
                    normalized_item = self._normalize_recommendation_item(item)
                    if not normalized_item:
                        continue

                    p_name = normalized_item.get("parameter", "")
                    # Intento de corrección si el LLM usó el nombre amigable del parámetro
                    internal_p_name = inv_params.get(p_name, p_name)

                    specialist_reason = (
                        specialist_map.get(internal_name, {})
                        .get(internal_p_name, {})
                        .get("reason", "")
                    )
                    fallback_reason = specialist_reason or "Cambio consolidado por el Ingeniero Jefe en base a telemetria."
                    normalized_item["reason"] = self._sanitize_reason_text(
                        normalized_item.get("reason", ""),
                        fallback_reason,
                    )

                    chief_map[internal_name][internal_p_name] = normalized_item

        # Merge final: conservar especialistas y aplicar overrides del jefe.
        for section_name, section_items in specialist_map.items():
            all_reco_map.setdefault(section_name, {}).update(section_items)
        for section_name, section_items in chief_map.items():
            all_reco_map.setdefault(section_name, {}).update(section_items)

        # Fallback secundario: si el chief devolvió JSON válido pero sin ítems dentro,
        # mantener solo especialistas y marcar motivo de degradacion.
        chief_total_items = sum(len(v) for v in chief_map.values())
        if chief_total_items == 0 and specialist_reports and "chief_no_items" not in fallback_reasons:
            fallback_reasons.append("chief_no_items")
            self._log_event(
                logging.WARNING,
                "chief_fallback_to_specialists",
                reason="chief_no_items",
                specialist_reports=len(specialist_reports),
            )

        self._log_event(
            logging.INFO,
            "reco_map_summary",
            sections=list(all_reco_map.keys()),
            items_per_section={k: len(v) for k, v in all_reco_map.items()},
        )

        # Normalización determinista para evitar asimetrías izquierda/derecha no justificadas.
        self._enforce_axle_symmetry(all_reco_map, setup_data)
        setup_agent_reports = self._build_setup_agent_reports(all_reco_map, specialist_reports)

        full_setup_recommendations = self._format_full_setup(all_reco_map, setup_data)

        fallback_cfg = self._jimmy_fallback_cfg()
        failure_signal_cfg = fallback_cfg.get("failureSignal", {})
        should_signal_degraded = bool(failure_signal_cfg.get("degraded", False))
        reason_field = failure_signal_cfg.get("reasonField", "fallback_reason")
        unique_reasons = []
        for reason in fallback_reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)
        fallback_reason_text = "; ".join(unique_reasons)

        result = {
            "driving_analysis": driving_analysis,
            "setup_analysis": "Análisis completo realizado por el equipo de ingenieros de pista. Se han evaluado todos los canales de telemetría curva a curva.",
            "full_setup": full_setup_recommendations,
            "agent_reports": specialist_reports,
            "setup_agent_reports": setup_agent_reports,
            "chief_reasoning": chief_reasoning
        }

        if provider_key == "jimmy" and should_signal_degraded and fallback_reason_text:
            result["degraded"] = True
            result[reason_field] = fallback_reason_text

        result["llm_provider"] = provider_key
        result["llm_model"] = getattr(self, "_current_model", model_tag or "")

        if fallback_reason_text:
            self._log_event(
                logging.WARNING,
                "analysis_completed",
                provider=provider_key,
                model=result["llm_model"],
                degraded=bool(result.get("degraded", False)),
                fallback_reason=fallback_reason_text,
                specialists_reports=len(specialist_reports),
                specialist_reasons=specialist_reasons,
                chief_present=bool(chief_engineer_report),
            )
        else:
            self._log_event(
                logging.INFO,
                "analysis_completed",
                provider=provider_key,
                model=result["llm_model"],
                degraded=False,
                specialists_reports=len(specialist_reports),
                specialist_reasons=specialist_reasons,
                chief_present=bool(chief_engineer_report),
            )

        return result
