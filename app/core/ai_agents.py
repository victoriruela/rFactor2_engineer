import json
import re
import asyncio
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_community.llms import GPT4All
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
import os
import g4f
import g4f.debug
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURACIÓN G4F ---
g4f.debug.logging = False

# --- PROMPTS ---

DRIVING_PROMPT = """
Eres un ingeniero de pista experto en rFactor 2.
Analiza los datos de telemetría de la sesión completa:
{telemetry_summary}
Estadísticas generales: {session_stats}

Identifica los puntos exactos donde el piloto está perdiendo tiempo por MALA CONDUCCIÓN, buscando patrones que se repiten a lo largo de las vueltas.
No te inventes datos. Usa únicamente la información proporcionada.
Responde SIEMPRE en CASTELLANO. IMPORTANTE: Sé directo y breve, no te enrolles.

Para cada punto indica:
1. Localización (Curva X o Nombre de la Curva).
2. Motivo técnico (Ej: Frenar demasiado tarde, no usar todo el ancho de pista, mala gestión de RPM, exceso de deslizamiento).
3. Cómo mejorarlo de forma específica.

Formato de respuesta:
- Curva X: [Motivo] -> [Mejora]
"""

SECTION_AGENT_PROMPT = """
SITUACIÓN: Circuito de {circuit_name} en rFactor 2.
RESUMEN TELEMETRÍA: {telemetry_summary}
VALORES ACTUALES ({section_name}): {section_data}
CONTEXTO ADICIONAL (Otras secciones relacionadas): {context_data}

Tu tarea es actuar como un Ingeniero Especialista en {section_name}. Analiza CADA parámetro.
Debes ser CRÍTICO y buscar patrones en la telemetría de toda la sesión.

Instrucciones estrictas:
1. Incluye TODOS los parámetros de {section_data}.
2. Si un parámetro no cambia, explica técnicamente por qué el valor actual es ya óptimo.
3. No sugieras cambios dinámicos "en pista" (como ajustar alerones o muelles mientras el coche corre). Los cambios son para el setup en el garaje.
4. Responde SIEMPRE en CASTELLANO.
5. Devuelve ÚNICAMENTE el JSON puro, sin texto adicional antes ni después.

JSON puro:
{{
  "items": [
    {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica" }}
  ]
}}
"""

TIRES_SUSPENSION_ANALYSIS_PROMPT = """
Eres un Ingeniero Especialista en Neumáticos y Suspensión de rFactor 2.
CIRCUITO: {circuit_name}
RESUMEN TELEMETRÍA: {telemetry_summary}
DATOS DE SETUP (5 SECCIONES): {setup_data}

Analiza en conjunto las 4 secciones de neumáticos y la de suspensión. Busca patrones de desgaste, temperaturas y comportamiento mecánico.
Propón cambios específicos para optimizar el paso por curva y la estabilidad.

Instrucciones:
1. Analiza los parámetros de las 5 secciones.
2. No sugieras cambios dinámicos "en pista" (como ajustar alerones o muelles mientras el coche corre). Los cambios son para el setup en el garaje.
3. Responde en CASTELLANO.

JSON puro:
{{
  "sections": [
    {{
      "name": "NombreSeccionInterno",
      "items": [
        {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica" }}
      ]
    }}
  ]
}}
"""

TIRES_SUSPENSION_VALIDATION_PROMPT = """
Eres el Ingeniero Jefe de Dinámica Vehicular. 
Debes validar y mejorar las propuestas del primer ingeniero para las secciones de Neumáticos y Suspensión.
CIRCUITO: {circuit_name}
RESUMEN TELEMETRÍA: {telemetry_summary}
DATOS ORIGINALES: {original_setup}
PROPUESTAS DEL PRIMER INGENIERO: {first_proposals}

Tu tarea:
1. Revisa si las propuestas son coherentes.
2. Añade nuevas propuestas si crees que falta algo importante.
3. Asegura que NO haya sugerencias de cambios imposibles de realizar en pista (ajustes de setup fijo).
4. Responde en CASTELLANO.

JSON puro:
{{
  "sections": [
    {{
      "name": "NombreSeccionInterno",
      "items": [
        {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación final validada" }}
      ]
    }}
  ]
}}
"""

CHIEF_ENGINEER_PROMPT = """
Eres el Ingeniero Jefe de Competición. Tu responsabilidad es dar la palabra final sobre el setup completo.
Recibes informes de los especialistas de cada área y del equipo de Neumáticos y Suspensión.

CIRCUITO: {circuit_name}
RESUMEN TELEMETRÍA: {telemetry_summary}

Informes de especialistas:
{specialist_reports}

Debes devolver el setup completo final, asegurando que todas las recomendaciones son coherentes.
ADVERTENCIA: No permitas sugerencias de cambios "en pista" para parámetros que solo se ajustan en el garaje (alerones, suspensiones, etc.). Todo el setup es para ser aplicado antes de salir a pista.
Responde SIEMPRE en CASTELLANO.

JSON puro:
{{
  "full_setup": {{
    "sections": [
      {{
        "name": "NombreSeccionInterno",
        "items": [
          {{ "parameter": "NombreOriginal", "new_value": "ValorFinal", "reason": "Justificación final del Jefe de Ingenieros" }}
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

class G4FLLM:
    """Wrapper minimalista para g4f compatible con el flujo de AIAngineer"""
    def __init__(self, model=None):
        # Usar un modelo y proveedor por defecto que suela ser más estable
        self.model = model or "gpt-4o"
    
    async def ainvoke(self, input_data):
        # El input de LangChain suele ser un PromptValue o string
        prompt = str(input_data)
        
        # Lista de proveedores solo estables y rápidos
        candidate_providers = [
            "PollinationsAI",
            "DeepInfra"
        ]
        
        providers = []
        for p_name in candidate_providers:
            if hasattr(g4f.Provider, p_name):
                providers.append(getattr(g4f.Provider, p_name))
        
        # Opción automática desactivada para mayor velocidad
        #providers.append(None)
        
        last_error = None
        for provider in providers:
            provider_name = provider.__name__ if provider else "Auto"
            try:
                # Intentar primero con el modelo solicitado
                # Si falla, intentaremos con el modelo por defecto del proveedor
                models_to_try = [self.model, ""]
                
                for model_name in models_to_try:
                    try:
                        response = await asyncio.wait_for(
                            g4f.ChatCompletion.create_async(
                                model=model_name,
                                provider=provider,
                                messages=[{"role": "user", "content": prompt}],
                            ),
                            timeout=15.0
                        )
                        if response and len(str(response)) > 10:
                            # Si el proveedor devuelve HTML (error común), lo ignoramos
                            if str(response).strip().startswith("<!DOCTYPE"):
                                continue
                            return str(response)
                    except (asyncio.TimeoutError, Exception):
                        continue
                        
            except Exception as e:
                last_error = e
                continue
                
        print(f"Error en G4F (todos los proveedores fallaron): {last_error}")
        return f"Error en el modelo gratuito: {last_error}. Prueba a cambiar el LLM_PROVIDER en el .env si el problema persiste."

    def __or__(self, other):
        # Soporte básico para el operador pipe de LangChain
        return G4FChain(self, other)

class G4FChain:
    def __init__(self, llm, next_component):
        self.llm = llm
        self.next_component = next_component

    async def ainvoke(self, inputs):
        # Si el componente anterior es un PromptTemplate
        if hasattr(self.llm, "format"):
            prompt = self.llm.format(**inputs)
            response = await self.next_component.ainvoke(prompt)
            return response
        
        # Flujo estándar: Prompt | LLM | Parser
        # Aquí inputs son los argumentos para el prompt
        prompt_tmpl = self.llm # Asumimos que es el PromptTemplate
        prompt_str = prompt_tmpl.format(**inputs)
        
        # Llamar al LLM (next_component es el G4FLLM en este caso o el Parser)
        if isinstance(self.next_component, G4FLLM):
            res = await self.next_component.ainvoke(prompt_str)
            return res
        return None

class AIAngineer:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "free-api").lower()
        self.llm = None
        self.output_parser = StrOutputParser()
        self.mapping_path = "app/core/param_mapping.json"
        self.mapping = self._load_mapping()

    def _init_llm(self):
        if self.provider == "groq":
            self.llm = ChatGroq(
                api_key=os.getenv("GROQ_API_KEY", "TU_API_KEY"),
                model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            )
        elif self.provider == "ollama":
            self.llm = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "llama3"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            )
        elif self.provider == "free-api":
            # Nuevo proveedor gratuito sin login
            self.llm = G4FLLM()
        else:
            # Proveedor LOCAL (Descarga directa mediante GPT4All)
            model_name = os.getenv("LOCAL_MODEL_NAME", "Llama-3.2-3B-Instruct-Q4_0.gguf")
            model_path = os.getenv("LOCAL_MODEL_PATH", "./models")
            if not os.path.exists(model_path):
                os.makedirs(model_path)
            
            full_path = os.path.join(model_path, model_name)
            print(f"Usando modelo local: {full_path}")
            
            # Intentar inicializar gpt4all directamente para asegurar la descarga y carga
            from gpt4all import GPT4All as GPT4AllModel
            # Esto descargará el modelo si no existe
            _ = GPT4AllModel(model_name=model_name, model_path=model_path, allow_download=True)

            self.llm = GPT4All(
                model=full_path,
                allow_download=False, # Ya está descargado
                verbose=True,
                n_ctx=4096 # Aumentar ventana de contexto a 4096
            )

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
        if self.provider == "free-api":
            # Manejo especial para G4F ya que no es un objeto LangChain completo
            prompt_tmpl = PromptTemplate.from_template(prompt)
            prompt_str = prompt_tmpl.format(**inputs)
            response = await self.llm.ainvoke(prompt_str)
        else:
            prompt_tmpl = PromptTemplate.from_template(prompt)
            chain = prompt_tmpl | self.llm | self.output_parser
            try:
                response = await chain.ainvoke(inputs)
            except Exception as e:
                response = ""
                print(f"Error en LLM: {e}")

        try:
            # Buscar el bloque JSON más externo
            json_match = re.search(r'(\{.*\})', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    # Intentar limpiar si hay comas finales o problemas menores
                    cleaned = re.sub(r',\s*\}', '}', json_match.group(1))
                    cleaned = re.sub(r',\s*\]', ']', cleaned)
                    return json.loads(cleaned)
        except Exception as e:
            error_msg = str(e)
            if "Connection error" in error_msg or "all connection attempts failed" in error_msg.lower():
                print(f"CRÍTICO: No se pudo conectar con {self.provider.upper()}.")
            else:
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

    async def analyze(self, telemetry_summary, setup_data, circuit_name="Desconocido", session_stats=None):
        if self.llm is None:
            print("Inicializando LLM...")
            self._init_llm()
            print(f"LLM listo con proveedor: {self.provider}")
        # 1. Actualizar mapeos si hay nuevos parámetros
        await self.update_mappings(setup_data)

        # 2. Análisis de Conducción
        if self.provider == "free-api":
            prompt_tmpl = PromptTemplate.from_template(DRIVING_PROMPT)
            prompt_str = prompt_tmpl.format(
                telemetry_summary=telemetry_summary, 
                circuit_name=circuit_name,
                session_stats=str(session_stats or {})
            )
            driving_analysis = await self.llm.ainvoke(prompt_str)
        else:
            driving_prompt = PromptTemplate.from_template(DRIVING_PROMPT)
            driving_chain = driving_prompt | self.llm | self.output_parser
            driving_analysis = await driving_chain.ainvoke({
                "telemetry_summary": telemetry_summary, 
                "circuit_name": circuit_name,
                "session_stats": str(session_stats or {})
            })

        # 3. Análisis de Setup Jerárquico
        specialist_reports = []
        tires_susp_sections = ["FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT", "LEFTFRONT", "RIGHTFRONT", "LEFTREAR", "RIGHTREAR", "SUSPENSION"]
        
        # Preparar datos para neumáticos y suspensión (5 secciones)
        tires_susp_setup = {s: setup_data[s] for s in setup_data if s in tires_susp_sections}
        
        # FLUJO NUEVO: Dos agentes secuenciales para Neumáticos y Suspensión
        # Agente 1: Propuesta inicial
        first_tires_susp_report = await self._get_json_from_llm(TIRES_SUSPENSION_ANALYSIS_PROMPT, {
            "setup_data": str(tires_susp_setup),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        
        # Agente 2: Validación y mejora
        final_tires_susp_report = await self._get_json_from_llm(TIRES_SUSPENSION_VALIDATION_PROMPT, {
            "original_setup": str(tires_susp_setup),
            "first_proposals": json.dumps(first_tires_susp_report) if first_tires_susp_report else "Sin propuestas",
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        
        if final_tires_susp_report:
            specialist_reports.extend(final_tires_susp_report.get("sections", []))
        elif first_tires_susp_report:
            specialist_reports.extend(first_tires_susp_report.get("sections", []))
        
        # Analizar otras secciones (Aerodinámica, Motor, etc.)
        for section_name, section_data in setup_data.items():
            if section_name in tires_susp_sections:
                continue # Ya procesadas arriba
                
            friendly_section = self._get_friendly_name(section_name, 'section')
            report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                "section_name": friendly_section,
                "telemetry_summary": telemetry_summary,
                "section_data": str(section_data),
                "context_data": "N/A",
                "circuit_name": circuit_name
            })
            if report:
                specialist_reports.append({"name": section_name, "items": report.get("items", [])})

        # Ingeniero Jefe de Ingenieros (Paso final)
        final_setup_json = await self._get_json_from_llm(CHIEF_ENGINEER_PROMPT, {
            "specialist_reports": json.dumps(specialist_reports),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })

        # 4. Formatear respuesta para el frontal
        full_setup_recommendations = {"sections": []}
        
        # Obtener secciones del Jefe de Ingenieros o fallback a especialistas
        final_sections_raw = []
        if final_setup_json and "full_setup" in final_setup_json:
            final_sections_raw = final_setup_json["full_setup"].get("sections", [])
        
        # Si el jefe de ingenieros no devolvió secciones, usamos los reportes individuales
        if not final_sections_raw:
            final_sections_raw = specialist_reports

        # Mapear secciones finales para fácil acceso
        final_sections_map = {s.get("name", ""): s for s in final_sections_raw}

        # Iterar sobre TODAS las secciones originales del setup
        for section_name, orig_section_data in setup_data.items():
            friendly_section = self._get_friendly_name(section_name, 'section')
            items = []
            
            # Buscar si el Ingeniero Jefe tiene recomendaciones para esta sección
            reco_section = final_sections_map.get(section_name)
            reco_map = {str(item.get('parameter', '')): item for item in reco_section.get('items', [])} if reco_section else {}

            for param_key, current_val in orig_section_data.items():
                # Ocultar relaciones de marchas fijas
                if param_key.startswith("Gear") and "Setting" in param_key:
                    num_part = param_key.replace("Gear", "").replace("Setting", "")
                    if num_part.isdigit(): continue

                reco = reco_map.get(param_key)
                clean_curr = self._clean_value(current_val)
                
                # Intentar limpiar también el valor recomendado
                reco_val = self._clean_value(reco['new_value']) if reco else clean_curr
                
                items.append({
                    "parameter": self._get_friendly_name(param_key),
                    "current": clean_curr,
                    "new": reco_val,
                    "reason": reco['reason'] if reco else "Analizado por el Ingeniero Jefe. Sin cambios requeridos."
                })
            
            if items:
                full_setup_recommendations["sections"].append({
                    "name": friendly_section,
                    "items": items
                })

        return {
            "driving_analysis": driving_analysis,
            "setup_analysis": "Análisis completo realizado por el equipo de ingenieros de pista.",
            "full_setup": full_setup_recommendations
        }
