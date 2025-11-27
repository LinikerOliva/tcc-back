# Simple Gemini client wrapper for backend summarization
# Uses google-generativeai SDK if available; otherwise falls back to HTTP via requests.

import json
import os

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENERATIVEAI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

_SYSTEM_PROMPT = """
VOCÊ É UM 'MEDICAL SCRIBE' (ESCRIVÃO MÉDICO) DE ELITE.
SUA ÚNICA FUNÇÃO É LER UMA TRANSCRIÇÃO DE CONSULTA E PREENCHER O PRONTUÁRIO.
⛔ REGRAS DE ELIMINAÇÃO DE RUÍDO (CRÍTICO):

A transcrição NÃO tem nomes. Você deve deduzir quem fala.

A primeira frase é QUASE SEMPRE do médico ("Bom dia", "O que sente?"). IGNORE ISSO NA QUEIXA.

SE O CAMPO FOR "BOM DIA" OU "TUDO BEM", DEIXE VAZIO STRING "".

🧠 COMO PREENCHER CADA CAMPO:

'queixa': O SINTOMA que o paciente diz. (Ex: "Dor de cabeça", "Febre"). NÃO inclua perguntas do médico.

'historia_doenca_atual': Detalhes de tempo, evolução, outros sintomas (Ex: "Começou há 2 dias, piora com luz").

'diagnostico': O nome da doença que o médico concluiu (Ex: "Faringite", "Virose").

'conduta': Orientações (Ex: "Repouso", "Beber água"). NÃO coloque remédios aqui.

'medicamentos': APENAS os nomes e dosagens dos remédios (Ex: "Dipirona 500mg").

'posologia': Como tomar (Ex: "1 cp a cada 6h se dor").

📝 EXEMPLO DE EXTRAÇÃO CORRETA: Entrada: "Oi doutor. Oi, o que houve? To com dor de barriga faz 3 dias." Saída JSON: { "queixa": "Dor de barriga", "historia_doenca_atual": "Duração de 3 dias", ... }

(Note que ignoramos o 'Oi doutor' e o 'o que houve' na queixa).

📤 SAÍDA ESPERADA: Retorne APENAS um JSON válido. Sem markdown. Sem 'Aqui está'.
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
    context_txt = json.dumps(contexto or {}, ensure_ascii=False, default=str)
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
        try:
            return _offline_structured(transcript)
        except Exception:
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
        return _offline_structured(transcript)
    except Exception:
        return _offline_structured(transcript)


def _extract_json(text: str) -> str:
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else text


def _postprocess(obj: dict, source_txt: str) -> dict:
    out = {
        "queixa": str(obj.get("queixa") or ""),
        "historia_doenca_atual": str(obj.get("historia_doenca_atual") or ""),
        "diagnostico": str(obj.get("diagnostico") or obj.get("diagnostico_principal") or ""),
        "conduta": str(obj.get("conduta") or ""),
        "medicamentos": str(obj.get("medicamentos") or ""),
        "posologia": str(obj.get("posologia") or ""),
        "alergias": str(obj.get("alergias") or ""),
        "pressao": str(obj.get("pressao") or ""),
        "frequencia_cardiaca": str(obj.get("frequencia_cardiaca") or ""),
        "temperatura": str(obj.get("temperatura") or ""),
        "saturacao": str(obj.get("saturacao") or ""),
    }
    out["queixa"] = _clean_queixa(out.get("queixa") or "")
    return out


def _extract_meds(text: str) -> tuple[str, str]:
    import re
    txt = str(text or "")
    lines = [l.strip() for l in txt.replace("\r", "").split("\n") if l.strip()]
    candidates = []
    for l in lines:
        if re.search(r"\b(mg|ml|mcg|comprimid|c[áa]psul|gotas|spray)\b", l, re.I):
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
        m = re.search(r"(.+?(\d+\s?(mg|ml|mcg)|comprimid|c[áa]psul|gotas|spray).*)", txt, re.I)
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
            try:
                a, b = [int(x) for x in val.split('/')]
                if a == b:
                    return f"a cada {b} horas"
            except Exception:
                pass
            return f"a cada {val.replace('/', ' ')} horas"
        m2 = re.search(r"a\s*cada\s*(\d{1,2})\s*h", s, re.I)
        if m2:
            n = int(m2.group(1))
            return f"a cada {n} horas"
        m3 = re.search(r"(\d)\s*x\s*ao\s*dia", s, re.I)
        if m3:
            f = int(m3.group(1))
            if f > 0:
                h = int(round(24 / f))
                return f"a cada {h} horas"
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

def _clean_queixa(s: str) -> str:
    frases = [
        "Bom dia, tudo bem?",
        "O que te traz aqui hoje?",
        "Olá, doutor",
        "Bom dia doutor",
        "Tudo bem?",
    ]
    t = (s or "").strip()
    low = t.lower()
    for f in frases:
        if f.lower() in low:
            return ""
    if low.startswith("bom dia"):
        t2 = t[len("Bom dia"):]
        t2 = t2.replace("tudo bem?", "")
        return t2.strip(",. ")
    return t


def extract_prescription_items(texto: str) -> list[dict]:
    # Primeiro, extrair localmente (sem depender da API)
    meds, poso = _extract_meds(texto or "")
    med_lines = [l.strip() for l in meds.replace("\r", "").split("\n") if l.strip()]
    poso_lines = [l.strip() for l in poso.replace("\r", "").split("\n") if l.strip()]
    items: list[dict] = []
    for ml in med_lines:
        match = next((pl for pl in poso_lines if pl.lower().startswith(ml.lower())), "")
        items.append({
            "medicamento": ml,
            "posologia": match or poso,
            "quantidade": None
        })
    if not items and (meds or poso):
        items.append({
            "medicamento": meds or "",
            "posologia": poso or "",
            "quantidade": None
        })
    # Se a API estiver disponível, tentar refinar
    try:
        result = summarize_transcript(texto or "", contexto=None)
        meds2 = str(result.get("medicamentos") or "").strip()
        poso2 = str(result.get("posologia") or "").strip()
        if meds2 or poso2:
            med2_lines = [l.strip() for l in meds2.replace("\r", "").split("\n") if l.strip()]
            poso2_lines = [l.strip() for l in poso2.replace("\r", "").split("\n") if l.strip()]
            items = []
            for ml in med2_lines or med_lines:
                match = next((pl for pl in poso2_lines if pl.lower().startswith(ml.lower())), "")
                items.append({
                    "medicamento": ml,
                    "posologia": match or poso2 or poso,
                    "quantidade": None
                })
    except Exception:
        pass
    return items


def _offline_structured(txt: str) -> dict:
    t = (txt or "").replace("\r", "").strip()
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    def contains(s: str, *k):
        s2 = s.lower()
        return all(kw.lower() in s2 for kw in k)
    # Queixa: primeira frase do paciente
    queixa = ""
    for l in lines:
        if contains(l, "estou") or contains(l, "tô") or contains(l, "eu tô") or contains(l, "eu estou"):
            queixa = l
            break
    if not queixa:
        import re
        m = re.search(r"eu\s+(?:tô|estou)\s+com\s+([^\.\n]+)", t, re.I)
        if m:
            queixa = m.group(1).strip()
    # História: procurar duração e febre
    hda_parts = []
    for l in lines:
        if contains(l, "começou") or contains(l, "faz uns") or contains(l, "dias"):
            hda_parts.append(l)
        if contains(l, "febre") or contains(l, "38"):
            hda_parts.append(l)
        if contains(l, "corpo") or contains(l, "mole"):
            hda_parts.append(l)
    historia = "; ".join(dict.fromkeys(hda_parts))
    # Diagnóstico: frases do médico com "parece ser" ou nome da condição
    diag = ""
    for l in lines:
        if contains(l, "parece ser") or contains(l, "faringite"):
            diag = l
            break
    # Conduta: recomendações
    cond_parts = []
    for l in lines:
        if contains(l, "repouso") or contains(l, "hidratação") or contains(l, "beber") or contains(l, "evite"):
            cond_parts.append(l)
    conduta = "; ".join(dict.fromkeys(cond_parts))
    # Medicamentos e posologia
    meds, poso = _extract_meds(t)
    return {
        "queixa": _clean_queixa(queixa),
        "historia_doenca_atual": historia,
        "diagnostico_principal": diag,
        "conduta": conduta,
        "medicamentos": meds,
        "posologia": poso,
    }
