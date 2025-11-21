# Simple Gemini client wrapper for backend summarization
# Uses google-generativeai SDK if available; otherwise falls back to HTTP via requests.

import json
import os

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENERATIVEAI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

_SYSTEM_PROMPT = """
Você é um assistente médico que lê a transcrição de uma consulta e retorna um resumo estruturado.
Responda APENAS JSON estrito com as chaves:
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
Regra de medicamentos: identifique linhas de prescrição mesmo sem rótulo, procurando padrões como dosagens (mg, ml, g, mcg), formas farmacêuticas (comprimido, cápsula, gotas, spray), frequências (1x ao dia, 12/12h, a cada N h) e durações (por N dias/semanas). Se houver múltiplos itens, una em uma string separada por \n. Em "posologia", coloque instruções de uso e frequência.
Formate unidades (mmHg, bpm, °C, %). Se um dado não existir, use string vazia.
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
                    result = json.loads(json_str)
                    return _postprocess(result, transcript)
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
                result = json.loads(json_str)
                return _postprocess(result, transcript)
            except Exception:
                return {"summary_text": text}
        return {"error": "Resposta vazia do Gemini"}
    except Exception as e:
        return {"error": str(e)}


def _extract_json(text: str) -> str:
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else text


def _postprocess(obj: dict, source_txt: str) -> dict:
    out = {
        "queixa": str(obj.get("queixa") or ""),
        "historia_doenca_atual": str(obj.get("historia_doenca_atual") or obj.get("historia") or ""),
        "diagnostico_principal": str(obj.get("diagnostico_principal") or obj.get("diagnostico") or ""),
        "conduta": str(obj.get("conduta") or ""),
        "medicamentos": str(obj.get("medicamentos") or ""),
        "posologia": str(obj.get("posologia") or ""),
        "alergias": str(obj.get("alergias") or ""),
        "pressao": str(obj.get("pressao") or ""),
        "frequencia_cardiaca": str(obj.get("frequencia_cardiaca") or ""),
        "temperatura": str(obj.get("temperatura") or ""),
        "saturacao": str(obj.get("saturacao") or ""),
    }

    meds, poso = _extract_meds(source_txt or "")
    if not out["medicamentos"] and meds:
        out["medicamentos"] = meds
    if not out["posologia"] and poso:
        out["posologia"] = poso

    return out


def _extract_meds(text: str) -> tuple[str, str]:
    import re
    txt = str(text or "")
    lines = [l.strip() for l in txt.replace("\r", "").split("\n") if l.strip()]
    candidates = []
    for l in lines:
        if re.search(r"\b(mg|ml|g|mcg|comprimid|c[áa]psul|gotas|spray)\b", l, re.I):
            candidates.append(l)
        elif re.search(r"\b(vou\s+(te\s+)?(receitar|prescrever|indicar|recomendar))\b", l, re.I):
            candidates.append(l)
        elif re.search(r"\b(associar|usar|tomar)\b.*\b(metoclopramida|ondansetrona|domperidona)\b", l, re.I):
            candidates.append(l)
    if not candidates:
        for m in re.finditer(r"(?:vou\s+(?:te\s+)?(?:receitar|prescrever|indicar|recomendar)\s+)([^\.;\n]+)", txt, re.I):
            candidates.append(m.group(0).strip())
        for m in re.finditer(r"(?:pode\s+associar|associar|usar|tomar)[^\n\.;]*(metoclopramida|ondansetrona|domperidona)[^\n\.;]*", txt, re.I):
            candidates.append(m.group(0).strip())
    if not candidates:
        m = re.search(r"(.+?(\d+\s?(mg|ml|g|mcg)|comprimid|c[áa]psul|gotas|spray).*)", txt, re.I)
        if m:
            candidates.append(m.group(1).strip())
    # Extrair nomes limpos (evitar parágrafos completos)
    name_set = set()
    known = [r"buscopan\s+composto", r"metoclopramida", r"ondansetrona", r"domperidona", r"dipirona"]
    for k in known:
        m = re.search(rf"\b{k}\b", txt, re.I)
        if m: name_set.add(m.group(0).strip())
    for l in candidates:
        nm = re.search(r"^([A-Za-zÀ-ÿ0-9 .+\-]+?)(?:\s+\d+\s?(mg|ml|g|mcg)|\s*[–-])", l)
        if nm: name_set.add(nm.group(1).strip())
    medicamentos = "\n".join(name_set) if name_set else "\n".join(candidates)
    def _norm_freq(s: str) -> str | None:
        m1 = re.search(r"(\d{1,2}\s*\/\s*\d{1,2})\s*h", s, re.I)
        if m1:
            val = m1.group(1).replace(" ", "")
            return f"de {val}H".upper()
        m2 = re.search(r"a\s*cada\s*(\d{1,2})\s*h", s, re.I)
        if m2:
            n = int(m2.group(1))
            return f"de {n}/{n}H".upper()
        m3 = re.search(r"(\d)\s*x\s*ao\s*dia", s, re.I)
        if m3:
            f = int(m3.group(1))
            if f > 0:
                h = int(round(24 / f))
                return f"de {h}/{h}H".upper()
        return None

    def _med_name(line: str) -> str:
        m = re.search(r"^([A-Za-zÀ-ÿ0-9 .+\-]+?)(?:\s+\d+\s?(mg|ml|g|mcg)|\s*[–-])", line)
        if m:
            return m.group(1).strip()
        parts = [p for p in line.split() if p]
        return " ".join(parts[:3]).strip()

    poso_lines: list[str] = []
    for l in candidates:
        name = _med_name(l)
        freq = _norm_freq(l) or _norm_freq(txt) or ""
        detail = None
        m = re.search(r"(?:\d+\s?(mg|ml|g|mcg)[^,;]*)[,;]?(.*)$", l, re.I)
        if m and m.group(2):
            detail = m.group(2).strip()
        else:
            m2 = re.search(r"(por\s*\d+\s*(dias?|semanas?|meses?)|n[aã]o\s*pass(e|ar)\s*de\s*\d+\s*(comprimidos?|capsulas?))", l, re.I)
            if m2:
                detail = m2.group(0).strip()
        limit_m = re.search(r"n[aã]o\s*pass(e|ar)\s*de\s*(\d+)\s*(comprimidos?|capsulas?)", txt, re.I)
        limit = None
        if limit_m:
            limit = f"Máx {limit_m.group(2)} {limit_m.group(3)}/24H"
        parts = [p for p in [freq, limit or detail] if p]
        if name and parts:
            poso_lines.append(f"{name} {'; '.join(parts)}")
        elif name and freq:
            poso_lines.append(f"{name} {freq}")
        elif detail:
            poso_lines.append(detail)
    posologia = "\n".join(poso_lines)
    return medicamentos, posologia