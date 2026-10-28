
<div align="center">

# ⚖️ AI Legal Workspace
### منصة المعالجة الذكية للنصوص القانونية

**A Bilingual AI-Powered Legal Text Processing Platform**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-LLM_API-6C47FF?style=for-the-badge)](https://openrouter.ai)
[![License](https://img.shields.io/badge/License-Academic_Use-gold?style=for-the-badge)](#)

> 🎓 **University Graduation Project** | Department of Translation Studies  
> *Developed by Youssef Nour Eldin*

---

[🔗 Live Dictionary Platform](https://dictionaryly.onrender.com) • [📖 Documentation](#-how-to-use) • [🚀 Quick Start](#-quick-start)

</div>

---

## 📌 Overview | نظرة عامة

**AI Legal Workspace** is an intelligent bilingual (Arabic ↔ English) legal document processing platform designed to assist legal translators in building high-quality, standardized terminology resources. It was developed as a graduation project for the **Department of Translation Studies**, addressing the real challenge of producing bilingual legal glossaries from parallel legal documents.

**AI Legal Workspace** هي منصة ذكية لمعالجة النصوص القانونية ثنائية اللغة (عربي ↔ إنجليزي)، صُممت لمساعدة المترجمين القانونيين على بناء موارد مصطلحية موحّدة وعالية الجودة. طُوِّرت كمشروع تخرج في **قسم الترجمة**، لمعالجة التحدي الحقيقي المتمثّل في إنتاج معاجم قانونية ثنائية اللغة من وثائق قانونية متوازية.

---

## ✨ Features | المميزات

### 🔀 Tab 1 — Alignment Studio (Beta)
> أداة المحاذاة التفاعلية

- **Automatic sentence alignment** of uploaded EN/AR `.docx` documents using a dynamic programming (DP) algorithm supporting 1:1, 1:2, and 2:1 merge ratios.
- **Interactive Alignment Editor** — a custom-built web component (vanilla JS) that allows the translator to:
  - ✏️ Edit any cell directly
  - ↕️ Drag-and-drop reorder segments
  - ✂️ Split a segment at cursor position
  - 🗑️ Delete unwanted rows
  - ➕ Add empty rows manually
  - ↩️ Undo up to 50 steps
- **TMX Export** — generates a standard Translation Memory eXchange (TMX 3.0) file, compatible with industry CAT tools (SDL Trados, MemoQ, OmegaT).

---

### 🤖 Tab 2 — AI Term Extractor
> مستخرج المصطلحات الذكي

- Accepts TMX input (uploaded file **or** in-memory pairs from Tab 1 — no data loss between tabs).
- **LLM-powered extraction** via [OpenRouter](https://openrouter.ai) with choice of:
  | Model | Use Case |
  |---|---|
  | ⚡ Gemini 3.8 Flash | Fast, high-quality — recommended |
  | ⚖️ GPT-4o Mini | Reliable general-purpose |
  | 🦙 Llama 4 Maverick | Open-weight alternative |
- **Strict filtering** removes stopwords, procedural phrases, article numbers, and short non-legal tokens.
- **Smart deduplication** via text normalization + groupby (casefold, punctuation-stripped keys).
- Each extracted term includes:
  - 🇬🇧 English term
  - 🇸🇦 Arabic equivalent
  - 📚 Arabic legal definition
  - 🏷️ Subject field (e.g., *International Public Law*, *Contractual Obligations*)
  - 💬 Source context sentences (EN + AR)
- **Automatic push** to the [AI Legal Dictionary](https://dictionaryly.onrender.com) platform for admin review.
- **Three export formats:**
  - 📊 `.xlsx` — Excel glossary
  - 📄 `.csv` — UTF-8 CSV with BOM (for Arabic compatibility)
  - 🗂️ `.pdf` — Formatted A4 terminology cards (ReportLab, RTL-ready Arabic)

---

## 🏗️ Architecture | البنية التقنية

```
app.py (899 lines — entire application)
│
├── normalize_text()            Unicode NFKC + invisible char removal
├── align_segments()            DP sentence alignment (1:1 / 1:2 / 2:1)
├── _is_low_value_term()        Stopword + short-token filter
├── _term_key()                 Deduplication key normalizer
├── extract_text_from_docx_bytes()   python-docx text + table extraction
├── process_docx_text_to_segments()  Regex sentence splitter (abbrev-aware)
├── parse_tmx_bytes()           TMX XML parser (xml.etree)
├── generate_tmx_file()         TMX 3.0 builder
├── generate_pdf_cards_bytes()  ReportLab A4 terminology cards
├── send_to_dictionary()        HTTP POST batches → dictionaryly.onrender.com
├── prepare_arabic_text()       arabic-reshaper + python-bidi for RTL PDF
└── _declare_alignment_studio() Writes + registers embedded JS component
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- An [OpenRouter API Key](https://openrouter.ai/keys) (free tier available)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yousefdg005/qwqw.git
cd qwqw

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
streamlit run app.py
```

### First Use
1. Open the app in your browser (usually `http://localhost:8501`)
2. Click **⚙️** in the sidebar to enter your OpenRouter API key
3. Select your preferred LLM model
4. Upload your parallel legal documents (EN + AR `.docx`) in **Tab 1**
5. Refine the alignment, then switch to **Tab 2** to extract terms

---

## 📦 Dependencies

```
streamlit          # Web UI framework
openai             # OpenAI-compatible SDK (used for OpenRouter)
pandas             # Data manipulation & deduplication
openpyxl           # Excel export
python-docx        # DOCX parsing
reportlab          # PDF generation
arabic-reshaper    # Arabic text shaping for PDF
python-bidi        # Bidirectional text algorithm
```

---

## 🔄 Data Flow

```
EN .docx + AR .docx
       ↓
  Text Extraction
  (python-docx)
       ↓
  Sentence Segmentation
  (regex, abbrev-aware)
       ↓
  DP Alignment Algorithm
  (1:1 / 1:2 / 2:1 merges)
       ↓
  Alignment Studio
  (interactive editing)
       ↓
  TMX File ──────────────────────────────────┐
       ↓                                     │
  LLM Term Extraction                        │
  (OpenRouter API, JSON mode)                │ reusable in CAT tools
       ↓                                     │
  Filter + Deduplicate                       │
       ↓                                     │
  ┌─────────────────────────────────┐        │
  │  Export: .xlsx / .csv / .pdf   │        │
  └─────────────────────────────────┘        │
       ↓                                     │
  Auto-push to AI Legal Dictionary ←─────────┘
  (for admin review & publication)
```

---

## 🎓 Academic Context

This project was developed as part of the graduation requirements for the **Department of Translation Studies**. It addresses the following research problems:

1. **Terminological inconsistency** in Arabic legal translation — the lack of standardized equivalents for technical legal terms.
2. **Manual bottleneck** — the time-intensive process of manually building bilingual glossaries from parallel legal corpora.
3. **Tool accessibility** — professional CAT tools and terminology management systems are expensive and inaccessible to students and independent translators.

The platform bridges **computational linguistics** (sentence alignment, NLP preprocessing) with **AI-assisted translation** workflows, demonstrating that modern LLMs can be applied meaningfully to specialized domain terminology extraction.

---

## 👤 Developer

**Youssef Nour Eldin**  
Translation Studies Department  
📧 ywsfalmqmz@gmail.com  
📞 0928756918

---

## 🔗 Related Project

This tool is part of a two-component ecosystem. Extracted terms are automatically sent to the companion platform:

➡️ **[AI Legal Dictionary](https://github.com/yousefdg005/-)** — A Flask-based bilingual legal dictionary with admin review pipeline and public reader interface.

---

<div align="center">

*Built with ❤️ for the legal translation community*  
*© 2026 Youssef Nour Eldin — All rights reserved*

</div>
