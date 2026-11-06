import base64
import hashlib
import io
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import pandas as pd
from docx import Document
from openai import OpenAI
import streamlit as st
import streamlit.components.v1 as components
import requests

def send_to_dictionary(extracted_terms):
    url = os.environ.get("DICTIONARY_API_URL", "https://dictionaryly.onrender.com/api/receive-terms")
    ingest_key = os.environ.get("INGEST_API_KEY")
    if not ingest_key:
        st.error("❌ متغير البيئة INGEST_API_KEY غير مهيأ. يرجى ضبط المفتاح في المتغيرات البيئية لإرسال المصطلحات تلقائياً.")
        return False

    headers = {
        "Authorization": f"Bearer {ingest_key}",
        "Content-Type": "application/json"
    }
    
    # تقسيم المصطلحات إلى دفعات (كل دفعة 10 مصطلحات) لتجنب الضغط وخطأ 500
    batch_size = 10
    success_all = True
    
    for i in range(0, len(extracted_terms), batch_size):
        batch = extracted_terms[i:i + batch_size]
        payload = {"terms": batch}
        # إعادة محاولة تلقائية عند سكون السيرفرليس (Neon Serverless Cold Start)
        batch_success = False
        for attempt in range(2):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=60)
                if response.status_code == 201:
                    batch_success = True
                    break
                elif attempt == 0:
                    time.sleep(2)
                else:
                    success_all = False
                    st.error(f"❌ تم الرفض في الدفعة {i//batch_size + 1}: كود الخطأ {response.status_code} - التفاصيل: {response.text}")
            except Exception as e:
                if attempt == 0:
                    time.sleep(2)
                else:
                    success_all = False
                    st.error(f"❌ فشل الاتصال في الدفعة {i//batch_size + 1}: {e}")
            
    return success_all

# =========================================================
# 1. إعدادات صفحة Streamlit — هوية LexTerm
# =========================================================
_ASSETS_DIR = Path(__file__).parent / "assets"
_LOGO_ICON_PATH = _ASSETS_DIR / "logo_icon.png"

st.set_page_config(
    page_title="LexTerm — Legal Terminology Workspace",
    page_icon=str(_LOGO_ICON_PATH) if _LOGO_ICON_PATH.exists() else "🦉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# 2. تحميل ملف الـ CSS
# =========================================================
def load_css(file_name="style.css"):
    try:
        css_path = Path(__file__).parent / file_name
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css("style.css")

# شعار المنصة (LexTerm) بترميز Base64 لتضمينه في الهيدر
def _asset_b64(name):
    path = Path(__file__).parent / "assets" / name
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except FileNotFoundError:
        return ""

LOGO_B64 = _asset_b64("logo.jpg")

# =========================================================
# 3. الهيدر العام للمنصة (LexTerm Branding)
# =========================================================
st.markdown(
    f"""
<div class="header-container" style="direction: ltr; text-align: left;">
    <img class="header-logo" src="data:image/jpeg;base64,{LOGO_B64}" alt="LexTerm Logo">
    <div class="header-text">
        <h1 class="lexterm-wordmark" style="text-align: center; margin: 0; font-size: 34px;">
            <span class="lex">Lex</span><span class="term">Term</span>
        </h1>
        <p class="lexterm-tagline" style="text-align: center;">
            Your all-in-one AI toolkit for legal text alignment &amp; term extraction
        </p>
        <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
            <span style="color: #F2F5FA; font-size: 12px; background: rgba(201,150,60,0.13); padding: 5px 14px; border-radius: 20px; border: 1px solid rgba(201,150,60,0.35); font-weight: 600;">
                🦉 Professional Legal Terminology
            </span>
            <span style="color: #F2F5FA; font-size: 12px; background: rgba(74,125,191,0.12); padding: 5px 14px; border-radius: 20px; border: 1px solid rgba(74,125,191,0.30); font-weight: 600;">
                🌐 AR ↔ EN
            </span>
            <span style="color: #93A5C4; font-size: 12px; background: rgba(147,165,196,0.08); padding: 5px 14px; border-radius: 20px; border: 1px solid rgba(147,165,196,0.20);">
                💻 Developed by Youssef Nour Eldin
            </span>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# 4. الشريط الجانبي للإعدادات
# =========================================================
st.sidebar.header("⚙️ إعدادات النظام")

st.sidebar.markdown(
    """
<div style="background-color: #14243E; padding: 12px; border-radius: 8px; border: 1px solid #2A4066; margin-bottom: 15px; text-align: center;">
    <span style="color: #F2F5FA; font-size: 13px;">ليس لديك مفتاح API؟</span><br>
    <a href="https://openrouter.ai/keys" target="_blank" style="color: #E8C069; font-weight: bold; text-decoration: none; font-size: 14px; display: inline-block; margin-top: 5px;">
        🔗 الحصول على المفتاح من OpenRouter
    </a>
</div>
""",
    unsafe_allow_html=True,
)

api_key = st.sidebar.text_input(
    "🔑 مفتاح OpenRouter API Key الخاص بك:",
    value="",
    type="password",
    placeholder="sk-or-v1-...",
)

PAID_MODELS_MAPPING = {
    "⚡ Gemini 3.8 Flash": "google/gemini-3.8-flash",
    "⚖️ GPT-4o Mini": "openai/gpt-4o-mini",
    "🦙 Llama 4 Maverick": "meta-llama/llama-4-maverick",
}

st.sidebar.subheader("🤖 اختيار النموذج المراد استعماله")
selected_model_label = st.sidebar.selectbox(
    "اختر النموذج لتنفيذ عملية التصفية والاستخراج:",
    options=list(PAID_MODELS_MAPPING.keys()),
    index=0,
)
selected_model_id = PAID_MODELS_MAPPING[selected_model_label]

with st.sidebar:
    st.markdown("---")
    st.subheader("📚 القاموس القانوني")
    st.link_button("🌐 فتح القاموس", "https://dictionaryly.onrender.com", use_container_width=True)

# =========================================================
# 5. إدارة حالة الجلسة (Session State)
# =========================================================
if "aligned_pairs" not in st.session_state:
    st.session_state["aligned_pairs"] = []
if "results_df" not in st.session_state:
    st.session_state["results_df"] = None
if "tmx_bytes" not in st.session_state:
    st.session_state["tmx_bytes"] = None
if "alignment_draft" not in st.session_state:
    st.session_state["alignment_draft"] = None


# =========================================================
# 6. دوال استخراج وقراءة ملفات Word و TMX
# =========================================================
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_XML_BAD_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    return text.replace("\u00a0", " ")

_EN_STOP = set("a an the and or but if then of to in on at by for from with without under over into upon is are was were be been being it this that these those as not no any all each such may shall will must can could should has have had do does did".split())
_AR_STOP = set("في من على إلى عن أن إن أو و ثم كما حيث هذا هذه ذلك التي الذي الذين اللذين كان تكون يكون يتم قد ما لا لم لن مع بين عند لدى كل أي بعض وفق بموجب بناء بعد قبل حيث إذا".split())

def _term_key(value):
    value = normalize_text(str(value or "")).casefold()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()

def align_segments(en_segments, ar_segments):
    n, m = len(en_segments), len(ar_segments)
    if not n or not m:
        count = max(n, m)
        return [(en_segments[i] if i < n else "", ar_segments[i] if i < m else "")
                for i in range(count)]
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

def _is_low_value_term(term):
    key = _term_key(term)
    if not key: return True
    words = key.split()
    if len(words) == 1 and (key in _EN_STOP or key in _AR_STOP): return True
    if len(words) == 1 and len(key) < 4 and not re.search(r"[\u0600-\u06ff]", key): return True
    return False

def extract_text_from_docx_bytes(data):
    notes = []
    try:
        doc = Document(io.BytesIO(data))
        paragraphs = []
        for p in doc.paragraphs:
            txt = p.text.strip()
            if txt:
                paragraphs.append(normalize_text(txt))
        if doc.tables:
            for table in doc.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        paragraphs.append(normalize_text(" | ".join(row_cells)))
            notes.append(f"تم استخراج المحتوى من {len(doc.tables)} جدول/جداول داخل المستند")
        return "\n\n".join(paragraphs), notes
    except Exception as e:
        return "", [f"خطأ أثناء قراءة ملف Word: {e}"]

def process_docx_text_to_segments(text):
    if not text: return []
    text = normalize_text(text)
    segments = []
    abbreviations = ("Mr.", "Mrs.", "Ms.", "Dr.", "Jr.", "Sr.", "Inc.", "Ltd.", "No.", "e.g.", "i.e.", "Art.", "Sec.")
    for paragraph in re.split(r"\n+", text):
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
    try:
        root = ET.fromstring(tmx_content)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ValueError(f"ملف TMX غير صالح: {exc}") from exc
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
    ET.SubElement(root,"header", {"creationtool":"LexTerm","creationtoolversion":"3.0","segtype":"sentence","adminlang":"en-us","srclang":"en","datatype":"plaintext"})
    body=ET.SubElement(root,"body")
    for en, ar in pairs:
        tu=ET.SubElement(body,"tu")
        for lang,text in (("en",en),("ar",ar)):
            tuv=ET.SubElement(tu,"tuv", {"{http://www.w3.org/XML/1998/namespace}lang":lang})
            ET.SubElement(tuv,"seg").text=_XML_BAD_RE.sub("",str(text or ""))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# =========================================================
# 7. علامات التبويب الرئيسية (Tabs)
# =========================================================
tab1, tab2 = st.tabs(["Alignment Studio (beta)", "AI Term Extractor"])

# =========================================================
# مكوّن استوديو المحاذاة
# =========================================================
ALIGNMENT_STUDIO_HTML = r"""<!DOCTYPE html>
<html lang="ar"><head><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; }
  body { font-family: 'Cairo','Segoe UI',Tahoma,Arial,sans-serif; background:#0A1220; color:#F2F5FA; margin:0; padding:10px; overflow:hidden; }
  #bar { display:flex; gap:10px; align-items:center; margin-bottom:12px; direction:rtl; flex-wrap:wrap; }
  #toast { color:#E8C069; font-size:13px; font-weight:600; }
  #alignmentScroll {
    height: 610px; max-height: calc(100vh - 140px); min-height: 240px;
    overflow-y: auto; overflow-x: hidden; padding: 10px;
    border: 1px solid #1D3050; border-radius: 14px; background: #0F1B30;
    scrollbar-width: thin; scrollbar-color: #2A4066 #0F1B30; overscroll-behavior: contain;
  }
  #alignmentScroll::-webkit-scrollbar { width: 7px; }
  #alignmentScroll::-webkit-scrollbar-track { background: #0F1B30; border-radius: 4px; }
  #alignmentScroll::-webkit-scrollbar-thumb { background: #2A4066; border-radius: 4px; }
  #alignmentScroll::-webkit-scrollbar-thumb:hover { background: #3A5580; }
  .alignment-container { display:flex; flex-direction:column; gap:10px; direction:rtl; padding-bottom:14px; }
  .segment-row { display:flex; gap:10px; background:#12233D; border:1px solid #1D3050; border-radius:12px; padding:12px 14px; align-items:center; transition: border-color 0.2s, box-shadow 0.2s; position: relative; }
  .segment-row::before { content:''; position:absolute; right:0; top:8px; bottom:8px; width:3px; background:linear-gradient(180deg,#C9963C,#A87B2E); border-radius:3px; opacity:0; transition:opacity 0.2s; }
  .segment-row:hover { border-color:#2A4066; box-shadow:0 2px 16px rgba(2,6,14,0.45); }
  .segment-row:hover::before { opacity:1; }
  .segment-num { color:#C9963C; font-weight:800; width:42px; text-align:center; font-size:13px; flex-shrink:0; letter-spacing:0.5px; }
  .cell { flex:1; display:flex; gap:6px; align-items:stretch; min-width:0; border:2px solid transparent; border-radius:8px; transition:border-color 0.18s, background 0.18s; }
  .cell.drag-over { border:2px dashed #C9963C; background:rgba(201,150,60,0.10); }
  .handle-container { display:flex; flex-direction:column; gap:2px; flex-shrink:0; align-items:center; justify-content:center; }
  .handle { width:22px; height:22px; display:flex; align-items:center; justify-content:center; background:#14243E; border-radius:5px; color:#566E93; cursor:grab; user-select:none; font-size:12px; border:1px solid #1D3050; transition:all 0.18s; }
  .handle:hover { color:#C9963C; border-color:rgba(201,150,60,0.35); background:#1B2E4D; }
  .move-btn { width:22px; height:18px; display:flex; align-items:center; justify-content:center; background:#14243E; border:1px solid #1D3050; border-radius:4px; color:#566E93; cursor:pointer; font-size:10px; padding:0; transition:all 0.18s; }
  .move-btn:hover { background:#1B2E4D; color:#C9963C; border-color:rgba(201,150,60,0.35); }
  .card-box { flex:1; min-width:0; background:#14243E; border:1px solid #1D3050; border-radius:8px; padding:10px 14px; min-height:55px; font-size:14px; line-height:1.75; white-space:pre-wrap; overflow-wrap:anywhere; cursor:text; transition:border-color 0.18s, background 0.18s, box-shadow 0.18s; }
  .card-box:focus { outline:none; border-color:#C9963C; background:#0F1B30; box-shadow:0 0 0 3px rgba(201,150,60,0.12); }
  .en-box { direction:ltr; text-align:left; color:#8FBBEA; }
  .ar-box { direction:rtl; text-align:right; color:#E8C069; }
  .action-btn-group { display:flex; flex-direction:column; gap:5px; flex-shrink:0; }
  .btn-ctrl { background:#14243E; color:#93A5C4; border:1px solid #1D3050; border-radius:6px; padding:5px 9px; font-size:11px; font-weight:700; cursor:pointer; font-family:inherit; transition:all 0.18s; }
  .btn-ctrl:hover { background:#1B2E4D; color:#C9963C; border-color:rgba(201,150,60,0.35); }
  .btn-del:hover { background:#3B0A0A; color:#FCA5A5; border-color:rgba(214,69,69,0.35); }
  .add-row-btn { background:linear-gradient(135deg,#E8C069 0%,#C9963C 55%,#A87B2E 100%); color:#0A1220; font-weight:800; border:none; border-radius:8px; padding:10px 20px; cursor:pointer; font-family:inherit; font-size:13px; box-shadow:0 4px 14px rgba(201,150,60,0.30); transition:all 0.2s; }
  .add-row-btn:hover { transform:translateY(-2px); box-shadow:0 6px 22px rgba(201,150,60,0.42); filter:brightness(1.06); }
  .undo-btn { background:#14243E; color:#93A5C4; border:1px solid #1D3050; border-radius:8px; padding:10px 16px; cursor:pointer; font-weight:700; font-family:inherit; font-size:13px; transition:all 0.18s; }
  .undo-btn:hover { background:#1B2E4D; color:#F2F5FA; border-color:#2A4066; }
</style></head>
<body>
<div id="bar">
  <button class="add-row-btn" id="addBtn">➕ إضافة وحدة محاذاة جديدة</button>
  <button class="undo-btn" id="undoBtn">↩️ تراجع</button>
  <span id="toast"></span>
</div>
<div id="alignmentScroll" aria-label="منطقة تمرير وحدات المحاذاة"><div class="alignment-container" id="alignmentContainer"></div></div>
<script>
  const container = document.getElementById('alignmentContainer');
  const toastEl = document.getElementById('toast');
  let data = [], historyStack = [], token = null, drag = null, sendTimer = null;

  function post(type, extra) { window.parent.postMessage(Object.assign({isStreamlitMessage:true, type}, extra||{}), '*'); }
  function pushValue() { post('streamlit:setComponentValue', {value: data.map(d => ({en:d.en, ar:d.ar})), dataType:'json'}); }
  function pushSoon() { clearTimeout(sendTimer); sendTimer = setTimeout(pushValue, 500); }
  
  function saveState() {
    historyStack.push(JSON.stringify(data));
    if (historyStack.length > 50) historyStack.shift();
  }

  window.addEventListener('message', (ev) => {
    if (!ev.data || ev.data.type !== 'streamlit:render') return;
    const args = ev.data.args || {};
    if (args.token !== token) {
      token = args.token;
      data = (args.pairs || []).map(p => ({en: p.en || '', ar: p.ar || ''}));
      historyStack = [];
      renderRows();
    }
  });
  post('streamlit:componentReady', {apiVersion: 1});
  post('streamlit:setFrameHeight', {height: 800});

  function toast(msg) { toastEl.textContent = msg; setTimeout(() => { if (toastEl.textContent === msg) toastEl.textContent = ''; }, 2500); }

  function moveCell(index, type, direction) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= data.length) return;
    saveState();
    const temp = data[index][type];
    data[index][type] = data[targetIndex][type];
    data[targetIndex][type] = temp;
    renderRows(); pushValue();
  }

  function makeCell(type, index) {
    const cell = document.createElement('div');
    cell.className = 'cell'; cell.dataset.index = index; cell.dataset.type = type;
    
    const handleContainer = document.createElement('div');
    handleContainer.className = 'handle-container';
    
    const upBtn = document.createElement('button');
    upBtn.className = 'move-btn'; upBtn.textContent = '▲'; upBtn.title = 'نقل للأعلى';
    upBtn.onclick = () => moveCell(index, type, -1);
    
    const handle = document.createElement('div');
    handle.className = 'handle'; handle.textContent = '⠿'; handle.draggable = true; handle.title = 'اسحب للتبديل';
    
    const downBtn = document.createElement('button');
    downBtn.className = 'move-btn'; downBtn.textContent = '▼'; downBtn.title = 'نقل للأسفل';
    downBtn.onclick = () => moveCell(index, type, 1);
    
    handleContainer.append(upBtn, handle, downBtn);

    const box = document.createElement('div');
    box.className = 'card-box ' + (type === 'en' ? 'en-box' : 'ar-box');
    box.dataset.index = index; box.dataset.type = type;
    box.contentEditable = 'plaintext-only';
    if (box.contentEditable !== 'plaintext-only') box.contentEditable = 'true';
    box.textContent = data[index][type];
    
    let prevText = box.textContent;
    box.addEventListener('focus', () => { prevText = box.innerText; });
    box.addEventListener('blur', () => {
      const currentText = box.innerText.replace(/\n$/, '');
      if (prevText !== currentText) { saveState(); data[index][type] = currentText; pushSoon(); }
    });
    box.addEventListener('input', () => { data[index][type] = box.innerText.replace(/\n$/, ''); pushSoon(); });
    box.addEventListener('paste', (e) => {
      if (box.contentEditable === 'plaintext-only') return;
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData('text/plain');
      const sel = window.getSelection();
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0);
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
      }
      data[Number(box.dataset.index)][box.dataset.type] = box.innerText.replace(/\n$/, '');
      pushSoon();
    });

    handle.addEventListener('dragstart', (e) => { drag = {index, type}; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(index)); });
    cell.addEventListener('dragover', (e) => {
      if (!drag || drag.type !== type) return;
      e.preventDefault(); cell.classList.add('drag-over');
      const scroller = document.getElementById('alignmentScroll');
      const rect = scroller.getBoundingClientRect();
      const edge = 70;
      if (e.clientY < rect.top + edge) scroller.scrollTop -= 20;
      else if (rect.bottom - e.clientY < edge) scroller.scrollTop += 20;
    });
    cell.addEventListener('dragleave', () => cell.classList.remove('drag-over'));
    cell.addEventListener('drop', (e) => {
      e.preventDefault(); cell.classList.remove('drag-over');
      if (!drag || drag.type !== type || drag.index === index) { drag = null; return; }
      saveState();
      const t = data[drag.index][type]; data[drag.index][type] = data[index][type]; data[index][type] = t;
      drag = null; renderRows(); pushValue();
    });
    
    cell.append(handleContainer, box);
    return cell;
  }

  function renderRows() {
    container.textContent = '';
    data.forEach((_, index) => {
      const row = document.createElement('div'); row.className = 'segment-row';
      const num = document.createElement('div'); num.className = 'segment-num'; num.textContent = '[' + (index + 1) + ']';
      const grp = document.createElement('div'); grp.className = 'action-btn-group';
      const sp = document.createElement('button'); sp.className = 'btn-ctrl'; sp.textContent = '✂️ تقسيم'; sp.title = 'تقسيم عند مكان المؤشر';
      const del = document.createElement('button'); del.className = 'btn-ctrl btn-del'; del.textContent = '🗑️ حذف'; del.title = 'حذف هذه الوحدة';
      [sp, del].forEach(b => b.addEventListener('mousedown', e => e.preventDefault()));
      sp.addEventListener('click', () => splitUnit(index));
      del.addEventListener('click', () => deleteRow(index));
      grp.append(sp, del);
      row.append(num, makeCell('en', index), makeCell('ar', index), grp);
      container.appendChild(row);
    });
  }

  function splitUnit(index) {
    const sel = window.getSelection();
    if (!sel.rangeCount || !sel.anchorNode) { toast('ضع المؤشر داخل النص أولاً'); return; }
    const el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
    const box = el && el.closest('.card-box');
    if (!box || Number(box.dataset.index) !== index) { toast('ضع المؤشر داخل نص هذه الوحدة ثم اضغط تقسيم'); return; }
    const type = box.dataset.type;
    const pre = document.createRange();
    pre.selectNodeContents(box); pre.setEnd(sel.anchorNode, sel.anchorOffset);
    const full = data[index][type];
    const offset = Math.min(pre.toString().length, full.length);
    const part1 = full.slice(0, offset).trim(), part2 = full.slice(offset).trim();
    if (!part2) { toast('المؤشر في نهاية النص، لا يوجد ما يُقسَّم'); return; }
    
    saveState();
    data[index][type] = part1;
    const nr = {en: '', ar: ''}; nr[type] = part2;
    data.splice(index + 1, 0, nr);
    renderRows(); pushValue();
  }

  function deleteRow(index) { saveState(); data.splice(index, 1); renderRows(); pushValue(); }
  
  document.getElementById('addBtn').addEventListener('click', () => {
    saveState();
    data.push({en: '', ar: ''}); renderRows(); pushValue();
    const scroller = document.getElementById('alignmentScroll');
    scroller.scrollTop = scroller.scrollHeight;
  });

  document.getElementById('undoBtn').addEventListener('click', () => {
    if (historyStack.length === 0) {
      toast('لا يوجد إجراء للتراجع عنه');
      return;
    }
    data = JSON.parse(historyStack.pop());
    renderRows(); pushValue();
  });
</script></body></html>"""

_COMPONENT_DIR = Path(__file__).parent / "alignment_studio_component"

def _declare_alignment_studio():
    _COMPONENT_DIR.mkdir(exist_ok=True)
    index = _COMPONENT_DIR / "index.html"
    if not index.exists() or index.read_text(encoding="utf-8") != ALIGNMENT_STUDIO_HTML:
        index.write_text(ALIGNMENT_STUDIO_HTML, encoding="utf-8")
    return components.declare_component("alignment_studio", path=str(_COMPONENT_DIR))

alignment_studio = _declare_alignment_studio()

# ---------------------------------------------------------
# Tab 1: استوديو المحاذاة الشامل الاحترافي
# ---------------------------------------------------------
with tab1:
    st.markdown("<style>.en-box{direction:ltr;text-align:left}.ar-box{direction:rtl;text-align:right} [data-testid='stDataEditor']{direction:rtl}</style>", unsafe_allow_html=True)
    st.subheader("📄 الخطوة 1: رفع ملفات Word (.docx) واستخراج النصوص")

    col_doc1, col_doc2 = st.columns(2)
    with col_doc1:
        doc_en = st.file_uploader("ارفع ملف Word المصدر (إنجليزي):", type=["docx"], key="doc_en")
    with col_doc2:
        doc_ar = st.file_uploader("ارفع ملف Word الهدف (عربي):", type=["docx"], key="doc_ar")

    if doc_en and doc_ar:
        text_en, notes_en = extract_text_from_docx_bytes(doc_en.getvalue())
        text_ar, notes_ar = extract_text_from_docx_bytes(doc_ar.getvalue())

        if text_en.strip() and text_ar.strip():
            st.success("✅ تم استخراج النصوص من ملفات Word بنجاح وسرعة فائقة!")
            all_notes = [f"EN — {n}" for n in notes_en] + [f"AR — {n}" for n in notes_ar]
            if all_notes:
                with st.expander("ℹ️ ملاحظات استخراج مستندات Word"):
                    for n in all_notes:
                        st.write("•", n)

            segs_en = process_docx_text_to_segments(text_en)
            segs_ar = process_docx_text_to_segments(text_ar)

            aligned_initial = align_segments(segs_en, segs_ar)

            st.markdown("---")
            st.subheader("🧩 الخطوة 2: استوديو المحاذاة التفاعلي")
            
            initial_pairs = [{"en": e, "ar": a} for e, a in aligned_initial]
            token = hashlib.md5((text_en + "\x00" + text_ar).encode("utf-8")).hexdigest()

            studio_value = alignment_studio(pairs=initial_pairs, token=token, key="alignment_studio", default=None)
            current_pairs = studio_value if studio_value is not None else initial_pairs
            st.session_state["alignment_draft"] = current_pairs

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("🚀 اعتماد المحاذاة النهائية وتوليد TMX", use_container_width=True):
                current_pairs = st.session_state.get("alignment_draft", current_pairs)
                final_pairs = [
                    (p["en"].strip(), p["ar"].strip()) for p in current_pairs if p["en"].strip() and p["ar"].strip()
                ]
                if final_pairs:
                    st.session_state["aligned_pairs"] = final_pairs
                    st.session_state["tmx_bytes"] = generate_tmx_file(final_pairs)
                else:
                    st.session_state["tmx_bytes"] = None
                    st.error("⚠️ يرجى التأكد من وجود جمل صالحة للتقابل.")

            if st.session_state.get("tmx_bytes"):
                st.success(f"🎉 تم اعتماد **{len(st.session_state['aligned_pairs'])}** وحدة محاذاة بنجاح!")
                st.download_button(
                    "💾 تنزيل ملف الـ TMX الموحد",
                    data=st.session_state["tmx_bytes"],
                    file_name="Aligned_Legal_Memory.tmx",
                    mime="application/x-tmx+xml",
                )
        else:
            st.error("⚠️ تعذر استخراج النصوص من ملفات Word المرفوعة.")

# ---------------------------------------------------------
# Tab 2: الاستخراج الذكي والتصدير
# ---------------------------------------------------------
with tab2:
    st.subheader("🔍 استخراج المصطلحات عبر الذكاء الاصطناعي")

    uploaded_tmx = st.file_uploader(
        "Upload your aligned .TMX memory file",
        type=["tmx"],
    )

    if uploaded_tmx is not None:
        aligned_units = parse_tmx_bytes(uploaded_tmx.read())
    else:
        aligned_units = st.session_state["aligned_pairs"]

    if aligned_units:
        if st.button("⚡ بدء الاستخراج الذكي والتصفية الصارمة"):
            if not api_key.strip():
                st.error("⚠️ يرجى إدخال مفتاح OpenRouter API Key أولاً.")
            else:
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key.strip(),
                )

                system_prompt = """You are a senior legal terminologist and termbase editor working on English–Arabic legal texts (contracts, legislation, international law, commercial and civil law). You produce entries of the kind found in a professional bilingual legal termbase.

INPUT
You will receive parallel English and Arabic legal text (possibly TMX-derived segments containing markup, numbering, or minor OCR noise — ignore these). Your task is to extract TERMS (specifically highly specialised legal words and stable legal collocations), never phrases, clauses, or sentences.

STEP 0 — FIELD DETECTION (silent)
Read the whole input and identify the dominant legal field, then the most specific sub-field of each term (e.g., "Contract Law", "Property Law", "Commercial Law", "International Public Law", "Maritime Law", "Civil Procedure"). Use short English labels (2–4 words). Reuse the same label for terms of the same sub-field; do not invent a new label per term.

WHAT COUNTS AS A TERM
A term is a lexical unit (a specialised single word or a stable legal collocation/multiword unit) that names ONE legal concept and could be a headword in a specialised legal dictionary. A candidate must pass ALL six tests:
1. Concept test: it designates a legal concept — a right, duty, liability, remedy, sanction, doctrine or principle, legal act or instrument, legal status, party type or legal role, institution or statutory body, or a procedural concept with a stable legal meaning (e.g., "burden of proof", "statute of limitations").
2. Definability test: it can be defined by genus + differentia ("X is a Y that ..."). If it can only be paraphrased, it is not a term.
3. Form test: English = a noun or noun phrase of 1–6 words with a nominal head; Arabic = 1–6 words, a noun or an idafa / noun-adjective construction. Established fixed legal collocations and expressions are allowed even if not nominal (e.g., "null and void", "bona fide", "mutatis mutandis", "force majeure").
4. Independence test: it keeps its full legal meaning outside the sentence it came from.
5. Specialisation test: it is either exclusive to law or carries a specialised legal meaning different from its ordinary meaning. Ordinary words ("building", "market", "payment date") are STRICTLY REJECTED unless they form a specific legal collocation.
6. Alignment test: the English term and its Arabic equivalent both occur in the supplied texts and correspond to each other. Use the Arabic rendering actually used in the text, not the one you consider ideal. If the equivalent cannot be identified with confidence, skip the term.

AUTOMATIC REJECTIONS
Reject any candidate that:
- contains a finite verb or modal (shall, may, must, is, are, يجب, يلتزم, ...), or is a clause or a sentence;
- is a verb phrase, a lone verb, or a lone adjective/adverb (except fixed expressions);
- is a boilerplate or preamble formula (pursuant to, in accordance with, having reviewed, in the event of, subject to, notwithstanding, بناءً على, بعد الاطلاع على, في حالة, ...);
- is a date, timestamp, number, decision number, law/resolution number, amount, percentage, duration, or article/clause/statutory reference;
- is the proper name of a specific person, company, place, or document (generic institution types such as "Court of Appeal" or "arbitral tribunal" are allowed);
- is a document-specific label ("First Party", "the Contractor", "the Premises");
- starts or ends with a preposition, conjunction, article, or punctuation;
- exceeds 6 words in either language.

NORMALISATION
- English: remove leading articles, determiners, and possessives; use the singular unless the plural is the lexicalised form ("damages", "proceeds"); keep the original capitalisation only for proper-noun parts of fixed terms.
- Arabic: remove attached conjunctions and prepositions (و، ف، ب، ل، ك) and use the form conventional in legal termbases (e.g., حق الانتفاع، القوة القاهرة).
- Do not convert between parts of speech ("liable" is not "liability").
- List each term once only.
- Nested terms: extract the longest stable unit ("right of usufruct"); extract its component ("usufruct") separately only if it also occurs independently in the text.

DEFINITION
Arabic, one sentence, at most 30 words, formal legal register, built as genus + differentia and consistent with the legal system of the text where identifiable. Do not begin with the term itself, do not copy a sentence from the text, and do not add content the text and field do not support.

QUANTITY AND QUALITY
There is no quota. Prefer precision over recall. Focus strictly on extracting robust legal collocations and highly specialised terminology. If the input contains no valid term, return {"terms": []}. Never pad the list. Order terms by first appearance in the English text.

INTERNAL CHECK (never output it)
Before answering, test every candidate against the six tests and the rejection rules, explicitly delete any dates, numbers, or decision references, and confirm that each "en" and "ar" string actually occurs in the supplied texts (allowing for inflection).

OUTPUT FORMAT
Return STRICTLY valid JSON and nothing else: no markdown, no code fences, no comments, no text before or after. Use exactly this structure:
{"terms": [{"ID": 1, "en": "English term", "ar": "Arabic equivalent", "definition": "Arabic definition", "subject field": "Detected sub-field"}]}
ID is an integer starting at 1 and increasing by 1. Keep every string on one line, escape internal quotation marks, and leave no trailing commas.

EXAMPLE
English: "The First Party grants the Second Party the right of usufruct over the building materials market for five years, and the Second Party shall be liable for any damage resulting from negligence. In the event of force majeure, neither party shall be liable for delay in performance. Issued in Decision No. 45 on October 12, 2023."
Arabic: "يمنح الطرف الأول الطرف الثاني حق الانتفاع بسوق مواد البناء لمدة خمس سنوات، ويكون الطرف الثاني مسؤولاً عن أي ضرر ناتج عن الإهمال. وفي حالة القوة القاهرة لا يتحمل أي من الطرفين المسؤولية عن التأخير في التنفيذ. صدر بالقرار رقم 45 بتاريخ 12 أكتوبر 2023."
Correct output:
{"terms": [{"ID": 1, "en": "right of usufruct", "ar": "حق الانتفاع", "definition": "حق عيني يخوّل صاحبه استعمال شيء مملوك للغير والانتفاع بثماره مدة معينة دون التصرف في رقبته.", "subject field": "Property Law"}, {"ID": 2, "en": "negligence", "ar": "الإهمال", "definition": "إخلال بواجب العناية الذي يفرضه القانون يترتب عليه ضرر للغير.", "subject field": "Contract Law"}, {"ID": 3, "en": "force majeure", "ar": "القوة القاهرة", "definition": "حادث خارجي غير متوقع يستحيل دفعه يجعل تنفيذ الالتزام مستحيلًا دون خطأ من المدين.", "subject field": "Contract Law"}]}
Correctly rejected here (never output these): "the Second Party shall be liable for any damage" (clause), "In the event of" (formula), "for five years" (duration), "building materials market" (ordinary noun phrase), "Decision No. 45" (decision number), "October 12, 2023" (date).
"""

                results = []
                progress_bar = st.progress(0)
                status_text = st.empty()

                def _s(item, key, default=""):
                    return str(item.get(key) or default).strip()

                MAX_CHARS = 8000 

                for i, (en_text, ar_text) in enumerate(aligned_units):
                    status_text.text(
                        f"جاري تحليل الوحدة ({i+1}/{len(aligned_units)})... عبر نموذج `{selected_model_id}`"
                    )

                    en_send = en_text[:MAX_CHARS // 2] if len(en_text) > MAX_CHARS // 2 else en_text
                    ar_send = ar_text[:MAX_CHARS // 2] if len(ar_text) > MAX_CHARS // 2 else ar_text
                    user_prompt = f"[EN]: {en_send}\n[AR]: {ar_send}"

                    try:
                        response = client.chat.completions.create(
                            model=selected_model_id,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.0,
                            response_format={"type": "json_object"},
                        )

                        raw_text = response.choices[0].message.content or ""
                        # حماية إضافية: إزالة أي محيط Markdown قد يضيفه النموذج رغم التعليمات الصارمة
                        cleaned = raw_text.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
                            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
                        raw = json.loads(cleaned)
                        terms = raw.get("terms", []) if isinstance(raw, dict) else raw

                        if terms and isinstance(terms, list):
                            for item in terms:
                                if isinstance(item, dict) and item.get("en") and not _is_low_value_term(item.get("en")):
                                    results.append({
                                        "en": _s(item, "en"),
                                        "ar": _s(item, "ar"),
                                        "Definition": _s(item, "definition"),
                                        "Subject field": _s(item, "subject field", "قانون عام"),
                                        "en Source text": en_text,
                                        "ar Source text": ar_text,
                                    })
                    except Exception as e:
                        st.warning(f"تنبيه في الوحدة {i+1}: {e}")

                    progress_bar.progress((i + 1) / len(aligned_units))

                status_text.text("✅ اكتمل الاستخراج والتصفية بنجاح!")

                if results:
                    df = pd.DataFrame(results)
                    df["_key"] = df["en"].map(_term_key) + "|" + df["ar"].map(_term_key)
                    df = df.groupby("_key", as_index=False, sort=False).agg({
                        "en":"first", "ar":"first", "Definition":"first", "Subject field":"first",
                        "en Source text":lambda x: "\n---\n".join(dict.fromkeys(x)),
                        "ar Source text":lambda x: "\n---\n".join(dict.fromkeys(x)),
                    })

                    df.drop(columns=["_key"], inplace=True)
                    # ترقيم تسلسلي للمصطلحات (1..N) بعد إزالة التكرار
                    df["ID"] = range(1, len(df) + 1)
                    df = df[["ID", "en", "ar", "Definition", "Subject field", "en Source text", "ar Source text"]]
                    st.session_state["results_df"] = df

                    # تجهيز الإرسال إلى القاموس: بدون عمود ID لأن القاموس لديه نظام ترقيم خاص به
                    # إرسال العمودين الجديدين (source text ar و source text en) بالصيغتين (بالمسافة والشرطة السفلية) لضمان التوافق التام مع واجهة القاموس
                    terms_to_send = [
                        {
                            "en": str(row.get("en", "")).strip(),
                            "ar": str(row.get("ar", "")).strip(),
                            "definition": str(row.get("Definition", "") or row.get("definition", "")).strip(),
                            "subject field": str(row.get("Subject field", "") or row.get("subject field", "")).strip(),
                            "source_text_en": str(row.get("en Source text", "") or row.get("source text en", "") or row.get("source_text_en", "")).strip(),
                            "source_text_ar": str(row.get("ar Source text", "") or row.get("source text ar", "") or row.get("source_text_ar", "")).strip(),
                            "source text en": str(row.get("en Source text", "") or row.get("source text en", "") or row.get("source_text_en", "")).strip(),
                            "source text ar": str(row.get("ar Source text", "") or row.get("source text ar", "") or row.get("source_text_ar", "")).strip(),
                        }
                        for _, row in df.iterrows() if row.get("en")
                    ]

                    if terms_to_send and send_to_dictionary(terms_to_send):
                        st.success("🚀 تم إرسال المصطلحات المستخرجة بنجاح إلى القاموس!")

                else:
                    st.error("لم يتم العثور على مصطلحات موضوعية بعد التصفية.")
                    
    # عرض النتائج والتصدير
    if st.session_state["results_df"] is not None:
        df_res = st.session_state["results_df"]

        st.subheader("📊 جدول المصطلحات المستخرجة:")
        edited_df = st.data_editor(
            df_res, use_container_width=True, hide_index=True, num_rows="dynamic",
            key="terms_editor",
        )
        st.session_state["results_df"] = edited_df
        df_res = edited_df

        # تجهيز التصدير بجميع الأعمدة المطلوبة (Excel وCSV فقط — بدون PDF أو Word)
        export_df = df_res.copy()
        # إعادة الترقيم التسلسلي للمصطلحات في ملفات التحميل حتى بعد أي تعديل أو حذف بالجدول
        export_df["ID"] = range(1, len(export_df) + 1)
        export_df = export_df[["ID", "en", "ar", "Definition", "Subject field", "en Source text", "ar Source text"]]

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False)
        excel_buffer.seek(0)

        csv_data = export_df.to_csv(index=False).encode("utf-8-sig")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                label="📥 تنزيل مسرد المصطلحات (Excel)",
                data=excel_buffer,
                file_name="Extracted_Legal_Glossary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col_d2:
            st.download_button("📄 تنزيل CSV (UTF-8)", data=csv_data, file_name="Extracted_Legal_Glossary.csv", mime="text/csv; charset=utf-8")

# =========================================================
# 8. التذييل بأسفل الصفحة
# =========================================================
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
<div class="lexterm-footer">
    <h3 style="text-align: center;">📫 تواصل معي (Contact & Support)</h3>
    <p style="font-size: 15px; color: #F2F5FA; margin: 5px; text-align: center;"><b>إعداد وتطوير:</b> يوسف نورالدين</p>
    <p style="font-size: 15px; color: #F2F5FA; margin: 5px; text-align: center;">📱 <b>الهاتف:</b> <a href="tel:0928756918" style="color: #E8C069; text-decoration: none;">0928756918</a> | ✉️ <b>البريد:</b> <a href="mailto:ywsfalmqmz@gmail.com" style="color: #E8C069; text-decoration: none;">ywsfalmqmz@gmail.com</a></p>
    <hr style="margin: 15px auto; width: 40%; border-top: 1px solid #1D3050;">
    <p style="font-size: 12px; color: #93A5C4; text-align: center;">جميع الحقوق محفوظة © <span class="footer-brand">Lex<span class="term">Term</span></span> — منصة المصطلحات القانونية الذكية</p>
</div>
""",
    unsafe_allow_html=True,
)
