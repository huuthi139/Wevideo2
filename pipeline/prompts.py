"""prompts.py — Biến kịch bản tiếng Việt → danh sách cảnh {doc, hinh, phude}.

- doc   : câu ĐỌC (tiếng Việt thuần, edge-tts đọc)
- hinh  : mô tả HÌNH tiếng Anh cho Veo (model hiểu tiếng Anh tốt hơn)
- phude : phụ đề kinetic (đánh dấu *từ khoá* → IN HOA + to)

Ý tưởng mượn từ autovideo/flowboard `prompt_synth.auto_prompt_storyboard`:
1 lần gọi LLM → N cảnh mạch lạc. Ở đây làm GỌN, không kéo DB: LLM là OpenAI-compatible
qua config (tuỳ chọn). KHÔNG có LLM → fallback template (video vẫn ra, hình chung chung hơn).
"""
from __future__ import annotations

import json
import re
import urllib.request

# Nền phong cách (từ skill người-que / 1_tao_anh) — prefix cho prompt HÌNH.
STYLE_NEN = {
    "phan": ("hand-drawn white chalk stick figure animation on a dark green chalkboard, "
             "minimalist doodle, chalk dust texture, subtle hand-drawn motion, vertical 9:16"),
    "trang": ("minimalist black stick figure drawn with bold black ink brush lines on a clean "
              "pure white background, hand-drawn doodle, a few bright accent colors, subtle "
              "hand-drawn motion, flat 2D, vertical 9:16"),
}
CAM = "no text, no words, no letters, no numbers"
# Màu phụ đề theo nền (make_subs_v2): phan=vàng chanh/bảng phấn · trang=mực đậm/nền trắng
SUB_STYLE = {"phan": "phan", "trang": "trang"}


def build_video_prompt(style: str, hinh: str, aspect: str = "9:16") -> str:
    """Ghép prompt HÌNH hoàn chỉnh gửi Veo/Flow. aspect 16:9 → đổi cụm 'vertical 9:16'."""
    nen = STYLE_NEN.get(style, STYLE_NEN["phan"])
    if aspect == "16:9":
        nen = nen.replace("vertical 9:16", "horizontal 16:9")
    return f"{nen}, {CAM} — {hinh.strip()}"


# ── LLM enrich (tuỳ chọn) ────────────────────────────────────────────────
_SYSTEM = (
    "You turn a short Vietnamese narration script into scenes for a stick-figure explainer "
    "video (9:16). For EACH spoken line produce: an English visual description of a SINGLE "
    "stick-figure scene that illustrates that line (concrete action/objects, no camera jargon, "
    "no on-screen text), and a Vietnamese kinetic subtitle of 1-2 SHORT lines where the single "
    "most important phrase is wrapped in *asterisks*. Keep characters/consistency simple (one "
    "stick figure). Return STRICT JSON only: "
    '{"scenes":[{"doc":"<original vn line>","hinh":"<english visual>","phude":["line1","*key* line2"]}]}'
)


def _llm(cfg: dict, system: str, user: str, timeout: float = 120.0) -> str:
    url = (cfg.get("url") or "").rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg.get("model", ""),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.7,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if cfg.get("key"):
        headers["Authorization"] = "Bearer " + cfg["key"]
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def _parse_structured(text: str):
    """Kịch bản cấu trúc sẵn: mỗi cảnh tách bởi dòng trống, khoá doc:/hinh:/phude:
    HOẶC 1 dòng "câu đọc | mô tả hình | phụ đề". Trả None nếu không nhận dạng được."""
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    scenes = []
    got_keyed = False
    for b in blocks:
        doc = hinh = broll = ""; phude = []
        for ln in b.splitlines():
            m = re.match(r"\s*(doc|đọc|hinh|hình|phude|phụ đề|broll|b-roll|cutaway)\s*[:：]\s*(.*)", ln, re.I)
            if m:
                got_keyed = True
                k = m.group(1).lower(); v = m.group(2).strip()
                if k in ("doc", "đọc"): doc = v
                elif k in ("hinh", "hình"): hinh = v
                elif k in ("broll", "b-roll", "cutaway"): broll = v
                else: phude = [s.strip() for s in re.split(r"\s*/\s*|\s*\|\s*", v) if s.strip()]
        if not got_keyed and "|" in b:
            parts = [p.strip() for p in b.split("|")]
            doc = parts[0]; hinh = parts[1] if len(parts) > 1 else ""
            if len(parts) > 2: phude = [parts[2]]
        if doc or hinh:
            scenes.append({"doc": doc, "hinh": hinh, "phude": phude, "broll": broll})
    return scenes if (got_keyed or any(s["hinh"] for s in scenes)) else None


def _naive(text: str):
    """Không LLM + không cấu trúc: mỗi dòng = 1 câu đọc; phụ đề = câu (bắt 1 từ khoá thô)."""
    out = []
    for ln in [x.strip() for x in text.splitlines() if x.strip()]:
        words = ln.rstrip(".!?,").split()
        # tô đậm cụm 1-2 từ ở giữa làm "từ khoá" (thô, không LLM)
        mid = max(0, len(words) // 2 - 1)
        kw = " ".join(words[mid:mid + 2]) if words else ""
        phude_line = ln
        if kw:
            phude_line = ln.replace(kw, f"*{kw}*", 1)
        out.append({"doc": ln, "hinh": "a stick figure gesturing while explaining, simple props",
                    "phude": [phude_line], "broll": ""})
    return out


def enrich_script(script_text: str, style: str, llm_cfg: dict | None):
    """Trả (scenes, source) với source ∈ {structured, llm, naive}. scenes = [{doc,hinh,phude}]."""
    st = _parse_structured(script_text)
    if st:
        for s in st:
            s.setdefault("broll", "")
            if not s["hinh"]:
                s["hinh"] = "a stick figure gesturing while explaining, simple props"
            if not s["phude"]:
                s["phude"] = [s["doc"]]
        return st, "structured"
    if llm_cfg and llm_cfg.get("url"):
        try:
            raw = _llm(llm_cfg, _SYSTEM, "Kịch bản (mỗi dòng 1 câu đọc):\n" + script_text)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.lstrip("`"); raw = raw[4:] if raw[:4].lower() == "json" else raw
                raw = raw.rsplit("```", 1)[0].strip()
            obj = json.loads(raw)
            scenes = obj["scenes"] if isinstance(obj, dict) else obj
            norm = []
            for s in scenes:
                ph = s.get("phude") or [s.get("doc", "")]
                if isinstance(ph, str): ph = [ph]
                norm.append({"doc": s.get("doc", ""), "hinh": s.get("hinh", ""), "phude": ph,
                             "broll": s.get("broll", "")})
            if norm:
                return norm, "llm"
        except Exception as e:
            print(f"[prompts] LLM enrich lỗi ({e}) → fallback naive")
    return _naive(script_text), "naive"
