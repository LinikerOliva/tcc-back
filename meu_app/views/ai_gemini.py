# Simple Gemini client wrapper for backend summarization
# Uses google-generativeai SDK if available; otherwise falls back to HTTP via requests.

import json
import os

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENERATIVEAI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

_SYSTEM_PROMPT = """
Você é um assistente médico que lê a transcrição de uma consulta e retorna um resumo estruturado.
Responda em JSON estrito com as chaves:
{
  "queixa": string,
  "historia_doenca_atual": string,
  "diagnostico_principal": string,
  "conduta": string,
  "medicamentos": string,
  "posologia": string,
  "alergias": string,
  "pressao": string,
  "frequencia_cardiaca": string,
  "temperatura": string,
  "saturacao": string
}
Formate as unidades quando possível (ex.: 120/80 mmHg, 75 bpm, 36.5 °C, 98%).
Se algum dado não estiver na transcrição, deixe a string vazia.
""".strip()


def _ensure_sdk():
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        return None
    if not API_KEY:
        return None
    try:
        genai.configure(api_key=API_KEY)
    except Exception:
        return None
    return genai


def summarize_transcript(transcript: str, contexto: dict | None = None) -> dict:
    """Summarize using Gemini and return a normalized JSON dict.
    If SDK unavailable or fails, tries HTTP.
    """
    context_txt = json.dumps(contexto or {}, ensure_ascii=False)
    user_text = f"{_SYSTEM_PROMPT}\n\nContexto prévio (opcional): {context_txt}\n\nTranscrição:\n{transcript or ''}"

    # Try SDK first
    genai = _ensure_sdk()
    if genai is not None:
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            resp = model.generate_content(user_text)
            text = getattr(resp, "text", None) or ""
            if not text and getattr(resp, "candidates", None):
                try:
                    text = resp.candidates[0].content.parts[0].text
                except Exception:
                    text = ""
            if text:
                try:
                    json_str = _extract_json(text)
                    return json.loads(json_str)
                except Exception:
                    return {"summary_text": text}
        except Exception:
            pass

    # Fallback: HTTP via requests
    if not API_KEY:
        return {"error": "GEMINI_API_KEY não configurada"}

    import requests  # lazy import
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user_text}]}
        ]
    }
    try:
        r = requests.post(endpoint, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        text = (
            (data.get("candidates") or [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if text:
            try:
                json_str = _extract_json(text)
                return json.loads(json_str)
            except Exception:
                return {"summary_text": text}
        return {"error": "Resposta vazia do Gemini"}
    except Exception as e:
        return {"error": str(e)}


def _extract_json(text: str) -> str:
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else text