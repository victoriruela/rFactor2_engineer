"""Debug script: test what Jimmy returns for a specialist prompt."""
import requests

test_prompt = (
    "Eres un Ingeniero Especialista en FRONTWING para rFactor 2.\n\n"
    "DATOS DE TELEMETRIA: Speed,Throttle\n100,80\n120,90\n\n"
    'PARAMETROS ACTUALES DE FRONTWING: {"FrontWingSetting": "5"}\n\n'
    "TU MISION: Analiza y propone cambios con valores reales.\n\n"
    "PARAMETROS FIJOS: Ninguno.\n\n"
    "JSON puro:\n"
    '{\n  "items": [\n    { "parameter": "NombreOriginal", "new_value": "ValorRecomendado", "reason": "Justificacion" }\n  ],\n  "summary": "Resumen tecnico"\n}\n'
)

resp = requests.post(
    "https://chatjimmy.ai/api/chat",
    headers={
        "Content-Type": "application/json",
        "Referer": "https://chatjimmy.ai/",
        "Origin": "https://chatjimmy.ai",
    },
    json={
        "messages": [{"role": "user", "content": test_prompt}],
        "chatOptions": {
            "selectedModel": "llama3.1-8B",
            "systemPrompt": (
                "Eres Jimmy (llama3.1-8B) ingeniero de pista rFactor2. "
                "Tono tecnico, breve y accionable. "
                "Si se solicita estructura, responde SOLO JSON estricto, sin texto extra ni markdown. "
                "No inventes vueltas, curvas ni distancias fuera de la telemetria dada. "
                "Especialistas: entrega items con parameter, new_value y reason, enfocados en cambios reales. "
                "Chief: integra propuestas validas de especialistas y conserva su razonamiento tecnico."
            ),
            "topK": 4,
            "temperature": 0.2,
        },
        "attachment": None,
    },
    timeout=90,
)
print("STATUS:", resp.status_code)
print("FULL RESPONSE:")
print(repr(resp.text))
print("\nFIRST 800 chars:")
print(resp.text[:800])
