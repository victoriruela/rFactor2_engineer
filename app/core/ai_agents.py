import json
import re
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
import os
from dotenv import load_dotenv

load_dotenv()

# --- PROMPTS ---

DRIVING_PROMPT = """
Eres un ingeniero de pista experto en rFactor 2.
Analiza los datos de telemetría de la sesión completa:
{telemetry_summary}
Estadísticas generales: {session_stats}

Identifica los puntos exactos donde el piloto está perdiendo tiempo por MALA CONDUCCIÓN, buscando patrones que se repiten a lo largo de las vueltas.
No te inventes datos. Usa únicamente la información proporcionada.
Responde SIEMPRE en CASTELLANO.

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
Considera el contexto de las otras secciones (especialmente si eres de Neumáticos o Suspensión).

Instrucciones estrictas:
1. Incluye TODOS los parámetros de {section_data}.
2. Si un parámetro no cambia, explica técnicamente por qué el valor actual es ya óptimo.
3. Responde SIEMPRE en CASTELLANO.

JSON puro:
{{
  "items": [
    {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación técnica" }}
  ]
}}
"""

TIRES_SUSPENSION_LEAD_PROMPT = """
Eres el Jefe de Neumáticos y Suspensión. 
Has recibido las propuestas de los ingenieros de cada neumático y de suspensión.
Tu objetivo es CORRELACIONAR esta información para asegurar un equilibrio perfecto del coche.
CIRCUITO: {circuit_name}
RESUMEN TELEMETRÍA: {telemetry_summary}

Propuestas recibidas:
{proposals}

Genera un informe consolidado y coherente para el Jefe de Ingenieros.
JSON puro:
{{
  "sections": [
    {{
      "name": "NombreSeccion",
      "items": [
        {{ "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificación coordinada" }}
      ]
    }}
  ]
}}
"""

CHIEF_ENGINEER_PROMPT = """
Eres el Ingeniero Jefe de Competición. Tu responsabilidad es dar la palabra final sobre el setup completo.
Recibes informes de los especialistas de cada área y del Jefe de Neumáticos y Suspensión.

CIRCUITO: {circuit_name}
RESUMEN TELEMETRÍA: {telemetry_summary}

Informes de especialistas:
{specialist_reports}

Debes devolver el setup completo final, asegurando que todas las recomendaciones son coherentes entre sí y maximizan el rendimiento en {circuit_name}.
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

class AIAngineer:
    def __init__(self):
        self.llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY", "TU_API_KEY"),
            model_name="llama-3.3-70b-versatile"
        )
        self.output_parser = StrOutputParser()
        self.mapping_path = "app/core/param_mapping.json"
        self.mapping = self._load_mapping()

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
        # 1. Actualizar mapeos si hay nuevos parámetros
        await self.update_mappings(setup_data)

        # 2. Análisis de Conducción
        driving_prompt = PromptTemplate.from_template(DRIVING_PROMPT)
        driving_chain = driving_prompt | self.llm | self.output_parser
        driving_analysis = await driving_chain.ainvoke({
            "telemetry_summary": telemetry_summary, 
            "circuit_name": circuit_name,
            "session_stats": str(session_stats or {})
        })

        # 3. Análisis de Setup Jerárquico
        specialist_reports = []
        tires_susp_proposals = []
        
        # Identificar secciones de neumáticos y suspensión
        tires_susp_sections = ["FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT", "LEFTFRONT", "RIGHTFRONT", "LEFTREAR", "RIGHTREAR", "SUSPENSION"]
        
        # Preparar contexto para neumáticos y suspensión
        tires_susp_context = {s: setup_data[s] for s in setup_data if s in tires_susp_sections}
        
        for section_name, section_data in setup_data.items():
            # Traducir sección para el prompt
            friendly_section = self._get_friendly_name(section_name, 'section')
            
            if section_name in tires_susp_sections:
                # Agente de neumáticos o suspensión (con contexto compartido)
                report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                    "section_name": friendly_section,
                    "telemetry_summary": telemetry_summary,
                    "section_data": str(section_data),
                    "context_data": str(tires_susp_context),
                    "circuit_name": circuit_name
                })
                if report:
                    tires_susp_proposals.append({"name": section_name, "items": report.get("items", [])})
            else:
                # Otros especialistas (Motor, Aerodinámica, etc.)
                report = await self._get_json_from_llm(SECTION_AGENT_PROMPT, {
                    "section_name": friendly_section,
                    "telemetry_summary": telemetry_summary,
                    "section_data": str(section_data),
                    "context_data": "N/A",
                    "circuit_name": circuit_name
                })
                if report:
                    specialist_reports.append({"name": section_name, "items": report.get("items", [])})

        # Jefe de Neumáticos y Suspensión
        tires_susp_lead_report = await self._get_json_from_llm(TIRES_SUSPENSION_LEAD_PROMPT, {
            "proposals": json.dumps(tires_susp_proposals),
            "telemetry_summary": telemetry_summary,
            "circuit_name": circuit_name
        })
        
        if tires_susp_lead_report:
            specialist_reports.extend(tires_susp_lead_report.get("sections", []))

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
