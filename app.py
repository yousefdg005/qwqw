import base64
import hashlib
import io
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from html import escape as html_escape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import arabic_reshaper
import pandas as pd
from bidi.algorithm import get_display
from docx import Document
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st
import streamlit.components.v1 as components
import requests

def send_to_dictionary(extracted_terms):
    url = "https://dictionaryly.onrender.com/api/receive-terms"
    headers = {
        "Authorization": "Bearer my_secure_platform_ingest_token_2026",
        "Content-Type": "application/json"
    }
    payload = {
        "terms": extracted_terms
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 201:
            return True
        else:
            st.error(f"❌ تم الرفض من القاموس! كود الخطأ: {response.status_code} - التفاصيل: {response.text}")
            return False
    except Exception as e:
        st.error(f"❌ فشل الاتصال بالخادم: {e}")
        return False

# =========================================================
# 1. إعدادات صفحة Streamlit
# =========================================================
st.set_page_config(
    page_title="AI Legal Workspace",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def load_css(file_name="style.css"):
    try:
        css_path = Path(__file__).parent / file_name
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css("style.css")

def prepare_arabic_text(text):
    if not text or not isinstance(text, str): return ""
    return get_display(arabic_reshaper.reshape(text))

# =========================================================
# 4. الهيدر العام للمنصة (بألوان Frozen Lake)
# =========================================================
st.markdown(
    """
<div class="header-container" style="direction: ltr; text-align: left;">
    <div class="header-text">
        <h1 style="color: #ADD8E6; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: -0.5px;">
            ⚖️ AI Legal Workspace
        </h1>
        <p style="color: #FFFAFA; font-size: 14px; margin: 10px 0 14px; line-height: 1.6;">
            Your all-in-one AI toolkit for legal text alignment &amp; term extraction
        </p>
        <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
            <span style="color: #000080; font-size: 12px; background: #ADD8E6; padding: 5px 14px; border-radius: 20px; font-weight: 700;">
                🤖 Smart AI Engine
            </span>
            <span style="color: #FFFAFA; font-size: 12px; background: #6D8196; padding: 5px 14px; border-radius: 20px; font-weight: 600;">
                🌐 AR ↔ EN
            </span>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

st.sidebar.header("⚙️ إعدادات النظام")
st.sidebar.markdown(
    """
<div style="background-color: #000080; padding: 12px; border-radius: 8px; border: 1px solid #6D8196; margin-bottom: 15px; text-align: center;">
    <a href="https://openrouter.ai/keys" target="_blank" style="color: #ADD8E6; font-weight: bold; text-decoration: none; font-size: 14px;">
        🔗 الحصول على المفتاح من OpenRouter
    </a>
</div>
""",
    unsafe_allow_html=True,
)

api_key = st.sidebar.text_input("🔑 مفتاح OpenRouter API Key الخاص بك:", type="password")

PAID_MODELS_MAPPING = {
    "⚡ Gemini 3.8 Flash": "google/gemini-3.8-flash",
    "⚖️ GPT-4o Mini": "openai/gpt-4o-mini",
    "🦙 Llama 4 Maverick": "meta-llama/llama-4-maverick",
}
st.sidebar.subheader("🤖 اختيار النموذج")
selected_model_label = st.sidebar.selectbox("اختر النموذج:", options=list(PAID_MODELS_MAPPING.keys()), index=0)
selected_model_id = PAID_MODELS_MAPPING[selected_model_label]

with st.sidebar:
    st.markdown("---")
    st.subheader("📚 القاموس القانوني")
    st.link_button("🌐 فتح القاموس", "https://dictionaryly.onrender.com", use_container_width=True)

for key in ["aligned_pairs", "results_df", "tmx_bytes", "alignment_draft"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key == "aligned_pairs" else None

_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_XML_BAD_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    return _INVISIBLE_RE.sub("", text).replace("\u00a0", " ")

def _term_key(value):
    value = normalize_text(str(value or "")).casefold()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()

def align_segments(en_segments, ar_segments):
    n, m = len(en_segments), len(ar_segments)
    if not n or not m:
        return [(en_segments[i] if i < n else "", ar_segments[i] if i < m else "") for i in range(max(n, m))]
    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    prev = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == inf: continue
            for a, b in ((1,1),(1,2),(2,1)):
                if i+a > n or j+b > m: continue
                le = sum(len(x) for x in en_segments[i:i+a]); la = sum(len(x) for x in ar_segments[j:j+b])
                cost = abs(__import__('math').log((le+1)/(la+1))) * 0.10 + (a+b-2)*0.18
                if dp[i][j] + cost < dp[i+a][j+b]:
                    dp[i+a][j+b] = dp[i][j] + cost; prev[i+a][j+b] = (i,j,a,b)
    if prev[n][m] is None:
        return [(en_segments[i] if i<n else "", ar_segments[i] if i<m else "") for i in range(max(n,m))]
    groups=[]; i,j=n,m
    while i or j:
        step=prev[i][j]
        if step is None: break
        pi,pj,a,b=step
        groups.append((" ".join(en_segments[pi:i]), " ".join(ar_segments[pj:j])))
        i,j=pi,pj
    return list(reversed(groups))

def extract_text_from_docx_bytes(data):
    notes = []
    try:
        doc = Document(io.BytesIO(data))
        paragraphs = [normalize_text(p.text.strip()) for p in doc.paragraphs if p.text.strip()]
        if doc.tables:
            for table in doc.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells: paragraphs.append(normalize_text(" | ".join(row_cells)))
            notes.append(f"تم استخراج المحتوى من {len(doc.tables)} جدول/جداول")
        return "\n\n".join(paragraphs), notes
    except Exception as e:
        return "", [f"خطأ أثناء قراءة ملف Word: {e}"]

def process_docx_text_to_segments(text):
    if not text: return []
    segments = []
    abbreviations = ("Mr.", "Mrs.", "Ms.", "Dr.", "Jr.", "Sr.", "Inc.", "Ltd.", "No.", "e.g.", "i.e.", "Art.", "Sec.")
    for paragraph in re.split(r"\n+", normalize_text(text)):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph: continue
        protected = paragraph
        for idx, abbr in enumerate(abbreviations):
            protected = re.sub(re.escape(abbr), f"{abbr[:-1]}<ABBR{idx}>", protected, flags=re.I)
        parts = re.split(r"(?<=[.!?؟؛])\s+", protected)
        for part in parts:
            part = re.sub(r"<ABBR(\d+)>", lambda m: abbreviations[int(m.group(1))][-1], part)
            part = re.sub(r"\s+", " ", part).strip()
            if part: segments.append(part)
    return segments

def parse_tmx_bytes(tmx_content):
    try: root = ET.fromstring(tmx_content)
    except Exception as exc: raise ValueError(f"ملف TMX غير صالح: {exc}") from exc
    pairs=[]
    for tu in root.iter():
        if tu.tag.split("}")[-1] != "tu": continue
        langs={}
        for tuv in list(tu):
            if tuv.tag.split("}")[-1] != "tuv": continue
            lang=next((v.lower() for k,v in tuv.attrib.items() if k.lower().endswith("lang")), "")
            seg=next((el for el in tuv.iter() if el.tag.split("}")[-1]=="seg"), None)
            value="".join(seg.itertext()).strip() if seg is not None else ""
            if lang.startswith("en"): langs["en"]=value
            elif lang.startswith("ar"): langs["ar"]=value
        if langs.get("en") or langs.get("ar"): pairs.append((langs.get("en",""),langs.get("ar","")))
    return pairs

def generate_tmx_file(pairs):
    root=ET.Element("tmx", {"version":"1.4"})
    ET.SubElement(root,"header", {"creationtool":"AI Legal Workspace","segtype":"sentence","srclang":"en","datatype":"plaintext"})
    body=ET.SubElement(root,"body")
    for en, ar in pairs:
        tu=ET.SubElement(body,"tu")
        for lang,text in (("en",en),("ar",ar)):
            tuv=ET.SubElement(tu,"tuv", {"{http://www.w3.org/XML/1998/namespace}lang":lang})
            ET.SubElement(tuv,"seg").text=_XML_BAD_RE.sub("",str(text or ""))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

# استوديو المحاذاة (تحديث ألوان HTML الداخلية لتتطابق مع Frozen Lake)
ALIGNMENT_STUDIO_HTML = r"""<!DOCTYPE html>
<html lang="ar"><head><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Cairo',sans-serif; background:#020412; color:#FFFAFA; margin:0; padding:10px; overflow:hidden; }
  #bar { display:flex; gap:10px; align-items:center; margin-bottom:12px; direction:rtl; flex-wrap:wrap; }
  #toast { color:#ADD8E6; font-size:13px; }
  #alignmentScroll { height: 610px; overflow-y: auto; padding: 10px; border: 1px solid #6D8196; border-radius: 14px; background: #000080; }
  .segment-row { display:flex; gap:10px; background:#1a1a99; border:1px solid #6D8196; border-radius:12px; padding:12px; align-items:center; }
  .segment-num { color:#ADD8E6; font-weight:800; width:42px; text-align:center; font-size:13px; }
  .cell { flex:1; display:flex; gap:6px; align-items:stretch; }
  .handle { width:22px; height:22px; display:flex; align-items:center; justify-content:center; background:#000080; color:#ADD8E6; cursor:grab; font-size:12px; border-radius:4px;}
  .move-btn { width:22px; height:18px; background:#000080; color:#ADD8E6; border:none; cursor:pointer; font-size:10px; border-radius:4px;}
  .card-box { flex:1; background:#020412; border:1px solid #6D8196; border-radius:8px; padding:10px; min-height:55px; font-size:14px; color:#FFFAFA; }
  .en-box { direction:ltr; text-align:left; }
  .ar-box { direction:rtl; text-align:right; }
  .btn-ctrl { background:#000080; color:#FFFAFA; border:1px solid #6D8196; border-radius:6px; padding:5px; font-size:11px; cursor:pointer; }
  .add-row-btn { background:linear-gradient(135deg,#ADD8E6 0%,#6D8196 100%); color:#000080; font-weight:800; border:none; border-radius:8px; padding:10px 20px; cursor:pointer; }
</style></head>
<body>
<div id="bar"><button class="add-row-btn" id="addBtn">➕ إضافة وحدة جديدة</button><span id="toast"></span></div>
<div id="alignmentScroll"><div id="alignmentContainer" style="display:flex; flex-direction:column; gap:10px;"></div></div>
<script>
  const container = document.getElementById('alignmentContainer');
  let data = [], token = null, sendTimer = null;
  function post(type, extra) { window.parent.postMessage(Object.assign({isStreamlitMessage:true, type}, extra||{}), '*'); }
  function pushValue() { clearTimeout(sendTimer); sendTimer = setTimeout(() => post('streamlit:setComponentValue', {value: data.map(d=>({en:d.en, ar:d.ar})), dataType:'json'}), 500); }
  window.addEventListener('message', (ev) => {
    if (!ev.data || ev.data.type !== 'streamlit:render') return;
    if (ev.data.args.token !== token) { token = ev.data.args.token; data = (ev.data.args.pairs || []).map(p=>({en: p.en||'', ar: p.ar||''})); renderRows(); }
  });
  post('streamlit:componentReady', {apiVersion: 1});
  function renderRows() {
    container.textContent = '';
    data.forEach((_, i) => {
      const row = document.createElement('div'); row.className = 'segment-row';
      row.innerHTML = `<div class="segment-num">[${i+1}]</div>
        <div class="cell"><div style="display:flex;flex-direction:column;gap:2px"><button class="move-btn" onclick="move(${i},'en',-1)">▲</button><div class="handle">⠿</div><button class="move-btn" onclick="move(${i},'en',1)">▼</button></div>
        <div class="card-box en-box" contenteditable="true" oninput="update(${i},'en',this)">${data[i].en}</div></div>
        <div class="cell"><div style="display:flex;flex-direction:column;gap:2px"><button class="move-btn" onclick="move(${i},'ar',-1)">▲</button><div class="handle">⠿</div><button class="move-btn" onclick="move(${i},'ar',1)">▼</button></div>
        <div class="card-box ar-box" contenteditable="true" oninput="update(${i},'ar',this)">${data[i].ar}</div></div>
        <div style="display:flex;flex-direction:column;gap:5px"><button class="btn-ctrl" onclick="del(${i})">🗑️ حذف</button></div>`;
      container.appendChild(row);
    });
  }
  window.move = (i, t, d) => { if(data[i+d]){ let tmp=data[i][t]; data[i][t]=data[i+d][t]; data[i+d][t]=tmp; renderRows(); pushValue(); } };
  window.update = (i, t, el) => { data[i][t] = el.innerText; pushValue(); };
  window.del = (i) => { data.splice(i, 1); renderRows(); pushValue(); };
  document.getElementById('addBtn').onclick = () => { data.push({en:'', ar:''}); renderRows(); pushValue(); };
</script></body></html>"""

_COMPONENT_DIR = Path(__file__).parent / "alignment_studio_component"
def _declare_alignment_studio():
    _COMPONENT_DIR.mkdir(exist_ok=True)
    index = _COMPONENT_DIR / "index.html"
    index.write_text(ALIGNMENT_STUDIO_HTML, encoding="utf-8")
    return components.declare_component("alignment_studio", path=str(_COMPONENT_DIR))
alignment_studio = _declare_alignment_studio()

tab1, tab2 = st.tabs(["Alignment Studio (beta)", "AI Term Extractor"])

with tab1:
    st.subheader("📄 الخطوة 1: رفع ملفات Word (.docx)")
    col_doc1, col_doc2 = st.columns(2)
    doc_en = col_doc1.file_uploader("ملف الإنجليزي:", type=["docx"])
    doc_ar = col_doc2.file_uploader("ملف العربي:", type=["docx"])

    if doc_en and doc_ar:
        text_en, _ = extract_text_from_docx_bytes(doc_en.getvalue())
        text_ar, _ = extract_text_from_docx_bytes(doc_ar.getvalue())
        
        if text_en and text_ar:
            st.success("✅ تم استخراج النصوص.")
            aligned_initial = align_segments(process_docx_text_to_segments(text_en), process_docx_text_to_segments(text_ar))
            initial_pairs = [{"en": e, "ar": a} for e, a in aligned_initial]
            token = hashlib.md5((text_en + "\x00" + text_ar).encode("utf-8")).hexdigest()
            
            studio_value = alignment_studio(pairs=initial_pairs, token=token, key="alignment_studio", default=None)
            current_pairs = studio_value if studio_value is not None else initial_pairs
            st.session_state["alignment_draft"] = current_pairs

            if st.button("🚀 اعتماد المحاذاة وتوليد TMX", use_container_width=True):
                final_pairs = [(p["en"].strip(), p["ar"].strip()) for p in current_pairs if p["en"].strip() and p["ar"].strip()]
                if final_pairs:
                    st.session_state["aligned_pairs"] = final_pairs
                    st.session_state["tmx_bytes"] = generate_tmx_file(final_pairs)
                else:
                    st.error("⚠️ يرجى التأكد من وجود جمل صالحة.")
            
            if st.session_state.get("tmx_bytes"):
                st.download_button("💾 تنزيل ملف TMX", data=st.session_state["tmx_bytes"], file_name="Aligned_Memory.tmx", mime="application/x-tmx+xml")

with tab2:
    st.subheader("🔍 استخراج المصطلحات عبر الذكاء الاصطناعي")
    uploaded_tmx = st.file_uploader("Upload .TMX memory (or use from Tab 1)", type=["tmx"])
    aligned_units = parse_tmx_bytes(uploaded_tmx.read()) if uploaded_tmx else st.session_state["aligned_pairs"]

    if aligned_units:
        if st.button("⚡ بدء الاستخراج الذكي"):
            if not api_key.strip():
                st.error("⚠️ أدخل مفتاح API أولاً.")
            else:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key.strip())
                system_prompt = """You are an expert legal terminologist. 
Analyze the FULL context of the provided text to precisely extract key terms and accurately determine the specific 'subject field' (e.g., International Public Law, Commercial Contracts, Real Estate Law).

OUTPUT FORMAT MUST BE VALID JSON:
{"terms": [
  {"ID": 1, "en": "English Term", "ar": "Arabic Term", "definition": "Arabic Description", "subject field": "Specific Sub-field"}
]}

Do NOT extract procedural filler words (e.g., 'Having reviewed', 'Pursuant to').
"""
                results = []
                progress_bar = st.progress(0)
                
                for i, (en_text, ar_text) in enumerate(aligned_units):
                    try:
                        response = client.chat.completions.create(
                            model=selected_model_id,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"[EN]: {en_text}\n[AR]: {ar_text}"},
                            ],
                            temperature=0.0,
                            response_format={"type": "json_object"},
                        )
                        raw = json.loads(response.choices[0].message.content)
                        terms = raw.get("terms", [])
                        
                        for item in terms:
                            if item.get("en"):
                                results.append({
                                    "ID": str(item.get("ID", len(results)+1)),
                                    "en": str(item.get("en", "")).strip(),
                                    "ar": str(item.get("ar", "")).strip(),
                                    "definition": str(item.get("definition", "")).strip(),
                                    "subject field": str(item.get("subject field", "")).strip(),
                                    "Source EN": en_text,
                                    "Source AR": ar_text,
                                })
                    except Exception:
                        pass
                    progress_bar.progress((i + 1) / len(aligned_units))
                
                if results:
                    df = pd.DataFrame(results)
                    df["_key"] = df["en"].map(_term_key) + "|" + df["ar"].map(_term_key)
                    df = df.groupby("_key", as_index=False, sort=False).agg({
                        "ID": "first", "en": "first", "ar": "first", "definition": "first", "subject field": "first",
                        "Source EN": lambda x: "\n---\n".join(dict.fromkeys(x)),
                        "Source AR": lambda x: "\n---\n".join(dict.fromkeys(x)),
                    })
                    df.drop(columns=["_key"], inplace=True)
                    st.session_state["results_df"] = df
                    
                    # تجهيز البيانات للإرسال بالأسماء الجديدة
                    terms_to_send = df[["ID", "en", "ar", "definition", "subject field"]].to_dict(orient="records")
                    if terms_to_send and send_to_dictionary(terms_to_send):
                        st.success("🚀 تم إرسال المصطلحات بنجاح إلى القاموس!")

    if st.session_state.get("results_df") is not None:
        df_res = st.session_state["results_df"]
        st.subheader("📊 جدول المصطلحات المستخرجة:")
        edited_df = st.data_editor(df_res, use_container_width=True, hide_index=True)
        st.session_state["results_df"] = edited_df
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            edited_df[["ID", "en", "ar", "definition", "subject field"]].to_excel(writer, index=False)
        excel_buffer.seek(0)
        
        st.download_button("📥 تنزيل (Excel)", data=excel_buffer, file_name="Extracted_Glossary.xlsx")
