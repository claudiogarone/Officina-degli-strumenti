# -*- coding: utf-8 -*-
"""
Dashboard Registri Lezioni Private
Autore: Claudio Vincenzo Garone - ENESTAR Maker Lab
Legge automaticamente tutti i registri (Google Sheets nativi e .xlsx)
contenuti in una cartella di Google Drive e ne ricava una dashboard interattiva.
"""

import io
import os
import re
import datetime as dt

import requests
from typing import Optional

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

try:
    import cancelleria as CANC
    CANCELLERIA_OK = True
    CANCELLERIA_ERRORE = ""
except Exception as _e:          # manca reportlab o il file cancelleria.py
    CANCELLERIA_OK = False
    CANCELLERIA_ERRORE = str(_e)

# ============================================================================
# CONFIGURAZIONE PAGINA
# ============================================================================

# ---------------------------------------------------------------------------
# IDENTITÀ DELL'APPLICAZIONE
# Cambia queste quattro righe per rinominare tutto: titolo della scheda del
# browser, intestazione, sottotitolo. Il logo si prende da loghi/enestar.jpg.
# ---------------------------------------------------------------------------

APP_MARCHIO = "ENESTAR"
APP_NOME = "Quadro"
APP_PAYOFF = "Il quadro di comando del Maker Lab"
APP_TITOLO_BROWSER = "ENESTAR · Quadro"
APP_LOGO = "enestar.jpg"          # dentro la cartella loghi/

VERDE = "#1BAF7A"
VERDE_SCURO = "#0E7A54"
VERDE_CHIARO = "#8FE3C4"
GRAFITE = "#16200F"


def _icona_pagina():
    """Il logo come icona della scheda del browser; se manca, un'emoji."""
    try:
        from PIL import Image
        return Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "loghi", APP_LOGO))
    except Exception:
        return "🌿"


st.set_page_config(
    page_title=APP_TITOLO_BROWSER,
    page_icon=_icona_pagina(),
    layout="wide",
    # "auto": aperta su PC, chiusa su smartphone (si apre col pulsante ☰)
    initial_sidebar_state="auto",
)

# ---------------------------------------------------------------------------
# Palette (validata per daltonismo - non modificare l'ordine degli slot)
# ---------------------------------------------------------------------------
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
           "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ = ["#e8f0fb", "#c5dbf5", "#93bced", "#5b9ae2", "#2a78d6", "#1d5aa5", "#123c70"]
C_OK, C_WARN, C_BAD = "#1baf7a", "#eda100", "#e34948"
GRID = "rgba(128,128,128,0.18)"
INK, INK2 = "#1a1a19", "#6b6a66"

PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=13, color=INK2),
    margin=dict(l=10, r=10, t=50, b=10),
    hoverlabel=dict(font_size=13, bordercolor="rgba(0,0,0,0.1)"),
    title=dict(font=dict(size=16, color=INK)),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID),
    legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                bgcolor="rgba(0,0,0,0)"),
)


def style(fig, height=380, title=None, showlegend=None):
    fig.update_layout(**PLOT_LAYOUT, height=height)
    if title:
        fig.update_layout(title=title)
    if showlegend is not None:
        fig.update_layout(showlegend=showlegend)
    return fig


import diario as DIARIO          # anche per l'ora italiana: DIARIO.adesso()
import voce as VOCE              # caselle che si possono dettare o scrivere a mano


def svuota_dopo(chiave):
    """
    Segna una casella di testo da svuotare al prossimo ricaricamento.

    Streamlit non permette di cambiare il contenuto di una casella dopo
    averla già disegnata in quel giro: solleva un errore. Il modo giusto è
    lasciare un biglietto adesso e svuotarla all'inizio del giro successivo,
    prima che venga creata — ci pensa `pulisci_se_segnata`.
    """
    st.session_state[f"__svuota__{chiave}"] = True


def pulisci_se_segnata(chiave):
    """Da chiamare subito prima di disegnare la casella."""
    if st.session_state.pop(f"__svuota__{chiave}", False):
        st.session_state[chiave] = ""


def chiave_ai():
    """La chiave di Google AI Studio: dai Secrets, o quella messa a mano."""
    return ((secret("google_api_key", "") or "").strip()
            or st.session_state.get("chiave_ai", ""))


def modello_ai():
    """
    Il nome del modello, da un posto solo: `studio.json`, campo ai.modello.

    Prima ogni sezione aveva il suo valore scritto nel codice, e quando Google
    ritirava un modello bisognava cambiarlo in quattro punti. Ora si cambia lì
    e vale ovunque.
    """
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "studio.json"), encoding="utf-8") as f:
            m = (_json.load(f).get("ai") or {}).get("modello")
        if m:
            return m
    except Exception:
        pass
    return "gemini-flash-latest"


def conferma(messaggio):
    """
    Conferma di salvataggio che si vede davvero.

    Il problema: dopo un salvataggio la pagina si ricarica, e un st.success()
    scritto prima del ricaricamento sparisce senza che tu faccia in tempo a
    leggerlo. Il toast invece resta a schermo attraverso il ricaricamento, e
    il messaggio viene anche messo da parte per mostrarlo in cima alla
    sezione al giro dopo.
    """
    st.toast(f"✅ {messaggio}")
    st.session_state["ultima_conferma"] = (messaggio, DIARIO.adesso())


def mostra_conferma():
    """Ripesca l'ultima conferma, se è recente. Da chiamare in cima a una sezione."""
    dato = st.session_state.get("ultima_conferma")
    if not dato:
        return
    messaggio, quando = dato
    if (DIARIO.adesso() - quando).total_seconds() < 25:
        st.success(f"✅ {messaggio} · {quando:%H:%M}")
    else:
        st.session_state.pop("ultima_conferma", None)


def pagina_html(html, altezza=600):
    """
    Mostra una pagina HTML dentro la dashboard.

    `st.iframe` è il modo nuovo; `components.html` resta come scorta per le
    versioni di Streamlit più vecchie, dove `st.iframe` non esiste ancora.
    """
    if hasattr(st, "iframe"):
        return st.iframe(html, height=altezza)
    import streamlit.components.v1 as components
    return components.html(html, height=altezza, scrolling=True)


def pulsante_ascolta(testo, etichetta="🔊 Ascolta"):
    """
    Legge un testo ad alta voce con la voce del browser: gratis, nessuna
    chiave. Il pulsante diventa «■ Ferma» mentre parla.
    """
    import json as _json
    if not str(testo or "").strip():
        return
    dati = _json.dumps(str(testo)[:2500]).replace("</", "<\\/")
    pagina_html(f"""
<style>
  body {{ margin: 0; font-family: sans-serif; }}
  button {{ width: 100%; font-size: 14px; padding: 6px 10px; border-radius: 8px;
           border: 1px solid #2a78d6; background: #2a78d6; color: #fff;
           cursor: pointer; }}
  button.ferma {{ background: #fff; color: #2a78d6; }}
</style>
<button id="b">{etichetta}</button>
<script>
  const T = {dati};
  const b = document.getElementById('b');
  const ETICHETTA = {_json.dumps(etichetta)};
  function torna() {{ b.textContent = ETICHETTA; b.className = ''; }}
  b.onclick = () => {{
    if (!('speechSynthesis' in window)) {{
      b.textContent = 'Questo browser non legge ad alta voce'; return;
    }}
    if (speechSynthesis.speaking) {{ speechSynthesis.cancel(); torna(); return; }}
    const u = new SpeechSynthesisUtterance(T);
    u.lang = 'it-IT';
    const voci = speechSynthesis.getVoices().filter(
      v => v.lang && v.lang.toLowerCase().startsWith('it'));
    if (voci.length) u.voice = voci[0];
    u.rate = 1;
    u.onend = torna;
    u.onerror = torna;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
    b.textContent = '■ Ferma'; b.className = 'ferma';
  }};
</script>""", altezza=44)


def scarica_tabella(tab, nome_file, etichetta="⬇️ Scarica i dati"):
    """
    Due pulsanti sotto a una tabella o a un grafico: CSV ed Excel.

    Sta in una funzione sola perché serve in una ventina di punti, e così
    quando vorrai cambiare qualcosa (il separatore, il nome dei file) la
    cambi qui una volta e vale ovunque.

    Nota sui grafici: il PNG non serve che lo faccia io. Ogni grafico ha in
    alto a destra, al passaggio del mouse, un'icona a forma di macchina
    fotografica che lo salva come immagine. Da telefono si tiene premuto.
    """
    import io as _io
    t = tab.copy()
    for c in t.columns:
        if pd.api.types.is_datetime64_any_dtype(t[c]):
            t[c] = t[c].dt.strftime("%Y-%m-%d")
    c1, c2 = st.columns(2)
    c1.download_button(f"{etichetta} (CSV)",
                       t.to_csv(index=False).encode("utf-8-sig"),
                       f"{nome_file}.csv", "text/csv",
                       width='stretch', key=f"csv_{nome_file}")
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        t.to_excel(w, index=False, sheet_name="Dati")
    c2.download_button(f"{etichetta} (Excel)", buf.getvalue(),
                       f"{nome_file}.xlsx",
                       "application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet",
                       width='stretch', key=f"xls_{nome_file}")


st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px;}
  [data-testid="stMetricValue"] {font-size: 1.75rem; font-weight: 650;}
  [data-testid="stMetricLabel"] {font-size: .82rem; opacity:.75; letter-spacing:.02em;}
  div[data-testid="stMetric"] {
      background: rgba(128,128,128,.06);
      border: 1px solid rgba(128,128,128,.14);
      border-radius: 12px; padding: .9rem 1rem;
  }
  h1 {font-size: 1.9rem !important; font-weight: 700 !important;}

  /* ---- tessere piccole del riepilogo ---- */
  .qd-tessere {display:flex; flex-wrap:wrap; gap:.5rem; margin:.2rem 0 .9rem 0;}
  .qd-t {
      flex:1 1 112px; min-width:102px;
      background: rgba(27,175,122,.07);
      border: 1px solid rgba(27,175,122,.20);
      border-radius: 9px; padding:.45rem .6rem;
  }
  .qd-t-eti {font-size:.70rem; opacity:.72; letter-spacing:.01em; line-height:1.15;}
  .qd-t-val {font-size:1.12rem; font-weight:680; line-height:1.3;}
  .qd-t-nota {font-size:.64rem; opacity:.62;}
  @media (max-width: 640px) { .qd-t {flex:1 1 44%;} }
  .stTabs [data-baseweb="tab"] {font-size: 0.95rem; font-weight: 550;}

  /* ===================== INTESTAZIONE ENESTAR ===================== */
  .qd-header {
      position: relative; overflow: hidden;
      display: flex; align-items: center; justify-content: space-between;
      gap: 1rem; padding: 1.15rem 1.4rem; margin: 0 0 .6rem 0;
      border-radius: 18px;
      background:
        radial-gradient(120% 160% at 0% 0%, rgba(27,175,122,.16) 0%, rgba(27,175,122,0) 58%),
        linear-gradient(135deg, rgba(27,175,122,.10) 0%, rgba(27,175,122,.02) 55%, rgba(143,227,196,.10) 100%);
      border: 1px solid rgba(27,175,122,.28);
  }
  .qd-piste {
      position: absolute; inset: 0; width: 100%; height: 100%;
      pointer-events: none;
  }
  .qd-base {opacity: .30;}
  .qd-nodi {opacity: .45;}
  /* un impulso che percorre le piste, come un segnale sul circuito */
  .qd-impulso {
      opacity: .85;
      stroke-dasharray: 26 1400; stroke-dashoffset: 0;
      animation: qd-impulso 9s linear infinite;
  }
  @keyframes qd-impulso { to { stroke-dashoffset: -1426; } }
  .qd-header:hover .qd-impulso {animation-duration: 3.5s;}
  @media (prefers-reduced-motion: reduce) {
      .qd-impulso {animation: none; opacity: 0;}
  }

  .qd-marchio {position: relative; display: flex; align-items: center; gap: .9rem;}
  .qd-logo {
      width: 58px; height: 58px; border-radius: 14px; object-fit: cover;
      box-shadow: 0 3px 14px rgba(14,122,84,.26);
      transition: transform .25s ease, box-shadow .25s ease;
  }
  .qd-header:hover .qd-logo {
      transform: translateY(-2px) scale(1.04);
      box-shadow: 0 7px 22px rgba(14,122,84,.34);
  }
  .qd-logo-vuoto {
      display: flex; align-items: center; justify-content: center;
      background: linear-gradient(135deg, #1BAF7A, #0E7A54);
      color: #fff; font-weight: 800; letter-spacing: .04em;
  }
  h1.qd-nome {
      font-size: 1.95rem !important; font-weight: 750 !important; line-height: 1.05;
      letter-spacing: -.015em; color: #16200F;
      margin: 0 !important; padding: 0 !important;
  }
  h1.qd-nome span {
      color: #0E7A54; letter-spacing: .06em; font-weight: 800;
  }
  .qd-payoff {
      font-size: .86rem; color: #4d5a46; margin-top: .22rem;
      letter-spacing: .01em;
  }
  .qd-stato {position: relative; text-align: right;}
  .qd-saluto {font-size: .95rem; font-weight: 650; color: #16200F;}
  .qd-data {font-size: .78rem; color: #6d7a66;}

  /* riquadri che rispondono al passaggio del mouse */
  div[data-testid="stMetric"] {
      transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
  }
  div[data-testid="stMetric"]:hover {
      transform: translateY(-2px);
      border-color: rgba(27,175,122,.55);
      box-shadow: 0 6px 18px rgba(14,122,84,.14);
  }
  .stTabs [data-baseweb="tab"]:hover {color: #0E7A54;}

  /* fondo scuro: colori leggibili */
  @media (prefers-color-scheme: dark) {
      h1.qd-nome, .qd-saluto {color: #EAF2E6;}
      h1.qd-nome span {color: #8FE3C4;}
      .qd-payoff {color: #a9b8a3;}
      .qd-data {color: #93a38d;}
      .qd-header {border-color: rgba(143,227,196,.26);}
  }

  @media (max-width: 820px) {
      .qd-header {flex-direction: column; align-items: flex-start; gap: .6rem;
                  padding: .9rem 1rem; border-radius: 14px;}
      .qd-logo {width: 46px; height: 46px; border-radius: 11px;}
      h1.qd-nome {font-size: 1.45rem !important;}
      .qd-payoff {font-size: .78rem;}
      .qd-stato {text-align: left;}
  }

  /* ---------- TABLET (fino a 1024px): due colonne al massimo ---------- */
  @media (max-width: 1024px) {
    .block-container {padding-left: 1.1rem; padding-right: 1.1rem; padding-top: 1.4rem;}
    [data-testid="stMetricValue"] {font-size: 1.4rem;}
  }

  /* ---------- SMARTPHONE (fino a 820px): tutto impilato ---------- */
  @media (max-width: 820px) {
    /* padding alto generoso: sotto la barra con ☰ e il menu di Streamlit */
    .block-container {padding-left: .7rem; padding-right: .7rem; padding-top: 3.4rem;}

    /* le colonne affiancate diventano una sotto l'altra */
    [data-testid="stHorizontalBlock"] {flex-wrap: wrap !important; gap: .6rem !important;}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }

    /* i riquadri KPI restano affiancati a due a due */
    [data-testid="stHorizontalBlock"]:has(.kpi-mark) > [data-testid="stColumn"] {
        flex: 1 1 calc(50% - .6rem) !important;
        min-width: calc(50% - .6rem) !important;
        width: auto !important;
    }

    h1 {font-size: 1.35rem !important; line-height: 1.25;}
    h5, .stMarkdown h5 {font-size: .95rem !important;}
    [data-testid="stMetricValue"] {font-size: 1.15rem;}
    [data-testid="stMetricLabel"] {font-size: .7rem;}
    div[data-testid="stMetric"] {padding: .55rem .6rem; border-radius: 10px;}

    /* le schede scorrono in orizzontale invece di andare a capo */
    .stTabs [data-baseweb="tab-list"] {
        overflow-x: auto; flex-wrap: nowrap; scrollbar-width: none;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {display: none;}
    .stTabs [data-baseweb="tab"] {font-size: .82rem; padding: .4rem .55rem; white-space: nowrap;}

    /* tabelle e grafici sempre entro lo schermo */
    [data-testid="stDataFrame"] {font-size: .78rem;}
    .js-plotly-plot, .plot-container {max-width: 100% !important;}
  }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# COLONNE CANONICHE  (A -> AA, 27 colonne)
# ============================================================================

COLS = [
    "Materia",                      # A
    "Allievo",                      # B
    "Numero Lezione",               # C
    "Data",                         # D
    "Mese",                         # E
    "Anno",                         # F
    "Ora Inizio",                   # G
    "Ora Fine",                     # H
    "Durata Lezione (Ore)",         # I
    "Ore preparazione",             # J
    "Totale Ore",                   # K
    "Argomento",                    # L
    "Materiale Fornito",            # M
    "Compito Assegnato",            # N
    "Compito Superato",             # O
    "Link Compito Assegnato",       # P
    "Link Report Risultati",        # Q
    "Voto",                         # R
    "Note",                         # S
    "Pagamento Ricevuto",           # T
    "Importo (€)",                  # U
    "Data Pagamento",               # V
    "Estremi Pagamento",            # W
    "Link Riunione",                # X
    "Link Registrazione",           # Y
    "Link Dispense",                # Z
    "Link Mappe Concettuali",       # AA
]
N_COLS = len(COLS)

MESI_IT = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
           "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
GIORNI_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]


# ============================================================================
# PARSER ROBUSTI  (i registri contengono tipi misti: str / time / float / datetime)
# ============================================================================

def _vuoto(v) -> bool:
    """True per None, NaN, NaT, stringhe vuote o segnaposto."""
    if v is None:
        return True
    try:
        if v is pd.NaT or (not isinstance(v, (list, tuple, dict)) and pd.isna(v)):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip().lower() in ("", "nan", "nat", "none", "-", "/", "n/a"):
        return True
    return False


def p_date(v) -> Optional[pd.Timestamp]:
    """Data da datetime, date, stringa gg/mm/aaaa, seriale Excel."""
    if _vuoto(v):
        return None
    if isinstance(v, dt.datetime):
        return pd.Timestamp(v).normalize()
    if isinstance(v, dt.date):
        return pd.Timestamp(v)
    if isinstance(v, (int, float)):
        try:
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
        except Exception:
            return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return None
    for dayfirst in (True, False):
        try:
            d = pd.to_datetime(s, dayfirst=dayfirst, errors="raise")
            return pd.Timestamp(d).normalize()
        except Exception:
            continue
    return None


def p_time(v) -> Optional[dt.time]:
    """Orario da time, datetime, stringa hh:mm[:ss], frazione di giorno."""
    if _vuoto(v):
        return None
    if isinstance(v, dt.time):
        return v
    if isinstance(v, dt.datetime):
        return v.time()
    if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
        f = float(v) % 1.0
        sec = int(round(f * 86400))
        return (dt.datetime(2000, 1, 1) + dt.timedelta(seconds=sec)).time()
    s = str(v).strip()
    m = re.match(r"^(\d{1,2})[:.](\d{1,2})(?:[:.](\d{1,2}))?", s)
    if m:
        h, mi = int(m.group(1)) % 24, int(m.group(2))
        se = int(m.group(3) or 0)
        try:
            return dt.time(h, min(mi, 59), min(se, 59))
        except Exception:
            return None
    return None


def p_hours(v) -> float:
    """Durata -> ore decimali. Gestisce '1:15:00', time(1,15), 0.0625, '1,5'."""
    if _vuoto(v):
        return 0.0
    if isinstance(v, dt.time):
        return v.hour + v.minute / 60 + v.second / 3600
    if isinstance(v, dt.timedelta):
        return v.total_seconds() / 3600
    if isinstance(v, dt.datetime):
        return v.hour + v.minute / 60 + v.second / 3600
    if isinstance(v, (int, float)):
        if isinstance(v, float) and np.isnan(v):
            return 0.0
        f = float(v)
        # valore < 1 = frazione di giorno (formato Excel durata); altrimenti ore
        return f * 24 if 0 < f < 1 else f
    s = str(v).strip().replace(",", ".")
    if not s or s.lower() in ("nan", "none", "-"):
        return 0.0
    m = re.match(r"^(\d+)[:.](\d{1,2})(?::(\d{1,2}))?$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60 + int(m.group(3) or 0) / 3600
    try:
        f = float(re.sub(r"[^\d.\-]", "", s))
        return f * 24 if 0 < f < 1 else f
    except Exception:
        return 0.0


def p_money(v) -> float:
    """Importo €. Alcune celle sono formattate come ora (10:00:00 = 10 €)."""
    if _vuoto(v):
        return 0.0
    if isinstance(v, dt.time):
        return v.hour + v.minute / 60 + v.second / 3600
    if isinstance(v, (int, float)):
        return 0.0 if (isinstance(v, float) and np.isnan(v)) else float(v)
    s = str(v).strip().replace("€", "").replace(" ", "")
    if not s or s.lower() in ("nan", "none", "-"):
        return 0.0
    m = re.match(r"^(\d{1,2})[:.](\d{2})(?::\d{2})?$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    s = s.replace(".", "").replace(",", ".") if ("," in s and "." in s) else s.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.\-]", "", s))
    except Exception:
        return 0.0


def p_bool(v) -> Optional[bool]:
    """Sì/No tollerante a maiuscole, accenti, x, 1/0."""
    if _vuoto(v):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and np.isnan(v):
            return None
        return bool(v)
    s = str(v).strip().lower()
    if not s or s in ("nan", "none", "-", "/"):
        return None
    if s in ("si", "sì", "s", "yes", "y", "true", "vero", "x", "1", "ok", "pagato"):
        return True
    if s in ("no", "n", "false", "falso", "0", "non pagato"):
        return False
    return None


def p_float(v) -> Optional[float]:
    if _vuoto(v):
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and np.isnan(v)) else float(v)
    s = str(v).strip().replace(",", ".")
    try:
        return float(re.sub(r"[^\d.\-]", "", s))
    except Exception:
        return None


def p_str(v) -> str:
    if _vuoto(v):
        return ""
    return str(v).strip()


# ============================================================================
# LETTURA WORKBOOK
# ============================================================================

def sheet_is_registro(name: str) -> bool:
    """Legge SOLO le schede del registro. Esclude Monitoraggio / Appoggio."""
    n = (name or "").strip().lower()
    if any(x in n for x in ("monitoraggio", "appoggio", "supporto", "calcoli",
                            "config", "pivot", "grafic")):
        return False
    return "registro" in n or "lezioni" in n


def read_workbook(content: bytes, source_name: str, diag: list) -> pd.DataFrame:
    """Da bytes xlsx a DataFrame normalizzato."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as e:
        diag.append({"file": source_name, "scheda": "-", "esito": f"❌ non leggibile: {e}", "righe": 0})
        return pd.DataFrame()

    frames = []
    for sname in wb.sheetnames:
        if not sheet_is_registro(sname):
            diag.append({"file": source_name, "scheda": sname, "esito": "⏭️ scheda esclusa", "righe": 0})
            continue
        ws = wb[sname]
        recs, vuote_allievo = [], 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue  # intestazione
            row = list(row) + [None] * (N_COLS - len(row))
            rec = dict(zip(COLS, row[:N_COLS]))
            data = p_date(rec["Data"])
            allievo = p_str(rec["Allievo"])
            # riga valida solo se ha una data o un orario di inizio
            if data is None and p_time(rec["Ora Inizio"]) is None:
                continue
            if not allievo:
                vuote_allievo += 1
                continue  # niente ripiego sul nome file: evita "allievi fantasma"
            rec["_data"] = data
            rec["_allievo"] = allievo
            rec["_file"] = source_name
            rec["_scheda"] = sname
            recs.append(rec)
        if vuote_allievo:
            diag.append({"file": source_name, "scheda": sname,
                         "esito": f"⚠️ {vuote_allievo} righe senza 'Allievo' scartate",
                         "righe": len(recs)})
        else:
            diag.append({"file": source_name, "scheda": sname, "esito": "✅ letta", "righe": len(recs)})
        if recs:
            frames.append(pd.DataFrame(recs))
    try:
        wb.close()
    except Exception:
        pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Colonne tipizzate e derivate."""
    if df.empty:
        return df
    out = pd.DataFrame()
    out["Allievo"] = df["_allievo"].astype(str).str.strip().str.title()
    out["Materia"] = df["Materia"].map(p_str).replace("", "(non indicata)").str.strip()
    out["Data"] = df["_data"]
    out["OraInizio"] = df["Ora Inizio"].map(p_time)
    out["OraFine"] = df["Ora Fine"].map(p_time)
    out["OreLezione"] = df["Durata Lezione (Ore)"].map(p_hours)
    out["OrePrep"] = df["Ore preparazione"].map(p_hours)
    out["OreTotali"] = df["Totale Ore"].map(p_hours)
    out["NumeroLezione"] = df["Numero Lezione"].map(p_float)
    out["Argomento"] = df["Argomento"].map(p_str)
    out["MaterialeFornito"] = df["Materiale Fornito"].map(p_bool)
    out["CompitoAssegnato"] = df["Compito Assegnato"].map(p_bool)
    out["CompitoSuperato"] = df["Compito Superato"].map(p_bool)
    out["Voto"] = df["Voto"].map(p_float)
    out["Note"] = df["Note"].map(p_str)
    out["Pagato"] = df["Pagamento Ricevuto"].map(p_bool)
    out["Importo"] = df["Importo (€)"].map(p_money)
    out["DataPagamento"] = df["Data Pagamento"].map(p_date)
    out["EstremiPagamento"] = df["Estremi Pagamento"].map(p_str)
    for c, src in [("LinkRiunione", "Link Riunione"), ("LinkRegistrazione", "Link Registrazione"),
                   ("LinkDispense", "Link Dispense"), ("LinkMappe", "Link Mappe Concettuali"),
                   ("LinkCompito", "Link Compito Assegnato"), ("LinkReport", "Link Report Risultati")]:
        out[c] = df[src].map(p_str)
    out["File"] = df["_file"]

    # se Totale Ore manca, ricostruiscilo
    manca = out["OreTotali"] <= 0
    out.loc[manca, "OreTotali"] = out.loc[manca, "OreLezione"] + out.loc[manca, "OrePrep"]
    # se manca la durata lezione, ricavala dagli orari
    def da_orari(r):
        if r["OreLezione"] > 0 or r["OraInizio"] is None or r["OraFine"] is None:
            return r["OreLezione"]
        a = r["OraInizio"].hour + r["OraInizio"].minute / 60
        b = r["OraFine"].hour + r["OraFine"].minute / 60
        d = b - a
        return d if d > 0 else 0.0
    out["OreLezione"] = out.apply(da_orari, axis=1)

    out = out[out["Data"].notna()].copy()
    out["Anno"] = out["Data"].dt.year
    out["MeseNum"] = out["Data"].dt.month
    out["Mese"] = out["MeseNum"].map(lambda m: MESI_IT[m - 1])
    out["AnnoMese"] = out["Data"].dt.to_period("M").astype(str)
    out["GiornoSett"] = out["Data"].dt.weekday.map(lambda i: GIORNI_IT[i])
    out["GiornoIdx"] = out["Data"].dt.weekday
    out["OraStart"] = out["OraInizio"].map(lambda t: t.hour if t else None)
    out["Pagato"] = out["Pagato"].fillna(False)
    out["Incassato"] = np.where(out["Pagato"], out["Importo"], 0.0)
    out["DaIncassare"] = np.where(~out["Pagato"], out["Importo"], 0.0)
    return out.sort_values("Data").reset_index(drop=True)


# ============================================================================
# PROGETTI E CONSULENZE  (file "Gestione Progetti" — scheda "Progetti")
# ============================================================================

PROG_COLS = [
    "Conteggio",        # A  1 = riga che apre un progetto
    "Progetto",         # B
    "Descrizione",      # C
    "Data Inizio",      # D
    "Data Consegna",    # E
    "Stato",            # F
    "Attività",         # G
    "Pagamento",        # H  es. "€245 - Acconto", "- €245 - STORNO"
    "Data Acconto",     # I
    "Data Saldo",       # J
    "Nome Cliente",     # K
    "Cognome Cliente",  # L
    "Link Cartella",    # M
    "Costo Progetto",   # N  quanto paga il cliente
    "Spesa Progetto",   # O  costi vivi sostenuti
    "Ricavo",           # P
    "Ore Lavorate",     # Q
    "Guadagno Orario",  # R
    "Note",             # S
]

STATI_ORDINE = ["Da Iniziare", "In Corso", "In lavorazione", "Completato"]
STATO_COLORE = {
    "Da Iniziare": PALETTE[3],      # giallo
    "In Corso": PALETTE[0],         # blu
    "In lavorazione": PALETTE[6],   # viola
    "Completato": PALETTE[2],       # verde
}


def p_pagamento(v):
    """Da '€245 - Acconto' / '- €245 - STORNO' a (importo firmato, tipo)."""
    s = p_str(v)
    if not s:
        return 0.0, ""
    tipo = "Storno" if "storn" in s.lower() else (
        "Acconto" if "accont" in s.lower() else (
            "Saldo" if "saldo" in s.lower() else "Altro"))
    m = re.search(r"(\d+(?:[.,]\d+)?)", s.replace("€", " "))
    if not m:
        return 0.0, tipo
    val = float(m.group(1).replace(",", "."))
    # segno negativo esplicito o storno
    if tipo == "Storno" or re.match(r"^\s*-", s):
        val = -abs(val)
    return val, tipo


def sheet_is_progetti(name: str) -> bool:
    n = (name or "").strip().lower()
    if any(x in n for x in ("pivot", "analisi", "regole", "appoggio")):
        return False
    return "progett" in n


def read_progetti(content: bytes, source_name: str, diag: list) -> pd.DataFrame:
    """Legge la scheda 'Progetti': una riga con Conteggio=1 apre un progetto,
    le righe successive con 0 sono altri movimenti dello stesso progetto."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as e:
        diag.append({"file": source_name, "scheda": "-", "esito": f"❌ non leggibile: {e}", "righe": 0})
        return pd.DataFrame(), pd.DataFrame()

    # quali schede leggere: per nome, oppure — se nessuna corrisponde — cercando
    # l'intestazione giusta, così funziona anche se la scheda si chiama "Foglio1"
    da_leggere = [sn for sn in wb.sheetnames if sheet_is_progetti(sn)]
    if not da_leggere:
        for sn in wb.sheetnames:
            try:
                prima = next(wb[sn].iter_rows(values_only=True), None)
            except Exception:
                prima = None
            if not prima:
                continue
            celle = [p_str(c).lower() for c in prima[:19]]
            piene = sum(1 for c in celle if c)
            inizio_ok = any("progetto" in c for c in celle[:3])
            colonne_chiave = sum(1 for parola in ("stato", "cliente", "costo",
                                                  "consegna", "pagamento")
                                 if any(parola in c for c in celle))
            if piene >= 8 and inizio_ok and colonne_chiave >= 3:
                da_leggere.append(sn)
                diag.append({"file": source_name, "scheda": sn,
                             "esito": "✅ riconosciuta dall'intestazione", "righe": 0})
    for sn in wb.sheetnames:
        if sn not in da_leggere:
            diag.append({"file": source_name, "scheda": sn,
                         "esito": "⏭️ saltata: il nome non contiene «progetti» e "
                                  "l'intestazione non corrisponde", "righe": 0})

    prog, movimenti = [], []
    for sname in da_leggere:
        ws = wb[sname]
        corrente = None
        n = 0
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            row = list(row) + [None] * (len(PROG_COLS) - len(row))
            rec = dict(zip(PROG_COLS, row[:len(PROG_COLS)]))
            nome = p_str(rec["Progetto"])
            if not nome:
                continue
            flag = p_float(rec["Conteggio"]) or 0
            importo, tipo = p_pagamento(rec["Pagamento"])
            if flag >= 1 or corrente is None:
                corrente = len(prog)
                n += 1
                cliente = (p_str(rec["Nome Cliente"]) + " " + p_str(rec["Cognome Cliente"])).strip()
                prog.append({
                    "id": corrente,
                    "Progetto": nome,
                    "Descrizione": p_str(rec["Descrizione"]),
                    "Cliente": cliente or "(non indicato)",
                    "Inizio": p_date(rec["Data Inizio"]),
                    "Consegna": p_date(rec["Data Consegna"]),
                    "Stato": p_str(rec["Stato"]) or "(non indicato)",
                    "Attività": p_str(rec["Attività"]),
                    "Costo": p_float(rec["Costo Progetto"]) or 0.0,
                    "Spesa": p_float(rec["Spesa Progetto"]) or 0.0,
                    "Ore": p_float(rec["Ore Lavorate"]) or 0.0,
                    "Link": p_str(rec["Link Cartella"]),
                    "Note": p_str(rec["Note"]),
                    "File": source_name,
                })
            movimenti.append({
                "id": corrente,
                "Progetto": nome,
                "Importo": importo,
                "Tipo": tipo,
                "Data": p_date(rec["Data Saldo"]) or p_date(rec["Data Acconto"]),
                "Testo": p_str(rec["Pagamento"]),
            })
        diag.append({"file": source_name, "scheda": sname, "esito": "✅ letta", "righe": n})
    try:
        wb.close()
    except Exception:
        pass
    if not prog:
        return pd.DataFrame(), pd.DataFrame()

    dfp = pd.DataFrame(prog)
    dfm = pd.DataFrame(movimenti)
    inc = dfm.groupby("id")["Importo"].sum().rename("Incassato")
    dfp = dfp.merge(inc, left_on="id", right_index=True, how="left")
    dfp["Incassato"] = dfp["Incassato"].fillna(0.0)
    dfp["Margine"] = dfp["Costo"] - dfp["Spesa"]
    dfp["Residuo"] = (dfp["Costo"] - dfp["Incassato"]).clip(lower=0)
    dfp["GuadagnoOrario"] = np.where(dfp["Ore"] > 0, dfp["Margine"] / dfp["Ore"], np.nan)
    # se nessuna data è valida le colonne restano di tipo generico: forzale
    dfp["Inizio"] = pd.to_datetime(dfp["Inizio"], errors="coerce")
    dfp["Consegna"] = pd.to_datetime(dfp["Consegna"], errors="coerce")
    dfp["Durata"] = (dfp["Consegna"] - dfp["Inizio"]).dt.days
    dfp["Etichetta"] = dfp["Progetto"] + np.where(
        dfp.duplicated("Progetto", keep=False),
        " · " + dfp["Cliente"].str.split().str[0], "")
    return dfp, dfm


def read_contatti(content: bytes, source_name: str) -> pd.DataFrame:
    """Legge 'Piano contatti' e 'Registro esiti' (intestazioni alla riga 4)."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        return pd.DataFrame()
    out = {}
    for sname in wb.sheetnames:
        n = sname.strip().lower()
        if "piano" not in n and "esiti" not in n:
            continue
        ws = wb[sname]
        rows = list(ws.iter_rows(values_only=True))
        # trova la riga di intestazione: la prima con almeno 4 celle piene
        hi = next((i for i, r in enumerate(rows)
                   if sum(1 for v in r if p_str(v)) >= 4), None)
        if hi is None:
            continue
        hdr = [p_str(v) for v in rows[hi]]
        data = [r for r in rows[hi + 1:] if any(p_str(v) for v in r)]
        if not data:
            continue
        d = pd.DataFrame(data, columns=hdr if len(set(hdr)) == len(hdr) else None)
        d = d.loc[:, [c for c in d.columns if p_str(c)]]
        out["piano" if "piano" in n else "esiti"] = d.map(p_str)
    try:
        wb.close()
    except Exception:
        pass
    return out.get("piano", pd.DataFrame()), out.get("esiti", pd.DataFrame())


# ============================================================================
# SORGENTE DATI: GOOGLE DRIVE
# ============================================================================

MIME_GSHEET = "application/vnd.google-apps.spreadsheet"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@st.cache_resource(show_spinner=False)
def drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = dict(secret("gcp_service_account"))
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def drive_list(folder_id: str):
    """Elenca tutti i fogli nella cartella: Google Sheets nativi E file .xlsx."""
    svc = drive_service()
    files, token = [], None
    q = f"'{folder_id}' in parents and trashed = false"
    while True:
        res = svc.files().list(
            q=q, pageToken=token, pageSize=200,
            fields="nextPageToken, files(id,name,mimeType,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            break
    keep = []
    for f in files:
        mt = f["mimeType"]
        if mt == MIME_GSHEET or mt == MIME_XLSX or f["name"].lower().endswith((".xlsx", ".xlsm")):
            keep.append(f)
    return keep


@st.cache_data(ttl=600, show_spinner=False)
def drive_list_qualsiasi(folder_id: str, _cache_key: float):
    """Elenca tutti i file di una cartella, senza filtrare per tipo (serve ai loghi)."""
    svc = drive_service()
    files, token = [], None
    while True:
        res = svc.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            pageToken=token, pageSize=200,
            fields="nextPageToken, files(id,name,mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            break
    return sorted(files, key=lambda f: f["name"].lower())


@st.cache_data(ttl=600, show_spinner=False)
def drive_file_bytes(file_id: str, _cache_key: float) -> bytes:
    """Scarica un singolo file (usato per i loghi)."""
    from googleapiclient.http import MediaIoBaseDownload
    svc = drive_service()
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id,
                                                        supportsAllDrives=True))
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def drive_download(f) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    svc = drive_service()
    if f["mimeType"] == MIME_GSHEET:
        req = svc.files().export_media(fileId=f["id"], mimeType=MIME_XLSX)
    else:
        req = svc.files().get_media(fileId=f["id"], supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


@st.cache_data(ttl=300, show_spinner="Lettura registri da Google Drive…")
def load_from_drive(folder_id: str, _cache_key: float):
    diag = []
    frames = []
    files = drive_list(folder_id)
    for f in files:
        try:
            content = drive_download(f)
            df = read_workbook(content, f["name"], diag)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            diag.append({"file": f["name"], "scheda": "-", "esito": f"❌ errore: {e}", "righe": 0})
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return normalize(raw), pd.DataFrame(diag), len(files)


@st.cache_data(show_spinner="Lettura progetti…")
def load_progetti(payload):
    """payload = tupla di (nome_file, bytes). Restituisce progetti, movimenti,
    piano contatti e diagnostica."""
    diag, lp, lm = [], [], []
    contatti, esiti = pd.DataFrame(), pd.DataFrame()
    base = 0
    for name, content in payload:
        diag.append({"file": name, "scheda": "(il file)", "esito": "📂 esaminato",
                     "righe": 0})
        dp, dm = read_progetti(content, name, diag)
        if not dp.empty:
            dp = dp.copy(); dm = dm.copy()
            dp["id"] += base; dm["id"] += base
            base = int(dp["id"].max()) + 1
            lp.append(dp); lm.append(dm)
        if contatti.empty:
            c, e = read_contatti(content, name)
            if not c.empty:
                contatti, esiti = c, e
    dfp = pd.concat(lp, ignore_index=True) if lp else pd.DataFrame()
    dfm = pd.concat(lm, ignore_index=True) if lm else pd.DataFrame()
    return dfp, dfm, contatti, esiti, pd.DataFrame(diag)


@st.cache_data(ttl=300, show_spinner="Lettura progetti da Google Drive…")
def progetti_payload_drive(folder_id: str, _cache_key: float):
    out = []
    for f in drive_list(folder_id):
        try:
            out.append((f["name"], drive_download(f)))
        except Exception:
            pass
    return tuple(out)


@st.cache_data(show_spinner="Lettura progetti dalla cartella locale…")
def progetti_payload_local(path: str):
    import glob, os
    out = []
    for p in sorted(glob.glob(os.path.join(path, "*.xlsx"))):
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), fh.read()))
    return tuple(out)


@st.cache_data(show_spinner="Lettura cartella locale…")
def load_from_local(path: str):
    """Modalità di prova: legge i .xlsx da una cartella del computer."""
    import glob, os
    diag, frames = [], []
    files = sorted(glob.glob(os.path.join(path, "*.xlsx")) + glob.glob(os.path.join(path, "*.xlsm")))
    for p in files:
        with open(p, "rb") as fh:
            df = read_workbook(fh.read(), os.path.basename(p), diag)
        if not df.empty:
            frames.append(df)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return normalize(raw), pd.DataFrame(diag), len(files)


@st.cache_data(show_spinner="Lettura file caricati…")
def load_from_uploads(payload):
    diag, frames = [], []
    for name, content in payload:
        df = read_workbook(content, name, diag)
        if not df.empty:
            frames.append(df)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return normalize(raw), pd.DataFrame(diag), len(payload)


# ============================================================================
# SIDEBAR - SORGENTE E FILTRI
# ============================================================================

st.sidebar.markdown(f"### 🌿 {APP_MARCHIO} {APP_NOME}")

def _mtime(nome_file: str) -> float:
    """Data di modifica di un file accanto al codice. Entra nella chiave della
    cache, così quando il file cambia la cache si invalida da sola."""
    try:
        return os.path.getmtime(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), nome_file))
    except Exception:
        return 0.0


SECRETS_ERRORE = ""   # errore di lettura/sintassi dei Secrets, se c'è


def secret(key, default=None):
    """Accesso ai secrets a prova di file mancante o malformato."""
    global SECRETS_ERRORE
    try:
        return st.secrets[key]
    except KeyError:
        return default          # i Secrets ci sono, manca questa chiave
    except Exception as e:      # file assente oppure TOML non valido
        SECRETS_ERRORE = str(e)
        return default


def chiavi_secrets():
    """Elenco delle chiavi di primo livello presenti nei Secrets (per diagnosi)."""
    try:
        return list(st.secrets.keys())
    except Exception:
        return []


has_secrets = secret("gcp_service_account") is not None
default_folder = secret("drive_folder_id", "") or ""

import os
LOCAL_DIR = os.environ.get("REGISTRI_LOCAL_DIR", "")
opzioni = ["Google Drive (automatico)", "Carica file manualmente"]
if LOCAL_DIR:
    opzioni.append("Cartella locale")

modo = st.sidebar.radio(
    "Sorgente dati",
    opzioni,
    index=(len(opzioni) - 1) if LOCAL_DIR else (0 if has_secrets else 1),
    label_visibility="collapsed",
)

if "cache_key" not in st.session_state:
    st.session_state.cache_key = 0.0

df = pd.DataFrame()
diag = pd.DataFrame()
n_file = 0

if modo.startswith("Google"):
    folder_id = st.sidebar.text_input("ID cartella Drive", value=default_folder,
                                      help="La parte dopo /folders/ nell'URL della cartella")
    if st.sidebar.button("🔄 Aggiorna tutto da Drive", width='stretch',
                         type="primary",
                         help="Rilegge i registri, la cartella dei progetti e "
                              "ricerca i file del diario e della Taratura. "
                              "Usalo quando hai appena modificato o caricato "
                              "qualcosa su Drive e non lo vedi ancora qui."):
        # Un solo pulsante per tutto. Oltre a svuotare la cache dei dati va
        # mosso anche `cerca_archivio`: la ricerca di Quadro_Diario.xlsx e
        # Quadro_Taratura.xlsx è tenuta da parte per un paio di minuti, e
        # senza questo scatto resterebbe ferma sul risultato vecchio anche
        # dopo aver svuotato il resto.
        st.session_state.cache_key = DIARIO.adesso().timestamp()
        st.session_state["cerca_archivio"] = \
            st.session_state.get("cerca_archivio", 0) + 1
        st.cache_data.clear()
        st.session_state["ultima_conferma"] = (
            "Riletti registri, progetti, diario e Taratura", DIARIO.adesso())
        st.rerun()
    if not has_secrets:
        trovate = chiavi_secrets()
        if SECRETS_ERRORE:
            st.error("⚠️ I Secrets non sono leggibili: probabilmente c'è un errore "
                     "di sintassi TOML (spesso la `private_key` andata a capo, "
                     "oppure il JSON incollato con le graffe invece del formato TOML).")
            st.code(SECRETS_ERRORE, language="text")
        elif not trovate:
            st.warning("⚠️ I Secrets di questa app sono **vuoti**. Se hai ricreato "
                       "l'app, i Secrets non vengono trasferiti: vanno reinseriti "
                       "in Settings → Secrets.")
        else:
            st.warning("⚠️ Nei Secrets manca il blocco `[gcp_service_account]`. "
                       "Le voci trovate sono elencate qui sotto.")
            st.code("chiavi presenti: " + ", ".join(map(str, trovate)), language="text")
        st.caption("In alternativa puoi usare **Carica file manualmente** "
                   "dalla barra laterale.")
        st.stop()
    if not folder_id:
        st.info("Inserisci l'ID della cartella Drive nella barra laterale.")
        st.stop()
    try:
        df, diag, n_file = load_from_drive(folder_id.strip(), st.session_state.cache_key)
    except Exception as e:
        st.error(f"Errore di accesso a Google Drive: {e}")
        st.caption("Verifica che la cartella sia condivisa con l'email del service account "
                   "(permesso *Visualizzatore*) e che l'API Google Drive sia attiva.")
        st.stop()
elif modo == "Cartella locale":
    df, diag, n_file = load_from_local(LOCAL_DIR)
else:
    up = st.sidebar.file_uploader("Carica i registri (.xlsx)", type=["xlsx", "xlsm"],
                                  accept_multiple_files=True)
    if not up:
        st.info("Carica uno o più file di registro dalla barra laterale per iniziare.")
        st.stop()
    df, diag, n_file = load_from_uploads(tuple((f.name, f.getvalue()) for f in up))

if df.empty:
    st.error("Nessuna riga valida trovata nei registri.")
    with st.expander("Diagnostica lettura"):
        st.dataframe(diag, width='stretch')
    st.stop()

# --- deduplica -------------------------------------------------------------
st.sidebar.divider()
dedup = st.sidebar.toggle("Rimuovi lezioni duplicate", value=True,
                          help="Stesso allievo, stessa data e stessa ora presenti in più file")
n_prima = len(df)
if dedup:
    df = df.drop_duplicates(subset=["Allievo", "Data", "OraInizio", "Materia"], keep="first")
n_dup = n_prima - len(df)

# --- filtri ----------------------------------------------------------------
st.sidebar.markdown("#### Filtri")
dmin, dmax = df["Data"].min().date(), df["Data"].max().date()
periodo = st.sidebar.date_input("Periodo", value=(dmin, dmax), min_value=dmin, max_value=dmax)
if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
    df = df[(df["Data"].dt.date >= periodo[0]) & (df["Data"].dt.date <= periodo[1])]

allievi = sorted(df["Allievo"].unique())
sel_a = st.sidebar.multiselect("Allievi", allievi, default=[],
                               placeholder="Tutti gli allievi")
materie = sorted(df["Materia"].unique())
sel_m = st.sidebar.multiselect("Materie", materie, default=[],
                               placeholder="Tutte le materie")
stato_pag = st.sidebar.selectbox("Stato pagamento", ["Tutti", "Solo pagate", "Solo da incassare"])

if sel_a:
    df = df[df["Allievo"].isin(sel_a)]
if sel_m:
    df = df[df["Materia"].isin(sel_m)]
if stato_pag == "Solo pagate":
    df = df[df["Pagato"]]
elif stato_pag == "Solo da incassare":
    df = df[~df["Pagato"]]

if df.empty:
    st.warning("Nessuna lezione corrisponde ai filtri selezionati.")
    st.stop()

# colore stabile per allievo (non dipende dai filtri)
cmap = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(allievi)}

st.sidebar.divider()
st.sidebar.caption(f"📂 {n_file} file letti · {len(df)} lezioni"
                   + (f" · {n_dup} duplicati rimossi" if n_dup else ""))

with st.sidebar.expander("🔍 Diagnostica lettura"):
    st.dataframe(diag, width='stretch', hide_index=True)


# ============================================================================
# INTESTAZIONE + KPI
# ============================================================================

# ---- intestazione del marchio -------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _logo_base64(_versione: float = 0.0):
    """Il logo per l'intestazione. Lo cerca prima nella cartella loghi/ della repo,
    poi nella cartella Drive dei loghi: così funziona anche se tieni le immagini
    solo su Drive."""
    import base64

    def _codifica(dati: bytes, nome: str) -> str:
        if nome.lower().endswith(".png"):
            tipo = "png"
        elif nome.lower().endswith(".svg"):
            tipo = "svg+xml"
        else:
            tipo = "jpeg"
        return f"data:image/{tipo};base64," + base64.b64encode(dati).decode()

    # 1) nella repo
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loghi", APP_LOGO)
        with open(p, "rb") as f:
            return _codifica(f.read(), APP_LOGO)
    except Exception:
        pass

    # 2) nella cartella Drive dei loghi
    try:
        id_loghi = (secret("drive_folder_id_loghi", "") or "").strip()
        if id_loghi:
            for f in drive_list_qualsiasi(id_loghi, 0.0):
                if f["name"].strip().lower() == APP_LOGO.lower():
                    return _codifica(drive_file_bytes(f["id"], 0.0), f["name"])
    except Exception:
        pass
    return ""


def _data_italiana(d=None):
    """La data per esteso in italiano: il server non ha la lingua installata."""
    d = d or DIARIO.oggi()
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato",
              "domenica"]
    testo = f"{giorni[d.weekday()]} {d.day} {MESI_IT[d.month - 1].lower()} {d.year}"
    return testo[0].upper() + testo[1:]


def _saluto():
    ora = DIARIO.adesso().hour
    if ora < 6:
        return "Ancora in piedi"
    if ora < 13:
        return "Buongiorno"
    if ora < 18:
        return "Buon pomeriggio"
    return "Buonasera"


_logo = _logo_base64(st.session_state.get("cache_key", 0.0))
_blocco_logo = (f'<img src="{_logo}" class="qd-logo" alt="{APP_MARCHIO}"/>'
                if _logo else '<div class="qd-logo qd-logo-vuoto">EN</div>')

st.markdown(f"""
<div class="qd-header">
  <svg class="qd-piste" viewBox="0 0 1200 160" preserveAspectRatio="none"
       aria-hidden="true">
    <defs>
      <g id="qd-tracciati" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path d="M0 118 H160 L190 88 H330 L356 62 H520"/>
        <path d="M0 52 H96 L124 80 H268 L296 108 H470"/>
        <path d="M1200 44 H1040 L1012 72 H880 L854 100 H700"/>
        <path d="M1200 126 H1080 L1052 98 H930"/>
        <path d="M560 160 V124 L590 96 H660"/>
      </g>
    </defs>
    <use href="#qd-tracciati" class="qd-base" stroke="{VERDE}" stroke-width="1.5"/>
    <use href="#qd-tracciati" class="qd-impulso" stroke="{VERDE_SCURO}" stroke-width="2.6"/>
    <g fill="{VERDE}" class="qd-nodi">
      <circle cx="190" cy="88" r="4"/><circle cx="356" cy="62" r="4"/>
      <circle cx="124" cy="80" r="4"/><circle cx="296" cy="108" r="4"/>
      <circle cx="1012" cy="72" r="4"/><circle cx="854" cy="100" r="4"/>
      <circle cx="1052" cy="98" r="4"/><circle cx="590" cy="96" r="4"/>
    </g>
  </svg>

  <div class="qd-marchio">
    {_blocco_logo}
    <div class="qd-testo">
      <h1 class="qd-nome"><span>{APP_MARCHIO}</span> {APP_NOME}</h1>
      <div class="qd-payoff">{APP_PAYOFF}</div>
    </div>
  </div>

  <div class="qd-stato">
    <div class="qd-saluto">{_saluto()}, Claudio</div>
    <div class="qd-data">{_data_italiana()}</div>
  </div>
</div>
""", unsafe_allow_html=True)

st.caption(f"Registri dal {df['Data'].min():%d/%m/%Y} al {df['Data'].max():%d/%m/%Y} · "
           f"aggiornamento automatico dai fogli su Google Drive")

# --- controllo qualità dei dati -------------------------------------------
anno_ora = DIARIO.oggi().year
anomalie = df[(df["Anno"] > anno_ora + 1) | (df["Anno"] < 2015)]
if not anomalie.empty:
    with st.expander(f"⚠️ {len(anomalie)} lezioni con una data probabilmente errata "
                     f"(anno fuori intervallo) — controlla i registri", expanded=False):
        t = anomalie[["Data", "Allievo", "Materia", "Argomento", "File"]].copy()
        t["Data"] = t["Data"].dt.strftime("%d/%m/%Y")
        st.dataframe(t, width='stretch', hide_index=True)

tot_lez = len(df)
tot_ore = df["OreTotali"].sum()
ore_lez = df["OreLezione"].sum()
ore_prep = df["OrePrep"].sum()
n_all = df["Allievo"].nunique()
incassato = df["Incassato"].sum()
da_incassare = df["DaIncassare"].sum()
tariffa = incassato / ore_lez if ore_lez else 0

# I numeri di tutto, piccoli e richiudibili. Prima erano sei riquadroni che
# occupavano mezzo schermo e mostravano solo le lezioni; ora sono tessere
# piccole, divise per area, dentro un pannello che si apre quando serve — e
# il filtro del periodo vale per tutte.
st.session_state.setdefault("riep_aperto", False)


def tessere(voci):
    """Una fila di numeretti. voci = [(etichetta, valore, nota|None), ...]"""
    pezzi = []
    for etichetta_t, valore_t, nota_t in voci:
        extra = (f"<div class='qd-t-nota'>{nota_t}</div>" if nota_t else "")
        pezzi.append(
            f"<div class='qd-t'><div class='qd-t-eti'>{etichetta_t}</div>"
            f"<div class='qd-t-val'>{valore_t}</div>{extra}</div>")
    st.markdown("<div class='qd-tessere'>" + "".join(pezzi) + "</div>",
                unsafe_allow_html=True)


def pannello_riepilogo(chiave):
    """
    Il riepilogo completo, uguale in ogni sezione.

    `chiave` serve solo a dare un nome diverso ai filtri in ogni tab, perché
    due widget con lo stesso nome nella stessa pagina non possono esistere.
    """
    with st.expander("📌 I numeri — lezioni, progetti, studio", expanded=False):
        prima = df["Data"].min().date() if not df.empty else DIARIO.oggi()
        f1, f2 = st.columns([2, 3])
        quando = f1.selectbox("Periodo", ["Sempre", "Ultimi 12 mesi",
                                          "Ultimi 3 mesi", "Quest'anno"],
                              key=f"riep_per_{chiave}")
        oggi_r = pd.Timestamp(DIARIO.oggi())
        if quando == "Ultimi 12 mesi":
            dal_r = oggi_r - pd.Timedelta(days=365)
        elif quando == "Ultimi 3 mesi":
            dal_r = oggi_r - pd.Timedelta(days=91)
        elif quando == "Quest'anno":
            dal_r = pd.Timestamp(dt.date(oggi_r.year, 1, 1))
        else:
            dal_r = pd.Timestamp(prima)

        d = df[df["Data"] >= dal_r] if not df.empty else df
        allievi_r = sorted(d["Allievo"].unique()) if not d.empty else []
        scelti_r = f2.multiselect("Allievi", allievi_r, default=[],
                                  placeholder="Tutti gli allievi",
                                  key=f"riep_all_{chiave}")
        if scelti_r:
            d = d[d["Allievo"].isin(scelti_r)]

        ore_l = d["OreLezione"].sum() if not d.empty else 0
        inc_r = d["Incassato"].sum() if not d.empty else 0
        st.markdown("**Ripetizioni**")
        tessere([
            ("Lezioni", f"{len(d):,}".replace(",", "."), None),
            ("Ore totali", f"{d['OreTotali'].sum():,.1f}".replace(",", "."), None),
            ("Allievi", f"{d['Allievo'].nunique() if not d.empty else 0}", None),
            ("Incassato", f"€ {inc_r:,.0f}".replace(",", "."), None),
            ("Da incassare", f"€ {d['DaIncassare'].sum():,.0f}".replace(",", "."),
             "in sospeso" if (not d.empty and d["DaIncassare"].sum() > 0) else None),
            ("€ l'ora", f"€ {(inc_r / ore_l if ore_l else 0):,.1f}".replace(",", "."), None),
        ])

        if "dfp" in globals() and not dfp.empty:
            p_r = dfp[dfp["Inizio"] >= dal_r] if quando != "Sempre" else dfp
            aperti = len(p_r[~p_r["Stato"].str.lower().str.contains("complet")])
            st.markdown("**Progetti**")
            tessere([
                ("Progetti", f"{len(p_r)}", None),
                ("Ancora aperti", f"{aperti}", None),
                ("Valore", f"€ {p_r['Costo'].sum():,.0f}".replace(",", "."), None),
                ("Incassato", f"€ {p_r['Incassato'].sum():,.0f}".replace(",", "."), None),
                ("Residuo", f"€ {p_r['Residuo'].sum():,.0f}".replace(",", "."), None),
            ])

        if "DIA" in globals() and not DIA.empty:
            ses_r = DIA[DIA["Tipo"].isin(DIARIO.TIPI_TEMPO)]
            ses_r = ses_r[ses_r["Data"] >= dal_r]
            pc_r = DIA[DIA["Tipo"] == "parlachiaro"]
            tappe_r = int((DIA["Tipo"] == "tappa").sum())
            st.markdown("**Studio e allenamento**")
            tessere([
                ("Giorni di fila", f"{DIARIO.striscia(DIA)}", None),
                ("Ore nel periodo", f"{ses_r['Minuti'].sum() / 60:,.1f}".replace(",", "."), None),
                ("Sessioni", f"{len(ses_r)}", None),
                ("Tappe fatte", f"{tappe_r}", None),
                ("Parla chiaro", f"{pc_r['Valore'].mean():.0f}/100"
                 if not pc_r.empty else "—", "media efficacia"),
                ("Corsi seguiti", f"{len(DIARIO.corsi(DIA))}", None),
            ])

        st.caption("Il filtro vale solo per questo pannello: i grafici delle "
                   "sezioni hanno i loro.")


st.divider()

# ============================================================================
# CARICAMENTO PROGETTI E CONSULENZE (seconda cartella Drive, facoltativa)
# ============================================================================

PROG_LOCAL = os.environ.get("PROGETTI_LOCAL_DIR", "")
prog_payload = ()
prog_msg = ""

if PROG_LOCAL:
    prog_payload = progetti_payload_local(PROG_LOCAL)
elif modo.startswith("Google"):
    st.sidebar.divider()
    st.sidebar.markdown("#### Progetti e consulenze")
    pid = st.sidebar.text_input("ID cartella Drive progetti",
                                value=secret("drive_folder_id_progetti", "") or "",
                                help="Cartella che contiene 'Gestione Progetti'")
    if pid.strip():
        try:
            prog_payload = progetti_payload_drive(pid.strip(), st.session_state.cache_key)
        except Exception as e:
            prog_msg = f"Non riesco a leggere la cartella progetti: {e}"
    else:
        prog_msg = ("Inserisci l'ID della cartella Drive che contiene il file "
                    "**Gestione Progetti** nella barra laterale, oppure aggiungi "
                    "`drive_folder_id_progetti` nei Secrets.")
else:
    st.sidebar.divider()
    upp = st.sidebar.file_uploader("File progetti (.xlsx)", type=["xlsx"],
                                   accept_multiple_files=True, key="up_prog")
    if upp:
        prog_payload = tuple((f.name, f.getvalue()) for f in upp)
    else:
        prog_msg = "Carica il file **Gestione Progetti** dalla barra laterale."

if prog_payload:
    dfp, dfm, contatti, esiti, diag_p = load_progetti(prog_payload)
else:
    dfp, dfm, contatti, esiti, diag_p = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                         pd.DataFrame(), pd.DataFrame())

# La `key` serve a poter cambiare scheda dal codice: scrivendo in
# st.session_state["tab_aperto"] il nome di una scheda e ricaricando, Quadro
# si sposta lì. È quello che fa «Comincia» nella sessione di oggi.
ETICHETTE_TAB = ["🧭 Scrivania", "👩‍💼 Segreteria", "🎓 Ripetizioni", "🗂️ Progetti",
                 "🛠️ Laboratorio", "💼 Lavoro", "🖋️ Cancelleria", "📚 Studio",
                 "🎙️ Parla chiaro", "📡 SENTINEL", "🛰️ Radar", "🌿 Equilibrio",
                 "⚙️ Taratura", "❓ Guida"]

# Aprire Quadro direttamente su una scheda con un link, per esempio
# https://…streamlit.app/?pagina=segretaria — è quello che si mette come
# icona sulla schermata Home del telefono. Vale solo alla prima apertura.
PAGINE_DIRETTE = {"segretaria": "👩‍💼 Segreteria", "segreteria": "👩‍💼 Segreteria",
                  "equilibrio": "🌿 Equilibrio",
                  "laboratorio": "🛠️ Laboratorio", "lavoro": "💼 Lavoro",
                  "radar": "🛰️ Radar", "studio": "📚 Studio", "scrivania": "🧭 Scrivania"}
# alcune pagine stanno dentro una scheda: (scheda, [(chiave delle sotto-schede, sotto-scheda), …])
SOTTOPAGINE = {"leggimelo": ("📚 Studio", [("studio_sezione", "📖 Leggimelo")]),
               "memoria": ("📚 Studio", [("studio_sezione", "🧠 Memoria")]),
               "aforismi": ("👩‍💼 Segreteria", [("sgr_area", "🤖 Segretaria virtuale"),
                                               ("sg_sezione", "✨ Aforismi")]),
               "assistant": ("👩‍💼 Segreteria", [("sgr_area", "🤝 Claudio Assistant")])}
_pagina = str(st.query_params.get("pagina", "")).lower()
if not st.session_state.get("_pagina_aperta"):
    if _pagina in PAGINE_DIRETTE:
        st.session_state["tab_aperto"] = PAGINE_DIRETTE[_pagina]
        st.session_state["_pagina_aperta"] = True
    elif _pagina in SOTTOPAGINE:
        _s, _livelli = SOTTOPAGINE[_pagina]
        st.session_state["tab_aperto"] = _s
        for _chiave, _sotto in _livelli:
            st.session_state[_chiave] = _sotto
        st.session_state["_pagina_aperta"] = True

# Il posto della segretaria nell'angolo: sta fuori dalle schede, così si vede
# su tutte. È «fisso» sullo schermo (CSS in segretaria.py), quindi non occupa
# spazio qui. Si riempie più giù, quando i dati della Scrivania sono pronti.
POSTO_SEGRETARIA = st.container(key="sg_angolo")
TAB = st.tabs(ETICHETTE_TAB, key="tab_aperto", default=ETICHETTE_TAB[0])

# Se un pulsante (della guida, o della segretaria) ha chiesto di aprire una
# scheda, qui la si apre. Sta nel contenitore della segretaria, fuori dal flusso.
# Il contenitore c'è sempre (anche vuoto), così la segretaria dopo di lui resta
# sempre allo stesso posto e il suo avatar non si ricarica.
with POSTO_SEGRETARIA:
    import guida as GUIDA
    with st.container(key="gd_naviga"):
        GUIDA.naviga_se_serve()


# ============================================================================
# TAB 0 - SCRIVANIA  (collegamenti rapidi e stato di salute)
# ============================================================================
with TAB[0]:
    pannello_riepilogo('scrivania')
    oggi_ts = pd.Timestamp(DIARIO.oggi())

    # ========================================================================
    # SALA DI COMANDO — la sessione di oggi, l'allenamento, l'andamento
    # ========================================================================
    import assistente as AI

    @st.cache_data(show_spinner=False)
    def _carica_json(nome, _versione: float):
        import json as _json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   nome), encoding="utf-8") as f:
                return _json.load(f)
        except Exception as e:
            return {"_errore": str(e)}

    CFG = _carica_json("scrivania.json", _mtime("scrivania.json"))
    SCI = _carica_json("scienza.json", _mtime("scienza.json"))

    SA = secret("gcp_service_account", None)
    FOGLIO = (secret("diario_sheet_id", "") or "").strip()

    # ------------------------------------------------------------ il diario --
    # Dove finiscono i dati, in ordine di preferenza: il file Excel su Drive,
    # un foglio di Google, la sola memoria. Il primo che si trova vince.
    @st.cache_data(ttl=120, show_spinner=False)
    def _cerca_file_diario(_segno):
        if not SA:
            return None
        cartelle = [secret("drive_folder_id_diario", ""),
                    secret("drive_folder_id_progetti", ""),
                    secret("drive_folder_id", "")]
        try:
            return DIARIO.trova_file(dict(SA), cartelle)
        except Exception:
            return None

    FILE_DIARIO = (_cerca_file_diario(st.session_state.get("cerca_archivio", 0))
                   if not FOGLIO else None)

    if FILE_DIARIO:
        DOVE, COME = FILE_DIARIO, "file"
    elif FOGLIO and SA:
        DOVE, COME = FOGLIO, "foglio"
    else:
        DOVE, COME = None, "memoria"

    @st.cache_data(ttl=60, show_spinner=False)
    def _leggi_diario(_dove, _come, _segno):
        if _come == "file":
            return DIARIO.leggi_xlsx(dict(SA), _dove)
        return DIARIO.leggi_foglio(dict(SA), _dove)

    def diario_corrente():
        if COME == "memoria":
            return st.session_state.get("diario_locale", DIARIO.vuoto()), None
        try:
            return _leggi_diario(DOVE, COME,
                                 st.session_state.get("diario_segno", 0)), None
        except Exception as e:
            return st.session_state.get("diario_locale", DIARIO.vuoto()), str(e)

    def diario_scrivi(righe):
        """Salva dove si può, e dice dove ha salvato."""
        if isinstance(righe, dict):
            righe = [righe]
        try:
            if COME == "file":
                DIARIO.aggiungi_xlsx(dict(SA), DOVE, righe)
            elif COME == "foglio":
                DIARIO.aggiungi_foglio(dict(SA), DOVE, righe)
            else:
                raise RuntimeError("nessun archivio collegato")
            st.session_state["diario_segno"] = st.session_state.get("diario_segno", 0) + 1
            return COME
        except Exception as e:
            if COME != "memoria":
                st.warning(f"Non sono riuscito a scrivere sull'archivio: {e}")
                st.caption("Salvo in memoria per non perdere quello che hai "
                           "scritto, ma controlla i permessi dell'archivio.")
            locale = st.session_state.get("diario_locale", DIARIO.vuoto())
            nuovo = pd.concat([locale, pd.DataFrame(righe)], ignore_index=True)
            st.session_state["diario_locale"] = DIARIO._sistema(nuovo)
            return "memoria"

    DIA, errore_diario = diario_corrente()
    if errore_diario:
        st.warning(f"Non riesco a leggere l'archivio del diario: {errore_diario}")
        st.caption("Controlla che sia condiviso **come Editor** con l'indirizzo "
                   "del service account. Intanto salvo in memoria.")

    mostra_conferma()

    # ---- il contesto per equilibrio.py e produttivita.py --------------------
    # Tutto quello che quei due file devono sapere di Quadro sta qui dentro,
    # in CTX: così non dipendono dal resto di app.py e si provano da soli.
    # I dati personali (pratiche, respiri, check-in) vanno nello stesso
    # archivio privato della Taratura, Quadro_Taratura.xlsx, e si aprono con
    # la stessa password.
    import types
    import taratura as TAR
    import equilibrio as EQ
    import produttivita as PROD

    @st.cache_data(ttl=120, show_spinner=False)
    def _eq_cerca_privato(_segno):
        if not SA:
            return None
        try:
            return DIARIO.trova_file(
                dict(SA), [secret("drive_folder_id_taratura", ""),
                           secret("drive_folder_id_diario", ""),
                           secret("drive_folder_id_progetti", ""),
                           secret("drive_folder_id", "")],
                "Quadro_Taratura.xlsx")
        except Exception:
            return None

    @st.cache_data(ttl=30, show_spinner=False)
    def _eq_leggi_privato(_f, _segno):
        return DIARIO.leggi_xlsx(dict(SA), _f)

    def privato_leggi():
        f = _eq_cerca_privato(st.session_state.get("cerca_archivio", 0))
        if not f:
            return st.session_state.get("tar_locale", DIARIO.vuoto())
        try:
            # stesso «tar_segno» della Taratura: quando scrive una, si
            # rilegge anche l'altra
            return _eq_leggi_privato(f, st.session_state.get("tar_segno", 0))
        except Exception:
            return st.session_state.get("tar_locale", DIARIO.vuoto())

    def privato_scrivi(r):
        f = _eq_cerca_privato(st.session_state.get("cerca_archivio", 0))
        if f:
            try:
                DIARIO.aggiungi_xlsx(dict(SA), f, [r])
                st.session_state["tar_segno"] = st.session_state.get("tar_segno", 0) + 1
                return True
            except Exception as e:
                st.warning(f"Non sono riuscito a scrivere nell'archivio privato: {e}")
        loc = st.session_state.get("tar_locale", DIARIO.vuoto())
        st.session_state["tar_locale"] = DIARIO._sistema(
            pd.concat([loc, pd.DataFrame([r])], ignore_index=True))
        return False

    def eq_aperto():
        """Aperto se la password è stata data da poco, qui o nella Taratura."""
        quando = st.session_state.get("tar_aperta_alle")
        return bool(quando) and not TAR.scaduta(quando)

    def eq_sblocca(pw):
        if TAR.password_giusta(pw, secret("taratura_password", "")):
            st.session_state["tar_aperta_alle"] = DIARIO.adesso()
            return True
        return False

    CTX = types.SimpleNamespace(
        DIA=DIA, DIARIO=DIARIO, AI=AI, VOCE=VOCE,
        cfg=_carica_json("equilibrio.json", _mtime("equilibrio.json")),
        chiave_ai=chiave_ai(), modello_ai=modello_ai(),
        pagina_html=pagina_html, ascolta=pulsante_ascolta,
        diario_scrivi=diario_scrivi, conferma=conferma,
        privato_leggi=privato_leggi, privato_scrivi=privato_scrivi,
        aperto=eq_aperto, sblocca=eq_sblocca, impostazione=EQ.impostazione,
        SA=SA, cartelle=[secret("drive_folder_id_diario", ""), secret("drive_folder_id_progetti", ""),
                         secret("drive_folder_id", ""), secret("drive_folder_id_taratura", "")],
        pratiche=getattr(TAR, "PRATICHE",
                         ["Respirazione", "Meditazione", "Yoga", "Camminata", "Altro"]))

    # la segretaria nell'angolo: si disegna nel contenitore preparato prima
    # delle schede, così resta lì qualunque scheda apri
    try:
        import segretaria as SEG
        with POSTO_SEGRETARIA:
            SEG.angolo(CTX)
    except Exception as _e_seg:
        st.caption(f"La segretaria nell'angolo non è partita: {_e_seg}")

    # l'aforisma del momento, se nelle preferenze hai chiesto di vederlo qui.
    # Questo pezzo si rilegge ogni minuto e cambia quando scatta l'intervallo.
    if EQ.impostazione(DIA, "aforismi", EQ.PREDEFINITE_AFORISMI).get("in_scrivania"):
        @st.fragment(run_every=60)
        def _aforisma_scrivania():
            # un problema dell'aforisma (l'audio, l'AI) non deve fermare il resto di Quadro
            try:
                EQ.riquadro_aforisma(CTX, chiave="scr")
            except Exception as _e_af:
                st.caption(f"L'aforisma ha avuto un problema: {_e_af}")
                st.session_state.pop("scr_audio", None)
        _aforisma_scrivania()

    # il rito della memoria: una riga solo se oggi c'è qualcosa da fare
    try:
        import memoria as MEMORIA
        MEMORIA.promemoria_scrivania(CTX, GUIDA.vai)
    except Exception:
        pass

    # --------------------------------------------------------- i tre numeri --
    minuti_7 = DIARIO.andamento(DIA, 7).sum()
    minuti_28 = DIARIO.andamento(DIA, 28).sum()
    n_ses = int(DIA["Tipo"].isin(DIARIO.TIPI_TEMPO).sum())
    k = st.columns(4)
    k[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
    k[0].metric("Giorni di fila", f"{DIARIO.striscia(DIA)}")
    k[1].metric("Minuti ultimi 7 giorni", f"{minuti_7:,.0f}".replace(",", "."))
    k[2].metric("Media al giorno (28 gg)", f"{minuti_28 / 28:.0f} min")
    k[3].metric("Sessioni registrate", f"{n_ses}")

    if COME == "memoria":
        st.warning("**Il diario non è collegato a nessun archivio**: quello che "
                   "registri adesso si perde quando chiudi la pagina.")
        with st.expander("Come si collega — due minuti, si fa una volta sola"):
            st.markdown(
                "Scarica qui sotto il file già pronto, caricalo in una delle "
                "cartelle di Drive che Quadro già conosce (quella dei progetti "
                "va benissimo) e condividi quella cartella con l'indirizzo del "
                "service account **come Editor** — non come Visualizzatore, "
                "perché qui deve scrivere. Poi ricarica questa pagina.\n\n"
                "Non serve nessun Secret nuovo: Quadro cerca il file per nome, "
                "quindi **non rinominarlo**.\n\n"
                "Perché non si può salvare direttamente sul server: Streamlit "
                "Cloud ricostruisce la macchina a ogni riavvio e cancella tutto "
                "quello che l'app ha scritto su disco. Non è aggirabile, i dati "
                "devono stare fuori.")
            if st.button("🔄 Ho appena caricato il file: cercalo di nuovo"):
                st.cache_data.clear()
                st.session_state["cerca_archivio"] = st.session_state.get("cerca_archivio", 0) + 1
                st.rerun()
            st.download_button("⬇️ Scarica Quadro_Diario.xlsx",
                               DIARIO.modello_xlsx(), DIARIO.NOME_FILE,
                               "application/vnd.openxmlformats-officedocument."
                               "spreadsheetml.sheet", type="primary")
    else:
        dove_umano = ("il file **Quadro_Diario.xlsx** su Drive" if COME == "file"
                      else "il tuo foglio di Google")
        st.caption(f"Diario collegato a {dove_umano}.")

    st.divider()

    # =================== LE TRE COSE DI OGGI ================================
    # Quelle non fatte tornano domani con un contatore. Non è per farti
    # sentire in colpa: quando una cosa arriva a cinque rinvii di solito vuol
    # dire che è posta male — troppo grande, o non tua — non che sei pigro.
    PRIOR = DIARIO.priorita(DIA)
    aperte_pr = PRIOR[PRIOR["Stato"] != "fatta"] if not PRIOR.empty else PRIOR

    with st.container(border=True):
        t1, t2 = st.columns([3, 1])
        t1.markdown("##### 🎯 Le tre cose di oggi")
        fatte_oggi = (DIA[(DIA["Tipo"] == "priorita")
                          & (DIA["Attivita"] == "fatta")
                          & (DIA["Data"] >= pd.Timestamp(DIARIO.oggi()))]
                      if not DIA.empty else DIA)
        t2.metric("Fatte oggi", len(fatte_oggi))

        if aperte_pr.empty:
            st.caption("Niente in lista. Scrivi le tre che contano: se ne "
                       "scrivi dieci, domani ne avrai dieci rimandate.")
        else:
            for i_pr, r in aperte_pr.iterrows():
                p1, p2, p3 = st.columns([5, 1, 1])
                avviso = ""
                if r["Rinvii"] >= 5:
                    avviso = (f"  \n<small style='color:#C0392B'>rimandata "
                              f"{r['Rinvii']} volte — forse è posta male, non "
                              f"è che sei pigro</small>")
                elif r["Rinvii"] >= 2:
                    avviso = (f"  \n<small style='opacity:.6'>rimandata "
                              f"{r['Rinvii']} volte</small>")
                p1.markdown(f"**{r['Cosa']}**{avviso}", unsafe_allow_html=True)
                if p2.button("✓ Fatta", key=f"pr_ok_{i_pr}", width='stretch'):
                    diario_scrivi(DIARIO.riga("priorita", "fatta", "", 0, None,
                                              r["Cosa"]))
                    conferma(f"Fatta: {r['Cosa'][:40]}")
                    st.rerun()
                if p3.button("↷ Rinvia", key=f"pr_no_{i_pr}", width='stretch'):
                    diario_scrivi(DIARIO.riga("priorita", "rinviata", "", 0,
                                              None, r["Cosa"]))
                    conferma("Rinviata a domani")
                    st.rerun()

        if len(aperte_pr) < 3:
            with st.form("nuova_priorita", clear_on_submit=True):
                q1, q2 = st.columns([4, 1])
                nuova_pr = q1.text_input(
                    "Aggiungi", label_visibility="collapsed",
                    placeholder="una cosa che oggi conta davvero")
                if q2.form_submit_button("➕ Aggiungi", width='stretch') \
                        and nuova_pr.strip():
                    diario_scrivi(DIARIO.riga("priorita", "aperta", "", 0,
                                              None, nuova_pr.strip()))
                    conferma("Aggiunta")
                    st.rerun()
        else:
            st.caption("Tre bastano. Chiudine una per farne entrare un'altra.")

        storiche = DIA[(DIA["Tipo"] == "priorita")
                       & (DIA["Attivita"] == "fatta")] if not DIA.empty else DIA
        if len(storiche) >= 5:
            with st.expander(f"Quelle già chiuse ({len(storiche)})"):
                for _, r in storiche.sort_values(
                        "Data", ascending=False).head(30).iterrows():
                    st.markdown(f"✓ **{r['Data']:%d/%m}** — {r['Nota']}")

    st.divider()

    # =================== LA SESSIONE DI OGGI ================================
    st.markdown("### 🎯 La sessione di oggi")

    attivita = CFG.get("attivita", [])
    etichette = [f"{a.get('icona', '•')} {a['nome']}" for a in attivita]

    if st.session_state.get("ses_avvio") is None:
        c1, c2 = st.columns([3, 2])
        scelta = c1.selectbox("Cosa fai adesso", etichette,
                              index=st.session_state.get("ses_indice", 0))
        durata = c2.radio("Per quanto", CFG.get("durate", [15, 30, 45, 60]),
                          index=1, horizontal=True,
                          format_func=lambda m: f"{m} min")
        a = attivita[etichette.index(scelta)]
        if a.get("nota"):
            st.caption(a["nota"])
        b1, b2 = st.columns([1, 3])
        if b1.button("▶️ Comincia", type="primary", width='stretch'):
            # se l'attività vive dentro Quadro, ci si sposta direttamente
            meta = a.get("vai_a") or {}
            if meta.get("tab") in ETICHETTE_TAB:
                st.session_state["tab_aperto"] = meta["tab"]
                if meta.get("chiave") and meta.get("valore"):
                    st.session_state[meta["chiave"]] = meta["valore"]
            st.session_state["ses_avvio"] = DIARIO.adesso()
            st.session_state["ses_durata"] = durata
            st.session_state["ses_attivita"] = a["nome"]
            st.session_state["ses_strumento"] = a.get("strumento", "")
            st.session_state["ses_url"] = a.get("url", "")
            st.session_state["ses_indice"] = etichette.index(scelta)
            st.rerun()
        if (a.get("url") or "").strip():
            b2.link_button(f"Apri {a.get('strumento', 'lo strumento')} ↗",
                           a["url"], width='stretch')
    else:
        avvio = st.session_state["ses_avvio"]
        durata = st.session_state["ses_durata"]

        # La pausa non ferma l'orologio: tiene il conto dei secondi stati in
        # pausa e li toglie dal tempo trascorso. Così si può mettere in pausa
        # quante volte si vuole senza falsare i minuti registrati.
        in_pausa = st.session_state.get("ses_pausa_da") is not None
        fermi = st.session_state.get("ses_fermi", 0.0)

        pz1, pz2 = st.columns(2)
        if not in_pausa:
            if pz1.button("⏸️ Pausa", width='stretch'):
                st.session_state["ses_pausa_da"] = DIARIO.adesso()
                st.rerun()
        else:
            if pz1.button("▶️ Riprendi", width='stretch', type="primary"):
                st.session_state["ses_fermi"] = fermi + (
                    DIARIO.adesso() - st.session_state["ses_pausa_da"]).total_seconds()
                st.session_state["ses_pausa_da"] = None
                st.rerun()
        pz2.caption(f"In pausa da {int((DIARIO.adesso() - st.session_state['ses_pausa_da']).total_seconds() // 60)} min"
                    if in_pausa else
                    (f"Pausa usata: {int(fermi // 60)} min" if fermi >= 60 else ""))

        # Il contatore delle interruzioni non fa niente: conta e basta. Dopo
        # qualche settimana è il numero che dice quali attività e quali orari
        # ti frammentano davvero — che di solito non sono quelli che pensi.
        n_int = st.session_state.get("ses_interruzioni", 0)
        i1, i2 = st.columns([1, 2])
        if i1.button(f"🔔 Mi sono distratto  ({n_int})", width='stretch',
                     help="Premilo ogni volta che qualcosa ti stacca da "
                          "quello che stai facendo. Non interrompe niente."):
            st.session_state["ses_interruzioni"] = n_int + 1
            st.rerun()
        if n_int:
            minuti_finora = max(1, (DIARIO.adesso() - avvio).total_seconds() / 60)
            i2.caption(f"{n_int} interruzioni · una ogni "
                       f"{minuti_finora / n_int:.0f} minuti")

        suono_on = st.toggle("Suono negli ultimi 10 secondi", value=True,
                             key="ses_suono",
                             help="Un bip al secondo nell'ultimo tratto e un "
                                  "segnale più lungo alla fine. Il volume è "
                                  "quello del dispositivo.")

        @st.fragment(run_every="1s" if not in_pausa else None)
        def _cronometro():
            fermo_ora = st.session_state.get("ses_pausa_da")
            sospesi = st.session_state.get("ses_fermi", 0.0)
            if fermo_ora:
                sospesi += (DIARIO.adesso() - fermo_ora).total_seconds()
            passati = (DIARIO.adesso() - avvio).total_seconds() - sospesi
            restano = max(0, durata * 60 - passati)
            if fermo_ora:
                st.markdown(
                    f"<div style='font-size:46px;font-weight:700;opacity:.45;"
                    f"letter-spacing:2px'>{int(restano // 60):02d}:"
                    f"{int(restano % 60):02d} ⏸</div>", unsafe_allow_html=True)
                st.caption(f"**{st.session_state['ses_attivita']}** · in pausa")
                return
            mm, ss = int(restano // 60), int(restano % 60)
            fatti = int(passati // 60)
            if restano > 0:
                colore = VERDE_SCURO if restano > 10 else "#C0392B"
                st.markdown(
                    f"<div style='font-size:46px;font-weight:700;color:{colore};"
                    f"letter-spacing:2px'>{mm:02d}:{ss:02d}</div>",
                    unsafe_allow_html=True)
                st.progress(min(1.0, passati / (durata * 60)))
            else:
                st.markdown(
                    f"<div style='font-size:46px;font-weight:700;color:{VERDE}'>"
                    f"✓ fatto</div>", unsafe_allow_html=True)
            st.caption(f"**{st.session_state['ses_attivita']}** · cominciata alle "
                       f"{avvio:%H:%M} · {fatti} minuti finora")

            # Il bip lo genera il browser: nessun file audio da caricare, e
            # così funziona anche offline. Suona solo quando il secondo
            # cambia, altrimenti a ogni ridisegno partirebbe di nuovo.
            if suono_on and 0 <= restano <= 10:
                sec = int(restano)
                if st.session_state.get("ses_ultimo_bip") != sec:
                    st.session_state["ses_ultimo_bip"] = sec
                    finale = (sec == 0)
                    nota_hz = 1320 if finale else 880
                    durata_bip = 0.6 if finale else 0.12
                    pagina_html(f"""
<script>
try {{
  const C = new (window.AudioContext || window.webkitAudioContext)();
  const o = C.createOscillator(), g = C.createGain();
  o.type = "sine";
  o.frequency.value = {nota_hz};
  o.connect(g); g.connect(C.destination);
  g.gain.setValueAtTime(0.0001, C.currentTime);
  g.gain.exponentialRampToValueAtTime(0.25, C.currentTime + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, C.currentTime + {durata_bip});
  o.start(); o.stop(C.currentTime + {durata_bip});
}} catch (e) {{ /* se il browser non lascia suonare, pazienza */ }}
</script>""", 0)

        _cronometro()

        if (st.session_state.get("ses_url") or "").strip():
            st.link_button(f"Apri {st.session_state['ses_strumento']} ↗",
                           st.session_state["ses_url"], width='stretch',
                           type="primary")

        with st.form("chiudi_sessione"):
            st.markdown("**Quando hai finito**")
            f1, f2 = st.columns([1, 2])
            _sosp = st.session_state.get("ses_fermi", 0.0)
            if st.session_state.get("ses_pausa_da"):
                _sosp += (DIARIO.adesso()
                          - st.session_state["ses_pausa_da"]).total_seconds()
            minuti_reali = f1.number_input(
                "Minuti davvero fatti", min_value=1, max_value=600,
                value=max(1, int(((DIARIO.adesso() - avvio).total_seconds()
                                  - _sosp) // 60)) or durata,
                help="Le pause sono già state tolte.")
            sens = CFG.get("sensazioni", {})
            voto = f2.select_slider(
                "Com'è andata", options=[1, 2, 3, 4, 5], value=3,
                format_func=lambda v: sens.get(str(v), str(v)))
            nota = st.text_input("Una riga su cosa hai fatto (facoltativa)")
            cc1, cc2 = st.columns(2)
            salva = cc1.form_submit_button("💾 Salva la sessione", type="primary",
                                           width='stretch')
            annulla = cc2.form_submit_button("Annulla", width='stretch')

        if salva:
            righe_ses = [DIARIO.riga(
                "sessione", st.session_state["ses_attivita"],
                st.session_state["ses_strumento"], minuti_reali, voto, nota)]
            if st.session_state.get("ses_interruzioni"):
                righe_ses.append(DIARIO.riga(
                    "interruzioni", st.session_state["ses_attivita"],
                    st.session_state["ses_strumento"], minuti_reali,
                    st.session_state["ses_interruzioni"],
                    f"{st.session_state['ses_interruzioni']} interruzioni in "
                    f"{minuti_reali} minuti"))
            dove = diario_scrivi(righe_ses)
            for chiave_s in ("ses_avvio", "ses_durata", "ses_attivita",
                             "ses_strumento", "ses_url", "ses_pausa_da",
                             "ses_fermi", "ses_ultimo_bip",
                             "ses_interruzioni"):
                st.session_state.pop(chiave_s, None)
            conferma(f"Sessione salvata: {minuti_reali} minuti di "
                     f"{st.session_state.get('ses_attivita', 'lavoro')}"
                     + ("" if dove != "memoria" else " (solo in memoria)"))
            st.rerun()
        if annulla:
            for chiave_s in ("ses_avvio", "ses_durata", "ses_attivita",
                             "ses_strumento", "ses_url", "ses_pausa_da",
                             "ses_fermi", "ses_ultimo_bip",
                             "ses_interruzioni"):
                st.session_state.pop(chiave_s, None)
            st.rerun()

    st.divider()

    # =================== SCIENZA: ESERCIZIO DEL GIORNO ======================
    st.markdown("### 🔬 Allenamento all'intuizione")

    if "_errore" in SCI:
        st.error(f"Non riesco a leggere `scienza.json`: {SCI['_errore']}")
    else:
        rot = SCI.get("rotazione", [])
        oggi_idx = DIARIO.oggi().weekday()
        voce = next((r for r in rot if r.get("giorno") == oggi_idx),
                    rot[0] if rot else None)

        # Qui c'erano st.tabs, ed erano la causa di due difetti che avevi
        # notato: ogni volta che si salva qualcosa la pagina si ricarica, e le
        # linguette di Streamlit al ricaricamento tornano SEMPRE sulla prima.
        # Per questo «tornava a esercizio del giorno» e sembrava che le altre
        # sezioni non funzionassero. Con una scelta che vive in session_state
        # il problema non esiste.
        SEZIONI_SC = ["🎯 Esercizio del giorno", "📓 Taccuino delle anomalie",
                      "🧩 I problemi aperti", "🎲 Le previsioni",
                      "💡 Sfide e idee"]
        scelta_sc = st.radio("Sezione", SEZIONI_SC, horizontal=True,
                             label_visibility="collapsed", key="scienza_sezione")

        # ------------------------------------------- esercizio del giorno ---
        if scelta_sc == SEZIONI_SC[0] and voce:
            g1, g2 = st.columns([3, 2])
            g1.markdown(f"#### {voce['nome']} — {voce['abilita']}")
            altri = [r["nome"] for r in rot]
            forzato = g2.selectbox(
                "Fai un altro esercizio", ["(quello di oggi)"] + altri,
                key="scienza_altro_giorno",
                help="La rotazione segue il giorno della settimana, ma se oggi "
                     "ti va di farne un altro, scegli qui.")
            if forzato != "(quello di oggi)":
                voce = next(r for r in rot if r["nome"] == forzato)
                st.caption(f"Stai facendo l'esercizio di {voce['nome']} "
                           f"invece di quello di oggi.")

            st.markdown(voce["esercizio"])
            if voce.get("esempio"):
                st.caption(voce["esempio"])
            if voce.get("domanda"):
                st.info(f"**La domanda a cui rispondere** — {voce['domanda']}")

            risp = VOCE.campo("La tua risposta", "scienza_risposta",
                              chiave_ai(), modello_ai(), altezza=160,
                              suggerimento="Scrivi, detta o carica la pagina "
                                           "scritta a mano. Non deve venire "
                                           "bene: deve venire scritto.")
            e1, e2 = st.columns(2)
            if e1.button("💾 Salva l'esercizio", type="primary", width='stretch'):
                if risp.strip():
                    diario_scrivi(DIARIO.riga("esercizio", voce["abilita"],
                                              "Scienza", 15, None, risp.strip()))
                    conferma("Esercizio del giorno salvato")
                    VOCE.svuota("scienza_risposta")
                    st.session_state.pop("scienza_chat", None)
                    st.rerun()
                else:
                    st.warning("Scrivi qualcosa prima di salvare.")

            if e2.button("🤖 Fammi le domande giuste", width='stretch'):
                if not risp.strip():
                    st.warning("Scrivi almeno due righe: senza, non ha niente "
                               "su cui farti domande.")
                else:
                    st.session_state["scienza_chat"] = [("io", risp.strip())]
                    st.session_state["scienza_chiedi"] = True

            # --------- la conversazione continua, invece di una botta sola ---
            chat = st.session_state.get("scienza_chat", [])
            if st.session_state.pop("scienza_chiedi", False):
                stato = st.empty()
                try:
                    with st.spinner("Sto pensando…"):
                        scambio = "\n\n".join(
                            ("Lui: " if r == "io" else "Tu: ") + t
                            for r, t in chat)
                        testo_ai = AI.chiedi(
                            "Sei un ricercatore esperto che fa da allenatore. "
                            f"L'esercizio di oggi è: {voce['esercizio']}\n\n"
                            f"La conversazione finora:\n{scambio}\n\n"
                            "Non dargli la soluzione. Fagli al massimo tre "
                            "domande brevi che lo costringano a essere più "
                            "preciso, e indicagli un modo economico per "
                            "verificare quello che pensa. Se ti ha appena "
                            "risposto, tieni conto di cosa ha detto invece di "
                            "ricominciare da capo. Italiano, frasi brevi.",
                            chiave_ai(), modello_ai(),
                            al_tentativo=lambda m: stato.info(m))
                    stato.empty()
                    chat.append(("ai", testo_ai))
                    st.session_state["scienza_chat"] = chat
                except AI.ErroreAI as e:
                    stato.empty()
                    st.error(e.messaggio)
                    if e.dettaglio:
                        st.caption(e.dettaglio)

            if chat:
                st.divider()
                for ruolo, testo_c in chat:
                    with st.chat_message("user" if ruolo == "io" else "assistant"):
                        st.markdown(testo_c)
                segue = st.chat_input("Rispondi o chiedi un chiarimento…",
                                      key="scienza_chat_input")
                if segue:
                    chat.append(("io", segue))
                    st.session_state["scienza_chat"] = chat
                    st.session_state["scienza_chiedi"] = True
                    st.rerun()
                c1, c2 = st.columns(2)
                if c1.button("💾 Salva tutta la conversazione", width='stretch',
                             type="primary"):
                    testo_tot = "\n\n".join(
                        ("IO: " if r == "io" else "AI: ") + t for r, t in chat)
                    diario_scrivi(DIARIO.riga("esercizio", voce["abilita"],
                                              "Scienza", 15, None, testo_tot))
                    conferma("Conversazione salvata nell'esercizio di oggi")
                    st.session_state.pop("scienza_chat", None)
                    VOCE.svuota("scienza_risposta")
                    st.rerun()
                if c2.button("🗑️ Ricomincia", width='stretch'):
                    st.session_state.pop("scienza_chat", None)
                    st.rerun()

            storico_es = DIA[DIA["Tipo"] == "esercizio"]
            if not storico_es.empty:
                with st.expander(f"Gli esercizi già fatti ({len(storico_es)})"):
                    for _, r in storico_es.sort_values(
                            "Data", ascending=False).head(20).iterrows():
                        st.markdown(f"**{r['Data']:%d/%m/%Y} · {r['Attivita']}**")
                        st.caption(r["Nota"][:500])

        # ------------------------------------------- taccuino anomalie ------
        elif scelta_sc == SEZIONI_SC[1]:
            tac = SCI.get("taccuino", {})
            st.markdown(f"**{tac.get('domanda', 'Che cosa ti ha sorpreso oggi?')}**")
            st.caption(tac.get("istruzioni", ""))
            an = VOCE.campo("L'anomalia, le tre ipotesi e il test più economico",
                            "scienza_anomalia", chiave_ai(), modello_ai(),
                            altezza=130)
            if st.button("💾 Salva nel taccuino", type="primary"):
                if an.strip():
                    diario_scrivi(DIARIO.riga("anomalia", "Taccuino", "Scienza",
                                              5, None, an.strip()))
                    conferma("Anomalia annotata nel taccuino")
                    VOCE.svuota("scienza_anomalia")
                    st.rerun()
                else:
                    st.warning("Scrivi qualcosa prima di salvare.")

            anomalie = DIA[DIA["Tipo"] == "anomalia"].sort_values(
                "Data", ascending=False)
            if not anomalie.empty:
                st.markdown(f"##### Le ultime annotazioni ({len(anomalie)} in tutto)")
                cerca_an = st.text_input("Cerca fra le annotazioni",
                                         placeholder="una parola qualsiasi")
                mostra_an = anomalie
                if cerca_an.strip():
                    mostra_an = mostra_an[mostra_an["Nota"].str.contains(
                        cerca_an.strip(), case=False, na=False)]
                for _, r in mostra_an.head(20).iterrows():
                    st.markdown(f"**{r['Data']:%d/%m/%Y}** — {r['Nota']}")
                scarica_tabella(
                    anomalie[["Data", "Nota"]].rename(
                        columns={"Nota": "Anomalia"}),
                    "taccuino_anomalie", "⬇️ Scarica il taccuino")

        # ------------------------------------------- problemi aperti --------
        elif scelta_sc == SEZIONI_SC[2]:
            st.caption("La lista dei problemi che ti stanno a cuore, tecnici o "
                       "no. Feynman ne teneva una dozzina in testa e provava su "
                       "quelli ogni strumento nuovo che imparava.")

            with st.form("nuovo_problema", clear_on_submit=True):
                nuovo_p = st.text_input("Aggiungi un problema aperto")
                if st.form_submit_button("➕ Aggiungi alla lista",
                                         type="primary") and nuovo_p.strip():
                    diario_scrivi(DIARIO.riga("problema", "aperto", "Scienza",
                                              0, None, nuovo_p.strip()))
                    conferma("Problema aggiunto alla lista")
                    st.rerun()

            elenco_p = DIARIO.problemi(DIA)
            if elenco_p.empty:
                st.info("La lista è vuota. Scrivine anche solo tre: si completa "
                        "da sola nelle settimane.")
            else:
                aperti = int((elenco_p["Stato"] != "risolto").sum())
                st.progress(min(1.0, aperti / 12),
                            text=f"{aperti} problemi aperti su 12 "
                                 f"· {len(elenco_p) - aperti} risolti")

                for i, r in elenco_p.iterrows():
                    pallino = {"aperto": "🔴", "in corso": "🟡",
                               "risolto": "🟢"}.get(r["Stato"], "🔴")
                    with st.expander(f"{pallino} {r['Problema']}",
                                     expanded=False):
                        st.caption(f"Annotato il {r['Aperto']:%d/%m/%Y}"
                                   + (f" · aggiornato il {r['Aggiornato']:%d/%m/%Y}"
                                      if r["Aggiornato"] != r["Aperto"] else ""))
                        chiave_p = f"prob_{i}"
                        with st.form(f"form_{chiave_p}"):
                            s1, s2 = st.columns([1, 3])
                            nuovo_stato = s1.selectbox(
                                "Stato", DIARIO.STATI_PROBLEMA,
                                index=DIARIO.STATI_PROBLEMA.index(r["Stato"])
                                if r["Stato"] in DIARIO.STATI_PROBLEMA else 0)
                            nuova_nota = s2.text_input(
                                "A che punto sei", value=r["Nota"],
                                placeholder="cosa hai provato, cosa manca")
                            agg = st.form_submit_button("💾 Aggiorna")
                        if agg:
                            testo_riga = r["Problema"] + (
                                f" :: {nuova_nota.strip()}" if nuova_nota.strip() else "")
                            diario_scrivi(DIARIO.riga(
                                "problema", nuovo_stato, "Scienza", 0, None,
                                testo_riga))
                            conferma(f"«{r['Problema'][:40]}» → {nuovo_stato}")
                            st.rerun()

                        # ---- rinomina, archivia, elimina ------------------
                        m1, m2, m3 = st.columns(3)
                        if m1.button("✏️ Rinomina", key=f"ren_{chiave_p}",
                                     width='stretch'):
                            st.session_state["prob_rinomina"] = r["Problema"]
                        if m2.button("📦 Archivia", key=f"arc_{chiave_p}",
                                     width='stretch',
                                     help="Sparisce dalla lista ma resta "
                                          "nello storico."):
                            diario_scrivi(DIARIO.riga(
                                "problema", "archiviato", "Scienza", 0, None,
                                r["Problema"] + (f" :: {r['Nota']}"
                                                 if r["Nota"] else "")))
                            conferma(f"Archiviato: {r['Problema'][:40]}")
                            st.rerun()
                        if m3.button("🗑️ Elimina", key=f"del_{chiave_p}",
                                     width='stretch'):
                            st.session_state["prob_elimina"] = r["Problema"]

                        if st.session_state.get("prob_rinomina") == r["Problema"]:
                            with st.form(f"ren_form_{chiave_p}"):
                                nome_nuovo = st.text_input(
                                    "Come si chiama adesso", value=r["Problema"])
                                r1, r2 = st.columns(2)
                                ok_r = r1.form_submit_button("Conferma",
                                                             type="primary")
                                no_r = r2.form_submit_button("Annulla")
                            if ok_r and nome_nuovo.strip() and \
                                    nome_nuovo.strip() != r["Problema"]:
                                # il vecchio esce di lista, il nuovo entra
                                # con lo stesso stato e la stessa nota
                                diario_scrivi([
                                    DIARIO.riga("problema", "cancellato",
                                                "Scienza", 0, None,
                                                r["Problema"]),
                                    DIARIO.riga("problema", r["Stato"],
                                                "Scienza", 0, None,
                                                nome_nuovo.strip()
                                                + (f" :: {r['Nota']}"
                                                   if r["Nota"] else "")),
                                ])
                                conferma("Rinominato")
                                st.session_state.pop("prob_rinomina", None)
                                st.rerun()
                            if no_r:
                                st.session_state.pop("prob_rinomina", None)
                                st.rerun()

                        if st.session_state.get("prob_elimina") == r["Problema"]:
                            st.warning(f"Elimino «{r['Problema'][:60]}»? "
                                       "Sparisce dalla lista e dallo storico "
                                       "visibile. Se vuoi solo toglierlo di "
                                       "mezzo, usa Archivia.")
                            e1, e2 = st.columns(2)
                            if e1.button("Sì, elimina", key=f"del2_{chiave_p}",
                                         type="primary", width='stretch'):
                                diario_scrivi(DIARIO.riga(
                                    "problema", "cancellato", "Scienza", 0,
                                    None, r["Problema"]))
                                conferma("Eliminato")
                                st.session_state.pop("prob_elimina", None)
                                st.rerun()
                            if e2.button("No, lascia stare",
                                         key=f"del3_{chiave_p}",
                                         width='stretch'):
                                st.session_state.pop("prob_elimina", None)
                                st.rerun()

                        if st.button("🤖 Come lo affronterei", key=f"ai_{chiave_p}"):
                            stato_p = st.empty()
                            try:
                                with st.spinner("Sto pensando…"):
                                    sug = AI.chiedi(
                                        "Sei un ingegnere esperto e pratico. "
                                        "Questa persona tiene una lista di "
                                        "problemi aperti su cui ragiona nel "
                                        f"tempo.\n\nIl problema: {r['Problema']}\n"
                                        f"A che punto è: {r['Nota'] or 'non ha ancora provato niente'}\n\n"
                                        "Proponi tre strade concrete per "
                                        "affrontarlo, in ordine da quella più "
                                        "economica da provare. Per ognuna dì in "
                                        "una riga come capiresti se funziona. "
                                        "Niente teoria: cose che può fare con "
                                        "un banco da maker. Italiano, frasi brevi.",
                                        chiave_ai(), modello_ai(),
                                        al_tentativo=lambda m: stato_p.info(m))
                                stato_p.empty()
                                st.markdown(sug)
                            except AI.ErroreAI as e:
                                stato_p.empty()
                                st.error(e.messaggio)
                                if e.dettaglio:
                                    st.caption(e.dettaglio)

                tab_p = elenco_p.copy()
                for c in ("Aperto", "Aggiornato"):
                    tab_p[c] = tab_p[c].dt.strftime("%d/%m/%Y")
                scarica_tabella(tab_p, "problemi_aperti",
                                "⬇️ Scarica la lista")

            archiviati = DIA[(DIA["Tipo"] == "problema")
                             & (DIA["Attivita"] == "archiviato")]
            if not archiviati.empty:
                with st.expander(f"Problemi archiviati ({len(archiviati)})"):
                    for _, r in archiviati.sort_values(
                            "Data", ascending=False).iterrows():
                        testo_a = r["Nota"].split(" :: ")[0]
                        a1, a2c = st.columns([4, 1])
                        a1.markdown(f"**{testo_a}**  \n"
                                    f"<small style='opacity:.6'>archiviato il "
                                    f"{r['Data']:%d/%m/%Y}</small>",
                                    unsafe_allow_html=True)
                        if a2c.button("↩️ Riprendi",
                                      key=f"ripr_{testo_a[:24]}",
                                      width='stretch'):
                            diario_scrivi(DIARIO.riga(
                                "problema", "aperto", "Scienza", 0, None,
                                r["Nota"]))
                            conferma(f"Ripreso: {testo_a[:40]}")
                            st.rerun()

        # ------------------------------------------- le previsioni ---------
        # L'esercizio più scomodo e più utile: scrivi cosa ti aspetti PRIMA
        # di sapere com'è andata, e quanto sei sicuro. Dopo un po' di
        # previsioni chiuse si vede se quando dici «sono sicuro al 90%» ci
        # azzecchi davvero nove volte su dieci. Non misura quanto sai:
        # misura quanto conosci i tuoi limiti.
        elif scelta_sc == SEZIONI_SC[3]:
            st.caption("Scrivi cosa ti aspetti **prima** di saperlo, e quanto "
                       "sei sicuro. Vale per un esperimento al banco come per "
                       "«questo cliente risponde entro venerdì». Quando sai "
                       "com'è andata, segni l'esito.")

            with st.form("nuova_previsione", clear_on_submit=True):
                testo_pv = st.text_input(
                    "Cosa prevedi",
                    placeholder="es. la bobina con nucleo di ferrite dà "
                                "almeno il doppio del segnale")
                v1, v2 = st.columns([3, 2])
                conf_pv = v1.slider(
                    "Quanto sei sicuro", 50, 99, 70, step=5,
                    help="50 vuol dire «è come tirare a indovinare». Sopra "
                         "il 95 mettilo solo se lo diresti a voce alta "
                         "davanti a qualcuno.")
                entro_pv = v2.date_input(
                    "Lo saprai entro", value=DIARIO.oggi() + dt.timedelta(days=7),
                    format="DD/MM/YYYY")
                if st.form_submit_button("💾 Registra la previsione",
                                         type="primary") and testo_pv.strip():
                    diario_scrivi(DIARIO.riga(
                        "previsione", "aperta", "Scienza", 0, conf_pv,
                        f"{testo_pv.strip()} :: {entro_pv:%Y-%m-%d}"))
                    conferma(f"Previsione registrata al {conf_pv}%")
                    st.rerun()

            tutte_pv = DIARIO.previsioni(DIA)
            aperte_pv = tutte_pv[tutte_pv["Stato"] == "aperta"] \
                if not tutte_pv.empty else tutte_pv
            chiuse_pv = tutte_pv[tutte_pv["Stato"].isin(["avverata", "smentita"])] \
                if not tutte_pv.empty else tutte_pv

            if not aperte_pv.empty:
                st.markdown(f"##### In attesa di esito ({len(aperte_pv)})")
                for i_pv, r in aperte_pv.iterrows():
                    scaduta_pv = (r["Entro"] and r["Entro"]
                                  < f"{DIARIO.oggi():%Y-%m-%d}")
                    with st.container(border=True):
                        w1, w2, w3 = st.columns([4, 1, 1])
                        quando_pv = ""
                        if r["Entro"]:
                            try:
                                d_pv = dt.date.fromisoformat(r["Entro"])
                                quando_pv = f" · entro il {d_pv:%d/%m/%Y}"
                            except ValueError:
                                pass
                        w1.markdown(f"**{r['Previsione']}**")
                        w1.caption(f"sicuro al {r['Confidenza']:.0f}%"
                                   + quando_pv
                                   + (" · **scaduta**" if scaduta_pv else ""))
                        if w2.button("✓ Giusta", key=f"pv_ok_{i_pv}",
                                     width='stretch'):
                            diario_scrivi(DIARIO.riga(
                                "previsione", "avverata", "Scienza", 0,
                                r["Confidenza"],
                                f"{r['Previsione']} :: {r['Entro']}"))
                            conferma("Segnata come avverata")
                            st.rerun()
                        if w3.button("✗ Sbagliata", key=f"pv_no_{i_pv}",
                                     width='stretch'):
                            diario_scrivi(DIARIO.riga(
                                "previsione", "smentita", "Scienza", 0,
                                r["Confidenza"],
                                f"{r['Previsione']} :: {r['Entro']}"))
                            conferma("Segnata come smentita")
                            st.rerun()

            if chiuse_pv.empty:
                st.info("La taratura compare quando avrai chiuso qualche "
                        "previsione. Ne servono una decina perché i numeri "
                        "dicano qualcosa, una cinquantina perché dicano "
                        "qualcosa di solido.")
            else:
                cal_pv, brier_pv = DIARIO.calibrazione(DIA)
                z1, z2, z3 = st.columns(3)
                z1.markdown('<span class="kpi-mark"></span>',
                            unsafe_allow_html=True)
                z1.metric("Previsioni chiuse", len(chiuse_pv))
                giuste_pv = (chiuse_pv["Stato"] == "avverata").sum()
                z2.metric("Azzeccate",
                          f"{100 * giuste_pv / len(chiuse_pv):.0f}%")
                z3.metric("Punteggio di Brier", f"{brier_pv:.3f}",
                          help="La distanza fra quanto eri sicuro e com'è "
                               "andata: 0 è perfetto, 0,25 è come tirare a "
                               "indovinare. Più è basso, meglio sei tarato.")

                if not cal_pv.empty:
                    figpv = go.Figure()
                    figpv.add_scatter(x=[50, 100], y=[50, 100], mode="lines",
                                      name="taratura perfetta",
                                      line=dict(color="#999", width=1,
                                                dash="dot"))
                    figpv.add_scatter(
                        x=cal_pv["Dichiarata"], y=cal_pv["Reale"],
                        mode="markers+text", name="tu",
                        text=cal_pv["Quante"].map(lambda n: f"{n}"),
                        textposition="top center",
                        marker=dict(size=cal_pv["Quante"] * 3 + 9,
                                    color=PALETTE[0]),
                        hovertemplate="dicevi %{x:.0f}%<br>"
                                      "in realtà %{y:.0f}%<extra></extra>")
                    figpv.update_xaxes(range=[45, 105], title="quanto eri sicuro")
                    figpv.update_yaxes(range=[0, 105], title="quante volte è andata così")
                    st.plotly_chart(
                        style(figpv, 320, "La tua taratura", showlegend=False),
                        width='stretch')
                    st.caption("I punti sopra la riga: eri più prudente di "
                               "quanto servisse. Sotto la riga: eri troppo "
                               "sicuro di te. Il numero dentro il punto dice "
                               "su quante previsioni è calcolato — con meno "
                               "di cinque non ci fare caso.")

                    sotto = cal_pv[cal_pv["Reale"] < cal_pv["Dichiarata"] - 10]
                    if not sotto.empty and sotto["Quante"].sum() >= 5:
                        st.markdown(
                            "🟡 &nbsp;Nelle fasce **"
                            + "**, **".join(sotto["Fascia"])
                            + "** sei più sicuro di quanto i fatti "
                              "giustifichino. È l'errore più comune e il più "
                              "utile da correggere: prova ad abbassare di "
                              "dieci punti quando stai per scrivere 90.",
                            unsafe_allow_html=True)

                    scarica_tabella(cal_pv, "taratura_previsioni",
                                    "⬇️ I dati della taratura")

                with st.expander(f"Le previsioni chiuse ({len(chiuse_pv)})"):
                    for _, r in chiuse_pv.sort_values(
                            "Chiusa", ascending=False).iterrows():
                        segno_pv = "✓" if r["Stato"] == "avverata" else "✗"
                        st.markdown(f"{segno_pv} **{r['Previsione']}** — "
                                    f"eri sicuro al {r['Confidenza']:.0f}%")

        # ----------------------------------- sfide e idee da inventare ---
        # Non è un esercizio: sono le cose difficili che aspettano qualcuno.
        # Le sfide sono domande scientifiche ancora aperte; i bisogni sono
        # problemi che vivono persone concrete. Da qui può nascere un'invenzione.
        elif scelta_sc == SEZIONI_SC[4]:
            IDEE = _carica_json("idee.json", _mtime("idee.json"))
            if "_errore" in IDEE:
                st.error(f"Non riesco a leggere `idee.json`: {IDEE['_errore']}")
            else:
                st.caption(IDEE.get("_nota", ""))
                II1, II2, II3 = st.tabs(["🔭 Sfide scientifiche",
                                         "🧰 Bisogni da risolvere",
                                         "💭 Le mie idee"])
                with II1:
                    sfide = IDEE.get("sfide", [])
                    if st.button("🎲 Estrai una sfida a caso", key="estrai_sfida") and sfide:
                        import random as _rnd
                        st.session_state["sfida_estratta"] = _rnd.choice(sfide)["titolo"]
                    if st.session_state.get("sfida_estratta"):
                        st.info(f"**Provaci con questa:** {st.session_state['sfida_estratta']}")
                    for s in sfide:
                        with st.expander(s["titolo"]):
                            st.markdown(f"**Perché conta.** {s.get('perche', '')}")
                            st.markdown(f"**Da dove partire.** {s.get('da_dove', '')}")
                            st.caption(f"Somiglia a: {s.get('legame', '—')}")
                with II2:
                    for b_ in IDEE.get("bisogni", []):
                        with st.container(border=True):
                            st.markdown(f"**{b_.get('chi', '')}**")
                            st.markdown(f"Problema: {b_.get('problema', '')}")
                            st.markdown(f"Un'idea: {b_.get('idea', '')}")
                            st.caption(f"Collegamento: {b_.get('legame', '—')}")
                with II3:
                    st.caption("Le idee che scrivi qui restano nel diario, "
                               "così le ritrovi quando serve.")
                    pulisci_se_segnata("idea_titolo")
                    if st.session_state.get("__idea_ok__"):
                        conferma("Idea salvata")
                        st.session_state.pop("__idea_ok__", None)
                    titolo_i = st.text_input("Il problema o l'idea, in breve",
                                             key="idea_titolo",
                                             placeholder="es. un modo per sapere quando un cliente dice il vero")
                    dettaglio_i = VOCE.campo("Perché conta, da dove partire",
                                             "idea_testo", chiave_ai(), modello_ai(),
                                             altezza=110)
                    if st.button("💾 Salva l'idea", type="primary", key="salva_idea"):
                        if titolo_i.strip():
                            diario_scrivi(DIARIO.riga(
                                "idea", titolo_i.strip()[:80], "Scienza", 0, None,
                                dettaglio_i.strip()[:600]))
                            VOCE.svuota("idea_testo")
                            svuota_dopo("idea_titolo")
                            st.session_state["__idea_ok__"] = True
                            st.rerun()
                        else:
                            st.warning("Serve almeno il titolo.")
                    mie = DIA[DIA["Tipo"] == "idea"].sort_values("Data", ascending=False)
                    if not mie.empty:
                        st.markdown("##### Le idee che hai scritto")
                        for _, r_i in mie.head(30).iterrows():
                            with st.expander(f"{r_i['Data']:%d/%m/%Y} · {r_i['Attivita']}"):
                                st.write(r_i["Nota"] or "—")

        # ---- l'abitudine della settimana -----------------------------------
        # Otto abitudini lette tutte insieme restano parole. Una alla volta,
        # per sette giorni, diventa una cosa su cui fai caso davvero. La
        # rotazione segue il numero della settimana nell'anno, quindi cambia
        # da sola il lunedì e torna uguale su ogni dispositivo.
        abitudini = SCI.get("abitudini", [])
        if abitudini:
            st.divider()
            anno_s, sett_s, _ = DIARIO.oggi().isocalendar()
            idx_ab = (sett_s - 1) % len(abitudini)
            AB = abitudini[idx_ab]

            with st.container(border=True):
                a1, a2 = st.columns([4, 1])
                a1.markdown(f"##### 🧭 L'abitudine di questa settimana — "
                            f"{AB['titolo']}")
                a2.caption(f"settimana {sett_s}")
                st.markdown(AB["testo"])

                chiave_ab = f"{anno_s}-W{sett_s:02d}"
                gia = DIA[(DIA["Tipo"] == "abitudine")
                          & (DIA["Attivita"] == chiave_ab)]
                if gia.empty:
                    nota_ab = st.text_input(
                        "Dove l'hai usata questa settimana?",
                        key="abitudine_nota",
                        placeholder="anche una riga sola: quando ti è tornata utile")
                    if st.button("💾 Chiudi la settimana", type="primary"):
                        if nota_ab.strip():
                            diario_scrivi(DIARIO.riga(
                                "abitudine", chiave_ab, "Scienza", 0, None,
                                f"{AB['titolo']} :: {nota_ab.strip()}"))
                            conferma(f"Settimana {sett_s} chiusa su «{AB['titolo']}»")
                            svuota_dopo("abitudine_nota")
                            st.rerun()
                        else:
                            st.warning("Scrivi una riga prima di chiudere.")
                else:
                    st.success("Settimana già chiusa: "
                               + gia.iloc[-1]["Nota"].split(" :: ", 1)[-1])

            passate = DIA[DIA["Tipo"] == "abitudine"].sort_values(
                "Data", ascending=False)
            if not passate.empty:
                with st.expander(f"Le settimane passate ({len(passate)})"):
                    for _, r in passate.iterrows():
                        titolo_ab = r["Nota"].split(" :: ")[0]
                        resto_ab = r["Nota"].split(" :: ", 1)[-1]
                        st.markdown(f"**{r['Attivita']} · {titolo_ab}** — {resto_ab}")

        with st.expander("Tutte e otto le abitudini, per rileggerle"):
            for i_ab, ab in enumerate(abitudini):
                segno = " ← questa settimana" if i_ab == idx_ab else ""
                st.markdown(f"**{ab['titolo']}**{segno} — {ab['testo']}")

    st.divider()

    # =================== TEMPO ED ENERGIA (vedi produttivita.py) =============
    PROD.mostra(CTX)

    st.divider()

    # =================== I CORSI CHE SEGUI ==================================
    st.markdown("### 🎓 I corsi che segui")
    st.caption("Udemy, YouTube, un libro, un corso in aula: qui dentro ci sta "
               "tutto. Ogni volta che avanzi registri a che punto sei, e la "
               "percentuale vecchia resta nello storico — così vedi se stai "
               "andando avanti o se un corso si è fermato.")

    riepilogo = DIARIO.corsi(DIA)

    with st.expander("➕ Registra un avanzamento", expanded=riepilogo.empty):
        gia_noti = sorted(riepilogo["Corso"].tolist()) if not riepilogo.empty else []
        with st.form("avanzamento_corso", clear_on_submit=True):
            q1, q2 = st.columns([3, 2])
            if gia_noti:
                scelto_c = q1.selectbox("Corso", gia_noti + ["➕ un corso nuovo…"])
            else:
                scelto_c = "➕ un corso nuovo…"
                q1.caption("Ancora nessun corso: scrivine uno qui sotto.")
            nome_nuovo = q1.text_input(
                "Nome del corso nuovo",
                disabled=scelto_c != "➕ un corso nuovo…",
                placeholder="es. 100 Days of Code — Python")
            piatt = q2.text_input("Dove", value="Udemy")
            q3, q4 = st.columns(2)
            perc = q3.slider("A che punto sei (%)", 0, 100, 0, step=5)
            min_c = q4.number_input("Minuti fatti oggi", 0, 600, 30, step=5)
            lez = st.text_input("Sezione o lezione a cui sei arrivato",
                                placeholder="es. Sezione 7 — i dizionari")
            salva_c = st.form_submit_button("💾 Registra", type="primary")

        if salva_c:
            nome_c = (nome_nuovo.strip() if scelto_c == "➕ un corso nuovo…"
                      else scelto_c)
            if not nome_c:
                st.warning("Serve il nome del corso.")
            else:
                diario_scrivi(DIARIO.riga("corso", nome_c, piatt.strip() or "—",
                                          min_c, perc, lez.strip()))
                conferma(f"«{nome_c}» aggiornato al {perc}%")
                st.rerun()

    if not riepilogo.empty:
        for _, c in riepilogo.iterrows():
            with st.container(border=True):
                t1, t2 = st.columns([3, 1])
                t1.markdown(f"**{c['Corso']}** · {c['Piattaforma']}")
                t1.progress(min(1.0, c["Avanzamento"] / 100),
                            text=f"{c['Avanzamento']:.0f}%")
                if c["Ultima lezione"]:
                    t1.caption(f"Ultima lezione: {c['Ultima lezione']}")
                gg = (pd.Timestamp(DIARIO.oggi()) - c["Ultimo aggiornamento"]).days
                t2.metric("Ore in tutto", f"{c['Minuti'] / 60:.1f}")
                t2.caption(f"aggiornato {gg} giorni fa" if gg else "aggiornato oggi")

        storia = DIA[DIA["Tipo"] == "corso"]
        if len(storia) >= 3:
            figc = go.Figure()
            for i, (nome_c, g) in enumerate(storia.groupby("Attivita")):
                g = g.sort_values("Data")
                figc.add_scatter(x=g["Data"], y=g["Valore"], mode="lines+markers",
                                 name=nome_c,
                                 line=dict(color=PALETTE[i % len(PALETTE)], width=2),
                                 hovertemplate="%{x|%d/%m/%Y}<br>%{y:.0f}%<extra></extra>")
            figc.update_yaxes(range=[0, 104], ticksuffix="%")
            st.plotly_chart(style(figc, 300, "Avanzamento nel tempo"),
                            width='stretch')

        tabc = riepilogo.copy()
        tabc["Ultimo aggiornamento"] = tabc["Ultimo aggiornamento"].dt.strftime("%d/%m/%Y")
        scarica_tabella(tabc, "corsi", "⬇️ Scarica i corsi")

    st.divider()

    # =================== ANDAMENTO E SUGGERIMENTI ===========================
    st.markdown("### 📈 Come sta andando")

    ses = DIA[DIA["Tipo"].isin(DIARIO.TIPI_TEMPO)]
    if ses.empty:
        st.info("Qui comparirà l'andamento appena registri la prima sessione.")
    else:
        # ------------------------- scelta del periodo e del passo ------------
        primo_giorno = DIA["Data"].min().date()
        oggi_d = DIARIO.oggi()

        p1, p2 = st.columns([2, 3])
        passo = p1.segmented_control(
            "Raggruppa per", list(DIARIO.PASSI.keys()), default="Giorno",
            key="passo_andamento") or "Giorno"

        preset = p2.segmented_control(
            "Periodo",
            ["7 giorni", "30 giorni", "3 mesi", "12 mesi", "Tutto", "Scelgo io"],
            default="30 giorni", key="periodo_andamento") or "30 giorni"

        salti = {"7 giorni": 7, "30 giorni": 30, "3 mesi": 91, "12 mesi": 365}
        if preset == "Tutto":
            dal, al = primo_giorno, oggi_d
        elif preset == "Scelgo io":
            scelta_date = st.date_input(
                "Da quando a quando",
                value=(max(primo_giorno, oggi_d - dt.timedelta(days=29)), oggi_d),
                min_value=primo_giorno, max_value=oggi_d, format="DD/MM/YYYY")
            if isinstance(scelta_date, (tuple, list)) and len(scelta_date) == 2:
                dal, al = scelta_date
            else:
                dal, al = primo_giorno, oggi_d
        else:
            dal = max(primo_giorno, oggi_d - dt.timedelta(days=salti[preset] - 1))
            al = oggi_d

        serie = DIARIO.serie_minuti(DIA, dal, al, passo)
        etic = DIARIO.etichette(serie.index, passo)
        nel_periodo = ses[(ses["Data"] >= pd.Timestamp(dal))
                          & (ses["Data"] <= pd.Timestamp(al))]

        # lo storico non si perde mai: questi numeri sono su TUTTO il diario
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Minuti nel periodo", f"{serie.sum():,.0f}".replace(",", "."))
        s2.metric("Sessioni nel periodo", f"{len(nel_periodo)}")
        s3.metric(f"Media per {passo.lower()}", f"{serie.mean():.0f} min")
        s4.metric("Ore da sempre", f"{ses['Minuti'].sum() / 60:,.1f}".replace(",", "."))

        g1, g2 = st.columns([3, 2])
        with g1:
            fig = go.Figure()
            fig.add_bar(x=etic, y=serie.values,
                        marker=dict(color=PALETTE[0], line=dict(width=0)),
                        name="minuti",
                        hovertemplate="%{x}<br>%{y:.0f} minuti<extra></extra>")
            if passo == "Giorno" and len(serie) >= 10:
                media = serie.rolling(7, min_periods=1).mean()
                fig.add_scatter(x=etic, y=media.values, mode="lines",
                                name="media su 7 giorni",
                                line=dict(color=VERDE_SCURO, width=2),
                                hovertemplate="%{x}<br>media %{y:.0f} min<extra></extra>")
            fig.update_xaxes(type="category")
            st.plotly_chart(
                style(fig, 320, f"Minuti per {passo.lower()} · "
                                f"dal {dal:%d/%m/%Y} al {al:%d/%m/%Y}"),
                width='stretch')
            tab_serie = pd.DataFrame({"Periodo": etic, "Minuti": serie.values})
            scarica_tabella(tab_serie, "andamento_minuti", "⬇️ I dati del grafico")

        with g2:
            if nel_periodo.empty:
                st.info("Nessuna sessione in questo periodo.")
            else:
                per_att = (nel_periodo.groupby("Attivita")["Minuti"].sum()
                           .sort_values(ascending=True))
                fig2 = go.Figure()
                fig2.add_bar(x=per_att.values, y=per_att.index, orientation="h",
                             marker=dict(color=PALETTE[1], line=dict(width=0)),
                             hovertemplate="%{y}<br>%{x:.0f} minuti<extra></extra>")
                fig2.update_xaxes(range=[0, float(per_att.max()) * 1.22])
                st.plotly_chart(style(fig2, 320, "Dove è finito il tempo"),
                                width='stretch')
                scarica_tabella(
                    per_att.rename("Minuti").rename_axis("Attività").reset_index(),
                    "minuti_per_attivita", "⬇️ I dati del grafico")

        # ----------------------------- i suggerimenti ------------------------
        st.markdown("##### Cosa noto nei tuoi dati")
        sugg = []

        strisc = DIARIO.striscia(DIA)
        if strisc >= 7:
            sugg.append(("🟢", f"Sei a **{strisc} giorni di fila**. È la cosa che "
                               "conta più di quanto fai in ogni singola sessione."))
        elif strisc == 0 and len(ses) > 0:
            ultima = ses["Data"].max()
            gg = (pd.Timestamp(DIARIO.oggi()) - ultima).days
            sugg.append(("🟡", f"Ultima sessione **{gg} giorni fa**. Per ripartire "
                               "fai la più corta che hai: quindici minuti valgono "
                               "più di un'ora rimandata."))

        ultimi14 = ses[ses["Data"] >= pd.Timestamp(DIARIO.oggi()) - pd.Timedelta(days=13)]
        if len(ultimi14) >= 3:
            fatte = set(ultimi14["Attivita"])
            trascurate = [a["nome"] for a in attivita if a["nome"] not in fatte]
            if trascurate:
                sugg.append(("🟡", "In due settimane non hai toccato: **"
                             + "**, **".join(trascurate[:3]) + "**."))

        voti = ses["Valore"].dropna()
        if len(voti) >= 5:
            recenti = voti.tail(5).mean()
            prima = voti.head(max(1, len(voti) - 5)).mean()
            if recenti >= prima + 0.5:
                sugg.append(("🟢", f"Le ultime sessioni ti stanno risultando più "
                                   f"scorrevoli di prima (media {recenti:.1f} "
                                   f"contro {prima:.1f})."))
            elif recenti <= prima - 0.5:
                sugg.append(("🟡", f"Le ultime sessioni sono più faticose della "
                                   f"media (media {recenti:.1f} contro {prima:.1f}). "
                                   "Spesso vuol dire che il passo è troppo lungo: "
                                   "spezza l'obiettivo in due."))

        lunghe = ses[ses["Minuti"] >= 60]
        if len(ses) >= 8 and len(lunghe) / len(ses) > 0.6:
            sugg.append(("🟡", "Quasi tutte le tue sessioni superano l'ora. "
                               "Le sessioni lunghe sono le prime a saltare quando "
                               "la giornata si complica: tienine qualcuna da trenta."))

        fermi = riepilogo[riepilogo["Ultimo aggiornamento"]
                          < pd.Timestamp(DIARIO.oggi()) - pd.Timedelta(days=21)] \
            if not riepilogo.empty else pd.DataFrame()
        for _, c in fermi.iterrows():
            sugg.append(("🟡", f"Il corso **{c['Corso']}** è fermo al "
                               f"{c['Avanzamento']:.0f}% da più di tre settimane."))

        n_anom = int((DIA["Tipo"] == "anomalia").sum())
        if n_anom == 0:
            sugg.append(("🟡", "Il taccuino delle anomalie è ancora vuoto. È "
                               "l'esercizio che rende tutto il resto più utile, e "
                               "costa cinque minuti."))
        elif n_anom >= 10:
            sugg.append(("🟢", f"**{n_anom} anomalie** annotate. Da qui in poi la "
                               "rilettura della domenica comincia a pagare: cerca "
                               "due annotazioni lontane che parlano della stessa cosa."))

        if not sugg:
            sugg.append(("🟢", "Troppo pochi dati per dire qualcosa di sensato. "
                               "Torna fra qualche sessione."))
        for pallino, testo in sugg:
            st.markdown(f"{pallino} &nbsp;{testo}", unsafe_allow_html=True)

        with st.expander(f"Tutte le righe del diario ({len(DIA)} da sempre)"):
            tab_dia = DIA.copy()
            tab_dia["Data"] = tab_dia["Data"].dt.strftime("%d/%m/%Y")
            st.dataframe(tab_dia, width='stretch', hide_index=True, height=340)
            scarica_tabella(DIA, "diario_completo")
            st.download_button("⬇️ Archivio completo (JSON)", DIARIO.esporta(DIA),
                               f"quadro_diario_{DIARIO.oggi():%Y%m%d}.json",
                               "application/json")

    st.divider()

    st.markdown("### ⚠️ Cosa richiede attenzione")

    avvisi = []
    if not dfp.empty:
        scadute = dfp[(dfp["Consegna"].notna()) & (dfp["Consegna"] < oggi_ts)
                      & (~dfp["Stato"].str.lower().str.contains("complet"))]
        for _, r in scadute.iterrows():
            giorni = (oggi_ts - r["Consegna"]).days
            avvisi.append(("🔴", "Consegna scaduta",
                           f"**{r['Etichetta']}** — consegna prevista il "
                           f"{r['Consegna']:%d/%m/%Y}, {giorni} giorni fa · {r['Stato']}"))

        in_arrivo = dfp[(dfp["Consegna"].notna())
                        & (dfp["Consegna"] >= oggi_ts)
                        & (dfp["Consegna"] <= oggi_ts + pd.Timedelta(days=30))
                        & (~dfp["Stato"].str.lower().str.contains("complet"))]
        for _, r in in_arrivo.iterrows():
            avvisi.append(("🟡", "Consegna vicina",
                           f"**{r['Etichetta']}** — fra {(r['Consegna'] - oggi_ts).days} "
                           f"giorni ({r['Consegna']:%d/%m/%Y})"))

        SOGLIA = 10  # sotto i 10 € non vale la pena segnalare
        sospesi = dfp[(dfp["Residuo"] >= SOGLIA)
                      & (dfp["Stato"].str.lower().str.contains("complet"))
                      ].sort_values("Residuo", ascending=False)
        for _, r in sospesi.iterrows():
            avvisi.append(("🔴", "Completato ma non saldato",
                           f"**{r['Etichetta']}** — restano "
                           f"{r['Residuo']:,.0f} € da incassare".replace(",", ".")))

        acconti = dfp[(dfp["Incassato"] > 0) & (dfp["Residuo"] >= SOGLIA)
                      & (~dfp["Stato"].str.lower().str.contains("complet"))
                      ].sort_values("Residuo", ascending=False)
        for _, r in acconti.iterrows():
            avvisi.append(("🟡", "Acconto incassato, lavoro aperto",
                           f"**{r['Etichetta']}** — incassati "
                           f"{r['Incassato']:,.0f} € su {r['Costo']:,.0f} €".replace(",", ".")))

        poco = dfp[(dfp["GuadagnoOrario"].notna()) & (dfp["GuadagnoOrario"] < 5)]
        for _, r in poco.iterrows():
            avvisi.append(("🟡", "Resa oraria bassa",
                           f"**{r['Etichetta']}** — {r['GuadagnoOrario']:.2f} € l'ora "
                           f"su {r['Ore']:.0f} ore"))

    if not df.empty:
        ultime = df.groupby("Allievo")["Data"].max()
        for nome, data in ultime.items():
            gg = (oggi_ts - data).days
            if 21 <= gg <= 400:
                avvisi.append(("🟡", "Allievo fermo",
                               f"**{nome}** — ultima lezione {gg} giorni fa "
                               f"({data:%d/%m/%Y})"))
        da_inc = df[(~df["Pagato"]) & (df["Importo"] >= 10)]
        if not da_inc.empty:
            per_allievo = da_inc.groupby("Allievo")["Importo"].sum().sort_values(ascending=False)
            for nome, imp in per_allievo.items():
                avvisi.append(("🔴", "Lezioni da incassare",
                               f"**{nome}** — {imp:,.0f} € in sospeso".replace(",", ".")))

    if avvisi:
        rossi = sum(1 for a in avvisi if a[0] == "🔴")
        k = st.columns(3)
        k[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
        k[0].metric("Segnalazioni", len(avvisi))
        k[1].metric("Urgenti", rossi)
        k[2].metric("Da tenere d'occhio", len(avvisi) - rossi)

        solo_urgenti = st.toggle("Mostra solo le urgenti", value=False)
        mostra = [a for a in avvisi if a[0] == "🔴"] if solo_urgenti else avvisi
        ordine = {"🔴": 0, "🟡": 1}
        mostra = sorted(mostra, key=lambda a: ordine.get(a[0], 2))
        MAX_PER_CATEGORIA = 6
        visti, nascosti = {}, {}
        for pallino, categoria, testo in mostra:
            n = visti.get(categoria, 0)
            if n < MAX_PER_CATEGORIA:
                st.markdown(f"{pallino} &nbsp;*{categoria}* — {testo}",
                            unsafe_allow_html=True)
                visti[categoria] = n + 1
            else:
                nascosti[categoria] = nascosti.get(categoria, 0) + 1
        for categoria, quanti in nascosti.items():
            st.caption(f"…e altre {quanti} segnalazioni della categoria "
                       f"«{categoria}»: le trovi nei tab Progetti ed Economia.")
    else:
        st.success("Nessuna segnalazione: consegne, pagamenti e allievi sono in ordine.")

    st.divider()

    # ---------------- collegamenti rapidi ---------------------------------
    st.markdown("### 🔗 Collegamenti rapidi")

    @st.cache_data(show_spinner=False)
    def carica_collegamenti(_versione: float):
        import json as _json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "collegamenti.json"), encoding="utf-8") as f:
                return _json.load(f).get("collegamenti", [])
        except Exception:
            return []

    voci = [v for v in carica_collegamenti(_mtime("collegamenti.json"))
            if (v.get("url") or "").strip()]

    # le cartelle Drive si ricavano dai Secrets: nessuna configurazione in più
    for etichetta, chiave in [("Cartella Registri", "drive_folder_id"),
                              ("Cartella Progetti", "drive_folder_id_progetti"),
                              ("Cartella Loghi", "drive_folder_id_loghi")]:
        fid = (secret(chiave, "") or "").strip()
        if fid:
            voci.append({"gruppo": "Google Drive", "icona": "📁", "nome": etichetta,
                         "url": f"https://drive.google.com/drive/folders/{fid}",
                         "nota": "I file che alimentano questa dashboard"})

    if not voci:
        st.info("Nessun collegamento configurato: compila `collegamenti.json`.")
    else:
        gruppi = []
        for v in voci:
            g = v.get("gruppo", "Altro")
            if g not in gruppi:
                gruppi.append(g)
        for g in gruppi:
            st.markdown(f"**{g}**")
            del_gruppo = [v for v in voci if v.get("gruppo", "Altro") == g]
            for riga in range(0, len(del_gruppo), 4):
                cols = st.columns(4)
                for col, v in zip(cols, del_gruppo[riga:riga + 4]):
                    col.link_button(f"{v.get('icona', '🔗')} {v['nome']}", v["url"],
                                    width='stretch', help=v.get("nota", ""))

    st.divider()

    # ---------------- promemoria operativi --------------------------------
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Prossime consegne")
        if not dfp.empty:
            prossime = (dfp[(dfp["Consegna"].notna()) & (dfp["Consegna"] >= oggi_ts)]
                        .sort_values("Consegna").head(8))
            if prossime.empty:
                st.caption("Nessuna consegna futura in calendario.")
            else:
                t = prossime[["Consegna", "Etichetta", "Cliente", "Stato"]].copy()
                t["Consegna"] = t["Consegna"].dt.strftime("%d/%m/%Y")
                st.dataframe(t.rename(columns={"Etichetta": "Progetto"}),
                             width='stretch', hide_index=True)
        else:
            st.caption("Dati dei progetti non caricati.")

    with c2:
        st.markdown("##### Ultime lezioni svolte")
        if not df.empty:
            ultime_lez = df.sort_values("Data", ascending=False).head(8)
            t = ultime_lez[["Data", "Allievo", "Materia", "OreTotali"]].copy()
            t["Data"] = t["Data"].dt.strftime("%d/%m/%Y")
            st.dataframe(t, width='stretch', hide_index=True,
                         column_config={"OreTotali": st.column_config.NumberColumn(
                             "Ore", format="%.2f")})
        else:
            st.caption("Dati delle lezioni non caricati.")


# ============================================================================
# TAB 2 - RIPETIZIONI  (tutto sulle lezioni private: era cinque tab separati)
# ============================================================================
with TAB[2]:
    pannello_riepilogo('ripetizioni')
    RIP = st.tabs(["📊 Panoramica", "👥 Allievi", "💶 Economia", "🎓 Didattica", "📋 Dettaglio"])

    # ---------------- Panoramica ----------------
    with RIP[0]:
        c1, c2 = st.columns([3, 2])

        with c1:
            m = (df.groupby("AnnoMese")
                   .agg(Ore=("OreTotali", "sum"), Lezioni=("Data", "size"))
                   .reset_index().sort_values("AnnoMese"))
            fig = go.Figure()
            fig.add_bar(x=m["AnnoMese"], y=m["Ore"], name="Ore erogate",
                        marker=dict(color=PALETTE[0], line=dict(width=0)),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{x}</b><br>%{y:.1f} ore<extra></extra>")
            if len(m) >= 4:
                fig.add_scatter(x=m["AnnoMese"], y=m["Ore"].rolling(3, min_periods=1).mean(),
                                mode="lines", name="media mobile 3 mesi",
                                line=dict(color=PALETTE[1], width=2),
                                hovertemplate="media 3 mesi: %{y:.1f} h<extra></extra>")
            style(fig, 400, "Ore di lezione per mese")
            fig.update_layout(hovermode="x unified", showlegend=False)
            fig.update_yaxes(title="ore")
            st.plotly_chart(fig, width='stretch')

        with c2:
            a = (df.groupby("Allievo")["OreTotali"].sum()
                   .sort_values(ascending=True).reset_index())
            fig = go.Figure(go.Bar(
                x=a["OreTotali"], y=a["Allievo"], orientation="h",
                marker=dict(color=[cmap[x] for x in a["Allievo"]], line=dict(width=0)),
                marker_cornerradius=4,
                text=a["OreTotali"].map(lambda v: f"{v:.1f}h"),
                textposition="outside", textfont=dict(color=INK2, size=11),
                hovertemplate="<b>%{y}</b><br>%{x:.1f} ore<extra></extra>"))
            style(fig, max(400, 34 * len(a)), "Ore per allievo", showlegend=False)
            fig.update_xaxes(title="ore", showgrid=True,
                             range=[0, float(a["OreTotali"].max()) * 1.18])
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, width='stretch')

        c3, c4 = st.columns(2)

        with c3:
            mt = df.groupby("Materia")["OreTotali"].sum().sort_values(ascending=False).reset_index()
            fig = px.treemap(mt, path=["Materia"], values="OreTotali",
                             color="OreTotali", color_continuous_scale=SEQ)
            fig.update_traces(
                marker=dict(cornerradius=6, line=dict(width=2, color="rgba(255,255,255,.9)")),
                texttemplate="<b>%{label}</b><br>%{value:.1f} h",
                hovertemplate="<b>%{label}</b><br>%{value:.1f} ore<extra></extra>")
            style(fig, 400, "Ore per materia", showlegend=False)
            fig.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig, width='stretch')

        with c4:
            hm = df.dropna(subset=["OraStart"]).copy()
            if not hm.empty:
                piv = (hm.pivot_table(index="GiornoIdx", columns="OraStart",
                                      values="Data", aggfunc="size").fillna(0))
                piv = piv.reindex(range(7), fill_value=0)
                ore_range = list(range(int(min(piv.columns)), int(max(piv.columns)) + 1))
                piv = piv.reindex(columns=ore_range, fill_value=0)
                fig = go.Figure(go.Heatmap(
                    z=piv.values, x=[f"{int(h):02d}:00" for h in piv.columns], y=GIORNI_IT,
                    colorscale=SEQ, xgap=2, ygap=2, showscale=False,
                    hovertemplate="<b>%{y} %{x}</b><br>%{z:.0f} lezioni<extra></extra>"))
                style(fig, 400, "Quando fai lezione (giorno × ora di inizio)")
                st.plotly_chart(fig, width='stretch')

        # calendario attività
        st.markdown("##### Attività giornaliera")
        day = df.groupby(df["Data"].dt.date)["OreTotali"].sum().reset_index()
        day.columns = ["Data", "Ore"]
        fig = go.Figure(go.Bar(
            x=day["Data"], y=day["Ore"],
            marker=dict(color=PALETTE[0], line=dict(width=0)), marker_cornerradius=3,
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>%{y:.1f} ore<extra></extra>"))
        style(fig, 260, showlegend=False)
        fig.update_yaxes(title="ore")
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08))
        st.plotly_chart(fig, width='stretch')

    # ---------------- Allievi ----------------
    with RIP[1]:
        oggi = pd.Timestamp(DIARIO.oggi())
        sched = (df.groupby("Allievo").agg(
            Lezioni=("Data", "size"),
            Ore=("OreTotali", "sum"),
            OreLezione=("OreLezione", "sum"),
            OrePrep=("OrePrep", "sum"),
            DurataMedia=("OreLezione", "mean"),
            Prima=("Data", "min"),
            Ultima=("Data", "max"),
            Incassato=("Incassato", "sum"),
            DaIncassare=("DaIncassare", "sum"),
        ).reset_index())
        sched["GiorniDaUltima"] = (oggi - sched["Ultima"]).dt.days
        sched = sched.sort_values("Ore", ascending=False)

        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("##### Scheda riepilogativa per allievo")
            show = sched.copy()
            show["Prima"] = show["Prima"].dt.strftime("%d/%m/%Y")
            show["Ultima"] = show["Ultima"].dt.strftime("%d/%m/%Y")
            st.dataframe(
                show[["Allievo", "Lezioni", "Ore", "DurataMedia", "Prima", "Ultima",
                      "GiorniDaUltima", "Incassato", "DaIncassare"]],
                width='stretch', hide_index=True,
                column_config={
                    "Ore": st.column_config.NumberColumn("Ore totali", format="%.1f h"),
                    "DurataMedia": st.column_config.NumberColumn("Durata media", format="%.2f h"),
                    "GiorniDaUltima": st.column_config.NumberColumn("Giorni da ultima", format="%d gg"),
                    "Incassato": st.column_config.NumberColumn("Incassato", format="€ %.0f"),
                    "DaIncassare": st.column_config.NumberColumn("Da incassare", format="€ %.0f"),
                })
            scarica_tabella(show, "scheda_allievi", "⬇️ Scarica la scheda")

        with c2:
            s = sched.sort_values("GiorniDaUltima")
            colori = [C_OK if g <= 14 else (C_WARN if g <= 45 else C_BAD) for g in s["GiorniDaUltima"]]
            fig = go.Figure(go.Bar(
                x=s["GiorniDaUltima"], y=s["Allievo"], orientation="h",
                marker=dict(color=colori, line=dict(width=0)), marker_cornerradius=4,
                text=s["GiorniDaUltima"].map(lambda v: f"{v} gg"),
                textposition="outside", textfont=dict(color=INK2, size=11),
                hovertemplate="<b>%{y}</b><br>%{x} giorni dall'ultima lezione<extra></extra>"))
            style(fig, max(380, 34 * len(s)), "Giorni dall'ultima lezione", showlegend=False)
            fig.update_yaxes(showgrid=False)
            fig.update_xaxes(range=[0, float(s["GiorniDaUltima"].max()) * 1.20])
            st.plotly_chart(fig, width='stretch')
            st.caption("🟢 attivo (≤14 gg) · 🟡 da ricontattare (≤45 gg) · 🔴 fermo (>45 gg)")

        c3, c4 = st.columns(2)
        with c3:
            fig = go.Figure()
            for a in sched["Allievo"]:
                d = df[df["Allievo"] == a]["OreLezione"]
                fig.add_box(y=d, name=a, marker_color=cmap[a], boxpoints="outliers",
                            line=dict(width=2), fillcolor="rgba(0,0,0,0)")
            style(fig, 400, "Distribuzione durata delle lezioni", showlegend=False)
            fig.update_yaxes(title="ore per lezione")
            st.plotly_chart(fig, width='stretch')

        with c4:
            pv = sched[["Allievo", "OreLezione", "OrePrep"]].melt(
                id_vars="Allievo", value_vars=["OreLezione", "OrePrep"],
                var_name="Tipo", value_name="OreVal").rename(columns={"OreVal": "Ore"})
            pv["Tipo"] = pv["Tipo"].map({"OreLezione": "Lezione", "OrePrep": "Preparazione"})
            fig = px.bar(pv, x="Allievo", y="Ore", color="Tipo",
                         color_discrete_map={"Lezione": PALETTE[0], "Preparazione": PALETTE[3]})
            fig.update_traces(marker_line=dict(width=2, color="rgba(255,255,255,.9)"),
                              marker_cornerradius=4,
                              hovertemplate="<b>%{x}</b><br>%{y:.1f} ore<extra></extra>")
            style(fig, 400, "Ore di lezione vs ore di preparazione")
            fig.update_yaxes(title="ore")
            st.plotly_chart(fig, width='stretch')

        st.markdown("##### Cadenza delle lezioni nel tempo")
        fig = go.Figure()
        for a in sorted(df["Allievo"].unique()):
            d = df[df["Allievo"] == a]
            fig.add_scatter(x=d["Data"], y=[a] * len(d), mode="markers", name=a,
                            marker=dict(size=9, color=cmap[a],
                                        line=dict(width=2, color="rgba(255,255,255,.9)")),
                            customdata=np.stack([d["Materia"], d["OreTotali"]], axis=-1),
                            hovertemplate="<b>%{y}</b> · %{x|%d/%m/%Y}<br>"
                                          "%{customdata[0]} · %{customdata[1]:.1f} h<extra></extra>")
        style(fig, max(320, 32 * df["Allievo"].nunique()), showlegend=False)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, width='stretch')

    # ---------------- Economia ----------------
    with RIP[2]:
        c1, c2 = st.columns([3, 2])
        with c1:
            inc = (df.groupby("AnnoMese")
                     .agg(Incassato=("Incassato", "sum"), DaIncassare=("DaIncassare", "sum"))
                     .reset_index().sort_values("AnnoMese"))
            inc["Cumulato"] = inc["Incassato"].cumsum()
            fig = go.Figure()
            fig.add_bar(x=inc["AnnoMese"], y=inc["Incassato"], name="Incassato",
                        marker=dict(color=PALETTE[2], line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{x}</b><br>€ %{y:,.0f} incassati<extra></extra>")
            fig.add_bar(x=inc["AnnoMese"], y=inc["DaIncassare"], name="Da incassare",
                        marker=dict(color=PALETTE[7], line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{x}</b><br>€ %{y:,.0f} da incassare<extra></extra>")
            style(fig, 400, "Incassi per mese")
            fig.update_layout(barmode="stack", hovermode="x unified")
            fig.update_yaxes(title="€")
            st.plotly_chart(fig, width='stretch')

        with c2:
            fig = go.Figure(go.Scatter(
                x=inc["AnnoMese"], y=inc["Cumulato"], mode="lines+markers",
                line=dict(color=PALETTE[0], width=2, shape="spline"),
                marker=dict(size=8, line=dict(width=2, color="rgba(255,255,255,.9)")),
                fill="tozeroy", fillcolor="rgba(42,120,214,.12)",
                hovertemplate="<b>%{x}</b><br>€ %{y:,.0f} cumulati<extra></extra>"))
            style(fig, 400, "Incassato cumulato", showlegend=False)
            fig.update_yaxes(title="€")
            st.plotly_chart(fig, width='stretch')

        c3, c4 = st.columns(2)
        with c3:
            pa = (df.groupby("Allievo")
                    .agg(Incassato=("Incassato", "sum"), DaIncassare=("DaIncassare", "sum"))
                    .reset_index().sort_values("Incassato"))
            fig = go.Figure()
            fig.add_bar(y=pa["Allievo"], x=pa["Incassato"], orientation="h", name="Incassato",
                        marker=dict(color=PALETTE[2], line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f} incassati<extra></extra>")
            fig.add_bar(y=pa["Allievo"], x=pa["DaIncassare"], orientation="h", name="Da incassare",
                        marker=dict(color=PALETTE[7], line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f} da incassare<extra></extra>")
            style(fig, max(400, 36 * len(pa)), "Situazione pagamenti per allievo")
            fig.update_layout(barmode="stack")
            fig.update_xaxes(title="€")
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, width='stretch')

        with c4:
            # aggregazione esplicita: groupby.apply cambiava forma a seconda dei dati
            g_tar = df[df["Incassato"] > 0].groupby("Allievo")
            tar = pd.DataFrame({
                "TariffaOraria": (g_tar["Incassato"].sum() / g_tar["OreLezione"].sum())
                .replace([np.inf, -np.inf], np.nan)
            }).reset_index()
            tar = tar[tar["TariffaOraria"] > 0].sort_values("TariffaOraria")
            if not tar.empty:
                fig = go.Figure(go.Bar(
                    x=tar["TariffaOraria"], y=tar["Allievo"], orientation="h",
                    marker=dict(color=[cmap[x] for x in tar["Allievo"]], line=dict(width=0)),
                    marker_cornerradius=4,
                    text=tar["TariffaOraria"].map(lambda v: f"€ {v:.1f}"),
                    textposition="outside", textfont=dict(color=INK2, size=11),
                    hovertemplate="<b>%{y}</b><br>€ %{x:.2f} / ora<extra></extra>"))
                style(fig, max(400, 36 * len(tar)), "Tariffa oraria effettiva", showlegend=False)
                fig.add_vline(x=tariffa, line=dict(color=INK2, width=2, dash="dot"),
                              annotation_text=f"media € {tariffa:.1f}", annotation_position="top")
                fig.update_xaxes(title="€ / ora",
                                 range=[0, float(tar["TariffaOraria"].max()) * 1.22])
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Nessun pagamento registrato nel periodo selezionato.")

        sosp = df[(~df["Pagato"]) & (df["Importo"] > 0)]
        if not sosp.empty:
            st.markdown("##### ⚠️ Lezioni da incassare")
            t = sosp[["Data", "Allievo", "Materia", "Argomento", "OreTotali", "Importo"]].copy()
            t["Data"] = t["Data"].dt.strftime("%d/%m/%Y")
            st.dataframe(t, width='stretch', hide_index=True,
                         column_config={"OreTotali": st.column_config.NumberColumn("Ore", format="%.1f h"),
                                        "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f")})
            scarica_tabella(t, "lezioni_da_incassare")

    # ---------------- Didattica ----------------
    with RIP[3]:
        c1, c2 = st.columns(2)
        with c1:
            comp = df.groupby("Allievo").agg(
                Assegnati=("CompitoAssegnato", lambda s: int(s.fillna(False).sum())),
                Superati=("CompitoSuperato", lambda s: int(s.fillna(False).sum())),
            ).reset_index().sort_values("Assegnati")
            comp = comp[comp["Assegnati"] > 0]
            if not comp.empty:
                fig = go.Figure()
                fig.add_bar(y=comp["Allievo"], x=comp["Assegnati"], orientation="h", name="Assegnati",
                            marker=dict(color=PALETTE[0], line=dict(width=0)), marker_cornerradius=4,
                            hovertemplate="<b>%{y}</b><br>%{x} compiti assegnati<extra></extra>")
                fig.add_bar(y=comp["Allievo"], x=comp["Superati"], orientation="h", name="Superati",
                            marker=dict(color=PALETTE[2], line=dict(width=0)), marker_cornerradius=4,
                            hovertemplate="<b>%{y}</b><br>%{x} compiti superati<extra></extra>")
                style(fig, max(380, 42 * len(comp)), "Compiti assegnati e superati")
                fig.update_layout(barmode="group", bargap=0.3)
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Nessun compito assegnato registrato nel periodo.")

        with c2:
            vt = df.dropna(subset=["Voto"])
            if not vt.empty:
                fig = go.Figure()
                for a in sorted(vt["Allievo"].unique()):
                    d = vt[vt["Allievo"] == a].sort_values("Data")
                    fig.add_scatter(x=d["Data"], y=d["Voto"], mode="lines+markers", name=a,
                                    line=dict(color=cmap[a], width=2, shape="spline"),
                                    marker=dict(size=9, line=dict(width=2, color="rgba(255,255,255,.9)")),
                                    hovertemplate="<b>%{fullData.name}</b><br>"
                                                  "%{x|%d/%m/%Y} · voto %{y}<extra></extra>")
                style(fig, 400, "Andamento dei voti")
                fig.update_yaxes(title="voto")
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("Nessun voto registrato nel periodo selezionato.")

        c3, c4 = st.columns([2, 1])
        with c3:
            st.markdown("##### Argomenti trattati più di frequente")
            arg = (df[df["Argomento"] != ""]["Argomento"]
                   .str.strip().str.capitalize().value_counts().head(15)
                   .sort_values().reset_index())
            arg.columns = ["Argomento", "Volte"]
            if not arg.empty:
                fig = go.Figure(go.Bar(
                    x=arg["Volte"], y=arg["Argomento"].str.slice(0, 60), orientation="h",
                    marker=dict(color=PALETTE[6], line=dict(width=0)), marker_cornerradius=4,
                    hovertemplate="<b>%{y}</b><br>%{x} lezioni<extra></extra>"))
                style(fig, max(400, 30 * len(arg)), showlegend=False)
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, width='stretch')

        with c4:
            st.markdown("##### Copertura materiali")
            tot = len(df)
            voci = [
                ("Materiale fornito", int(df["MaterialeFornito"].fillna(False).sum()), PALETTE[0]),
                ("Dispense", int((df["LinkDispense"] != "").sum()), PALETTE[2]),
                ("Registrazione", int((df["LinkRegistrazione"] != "").sum()), PALETTE[3]),
                ("Mappe concettuali", int((df["LinkMappe"] != "").sum()), PALETTE[6]),
                ("Compito assegnato", int(df["CompitoAssegnato"].fillna(False).sum()), PALETTE[4]),
            ]
            for nome, val, col in voci:
                pct = val / tot if tot else 0
                st.markdown(f"**{nome}** — {val} su {tot} ({pct:.0%})")
                st.progress(min(pct, 1.0))

    # ---------------- Dettaglio ----------------
    with RIP[4]:
        st.markdown("##### Tutte le lezioni")
        q = st.text_input("Cerca (argomento, note, allievo, materia)", "")
        d = df.copy()
        if q:
            mask = (d["Argomento"].str.contains(q, case=False, na=False)
                    | d["Note"].str.contains(q, case=False, na=False)
                    | d["Allievo"].str.contains(q, case=False, na=False)
                    | d["Materia"].str.contains(q, case=False, na=False))
            d = d[mask]

        tab = d[["Data", "Allievo", "Materia", "NumeroLezione", "OraInizio", "OraFine",
                 "OreLezione", "OrePrep", "OreTotali", "Argomento", "CompitoAssegnato",
                 "CompitoSuperato", "Voto", "Pagato", "Importo", "DataPagamento", "Note",
                 "LinkRiunione", "LinkRegistrazione", "LinkDispense", "LinkMappe"]].copy()
        tab["Data"] = tab["Data"].dt.strftime("%d/%m/%Y")
        tab["DataPagamento"] = pd.to_datetime(tab["DataPagamento"], errors="coerce").dt.strftime("%d/%m/%Y")
        tab["OraInizio"] = tab["OraInizio"].map(lambda t: t.strftime("%H:%M") if t else "")
        tab["OraFine"] = tab["OraFine"].map(lambda t: t.strftime("%H:%M") if t else "")

        st.dataframe(
            tab, width='stretch', hide_index=True, height=520,
            column_config={
                "NumeroLezione": st.column_config.NumberColumn("N°", format="%.0f"),
                "OreLezione": st.column_config.NumberColumn("Ore lez.", format="%.2f"),
                "OrePrep": st.column_config.NumberColumn("Ore prep.", format="%.2f"),
                "OreTotali": st.column_config.NumberColumn("Ore tot.", format="%.2f"),
                "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f"),
                "Pagato": st.column_config.CheckboxColumn("Pagato"),
                "CompitoAssegnato": st.column_config.CheckboxColumn("Compito"),
                "CompitoSuperato": st.column_config.CheckboxColumn("Superato"),
                "LinkRiunione": st.column_config.LinkColumn("Riunione", display_text="apri"),
                "LinkRegistrazione": st.column_config.LinkColumn("Registrazione", display_text="apri"),
                "LinkDispense": st.column_config.LinkColumn("Dispense", display_text="apri"),
                "LinkMappe": st.column_config.LinkColumn("Mappe", display_text="apri"),
            })

        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Scarica CSV", tab.to_csv(index=False).encode("utf-8-sig"),
                           f"registro_lezioni_{DIARIO.oggi():%Y%m%d}.csv", "text/csv",
                           width='stretch')
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            tab.to_excel(w, index=False, sheet_name="Lezioni")
        c2.download_button("⬇️ Scarica Excel", buf.getvalue(),
                           f"registro_lezioni_{DIARIO.oggi():%Y%m%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width='stretch')

# TAB 3 - PROGETTI E CONSULENZE
# ============================================================================
with TAB[3]:
    pannello_riepilogo('progetti')
    if dfp.empty:
        st.warning(prog_msg or "Nessun progetto trovato nei file indicati.")
        st.markdown("##### Cosa ha visto l'app")
        if not prog_payload:
            st.error("Nella cartella indicata non è stato trovato nessun file "
                     "leggibile (Google Sheets o .xlsx).")
            st.markdown(
                "Controlla tre cose, in quest'ordine:\n\n"
                "1. che `drive_folder_id_progetti` nei Secrets sia l'ID della "
                "cartella **che contiene** il file *Gestione Progetti*, non del file;\n"
                "2. che quella cartella sia condivisa come **Visualizzatore** con "
                "`dashboard-registri@registri-lezioni.iam.gserviceaccount.com`;\n"
                "3. che il file non stia dentro una sottocartella: l'app legge solo "
                "il primo livello.")
        else:
            st.caption(f"{len(prog_payload)} file letti dalla cartella:")
            st.code("\n".join(n for n, _ in prog_payload), language="text")
            st.markdown(
                "I file ci sono ma nessuna riga di progetto è stata riconosciuta. "
                "L'app cerca una scheda chiamata **Progetti** (o che contenga quella "
                "parola); se non la trova prova a riconoscerla dall'intestazione, "
                "che deve avere *Nome Progetto* nella colonna B. "
                "Nella tabella qui sotto vedi scheda per scheda cosa è successo.")
        if not diag_p.empty:
            st.markdown("##### Diagnostica, scheda per scheda")
            st.dataframe(diag_p, width='stretch', hide_index=True)
    else:
        # ---------------- filtri ----------------
        f1, f2 = st.columns([1, 1])
        stati = [s for s in STATI_ORDINE if s in set(dfp["Stato"])]
        stati += [s for s in sorted(dfp["Stato"].unique()) if s not in stati]
        sel_s = f1.multiselect("Stato", stati, default=[], placeholder="Tutti gli stati")
        clienti = sorted(dfp["Cliente"].unique())
        sel_c = f2.multiselect("Cliente", clienti, default=[], placeholder="Tutti i clienti")

        p = dfp.copy()
        if sel_s:
            p = p[p["Stato"].isin(sel_s)]
        if sel_c:
            p = p[p["Cliente"].isin(sel_c)]
        if p.empty:
            st.warning("Nessun progetto corrisponde ai filtri.")
            st.stop()
        m = dfm[dfm["id"].isin(p["id"])] if not dfm.empty else pd.DataFrame()

        # ---------------- KPI ----------------
        val = p["Costo"].sum()
        inc = p["Incassato"].sum()
        res = p["Residuo"].sum()
        marg = p["Margine"].sum()
        ore = p["Ore"].sum()
        go_medio = marg / ore if ore else 0
        n_corso = int((~p["Stato"].str.lower().str.contains("complet")).sum())

        kp = st.columns(6)
        kp[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
        kp[0].metric("Progetti", len(p))
        kp[1].metric("Ancora aperti", n_corso)
        kp[2].metric("Valore concordato", f"€ {val:,.0f}".replace(",", "."))
        kp[3].metric("Incassato", f"€ {inc:,.0f}".replace(",", "."))
        kp[4].metric("Margine", f"€ {marg:,.0f}".replace(",", "."))
        kp[5].metric("Guadagno orario", f"€ {go_medio:,.1f}".replace(",", "."))

        if res > 0:
            st.caption(f"💶 Residuo da incassare su questi progetti: "
                       f"**€ {res:,.0f}**".replace(",", "."))

        st.divider()

        # ---------------- timeline (Gantt) ----------------
        g = p.dropna(subset=["Inizio", "Consegna"]).copy()
        g = g[g["Consegna"] >= g["Inizio"]]
        if not g.empty:
            g = g.sort_values("Inizio")
            # i progetti di un solo giorno sarebbero invisibili: larghezza minima
            uguali = g["Consegna"] == g["Inizio"]
            g.loc[uguali, "Consegna"] = g.loc[uguali, "Inizio"] + pd.Timedelta(days=1)
            g["Etichetta"] = g["Etichetta"].str.slice(0, 38)
            fig = px.timeline(g, x_start="Inizio", x_end="Consegna", y="Etichetta",
                              color="Stato", color_discrete_map=STATO_COLORE,
                              custom_data=["Cliente", "Costo", "Ore", "Stato"])
            fig.update_traces(
                marker_line=dict(width=2, color="rgba(255,255,255,.9)"),
                hovertemplate="<b>%{y}</b><br>%{customdata[3]} · %{customdata[0]}"
                              "<br>%{x|%d/%m/%Y}<br>€ %{customdata[1]:,.0f} · "
                              "%{customdata[2]:.0f} ore<extra></extra>")
            fig.update_yaxes(autorange="reversed", showgrid=False, title=None)
            style(fig, max(380, 30 * len(g) + 90), "Durata dei progetti")
            # la linea "oggi" solo se cade dentro il periodo mostrato
            oggi = pd.Timestamp(DIARIO.oggi())
            if g["Inizio"].min() <= oggi <= g["Consegna"].max():
                # su un asse temporale plotly vuole i millisecondi, non una data
                fig.add_vline(x=oggi.timestamp() * 1000,
                              line=dict(color=INK2, width=2, dash="dot"),
                              annotation_text="oggi", annotation_position="top")
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Nessun progetto ha sia data di inizio sia data di consegna valide.")

        c1, c2 = st.columns([3, 2])

        # ---------------- economia per progetto ----------------
        with c1:
            e = p.sort_values("Costo").copy()
            fig = go.Figure()
            fig.add_bar(y=e["Etichetta"], x=e["Spesa"], orientation="h", name="Spese vive",
                        marker=dict(color=PALETTE[1],
                                    line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f} di spese<extra></extra>")
            fig.add_bar(y=e["Etichetta"], x=e["Margine"], orientation="h", name="Margine",
                        marker=dict(color=PALETTE[2],
                                    line=dict(width=2, color="rgba(255,255,255,.9)")),
                        marker_cornerradius=4,
                        hovertemplate="<b>%{y}</b><br>€ %{x:,.0f} di margine<extra></extra>")
            style(fig, max(400, 34 * len(e)), "Come si compone il valore di ogni progetto")
            fig.update_layout(barmode="stack")
            fig.update_xaxes(title="€")
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, width='stretch')

        # ---------------- guadagno orario ----------------
        with c2:
            q = p.dropna(subset=["GuadagnoOrario"]).sort_values("GuadagnoOrario")
            if not q.empty:
                col = [C_BAD if v < 5 else (C_WARN if v < 10 else C_OK)
                       for v in q["GuadagnoOrario"]]
                fig = go.Figure(go.Bar(
                    x=q["GuadagnoOrario"], y=q["Etichetta"], orientation="h",
                    marker=dict(color=col, line=dict(width=0)), marker_cornerradius=4,
                    text=q["GuadagnoOrario"].map(lambda v: f"€ {v:.1f}"),
                    textposition="outside", textfont=dict(color=INK2, size=11),
                    customdata=np.stack([q["Margine"], q["Ore"]], axis=-1),
                    hovertemplate="<b>%{y}</b><br>€ %{x:.2f} l'ora<br>"
                                  "€ %{customdata[0]:,.0f} su %{customdata[1]:.0f} ore"
                                  "<extra></extra>"))
                style(fig, max(400, 34 * len(q)), "Quanto rende un'ora di lavoro",
                      showlegend=False)
                fig.update_xaxes(title="€ / ora",
                                 range=[min(0, float(q["GuadagnoOrario"].min()) * 1.2),
                                        float(q["GuadagnoOrario"].max()) * 1.25])
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, width='stretch')
                st.caption("🔴 sotto 5 €/ora · 🟡 fra 5 e 10 · 🟢 sopra 10")

        c3, c4 = st.columns(2)

        # ---------------- incassi nel tempo ----------------
        with c3:
            mm = m.dropna(subset=["Data"]).copy() if not m.empty else pd.DataFrame()
            if not mm.empty:
                mm["AnnoMese"] = mm["Data"].dt.to_period("M").astype(str)
                s = mm.groupby("AnnoMese")["Importo"].sum().reset_index().sort_values("AnnoMese")
                s["Cumulato"] = s["Importo"].cumsum()
                fig = go.Figure()
                fig.add_bar(x=s["AnnoMese"], y=s["Importo"], name="movimenti del mese",
                            marker=dict(color=np.where(s["Importo"] >= 0, PALETTE[2], PALETTE[7]),
                                        line=dict(width=0)),
                            marker_cornerradius=4,
                            hovertemplate="<b>%{x}</b><br>€ %{y:,.0f}<extra></extra>")
                fig.add_scatter(x=s["AnnoMese"], y=s["Cumulato"], mode="lines+markers",
                                name="cumulato",
                                line=dict(color=PALETTE[0], width=2),
                                marker=dict(size=8, line=dict(width=2,
                                            color="rgba(255,255,255,.9)")),
                                hovertemplate="cumulato: € %{y:,.0f}<extra></extra>")
                style(fig, 400, "Incassi dei progetti nel tempo")
                fig.update_layout(hovermode="x unified")
                fig.update_yaxes(title="€")
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("I movimenti di pagamento non hanno date utilizzabili.")

        # ---------------- clienti ----------------
        with c4:
            cl = (p.groupby("Cliente")
                    .agg(Valore=("Costo", "sum"), Progetti=("id", "size"),
                         Ore=("Ore", "sum"))
                    .reset_index().sort_values("Valore"))
            fig = go.Figure(go.Bar(
                x=cl["Valore"], y=cl["Cliente"], orientation="h",
                marker=dict(color=PALETTE[0], line=dict(width=0)), marker_cornerradius=4,
                text=cl["Valore"].map(lambda v: f"€ {v:,.0f}".replace(",", ".")),
                textposition="outside", textfont=dict(color=INK2, size=11),
                customdata=np.stack([cl["Progetti"], cl["Ore"]], axis=-1),
                hovertemplate="<b>%{y}</b><br>€ %{x:,.0f}<br>"
                              "%{customdata[0]} progetti · %{customdata[1]:.0f} ore"
                              "<extra></extra>"))
            style(fig, max(400, 34 * len(cl)), "Valore per cliente", showlegend=False)
            fig.update_xaxes(title="€", range=[0, float(cl["Valore"].max()) * 1.25])
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(fig, width='stretch')

        # ---------------- stato di avanzamento ----------------
        st.markdown("##### Stato dei progetti")
        sc = p["Stato"].value_counts().reindex(
            [s for s in stati if s in set(p["Stato"])]).dropna().reset_index()
        sc.columns = ["Stato", "Progetti"]
        fig = go.Figure(go.Bar(
            x=sc["Stato"], y=sc["Progetti"],
            marker=dict(color=[STATO_COLORE.get(s, PALETTE[0]) for s in sc["Stato"]],
                        line=dict(width=0)),
            marker_cornerradius=4,
            text=sc["Progetti"], textposition="outside", textfont=dict(color=INK2),
            hovertemplate="<b>%{x}</b><br>%{y} progetti<extra></extra>"))
        style(fig, 300, showlegend=False)
        fig.update_yaxes(title="progetti")
        st.plotly_chart(fig, width='stretch')

        # ---------------- tabella ----------------
        st.markdown("##### Elenco progetti")
        t = p[["Progetto", "Cliente", "Stato", "Attività", "Inizio", "Consegna",
               "Costo", "Spesa", "Margine", "Incassato", "Residuo", "Ore",
               "GuadagnoOrario", "Descrizione", "Note", "Link"]].copy()
        t["Inizio"] = t["Inizio"].dt.strftime("%d/%m/%Y")
        t["Consegna"] = t["Consegna"].dt.strftime("%d/%m/%Y")
        st.dataframe(
            t.sort_values("Consegna", ascending=False), width='stretch',
            hide_index=True, height=420,
            column_config={
                "Costo": st.column_config.NumberColumn("Valore", format="€ %.0f"),
                "Spesa": st.column_config.NumberColumn("Spese", format="€ %.0f"),
                "Margine": st.column_config.NumberColumn("Margine", format="€ %.0f"),
                "Incassato": st.column_config.NumberColumn("Incassato", format="€ %.0f"),
                "Residuo": st.column_config.NumberColumn("Residuo", format="€ %.0f"),
                "Ore": st.column_config.NumberColumn("Ore", format="%.0f"),
                "GuadagnoOrario": st.column_config.NumberColumn("€/ora", format="€ %.2f"),
                "Link": st.column_config.LinkColumn("Cartella", display_text="apri"),
            })
        scarica_tabella(t, "progetti", "⬇️ Scarica i progetti")

        # ---------------- movimenti ----------------
        if not m.empty:
            with st.expander("Movimenti di pagamento (acconti, saldi, storni)"):
                mv = m.merge(p[["id", "Etichetta"]], on="id", how="left")
                mv = mv[["Data", "Etichetta", "Tipo", "Importo", "Testo"]].copy()
                mv["Data"] = mv["Data"].dt.strftime("%d/%m/%Y")
                st.dataframe(mv.rename(columns={"Etichetta": "Progetto",
                                                "Testo": "Come da registro"}),
                             width='stretch', hide_index=True,
                             column_config={"Importo": st.column_config.NumberColumn(
                                 "Importo", format="€ %.2f")})
                scarica_tabella(mv, "movimenti_pagamento")

        # ---------------- piano contatti ----------------
        if not contatti.empty:
            with st.expander("📇 Piano contatti dei progetti"):
                st.dataframe(contatti, width='stretch', hide_index=True, height=340)
                scarica_tabella(contatti, "piano_contatti")
                if not esiti.empty:
                    st.markdown("**Registro esiti dei contatti**")
                    st.dataframe(esiti, width='stretch', hide_index=True)
                    scarica_tabella(esiti, "esiti_contatti")

        if not diag_p.empty:
            with st.expander("🔍 Diagnostica lettura progetti"):
                st.dataframe(diag_p, width='stretch', hide_index=True)


# ============================================================================
# TAB 6 - CANCELLERIA  (generatore di documenti e materiale intestato)
# ============================================================================
with TAB[6]:
    pannello_riepilogo('cancelleria')
    if not CANCELLERIA_OK:
        st.error("Il modulo della cancelleria non è disponibile: "
                 f"{CANCELLERIA_ERRORE}")
        st.caption("Controlla che nella repo ci siano `cancelleria.py` e `marchi.json`, "
                   "e che `reportlab` sia elencato in `requirements.txt`.")
        st.stop()

    mitt_def, marchi = CANC.carica_marchi()
    nomi_marchi = [m["nome"] for m in marchi]

    st.markdown("##### 1 · Marchio e identità")
    c1, c2, c3 = st.columns([2, 2, 1])
    scelto = c1.selectbox("Marchio", nomi_marchi, index=0)
    base = next(m for m in marchi if m["nome"] == scelto)
    sottotitolo = c2.text_input("Sottotitolo", value=base.get("sottotitolo", ""))
    col_marchio = c3.color_picker("Colore", value=base.get("colore", "#1baf7a"))

    # ---- logo -------------------------------------------------------------
    def logo_del_marchio(nome_file: str):
        """Cerca il logo del marchio prima nella cartella Drive, poi in loghi/.
        Restituisce (bytes, provenienza) oppure (None, "")."""
        nome_file = (nome_file or "").strip()
        if not nome_file:
            return None, ""
        id_loghi = (secret("drive_folder_id_loghi", "") or "").strip()
        if id_loghi:
            try:
                for f in drive_list_qualsiasi(id_loghi, st.session_state.cache_key):
                    if f["name"].strip().lower() == nome_file.lower():
                        return (drive_file_bytes(f["id"], st.session_state.cache_key),
                                f"cartella Drive dei loghi · {f['name']}")
            except Exception:
                pass
        locale = CANC.logo_locale(nome_file)
        if locale:
            return locale, f"repository · loghi/{nome_file}"
        return None, ""

    logo_bytes = None
    logo_marchio, provenienza = logo_del_marchio(base.get("logo", ""))
    lc1, lc2 = st.columns([2, 3])
    opzioni_logo = ["Carica un file", "Scegli dalla cartella Drive", "Nessuno"]
    if logo_marchio:
        opzioni_logo.insert(0, "Quello del marchio")
    sorgente_logo = lc1.radio("Logo", opzioni_logo, horizontal=False, key="src_logo")
    if sorgente_logo == "Quello del marchio":
        logo_bytes = logo_marchio
        lc2.success(f"Caricato da solo dalla {provenienza}")
    elif not logo_marchio and base.get("logo"):
        lc2.caption(f"Per avere il logo automatico, carica un file chiamato "
                    f"**{base['logo']}** nella cartella Drive dei loghi.")
    if sorgente_logo == "Carica un file":
        up_logo = lc2.file_uploader("PNG, JPG o SVG", type=["png", "jpg", "jpeg", "svg"],
                                    key="logo_up")
        if up_logo:
            logo_bytes = up_logo.getvalue()
    elif sorgente_logo == "Scegli dalla cartella Drive":
        id_loghi = (secret("drive_folder_id_loghi", "") or "").strip()
        if not id_loghi:
            lc2.info("Aggiungi `drive_folder_id_loghi` nei Secrets con l'ID della "
                     "cartella Drive dei loghi, e condividila col service account.")
        else:
            try:
                immagini = [f for f in drive_list_qualsiasi(id_loghi, st.session_state.cache_key)
                            if f["name"].lower().endswith((".png", ".jpg", ".jpeg", ".svg"))]
                if immagini:
                    nomi = [f["name"] for f in immagini]
                    pick = lc2.selectbox("File del logo", nomi)
                    logo_bytes = drive_file_bytes(
                        next(f for f in immagini if f["name"] == pick)["id"],
                        st.session_state.cache_key)
                else:
                    lc2.warning("Nessuna immagine trovata in quella cartella.")
            except Exception as e:
                lc2.error(f"Non riesco a leggere la cartella dei loghi: {e}")

    # ---- mittente ---------------------------------------------------------
    with st.expander("2 · I tuoi dati (compaiono su tutti i documenti)", expanded=False):
        m1, m2 = st.columns(2)
        mittente = {
            "ragione_sociale": m1.text_input("Nome o ragione sociale",
                                             mitt_def.get("ragione_sociale", "")),
            "cap_citta": m1.text_input("Indirizzo", mitt_def.get("cap_citta", "")),
            "email": m1.text_input("Email", mitt_def.get("email", "")),
            "telefono": m2.text_input("Telefono", mitt_def.get("telefono", "")),
            "piva_cf": m2.text_input("P.IVA / Codice fiscale", mitt_def.get("piva_cf", "")),
            "sito": m2.text_input("Sito", mitt_def.get("sito", "")),
        }
        mittente["link"] = st.text_input(
            "Link da stampare sui documenti e da codificare nel QR",
            value=base.get("link") or mitt_def.get("link", ""),
            help="Finisce nel piè di pagina e dentro il codice QR di biglietti, "
                 "volantini, etichette e tessera.")

    # ---- stile del documento ---------------------------------------------
    with st.expander("3 · Stile dei documenti", expanded=False):
        temi = list(CANC.STILI_PREDEFINITI.keys())
        s1, s2 = st.columns([1, 2])
        tema = s1.selectbox("Tema", temi, index=0)
        pre = CANC.STILI_PREDEFINITI[tema]
        s2.caption({
            "Elegante": "Titoli con grazie, maiuscoletto spaziato, filetto doppio, "
                        "molto respiro. Il più adatto a preventivi e accordi.",
            "Minimale": "Tutto lineare, un filetto sottile, piè di pagina ridotto "
                        "all'essenziale.",
            "Tecnico": "Banda di colore sul lato, testo compatto, più informazioni "
                       "nella stessa pagina. Per schede e documentazione.",
            "Classico": "Logo e intestazione centrati, carattere con grazie anche "
                        "nel testo. Formale, da lettera istituzionale.",
        }.get(tema, ""))

        st.markdown("**Vuoi cambiare qualcosa del tema?**")
        o1, o2, o3 = st.columns(3)
        v_logo = o1.selectbox("Posizione del logo", ["(come il tema)", "sinistra",
                                                     "centro"])
        v_filetto = o2.selectbox("Filetto sotto l'intestazione",
                                 ["(come il tema)", "sottile", "pieno", "doppio",
                                  "corto", "nessuno"])
        v_piede = o3.selectbox("Piè di pagina", ["(come il tema)", "completo",
                                                 "minimo"])
        p1, p2, p3 = st.columns(3)
        v_titoli = p1.selectbox("Carattere dei titoli",
                                ["(come il tema)", "Helvetica-Bold", "Times-Bold"])
        v_corpo = p2.selectbox("Carattere del testo",
                               ["(come il tema)", "Helvetica", "Times-Roman"])
        v_sp = p3.selectbox("Spaziatura", ["(come il tema)", "ampia", "normale",
                                           "compatta"])
        q1, q2, q3 = st.columns(3)
        v_maiusc = q1.checkbox("Nome in maiuscoletto spaziato",
                               value=pre.get("maiuscoletto", False))
        v_banda = q2.checkbox("Banda di colore sul lato",
                              value=pre.get("banda_laterale", False))
        v_pt = q3.slider("Dimensione del testo", 8.0, 12.0,
                         float(pre.get("corpo_pt", 9.5)), 0.5)

        def _o(valore):
            return None if valore == "(come il tema)" else valore

        stile = {"logo_posizione": _o(v_logo), "filetto": _o(v_filetto),
                 "piede": _o(v_piede), "font_titoli": _o(v_titoli),
                 "font_corpo": _o(v_corpo), "spaziatura": _o(v_sp),
                 "maiuscoletto": v_maiusc, "banda_laterale": v_banda,
                 "corpo_pt": v_pt}

    cfg = {"nome": scelto, "sottotitolo": sottotitolo, "colore": col_marchio,
           "mittente": mittente, "link": mittente.get("link", ""),
           "descrizione": base.get("descrizione", ""),
           "tema": tema, "stile": stile,
           "_logo": CANC._logo_oggetto(logo_bytes)}

    st.divider()
    st.markdown("##### 4 · Documento")

    TIPI = ["Carta intestata", "Biglietti da visita", "Tessera con QR",
            "Scheda progetto", "Volantino A5", "Etichette adesive",
            "Firma per la posta elettronica", "Preventivo", "Ricevuta",
            "Informativa privacy e contratto", "Accordo di riservatezza (NDA)",
            "Attestato di partecipazione"]
    tipo = st.selectbox("Tipo di documento", TIPI)

    # ---- precompilazione da progetti / allievi ----------------------------
    pre = {}
    if tipo in ("Preventivo", "Ricevuta", "Informativa privacy e contratto",
                "Accordo di riservatezza (NDA)") and not dfp.empty:
        etichette = ["— nessuno —"] + list(dfp["Etichetta"])
        sc = st.selectbox("Precompila dai progetti", etichette)
        if sc != "— nessuno —":
            r = dfp[dfp["Etichetta"] == sc].iloc[0]
            pre = {"cliente": r["Cliente"], "oggetto": r["Descrizione"] or r["Progetto"],
                   "importo": float(r["Costo"]), "progetto": r["Progetto"]}
    if tipo in ("Attestato di partecipazione", "Ricevuta") and not df.empty:
        el_all = ["— nessuno —"] + sorted(df["Allievo"].unique())
        sa = st.selectbox("Precompila dagli allievi", el_all)
        if sa != "— nessuno —":
            d = df[df["Allievo"] == sa]
            pre.update({
                "allievo": sa,
                "corso": d["Materia"].mode().iloc[0] if not d["Materia"].mode().empty else "",
                "ore": round(float(d["OreTotali"].sum()), 1),
                "periodo": f"{d['Data'].min():%B %Y} – {d['Data'].max():%B %Y}",
                "importo_allievo": float(d["Incassato"].sum()),
                "argomenti": ", ".join(
                    d[d["Argomento"] != ""]["Argomento"].drop_duplicates().head(6)),
            })

    def campi_destinatario(chiave, nome_default=""):
        d1, d2 = st.columns(2)
        return {
            "nome": d1.text_input("Destinatario", nome_default, key=f"n{chiave}"),
            "indirizzo": d1.text_input("Indirizzo", key=f"i{chiave}"),
            "citta": d2.text_input("CAP e città", key=f"c{chiave}"),
            "piva": d2.text_input("C.F. / P.IVA", key=f"p{chiave}"),
        }

    pdf_bytes, nome_file = None, "documento.pdf"

    # ------------------------------------------------------------------ 1
    if tipo == "Carta intestata":
        dest = campi_destinatario("ci", pre.get("cliente", ""))
        oggetto = st.text_input("Oggetto", pre.get("oggetto", "")[:90])
        corpo = st.text_area("Testo della lettera", height=240,
                             value="Gentile Signore,\n\n\n\nResto a disposizione per "
                                   "qualsiasi chiarimento.")
        if st.button("Genera la carta intestata", type="primary"):
            pdf_bytes = CANC.carta_intestata(cfg, oggetto, corpo, dest)
            nome_file = "carta_intestata.pdf"

    # ------------------------------------------------------------------ 2
    elif tipo == "Biglietti da visita":
        ruolo = st.text_input("Ruolo o qualifica",
                              "Ingegnere industriale · Formatore tecnico")
        crocini = st.checkbox("Segni di taglio agli angoli", value=True)
        st.caption("Dieci biglietti 85×55 mm su foglio A4. Stampa a dimensione reale, "
                   "senza adattamento alla pagina.")
        if st.button("Genera i biglietti", type="primary"):
            pdf_bytes = CANC.biglietti_da_visita(cfg, ruolo, crocini)
            nome_file = "biglietti_da_visita.pdf"

    # ------------------------------------------------------------------ 2b
    elif tipo == "Tessera con QR":
        invito = st.text_input("Frase di invito",
                               "Inquadra il codice per tutti i miei progetti")
        st.caption("Due facciate da 55×85 mm: fronte con il QR, retro con i recapiti. "
                   "Stampa fronte-retro e plastificala se la porti in tasca.")
        if not cfg.get("link"):
            st.warning("Senza link il QR non viene stampato: compilalo in "
                       "«I tuoi dati».")
        if st.button("Genera la tessera", type="primary"):
            pdf_bytes = CANC.tessera_qr(cfg, invito)
            nome_file = "tessera_qr.pdf"

    # ------------------------------------------------------------------ 2c
    elif tipo == "Scheda progetto":
        sp1, sp2 = st.columns([2, 1])
        titolo_p = sp1.text_input("Titolo", scelto)
        stato_p = sp2.text_input("Stato", "")
        descr_p = st.text_area("Descrizione", base.get("descrizione", ""), height=120)
        punti_txt = st.text_area("Punti chiave (uno per riga)", height=110,
                                 placeholder="Cosa risolve\nCome funziona, a grandi linee\nA chi serve")
        cerco = st.text_input("Cosa cerco",
                              "Un partner industriale per la sperimentazione sul campo.")
        nota_nda = st.checkbox("Aggiungi la nota sulla riservatezza", value=True,
                               help="Consigliata per i progetti pre-brevetto: dice che "
                                    "i dettagli tecnici si condividono solo con un NDA.")
        if st.button("Genera la scheda", type="primary"):
            pdf_bytes = CANC.scheda_progetto(cfg, titolo_p, descr_p,
                                             punti_txt.split("\n"), stato_p, cerco,
                                             nota_nda)
            nome_file = f"scheda_{titolo_p.replace(' ', '_')}.pdf"

    # ------------------------------------------------------------------ 2d
    elif tipo == "Volantino A5":
        v1, v2 = st.columns([2, 1])
        titolo_v = v1.text_input("Titolo grande", scelto)
        due = v2.checkbox("Due per foglio A4", value=True)
        claim = st.text_input("Frase di richiamo", base.get("sottotitolo", ""))
        testo_v = st.text_area("Testo", base.get("descrizione", ""), height=180)
        if st.button("Genera il volantino", type="primary"):
            pdf_bytes = CANC.volantino(cfg, titolo_v, claim, testo_v, due)
            nome_file = f"volantino_{titolo_v.replace(' ', '_')}.pdf"

    # ------------------------------------------------------------------ 2e
    elif tipo == "Etichette adesive":
        e1, e2 = st.columns([3, 1])
        r1 = e1.text_input("Prima riga", scelto)
        quante = e2.number_input("Quante", 1, 24, 24)
        r2 = st.text_input("Seconda riga", mittente.get("cap_citta", ""))
        r3 = st.text_input("Terza riga", mittente.get("email", ""))
        qr_et = st.checkbox("Includi il QR", value=bool(cfg.get("link")))
        st.caption("Ventiquattro etichette 70×37 mm su A4: è il formato dei fogli "
                   "adesivi comuni. Stampa a dimensione reale.")
        if st.button("Genera le etichette", type="primary"):
            pdf_bytes = CANC.etichette(cfg, r1, r2, r3, qr_et, int(quante))
            nome_file = "etichette.pdf"

    # ------------------------------------------------------------------ 2f
    elif tipo == "Firma per la posta elettronica":
        ruolo_f = st.text_input("Ruolo", "Ingegnere industriale · Formatore tecnico")
        claim_f = st.text_input("Invito finale", "Guarda i miei progetti")
        if st.button("Genera la firma", type="primary"):
            html_firma, testo_firma = CANC.firma_email(cfg, ruolo_f, claim_f)
            st.session_state["firma_html"] = html_firma
            st.session_state["firma_testo"] = testo_firma
        if st.session_state.get("firma_html"):
            st.markdown("**Anteprima**")
            st.markdown(st.session_state["firma_html"], unsafe_allow_html=True)
            st.markdown("**Codice HTML** — copialo e incollalo nella firma del tuo "
                        "client di posta (Gmail: Impostazioni → Firma).")
            st.code(st.session_state["firma_html"], language="html")
            st.download_button("⬇️ Scarica la firma in HTML",
                               st.session_state["firma_html"].encode("utf-8"),
                               "firma_email.html", "text/html")
            with st.expander("Versione in solo testo"):
                st.code(st.session_state["firma_testo"], language="text")

    # ------------------------------------------------------------------ 3
    elif tipo == "Preventivo":
        p1, p2, p3 = st.columns(3)
        numero = p1.text_input("Numero", f"{DIARIO.oggi():%Y}-001")
        validita = p2.number_input("Validità (giorni)", 1, 365, 30)
        iva = p3.number_input("Aliquota IVA %", 0.0, 30.0, 0.0, step=1.0)
        dest = campi_destinatario("pv", pre.get("cliente", ""))
        st.markdown("**Voci del preventivo**")
        voci_base = pd.DataFrame([
            {"descrizione": pre.get("oggetto", ""), "quantita": 1.0,
             "prezzo": pre.get("importo", 0.0)},
            {"descrizione": "", "quantita": 1.0, "prezzo": 0.0},
        ])
        voci = st.data_editor(voci_base, num_rows="dynamic", width='stretch',
                              key="voci_prev",
                              column_config={
                                  "descrizione": st.column_config.TextColumn("Descrizione", width="large"),
                                  "quantita": st.column_config.NumberColumn("Q.tà", format="%.2f"),
                                  "prezzo": st.column_config.NumberColumn("Prezzo unitario", format="%.2f")})
        n1, n2 = st.columns(2)
        note = n1.text_area("Note", height=110)
        condizioni = n2.text_area("Condizioni", height=110,
                                  value="Acconto del 30% alla conferma, saldo alla consegna.")
        if st.button("Genera il preventivo", type="primary"):
            righe = [v for v in voci.to_dict("records") if str(v.get("descrizione", "")).strip()]
            if not righe:
                st.warning("Inserisci almeno una voce con la descrizione.")
            else:
                pdf_bytes = CANC.preventivo(cfg, numero, dest, righe, int(validita),
                                            note, float(iva), condizioni)
                nome_file = f"preventivo_{numero}.pdf"

    # ------------------------------------------------------------------ 4
    elif tipo == "Ricevuta":
        r1, r2, r3 = st.columns(3)
        numero = r1.text_input("Numero", f"{DIARIO.oggi():%m}/{DIARIO.oggi():%Y}")
        importo = r2.number_input("Importo €", 0.0, 1e6,
                                  float(pre.get("importo_allievo") or pre.get("importo") or 0.0),
                                  step=10.0)
        data_pag = r3.date_input("Data", DIARIO.oggi())
        modalita = st.selectbox("Modalità di pagamento",
                                ["Bonifico bancario", "PayPal", "Contanti",
                                 "Satispay", "Carta di credito"])
        dest = campi_destinatario("rc", pre.get("allievo") or pre.get("cliente", ""))
        descr_def = ""
        if pre.get("allievo"):
            descr_def = (f"Lezioni private di {pre.get('corso', '')}\n"
                         f"{pre.get('periodo', '')} — {pre.get('ore', '')} ore")
        elif pre.get("oggetto"):
            descr_def = pre["oggetto"]
        descrizione = st.text_area("Causale", value=descr_def, height=100)
        bollo = st.checkbox("Ricorda la marca da bollo sopra 77,47 €", value=True)
        if st.button("Genera la ricevuta", type="primary"):
            pdf_bytes = CANC.ricevuta(cfg, numero, dest, descrizione, importo,
                                      modalita, data_pag, bollo)
            nome_file = f"ricevuta_{numero.replace('/', '-')}.pdf"

    # ------------------------------------------------------------------ 5
    elif tipo == "Informativa privacy e contratto":
        dest = campi_destinatario("pr", pre.get("cliente", ""))
        oggetto = st.text_area("Oggetto della fornitura", pre.get("oggetto", ""), height=100)
        q1, q2, q3 = st.columns(3)
        corrispettivo = q1.number_input("Corrispettivo €", 0.0, 1e6,
                                        float(pre.get("importo", 0.0)), step=10.0)
        acconto = q2.number_input("Acconto € (0 = nessuno)", 0.0, 1e6, 0.0, step=10.0)
        modalita = q3.selectbox("Pagamento a mezzo",
                                ["bonifico bancario", "PayPal", "contanti", "Satispay"])
        termine = st.text_input("Termine di consegna",
                                "Entro 30 giorni dalla sottoscrizione.")
        con_contratto = st.checkbox("Includi anche le condizioni contrattuali", value=True)
        if acconto and corrispettivo and acconto > corrispettivo:
            st.warning("L'acconto è superiore al corrispettivo: controlla gli importi.")
        if st.button("Genera il documento", type="primary"):
            pdf_bytes = CANC.informativa_privacy(cfg, dest, oggetto, corrispettivo,
                                                 acconto or "", modalita, termine,
                                                 con_contratto)
            nome_file = "informativa_privacy_contratto.pdf"

    # ------------------------------------------------------------------ 6
    elif tipo == "Accordo di riservatezza (NDA)":
        dest = campi_destinatario("nd", pre.get("cliente", ""))
        oggetto = st.text_area(
            "Oggetto dei contatti riservati",
            value=(f"la valutazione congiunta del progetto {pre.get('progetto', '')}"
                   if pre.get("progetto") else
                   "la valutazione congiunta di una possibile collaborazione"),
            height=80)
        a1, a2, a3 = st.columns(3)
        durata = a1.number_input("Durata (anni)", 1, 20, 5)
        reciproco = a2.selectbox("Tipo", ["Reciproco", "Unilaterale"]) == "Reciproco"
        foro = a3.text_input("Foro competente", "Salerno")
        penale = st.number_input("Penale € (0 = nessuna clausola)", 0.0, 1e7, 0.0,
                                 step=500.0)
        st.info("Questo è un modello, non un parere legale. Per i progetti con "
                "brevetto depositato o con più co-titolari fallo verificare da un "
                "legale prima di firmarlo.")
        if st.button("Genera l'accordo", type="primary"):
            pdf_bytes = CANC.accordo_riservatezza(cfg, dest, oggetto, int(durata),
                                                  reciproco, penale or "", foro)
            nome_file = "accordo_riservatezza.pdf"

    # ------------------------------------------------------------------ 7
    else:
        t1, t2 = st.columns(2)
        allievo = t1.text_input("Nome dell'allievo", pre.get("allievo", ""))
        corso = t2.text_input("Titolo del corso", pre.get("corso", ""))
        u1, u2 = st.columns(2)
        ore = u1.number_input("Ore totali", 0.0, 1000.0,
                              float(pre.get("ore", 0.0)), step=0.5)
        periodo = u2.text_input("Periodo", pre.get("periodo", ""))
        argomenti = st.text_area("Argomenti trattati", pre.get("argomenti", ""),
                                 height=80)
        if st.button("Genera l'attestato", type="primary"):
            if not allievo.strip():
                st.warning("Serve almeno il nome dell'allievo.")
            else:
                pdf_bytes = CANC.attestato(cfg, allievo, corso, ore, periodo, argomenti)
                nome_file = f"attestato_{allievo.replace(' ', '_')}.pdf"

    # ---- esito ------------------------------------------------------------
    if pdf_bytes:
        st.divider()
        st.markdown("##### Anteprima")
        st.caption("È il documento vero, pagina per pagina. Se qualcosa non ti "
                   "torna cambia i campi qui sopra e rigeneralo: il file lo "
                   "scarichi solo quando ti piace.")
        try:
            st.pdf(pdf_bytes, height=720)
        except Exception as e:
            st.info("L'anteprima non è disponibile: scarica il file per vederlo.")
            if "streamlit-pdf" in str(e) or "pdf" in str(e).lower():
                st.caption("Manca la libreria dell'anteprima. Nel file "
                           "`requirements.txt` la riga di streamlit deve essere "
                           "`streamlit[pdf]>=1.50`, poi Reboot dell'app.")
        st.download_button("⬇️ Scarica il PDF", pdf_bytes, nome_file,
                           "application/pdf", type="primary", width='stretch')


# ============================================================================
# TAB 7 - STUDIO  (percorsi, prontuari, strumenti AI, prompt pronti)
# ============================================================================
with TAB[7]:
    pannello_riepilogo('studio')

    @st.cache_data(show_spinner=False)
    def carica_studio(_versione: float):
        import json as _json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "studio.json"), encoding="utf-8") as f:
                return _json.load(f)
        except Exception as e:
            return {"_errore": str(e)}

    S = carica_studio(_mtime("studio.json"))
    if "_errore" in S:
        st.error(f"Non riesco a leggere `studio.json`: {S['_errore']}")
        st.caption("Controlla che il file sia nella repo accanto ad app.py e che il "
                   "JSON sia valido (una virgola di troppo basta a invalidarlo).")
        st.stop()

    # «Leggimelo» sta subito dopo l'Officina; SEZ tiene i numeri di prima,
    # così le sezioni qui sotto restano SEZ[0]…SEZ[5] come sempre
    _SEZ = st.tabs(["🧪 Officina", "📖 Leggimelo", "🧠 Memoria", "🎯 Percorsi", "🧰 Strumenti",
                    "📋 Prontuari", "🤖 Assistente", "💬 Prompt pronti"], key="studio_sezione")
    SEZ = [_SEZ[0]] + list(_SEZ[3:])

    # ================= MEMORIA ===========================================
    # Il rito quotidiano dei cinque passi, il ripasso, l'allenamento lampo.
    with _SEZ[2]:
        try:
            import memoria as MEMORIA
            MEMORIA.mostra(CTX)
        except Exception as _e_mem:
            st.error(f"La parte Memoria ha avuto un problema: {_e_mem}")

    # ================= LEGGIMELO =========================================
    # Foto, PDF, link o testo incollato → lettura ad alta voce, audio da
    # scaricare, mappe, infografiche, flashcard. Tutto in lettura.py.
    with _SEZ[1]:
        try:
            import lettura as LETTURA
            LETTURA.mostra(CTX)
        except Exception as _e_lt:
            st.error(f"Leggimelo ha avuto un problema: {_e_lt}")

    # ================= OFFICINA ==========================================
    # I tuoi strumenti, quelli che hai costruito tu. Vivono su un indirizzo
    # loro (microfono, webcam e memoria del browser non funzionano dentro
    # Quadro), quindi qui ci sono le porte d'ingresso, non le app incastrate.
    with SEZ[0]:
        OFF = S.get("officina", {})
        st.caption(OFF.get("intro", "L'officina degli strumenti: quelli che hai "
                                    "costruito tu, raccolti in un posto solo."))

        strumenti_off = OFF.get("strumenti", [])
        for riga in range(0, len(strumenti_off), 2):
            cols = st.columns(2)
            for col, t in zip(cols, strumenti_off[riga:riga + 2]):
                with col:
                    with st.container(border=True):
                        st.markdown(f"#### {t.get('icona', '🔧')} {t['nome']}")
                        if t.get("sottotitolo"):
                            st.caption(t["sottotitolo"])
                        if t.get("cosa_ci_fai"):
                            st.markdown(t["cosa_ci_fai"])

                        url = (t.get("url") or "").strip()
                        if url:
                            st.link_button(f"Apri {t['nome']} ↗", url,
                                           width='stretch', type="primary")
                        else:
                            st.info("Manca l'indirizzo: aggiungilo in `studio.json`, "
                                    f"voce **{t['nome']}**, campo `url`.")

                        # sezioni interne (p.es. «Scienza» dentro Inchiostro)
                        sezioni = t.get("sezioni", [])
                        if sezioni:
                            st.markdown("**Dentro ci trovi**")
                            for sz in sezioni:
                                u = (sz.get("url") or "").strip() or url
                                c1, c2 = st.columns([3, 1])
                                c1.markdown(f"**{sz['nome']}** — {sz.get('nota', '')}")
                                if u:
                                    c2.link_button("Vai", u, width='stretch')

        # ---------------- altri collegamenti -------------------------------
        link = [l for l in S.get("link_rapidi", []) if (l.get("url") or "").strip()]
        mancanti = [l["nome"] for l in S.get("link_rapidi", [])
                    if not (l.get("url") or "").strip()]
        if link:
            st.markdown("##### Altri collegamenti")
            cols = st.columns(min(4, len(link)))
            for col, l in zip(cols, link):
                col.link_button(f"{l.get('icona', '🔗')} {l['nome']}", l["url"],
                                width='stretch', help=l.get("nota", ""))
        if mancanti:
            st.caption("Senza indirizzo in `studio.json`, quindi non mostrati: "
                       + ", ".join(mancanti))

    # ================= PERCORSI ==========================================
    with SEZ[1]:
        percorsi = S.get("percorsi", [])
        nomi = [p["argomento"] for p in percorsi]
        scelto_p = st.radio("Argomento", nomi, horizontal=True,
                            label_visibility="collapsed")
        p = next(x for x in percorsi if x["argomento"] == scelto_p)

        st.markdown(f"### {p.get('icona', '')} {p['argomento']}")
        st.caption(f"**{p.get('livello', '')}**")
        st.markdown(p.get("dove_sono", ""))

        if p.get("serve_prima"):
            st.markdown(f"**Cosa serve per cominciare** — {p['serve_prima']}")
        if p.get("primo_risultato"):
            st.success(f"**Il primo risultato** — {p['primo_risultato']}")
        if p.get("prossimo_passo"):
            st.info(f"**Prossimo passo** — {p['prossimo_passo']}")

        # ---- a che punto sei: le spunte si salvano nel diario ---------------
        # Le tappe spuntate in questo giro restano anche in sessione: così la
        # pagina non deve ricaricarsi per aggiornare la barra, e soprattutto
        # non rischia di riscrivere la stessa tappa all'infinito se la
        # scrittura sull'archivio tarda o fallisce.
        appena = st.session_state.setdefault("tappe_appena", set())
        fatte = DIARIO.tappe_fatte(DIA, p["argomento"]) | {
            n for (a, n) in appena if a == p["argomento"]}
        tutte_tappe = [t for l in p.get("livelli", []) for t in l.get("tappe", [])]
        if tutte_tappe:
            quante = len([t for t in tutte_tappe if t in fatte])
            st.progress(quante / len(tutte_tappe),
                        text=f"{quante} tappe su {len(tutte_tappe)} "
                             f"({quante / len(tutte_tappe) * 100:.0f}%)")

        if p.get("fonti"):
            st.markdown("##### Su cosa studiare davvero")
            st.caption("Non sono link generici: sono le fonti su cui studia chi "
                       "fa questo mestiere. Aprine una e stacci dentro.")
            for riga_f in range(0, len(p["fonti"]), 2):
                cf = st.columns(2)
                for col, f in zip(cf, p["fonti"][riga_f:riga_f + 2]):
                    with col:
                        st.markdown(f"**{f['nome']}**")
                        st.caption(f.get("nota", ""))
                        st.link_button("Apri ↗", f["url"], width='stretch')

        livelli = p.get("livelli", [])
        if livelli:
            st.markdown("")
            LT = st.tabs([f"{i+1} · {l['nome']}" for i, l in enumerate(livelli)])
            for i_liv, (scheda, l) in enumerate(zip(LT, livelli)):
                with scheda:
                    if l.get("traguardo"):
                        st.markdown(f"**Dove arrivi** — {l['traguardo']}")
                    c1, c2 = st.columns([3, 2])
                    with c1:
                        st.markdown("###### Le tappe — spunta quelle che hai fatto")
                        for i, t in enumerate(l.get("tappe", []), 1):
                            chiave_t = f"tappa_{p['argomento']}_{i_liv}_{i}"
                            era = t in fatte
                            ora = st.checkbox(f"**{i}.** {t}", value=era,
                                              key=chiave_t)
                            if ora and not era:
                                diario_scrivi(DIARIO.riga(
                                    "tappa", p["argomento"], "Studio", 0, None, t))
                                appena.add((p["argomento"], t))
                                st.toast(f"Tappa segnata: {t}")
                    with c2:
                        st.markdown("###### Esercizi")
                        for e in l.get("esercizi", []):
                            st.markdown(f"- {e}")

        if p.get("errori_tipici"):
            st.markdown("##### Errori che fanno tutti, a ogni livello")
            for e in p["errori_tipici"]:
                st.markdown(f"- {e}")
        if p.get("come_so_di_aver_capito"):
            st.markdown(f"> **Come capisci di averlo imparato** — "
                        f"{p['come_so_di_aver_capito']}")

    # ================= PRONTUARI =========================================
    with SEZ[3]:
        prontuari = S.get("prontuari", [])
        cerca = st.text_input("Cerca fra tutti i comandi",
                              placeholder="per esempio: rinomina, groupby, GPIO, JOIN")

        trovati = 0
        for pr in prontuari:
            voci = pr.get("voci", [])
            if cerca:
                q = cerca.lower()
                voci = [v for v in voci
                        if q in v.get("comando", "").lower()
                        or q in v.get("cosa_fa", "").lower()]
            if not voci:
                continue
            trovati += len(voci)
            with st.expander(f"{pr.get('icona', '')} {pr['titolo']}  ·  "
                             f"{len(voci)} voci", expanded=bool(cerca)):
                for v in voci:
                    st.code(v["comando"], language="text")
                    st.caption(v.get("cosa_fa", ""))
        if cerca and trovati == 0:
            st.warning("Nessun comando corrisponde. Prova con una parola più corta.")

        st.divider()
        righe_tutte = []
        for pr in prontuari:
            for v in pr.get("voci", []):
                righe_tutte.append({"Prontuario": pr["titolo"],
                                    "Comando": v.get("comando", ""),
                                    "Cosa fa": v.get("cosa_fa", "")})
        tab_pront = pd.DataFrame(righe_tutte)
        d1, d2 = st.columns(2)

        buf_x = io.BytesIO()
        with pd.ExcelWriter(buf_x, engine="openpyxl") as w:
            tab_pront.to_excel(w, index=False, sheet_name="Tutti i comandi")
            for pr in prontuari:
                nome_sc = re.sub(r"[\\/*?:\[\]]", "", pr["titolo"].split("—")[0].strip())[:30]
                pd.DataFrame(pr.get("voci", [])).rename(
                    columns={"comando": "Comando", "cosa_fa": "Cosa fa"}
                ).to_excel(w, index=False, sheet_name=nome_sc or "Foglio")
        d1.download_button("⬇️ Scarica tutti i prontuari in Excel", buf_x.getvalue(),
                           f"prontuari_{DIARIO.oggi():%Y%m%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument."
                           "spreadsheetml.sheet", width='stretch')
        d2.download_button("⬇️ Scarica in CSV",
                           tab_pront.to_csv(index=False).encode("utf-8-sig"),
                           f"prontuari_{DIARIO.oggi():%Y%m%d}.csv", "text/csv",
                           width='stretch')
        st.caption(f"{len(tab_pront)} comandi in {len(prontuari)} prontuari. "
                   "Nel file Excel trovi un foglio per prontuario più uno con tutto "
                   "insieme. Per aggiungerne, modifica `studio.json`.")

    # ================= ASSISTENTE IA =====================================
    with SEZ[4]:
        MODELLO_DEF = S.get("ai", {}).get("modello", "gemini-3.8-flash")

        chiave = (secret("google_api_key", "") or "").strip()
        da_secrets = bool(chiave)
        if not da_secrets:
            chiave = st.session_state.get("chiave_ai", "")

        with st.expander("⚙️ Collegamento all'intelligenza artificiale",
                         expanded=not bool(chiave)):
            if da_secrets:
                st.success("Chiave configurata nei Secrets dell'app: non devi fare "
                           "niente.")
            else:
                st.markdown(
                    "Serve una chiave gratuita di **Google AI Studio**. "
                    "La prendi da [aistudio.google.com/apikey]"
                    "(https://aistudio.google.com/apikey) in due minuti: accedi, "
                    "clicca *Create API key*, copia la stringa che comincia per `AIza`.")
                k = st.text_input("Incolla qui la chiave", type="password",
                                  value=chiave,
                                  help="Resta solo in questa sessione del browser e "
                                       "sparisce quando chiudi la pagina.")
                if k:
                    st.session_state["chiave_ai"] = k.strip()
                    chiave = k.strip()
                st.caption("Per non doverla reinserire ogni volta, mettila nei "
                           "Secrets dell'app come `google_api_key = \"AIza...\"`.")

            # la chiave dipende dal valore predefinito: se cambia studio.json,
            # il campo riparte dal nuovo valore invece di tenere quello vecchio
            modello = st.text_input("Modello", MODELLO_DEF,
                                    key=f"modello_ai__{MODELLO_DEF}",
                                    help="Se ricevi un errore 404, il nome del "
                                         "modello non è più valido: usa il pulsante "
                                         "qui sotto e scegline uno dall'elenco.")
            if st.button("🔄 Ricarica i contenuti dai file"):
                st.cache_data.clear()
                for k in list(st.session_state.keys()):
                    if str(k).startswith("modello_ai__"):
                        del st.session_state[k]
                st.rerun()
            if chiave and st.button("Quali modelli posso usare?"):
                try:
                    r = requests.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        params={"key": chiave}, timeout=30)
                    if r.status_code == 200:
                        nomi = [m["name"].replace("models/", "")
                                for m in r.json().get("models", [])
                                if "generateContent" in m.get(
                                    "supportedGenerationMethods", [])]
                        st.code("\n".join(nomi) or "nessuno", language="text")
                        st.caption("Copia uno di questi nel campo «Modello», e "
                                   "scrivilo anche in `studio.json` per renderlo "
                                   "predefinito.")
                    else:
                        st.error(f"Errore {r.status_code}: {r.text[:300]}")
                except Exception as e:
                    st.error(f"Non riesco a contattare il servizio: {e}")

        if not chiave:
            st.info("Inserisci la chiave qui sopra per usare l'assistente. "
                    "Nel frattempo puoi usare i **Prompt pronti**: fanno le stesse "
                    "cose, copiandoli in Claude o in AI Studio.")
        else:
            COMPITI = {
                "Riassumi": (
                    "Riassumi il testo che segue per qualcuno che deve studiarlo. "
                    "Struttura: tre righe di sintesi generale, poi i concetti "
                    "chiave come elenco puntato, poi le tre cose da ricordare "
                    "assolutamente. Usa parole semplici, niente gergo inutile."),
                "Mappa concettuale": (
                    "Costruisci una mappa concettuale del testo che segue. "
                    "Rispondi SOLO con un diagramma Mermaid valido, senza testo "
                    "prima o dopo e senza i marcatori di blocco di codice. "
                    "Usa la sintassi 'graph TD'. Massimo 15 nodi. Le etichette dei "
                    "nodi vanno sempre fra virgolette doppie e non devono contenere "
                    "parentesi tonde."),
                "Domande di verifica": (
                    "Dal testo che segue ricava dieci domande di verifica di "
                    "difficoltà crescente. Scrivi prima tutte le domande numerate, "
                    "poi una riga di separazione, poi le risposte. Le domande devono "
                    "far ragionare, non far ripetere a memoria."),
                "Spiegamelo semplice": (
                    "Spiega l'argomento che segue a chi parte da zero. Prima un "
                    "paragone con qualcosa di quotidiano, poi la spiegazione "
                    "corretta, poi dove il paragone non regge. Chiudi con l'errore "
                    "che fanno quasi tutti i principianti su questo argomento."),
                "Schema dagli appunti": (
                    "Il testo che segue sono appunti presi di fretta, disordinati. "
                    "Riordinali in uno schema pulito: titoli, sottotitoli, elenchi. "
                    "Non aggiungere niente che non ci sia, ma segnala alla fine i "
                    "punti rimasti poco chiari o incompleti."),
                "Traccia di lezione": (
                    "Dal materiale che segue ricava una traccia di lezione da 60 "
                    "minuti: obiettivo, tre concetti chiave, un esempio pratico da "
                    "svolgere insieme, un esercizio da assegnare e tre domande di "
                    "verifica. Deve essere usabile così com'è."),
                "Scheda per Anki": (
                    "Dal testo che segue ricava venti schede domanda/risposta per il "
                    "ripasso con Anki. Una per riga, nel formato "
                    "'domanda; risposta' (punto e virgola come separatore). "
                    "Domande brevi, risposte di una riga. Nessun altro testo."),
            }

            c1, c2 = st.columns([1, 1])
            compito = c1.selectbox("Cosa devo fare", list(COMPITI.keys()))
            argomento = c2.text_input("Argomento (facoltativo)",
                                      placeholder="es. legge di Ohm, JOIN in SQL")

            up = st.file_uploader("Oppure carica un file di testo",
                                  type=["txt", "md"], key="up_studio")
            testo_pre = ""
            if up:
                try:
                    testo_pre = up.getvalue().decode("utf-8", errors="replace")
                except Exception:
                    testo_pre = ""
            testo = st.text_area("Testo di partenza", value=testo_pre, height=200,
                                 placeholder="Incolla qui gli appunti, il capitolo, "
                                             "il codice o la descrizione.")

            if st.button("Chiedi all'assistente", type="primary"):
                if not testo.strip() and not argomento.strip():
                    st.warning("Serve almeno un testo o un argomento.")
                else:
                    prompt = COMPITI[compito]
                    if argomento.strip():
                        prompt += f"\n\nArgomento: {argomento.strip()}"
                    if testo.strip():
                        prompt += f"\n\nTesto:\n{testo.strip()}"
                    prompt += ("\n\nRispondi in italiano, con parole semplici e "
                               "frasi brevi.")
                    import assistente as AI
                    stato = st.empty()
                    try:
                        with st.spinner("Sto pensando…"):
                            risposta = AI.chiedi(prompt, chiave, modello,
                                                 al_tentativo=lambda m: stato.info(m))
                        stato.empty()
                        st.session_state["ultima_risposta"] = risposta
                        st.session_state["ultimo_compito"] = compito
                    except AI.ErroreAI as e:
                        stato.empty()
                        st.error(e.messaggio)
                        if e.dettaglio:
                            st.caption(e.dettaglio)
                        if e.codice == 404:
                            st.caption("Apri le impostazioni qui sopra e usa "
                                       "«Quali modelli posso usare».")
                    except Exception as e:
                        stato.empty()
                        st.error(f"Non sono riuscito a contattare il servizio: {e}")

            risposta = st.session_state.get("ultima_risposta", "")
            if risposta:
                st.divider()
                if st.session_state.get("ultimo_compito") == "Mappa concettuale":
                    codice = (risposta.replace("```mermaid", "")
                              .replace("```", "").strip())
                    pagina_html(f"""
<div class="mermaid">{codice}</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad:true, theme:'neutral'}});</script>
<style>body{{margin:0;font-family:Helvetica,Arial,sans-serif;background:transparent}}
.mermaid{{display:flex;justify-content:center}}</style>
""", 560)
                    with st.expander("Il codice della mappa"):
                        st.code(codice, language="text")
                        st.caption("Puoi incollarlo su mermaid.live per modificarlo "
                                   "e scaricarlo come immagine.")
                else:
                    st.markdown(risposta)

                st.download_button("⬇️ Scarica il risultato", risposta.encode("utf-8"),
                                   f"studio_{DIARIO.oggi():%Y%m%d}.md",
                                   "text/markdown")

        st.divider()
        st.markdown("##### Altri strumenti con l'intelligenza artificiale")
        strumenti = S.get("strumenti_ai", [])
        for riga in range(0, len(strumenti), 2):
            cols = st.columns(2)
            for col, t in zip(cols, strumenti[riga:riga + 2]):
                with col:
                    st.markdown(f"**{t['nome']}**")
                    st.caption(t.get("a_cosa_serve", ""))
                    st.link_button("Apri", t["url"], width='stretch')

    # ================= STRUMENTI DI STUDIO ===============================
    with SEZ[2]:
        st.caption("Scelti per quello che serve davvero: prendere appunti che "
                   "ritrovi, fissare le cose in memoria, provare senza comprare "
                   "hardware.")
        for cat in S.get("strumenti_studio", []):
            st.markdown(f"##### {cat.get('icona', '')} {cat['categoria']}")
            for v in cat.get("voci", []):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{v['nome']}** — {v.get('nota', '')}")
                c2.link_button("Apri", v["url"], width='stretch')
            st.markdown("")

    # ================= PROMPT PRONTI =====================================
    with SEZ[5]:
        st.caption("Copia il testo, incollalo nell'assistente e sostituisci le parti "
                   "fra parentesi quadre. Sono scritti per farti **spiegare** le cose, "
                   "non per fartele risolvere.")
        for pr in S.get("prompt_pronti", []):
            with st.expander(f"💬 {pr['titolo']}"):
                if pr.get("quando"):
                    st.caption(f"*{pr['quando']}*")
                st.code(pr["testo"], language="text")


# ============================================================================
# TAB 8 - PARLA CHIARO  (allenamento alla comunicazione, nativo in Quadro)
# ============================================================================
with TAB[8]:
    pannello_riepilogo('parlachiaro')
    import parlachiaro as PC

    PCFG = _carica_json("parlachiaro.json", _mtime("parlachiaro.json"))
    if "_errore" in PCFG:
        st.error(f"Non riesco a leggere `parlachiaro.json`: {PCFG['_errore']}")
        st.stop()


    mostra_conferma()
    st.markdown("#### 🎙️ Parla chiaro")
    st.caption("Sei esercizi, la tua voce, e un'analisi che misura ritmo, "
               "riempitivi, grammatica e registro. Tutto quello che fai qui "
               "finisce nel diario insieme al resto.")

    PT = st.tabs(["🏋️ Allenamento", "🧭 Coach", "📇 Grammatica",
                  "📚 Lezioni", "🧍 Presenza", "📈 Andamento"])

    # ======================= ALLENAMENTO ====================================
    with PT[0]:
        blocchi = PCFG.get("blocchi", [])
        settimane = PCFG.get("settimane", {})
        scenari = PCFG.get("scenari", [])

        c1, c2 = st.columns([2, 3])
        sett = c1.selectbox("Settimana", list(settimane.keys()),
                            format_func=lambda k: f"{k} · "
                            + ["Fondamenta", "Chiarezza", "Voce manageriale",
                               "Padronanza"][int(k) - 1])
        c2.caption(settimane.get(sett, ""))

        scelto_b = st.radio(
            "Esercizio", range(len(blocchi)), horizontal=True,
            format_func=lambda i: f"{i+1}. {blocchi[i]['titolo']}",
            label_visibility="collapsed")
        B = blocchi[scelto_b]

        with st.container(border=True):
            b1, b2 = st.columns([4, 1])
            b1.markdown(f"##### {B['titolo']}")
            b2.metric("Durata", f"{B['minuti']} min")
            st.markdown(B["consegna"])

            if scelto_b >= 2 and scenari:
                if "pc_scenario" not in st.session_state:
                    st.session_state["pc_scenario"] = 0
                st.info(f"**Scenario** — {scenari[st.session_state['pc_scenario'] % len(scenari)]}")
                if st.button("🎲 Cambia scenario"):
                    st.session_state["pc_scenario"] += 1
                    st.rerun()

        st.markdown("##### Registra il tuo intervento")
        st.caption("Uno o due minuti bastano: sono più utili di dieci, e "
                   "l'analisi è più precisa. Se preferisci, puoi anche solo "
                   "scrivere il testo più sotto.")

        audio = st.audio_input("Premi per registrare")

        if audio is not None:
            dati_audio = audio.getvalue()
            st.caption(f"Registrazione di {len(dati_audio) / 1024 / 1024:.1f} MB.")
            if st.button("✍️ Trascrivi con l'intelligenza artificiale",
                         type="primary"):
                stato_t = st.empty()
                try:
                    with st.spinner("Sto ascoltando…"):
                        testo_t = PC.trascrivi(
                            dati_audio, chiave_ai(), modello_ai(),
                            getattr(audio, "type", None) or "audio/wav",
                            avvisa=lambda m: stato_t.info(m))
                    stato_t.empty()
                    # IMPORTANTE: si scrive direttamente nella chiave del
                    # riquadro, non in una variabile d'appoggio. Una casella di
                    # testo che ha una `key` si tiene il proprio contenuto e
                    # ignora il `value` ai ricaricamenti successivi: era questo
                    # il motivo per cui la trascrizione riusciva ma non
                    # compariva da nessuna parte.
                    st.session_state["__trascritto__"] = testo_t
                    conferma("Trascrizione pronta nel riquadro qui sotto")
                    st.rerun()
                except PC.ErroreTrascrizione as e:
                    stato_t.empty()
                    st.error(str(e))

        pulisci_se_segnata("pc_area")
        if "__trascritto__" in st.session_state:
            st.session_state["pc_area"] = st.session_state.pop("__trascritto__")
        testo = st.text_area(
            "Il testo del tuo intervento", height=180, key="pc_area",
            placeholder="Qui compare la trascrizione, oppure scrivi tu.")

        d1, d2 = st.columns(2)
        durata_s = d1.number_input("Quanti secondi è durato", 5, 3600, 60, step=5,
                                   help="Serve per calcolare le parole al minuto.")
        minuti_ses = d2.number_input("Minuti di allenamento da registrare",
                                     1, 180, B["minuti"], step=1)

        t1, t2 = st.columns(2)
        tens_pre = t1.slider("Tensione prima", 0, 10, 6)
        tens_post = t2.slider("Tensione dopo", 0, 10, 4)

        if testo.strip():
            R = PC.analizza(testo, durata_s, PCFG)

            st.divider()
            m = st.columns(5)
            m[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
            m[0].metric("Efficacia", f"{R['punteggio']}/100")
            m[1].metric("Parole al minuto", R["wpm"] or "—")
            m[2].metric("Parole per frase", R["media_frase"] or "—")
            m[3].metric("Riempitivi", R["riempitivi"])
            m[4].metric("Possibili errori", R["errori_grammatica"])

            r1, r2 = st.columns([2, 3])
            with r1:
                assi = PC.radar(R)
                figr = go.Figure()
                figr.add_scatterpolar(
                    r=list(assi.values()) + [list(assi.values())[0]],
                    theta=list(assi.keys()) + [list(assi.keys())[0]],
                    fill="toself", line=dict(color=VERDE, width=2),
                    fillcolor="rgba(27,175,122,.25)",
                    hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>")
                figr.update_polars(radialaxis=dict(range=[0, 100], showticklabels=False))
                st.plotly_chart(style(figr, 300, "Le cinque misure",
                                      showlegend=False), width='stretch')
                scarica_tabella(
                    pd.DataFrame({"Misura": list(assi.keys()),
                                  "Valore": list(assi.values())}),
                    "parlachiaro_misure", "⬇️ I dati del grafico")

            with r2:
                st.markdown("##### Cosa migliorare")
                for tipo_c, testo_c in R["consigli"]:
                    if tipo_c == "ok":
                        st.success(testo_c)
                    elif tipo_c == "errore":
                        st.warning(testo_c)
                    else:
                        st.markdown(f"• {testo_c}")

            nota_pc = st.text_input("Una nota per te (facoltativa)",
                                    key="pc_nota")
            if st.button("💾 Salva la sessione nel diario", type="primary",
                         width='stretch'):
                diario_scrivi([
                    DIARIO.riga("parlachiaro", f"{B['titolo']}", "ParlaChiaro",
                                minuti_ses, R["punteggio"],
                                f"[tensione {tens_pre}→{tens_post}] "
                                f"{nota_pc.strip()} :: {testo.strip()[:400]}"),
                    # la tensione in una riga sua: così finisce nei grafici
                    # invece di restare sepolta dentro il testo della nota
                    DIARIO.riga("tensione", B["titolo"], "ParlaChiaro",
                                0, tens_post - tens_pre,
                                f"prima {tens_pre} · dopo {tens_post}"),
                ])
                conferma(f"Allenamento salvato: {R['punteggio']}/100, "
                         f"{minuti_ses} minuti, tensione da {tens_pre} a "
                         f"{tens_post}")
                svuota_dopo("pc_area")
                st.rerun()
        else:
            st.info("Registra o scrivi qualcosa e qui compaiono i punteggi.")

    # ============================ COACH =====================================
    with PT[1]:
        domande = PCFG.get("domande_coach", [])
        st.caption("Sette domande in fila: sono quelle che ti farebbero in una "
                   "riunione vera. Rispondi a tutte e in fondo esce il "
                   "canovaccio del tuo intervento.")

        tema = st.text_input("Tema dell'intervento",
                             value="Presento la Business Review Campania")
        risposte = st.session_state.setdefault("pc_risposte", {})

        for i, dom in enumerate(domande):
            risposte[i] = st.text_area(f"**{i+1}.** {dom}",
                                       value=risposte.get(i, ""),
                                       height=70, key=f"pc_dom_{i}")

        piene = [r for r in risposte.values() if r.strip()]
        st.progress(len(piene) / len(domande),
                    text=f"{len(piene)} risposte su {len(domande)}")

        if len(piene) >= 4:
            st.markdown("##### Il tuo canovaccio")
            canovaccio = f"**{tema}**\n\n"
            for i, dom in enumerate(domande):
                if risposte.get(i, "").strip():
                    canovaccio += f"- *{dom}* {risposte[i].strip()}\n"
            st.markdown(canovaccio)

            # ---- e adesso? il canovaccio da solo non serve a niente -------
            st.markdown("##### E adesso")
            st.caption("Il canovaccio è la scaletta, non l'intervento. Da qui "
                       "si fanno tre cose, in ordine.")

            n1, n2, n3 = st.columns(3)
            if n1.button("🔍 Trova i punti deboli", width='stretch'):
                st.session_state["coach_azione"] = "critica"
            if n2.button("🎤 Fammi le domande cattive", width='stretch'):
                st.session_state["coach_azione"] = "domande"
            if n3.button("✂️ Riducilo a 90 secondi", width='stretch'):
                st.session_state["coach_azione"] = "taglia"

            azione = st.session_state.pop("coach_azione", None)
            if azione:
                istruzioni = {
                    "critica": "Fai le pulci a questo canovaccio: dimmi dove "
                               "un ascoltatore si perderebbe, dove manca un "
                               "dato, e dove sto dando per scontata una cosa "
                               "che non lo è. Massimo cinque punti, ognuno con "
                               "come lo sistemo.",
                    "domande": "Fammi le cinque domande più scomode che mi "
                               "farebbero in riunione su questo intervento, "
                               "quelle che non vorrei sentirmi fare. Per "
                               "ognuna, in una riga, come imposterei la "
                               "risposta — non la risposta, l'impostazione.",
                    "taglia": "Riscrivi questo intervento in modo che si legga "
                              "in novanta secondi ad alta voce, circa 200 "
                              "parole. Tieni il messaggio, il dato e la "
                              "richiesta; butta via il resto. Poi dimmi in una "
                              "riga cosa hai tolto e perché.",
                }[azione]
                stato_cv = st.empty()
                try:
                    with st.spinner("Sto leggendo il canovaccio…"):
                        esito = AI.chiedi(
                            "Sei un dirigente esperto che prepara interventi "
                            "per riunioni aziendali.\n\n"
                            f"Tema: {tema}\n\nIl canovaccio:\n{canovaccio}\n\n"
                            + istruzioni + "\nRispondi in italiano, frasi brevi.",
                            chiave_ai(), modello_ai(),
                            al_tentativo=lambda m: stato_cv.info(m))
                    stato_cv.empty()
                    st.session_state["coach_esito"] = (azione, esito)
                except AI.ErroreAI as e:
                    stato_cv.empty()
                    st.error(e.messaggio)
                    if e.dettaglio:
                        st.caption(e.dettaglio)

            if st.session_state.get("coach_esito"):
                quale, testo_e = st.session_state["coach_esito"]
                st.divider()
                st.markdown(testo_e)
                canovaccio = canovaccio + "\n\n---\n\n" + testo_e

            st.divider()
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ Scarica il canovaccio",
                               canovaccio.encode("utf-8"),
                               f"canovaccio_{DIARIO.oggi():%Y%m%d}.md",
                               "text/markdown", width='stretch')
            if d2.button("💾 Salva nel diario", type="primary", width='stretch'):
                diario_scrivi(DIARIO.riga(
                    "coach", tema[:60], "ParlaChiaro", 15, len(piene) * 100 // len(domande),
                    canovaccio[:1200]))
                conferma(f"Canovaccio salvato: «{tema[:40]}»")
                st.session_state.pop("coach_esito", None)
                st.rerun()

            passati_cv = DIA[DIA["Tipo"] == "coach"].sort_values(
                "Data", ascending=False)
            if not passati_cv.empty:
                with st.expander(f"I canovacci già preparati ({len(passati_cv)})"):
                    for _, r in passati_cv.head(12).iterrows():
                        st.markdown(f"**{r['Data']:%d/%m/%Y} · {r['Attivita']}**")
                        st.caption(r["Nota"][:400])
        else:
            st.caption("Completa almeno quattro risposte per vedere il canovaccio.")

    # ========================= GRAMMATICA ===================================
    with PT[2]:
        carte = PCFG.get("carte", [])
        st.caption("Diciotto carte. Leggi la frase sbagliata, dì ad alta voce "
                   "come la correggeresti, poi scopri la risposta. Quelle che "
                   "sbagli tornano più spesso.")

        # La memoria delle carte sta nel diario, non solo in questa sessione:
        # prima «La sapevo» si perdeva ricaricando la pagina. Vale l'ultimo
        # giudizio dato a ogni carta.
        memoria = st.session_state.setdefault("pc_memoria", {})
        storico_c = DIA[DIA["Tipo"] == "carta"].sort_values("Data")
        for _, rc in storico_c.iterrows():
            num = rc["Nota"].split(" · ")[0].strip()
            try:
                memoria[int(num)] = int(rc["Valore"]) if pd.notna(rc["Valore"]) else 0
            except (TypeError, ValueError):
                pass

        i_carta = st.session_state.setdefault("pc_carta", 0)
        C = carte[i_carta % len(carte)]

        giuste = sum(1 for v in memoria.values() if v >= 1)
        st.progress(min(1.0, giuste / len(carte)),
                    text=f"{giuste} carte su {len(carte)} le sai")
        da_rivedere = [c["id"] for c in carte if memoria.get(c["id"], -1) == 0]
        if da_rivedere:
            st.caption("Da ripassare: carte "
                       + ", ".join(str(n) for n in da_rivedere[:12]))

        with st.container(border=True):
            st.caption(f"Carta {C['id']} · {C['categoria']}")
            st.markdown(f"### ❌ {C['sbagliato']}")
            if st.session_state.get("pc_scopri") == C["id"]:
                st.markdown(f"### ✅ {C['giusto']}")
                st.info(C["regola"])
                g1, g2 = st.columns(2)
                if g1.button("👍 La sapevo", width='stretch', type="primary"):
                    memoria[C["id"]] = memoria.get(C["id"], 0) + 1
                    diario_scrivi(DIARIO.riga(
                        "carta", C["categoria"], "ParlaChiaro", 1, 1,
                        f"{C['id']} · {C['giusto'][:70]}"))
                    conferma(f"Carta {C['id']} segnata come saputa")
                    st.session_state["pc_carta"] = i_carta + 1
                    st.session_state.pop("pc_scopri", None)
                    st.rerun()
                if g2.button("👎 Da ripassare", width='stretch'):
                    memoria[C["id"]] = 0
                    diario_scrivi(DIARIO.riga(
                        "carta", C["categoria"], "ParlaChiaro", 1, 0,
                        f"{C['id']} · {C['giusto'][:70]}"))
                    conferma(f"Carta {C['id']} messa fra quelle da ripassare")
                    st.session_state["pc_carta"] = i_carta + 1
                    st.session_state.pop("pc_scopri", None)
                    st.rerun()
            else:
                if st.button("Mostra la risposta", type="primary"):
                    st.session_state["pc_scopri"] = C["id"]
                    st.rerun()

        with st.expander("Tutte le carte in un elenco"):
            tabc = pd.DataFrame([{"N°": c["id"], "Categoria": c["categoria"],
                                  "Si dice": c["giusto"],
                                  "Non si dice": c["sbagliato"],
                                  "Perché": c["regola"]} for c in carte])
            st.dataframe(tabc, width='stretch', hide_index=True)
            scarica_tabella(tabc, "carte_grammatica", "⬇️ Scarica le carte")

    # =========================== LEZIONI ====================================
    with PT[3]:
        lezioni = PCFG.get("lezioni", [])
        aree = []
        for l in lezioni:
            if l["area"] not in aree:
                aree.append(l["area"])
        for area in aree:
            st.markdown(f"##### {area}")
            for l in [x for x in lezioni if x["area"] == area]:
                with st.expander(l["titolo"]):
                    st.markdown(l["testo"])

    # ========================== PRESENZA ====================================
    with PT[4]:
        st.caption("Lo specchio di presenza con la webcam non c'è qui dentro: "
                   "Quadro gira su un server e non può guardare il video in "
                   "diretta. Per quello resta la versione vecchia, che trovi "
                   "fra i collegamenti nel tab Studio marcata «old». Quella "
                   "che segue è la lista da controllare davanti allo specchio "
                   "o alla webcam del computer.")
        voci_pres = PCFG.get("checklist_presenza", [])
        spuntate = [v for v in voci_pres
                    if st.session_state.get(f"pc_chk_{v[:20]}")]
        st.progress(len(spuntate) / len(voci_pres) if voci_pres else 0,
                    text=f"{len(spuntate)} punti su {len(voci_pres)}")
        for v in voci_pres:
            st.checkbox(v, key=f"pc_chk_{v[:20]}")

        st.caption("Le spunte sono un promemoria mentre provi davanti allo "
                   "specchio: si azzerano ogni volta. Quando hai finito, "
                   "registra il controllo qui sotto e finisce nel diario con "
                   "il punteggio, così vedi se migliora.")
        if st.button("💾 Registra il controllo di presenza", type="primary",
                     disabled=not spuntate):
            diario_scrivi(DIARIO.riga(
                "presenza", "Controllo presenza", "ParlaChiaro", 5,
                round(100 * len(spuntate) / len(voci_pres)),
                "; ".join(spuntate)))
            conferma(f"Controllo registrato: {len(spuntate)} punti su "
                     f"{len(voci_pres)}")
            for v in voci_pres:
                st.session_state[f"pc_chk_{v[:20]}"] = False
            st.rerun()

        pres = DIA[DIA["Tipo"] == "presenza"].sort_values("Data")
        if len(pres) >= 2:
            figpr = go.Figure()
            figpr.add_scatter(x=pres["Data"], y=pres["Valore"],
                              mode="lines+markers",
                              line=dict(color=PALETTE[0], width=2),
                              hovertemplate="%{x|%d/%m/%Y}<br>%{y:.0f}%<extra></extra>")
            figpr.update_yaxes(range=[0, 104], ticksuffix="%")
            st.plotly_chart(style(figpr, 260, "I tuoi controlli di presenza"),
                            width='stretch')

    # ========================== ANDAMENTO ===================================
    with PT[5]:
        PCD = DIA[DIA["Tipo"] == "parlachiaro"].sort_values("Data")
        if PCD.empty:
            st.info("Qui compare l'andamento appena salvi il primo allenamento.")
        else:
            a1, a2, a3 = st.columns(3)
            a1.metric("Allenamenti", len(PCD))
            a2.metric("Minuti in tutto", f"{PCD['Minuti'].sum():,.0f}".replace(",", "."))
            a3.metric("Efficacia media", f"{PCD['Valore'].mean():.0f}/100")

            figp = go.Figure()
            figp.add_scatter(x=PCD["Data"], y=PCD["Valore"], mode="lines+markers",
                             name="efficacia",
                             line=dict(color=VERDE, width=2),
                             hovertemplate="%{x|%d/%m/%Y}<br>%{y:.0f}/100<extra></extra>")
            if len(PCD) >= 4:
                med = PCD["Valore"].rolling(3, min_periods=1).mean()
                figp.add_scatter(x=PCD["Data"], y=med, mode="lines",
                                 name="media su 3",
                                 line=dict(color=VERDE_SCURO, width=2, dash="dot"))
            figp.update_yaxes(range=[0, 104])
            st.plotly_chart(style(figp, 300, "Indice di efficacia nel tempo"),
                            width='stretch')

            per_bl = PCD.groupby("Attivita")["Valore"].mean().sort_values()
            figb = go.Figure()
            figb.add_bar(x=per_bl.values, y=per_bl.index, orientation="h",
                         marker=dict(color=PALETTE[1], line=dict(width=0)),
                         hovertemplate="%{y}<br>%{x:.0f}/100<extra></extra>")
            figb.update_xaxes(range=[0, 108])
            st.plotly_chart(style(figb, 280, "Efficacia media per esercizio"),
                            width='stretch')

            tabp = PCD[["Data", "Attivita", "Minuti", "Valore", "Nota"]].copy()
            tabp["Data"] = tabp["Data"].dt.strftime("%d/%m/%Y")
            tabp = tabp.rename(columns={"Attivita": "Esercizio",
                                        "Valore": "Efficacia"})
            with st.expander("Tutti gli allenamenti"):
                st.dataframe(tabp, width='stretch', hide_index=True)
            scarica_tabella(tabp, "parlachiaro_allenamenti",
                            "⬇️ Scarica gli allenamenti")



# ============================================================================
# TAB 9 - SENTINEL  (il corso «SENTINEL da zero», con l'avanzamento nel diario)
# ============================================================================
with TAB[9]:
    pannello_riepilogo('sentinel')
    import sentinel as SENT

    st.markdown("#### 📡 SENTINEL da zero")
    st.caption("Il corso completo sulla tua stazione ELF: sedici moduli dalle "
               "basi elettriche all'indice PRISMA, più quattro appendici. "
               "Si legge qui dentro e funziona anche senza rete.")

    _p_sent = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "sentinel.html")

    @st.cache_data(show_spinner=False)
    def _corso_sentinel(_versione: float):
        return SENT.carica(_p_sent)

    try:
        HTML_SENT, MODULI_S = _corso_sentinel(_mtime("sentinel.html"))
    except FileNotFoundError:
        HTML_SENT, MODULI_S = None, []
        st.error("Manca il file `sentinel.html` accanto ad app.py.")
        st.caption("È il corso in un file solo: caricalo nella repo insieme "
                   "agli altri.")

    if MODULI_S:
        PERCORSO_SENT = "SENTINEL da zero"
        fatti_s = DIARIO.tappe_fatte(DIA, PERCORSO_SENT)
        appena_s = st.session_state.setdefault("sent_appena", set())
        fatti_s |= appena_s

        etichette_s = [SENT.etichetta(m) for m in MODULI_S]
        scelto_s = st.selectbox(
            "Modulo", range(len(MODULI_S)),
            format_func=lambda i: ("✅ " if etichette_s[i] in fatti_s else "")
                                  + etichette_s[i])
        M = MODULI_S[scelto_s]

        c1, c2, c3 = st.columns([3, 1, 1])
        c1.caption(M["parte"])
        era_s = SENT.etichetta(M) in fatti_s
        if c2.checkbox("Fatto", value=era_s, key=f"sent_fatto_{M['id']}") and not era_s:
            diario_scrivi(DIARIO.riga("tappa", PERCORSO_SENT, "SENTINEL",
                                      0, None, SENT.etichetta(M)))
            appena_s.add(SENT.etichetta(M))
            conferma(f"Modulo segnato: {SENT.etichetta(M)}")
        c3.metric("Avanzamento", f"{len(fatti_s)}/{len(MODULI_S)}")

        st.progress(len(fatti_s) / len(MODULI_S))

        pagina_html(SENT.pagina(HTML_SENT, M["id"]), 900)

        st.caption("I collegamenti dentro la pagina sono disattivati apposta: "
                   "per cambiare modulo usa il menù qui sopra. Le spunte che "
                   "metti qui finiscono nel diario, quindi restano anche "
                   "cambiando dispositivo.")

        st.divider()
        SS1, SS2 = st.tabs(["🤖 Chiedi su questo modulo", "📈 Come stai andando"])

        with SS1:
            st.caption("La domanda arriva all'assistente insieme al titolo del "
                       "modulo che stai leggendo, quindi non devi spiegargli "
                       "di cosa stai parlando.")
            dubbio = VOCE.campo(
                "Cosa non ti torna", "sent_dubbio", chiave_ai(), modello_ai(),
                altezza=110,
                suggerimento="es. non capisco perché la ferrite aumenta il "
                             "segnale invece di schermarlo")
            q1, q2 = st.columns(2)
            chiedi_s = q1.button("Chiedi", type="primary", width='stretch')
            salva_s = q2.button("💾 Salva la domanda e la risposta",
                                width='stretch',
                                disabled=not st.session_state.get("sent_risposta"))

            if chiedi_s:
                if not dubbio.strip():
                    st.warning("Scrivi la domanda prima.")
                else:
                    stato_s = st.empty()
                    try:
                        with st.spinner("Sto pensando…"):
                            risp_s = AI.chiedi(
                                "Sei un ingegnere che spiega a un collega "
                                "preparato ma non specialista. Sta studiando "
                                "un corso sulla sua stazione di misura dei "
                                "campi elettromagnetici a bassissima "
                                f"frequenza.\n\nModulo: {SENT.etichetta(M)} "
                                f"({M['parte']})\n\nLa sua domanda:\n"
                                f"{dubbio.strip()}\n\n"
                                "Rispondi in italiano, concreto, con un "
                                "esempio numerico se aiuta. Se la domanda "
                                "nasce da un equivoco, dillo e spiega dove "
                                "sta. Niente elenchi lunghi: tre o quattro "
                                "capoversi.",
                                chiave_ai(), modello_ai(),
                                al_tentativo=lambda m: stato_s.info(m))
                        stato_s.empty()
                        st.session_state["sent_risposta"] = risp_s
                        st.session_state["sent_domanda"] = dubbio.strip()
                        st.rerun()
                    except AI.ErroreAI as e:
                        stato_s.empty()
                        st.error(e.messaggio)
                        if e.dettaglio:
                            st.caption(e.dettaglio)

            if st.session_state.get("sent_risposta"):
                st.markdown(st.session_state["sent_risposta"])

            if salva_s:
                diario_scrivi(DIARIO.riga(
                    "dubbio", SENT.etichetta(M), "SENTINEL", 5, None,
                    f"{st.session_state.get('sent_domanda', '')} :: "
                    f"{st.session_state.get('sent_risposta', '')[:900]}"))
                conferma("Domanda e risposta salvate nel diario")
                st.session_state.pop("sent_risposta", None)
                VOCE.svuota("sent_dubbio")
                st.rerun()

            dubbi = DIA[DIA["Tipo"] == "dubbio"].sort_values(
                "Data", ascending=False)
            if not dubbi.empty:
                with st.expander(f"Le domande che hai già fatto ({len(dubbi)})"):
                    for _, r in dubbi.head(15).iterrows():
                        dom_d = r["Nota"].split(" :: ")[0]
                        st.markdown(f"**{r['Data']:%d/%m/%Y} · {r['Attivita']}** "
                                    f"— {dom_d}")
                        st.caption(r["Nota"].split(" :: ", 1)[-1][:400])

        with SS2:
            tappe_s = DIA[(DIA["Tipo"] == "tappa")
                          & (DIA["Attivita"] == PERCORSO_SENT)].sort_values("Data")
            if tappe_s.empty:
                st.info("Qui compare l'andamento appena segni il primo modulo "
                        "come fatto.")
            else:
                v1, v2, v3 = st.columns(3)
                v1.metric("Moduli fatti", f"{len(fatti_s)}/{len(MODULI_S)}")
                giorni_s = (tappe_s["Data"].max() - tappe_s["Data"].min()).days + 1
                v2.metric("Giorni dal primo", giorni_s)
                v3.metric("Domande fatte",
                          int((DIA["Tipo"] == "dubbio").sum()))

                cumul = tappe_s.groupby(tappe_s["Data"].dt.normalize()).size().cumsum()
                figs = go.Figure()
                figs.add_scatter(x=cumul.index, y=cumul.values,
                                 mode="lines+markers", line_shape="hv",
                                 line=dict(color=PALETTE[0], width=2),
                                 hovertemplate="%{x|%d/%m/%Y}<br>%{y} moduli<extra></extra>")
                figs.add_hline(y=len(MODULI_S), line_dash="dot",
                               line_color=VERDE_SCURO,
                               annotation_text="tutti i moduli")
                figs.update_yaxes(range=[0, len(MODULI_S) + 1])
                st.plotly_chart(style(figs, 300, "Moduli completati nel tempo"),
                                width='stretch')

                if len(tappe_s) >= 2 and len(fatti_s) < len(MODULI_S):
                    al_giorno = len(tappe_s) / max(1, giorni_s)
                    mancano = len(MODULI_S) - len(fatti_s)
                    st.caption(f"A questo ritmo — {al_giorno:.2f} moduli al "
                               f"giorno — per finire gli altri {mancano} ci "
                               f"vogliono circa {mancano / al_giorno:.0f} giorni.")

                tab_s = tappe_s[["Data", "Nota"]].rename(columns={"Nota": "Modulo"})
                tab_s = tab_s.copy()
                scarica_tabella(tab_s, "sentinel_avanzamento",
                                "⬇️ Scarica l'avanzamento")



# ============================================================================
# TAB 10 - RADAR  (cosa esce di nuovo sulle cose che segui — vedi radar.py)
# ============================================================================
with TAB[10]:
    import radar as RAD

    pannello_riepilogo('radar')
    mostra_conferma()

    RCFG = _carica_json("radar.json", _mtime("radar.json"))
    if "_errore" in RCFG:
        st.error(f"Non riesco a leggere `radar.json`: {RCFG['_errore']}")
        st.stop()

    st.markdown("#### 🛰️ Radar")
    st.caption("Quello che è uscito di nuovo sulle fonti che segui, setacciato "
               "sulle cose che ti interessano, senza doppioni e con l'italiano "
               "davanti. Si aggiorna da solo ogni ora.")

    # ======================= le fonti, su Drive =============================
    # Perché non restano in `radar.json`: quel file sta nella repository, e
    # Streamlit ricostruisce il disco a ogni riavvio. Una fonte aggiunta
    # dall'interfaccia sparirebbe al primo Reboot. Su Drive invece resta.
    #
    # Il formato è lo stesso degli altri archivi, otto colonne, così si
    # riusano le funzioni già scritte:
    #   Tipo=fonte      Attivita=nome   Strumento=ambito|lingua|contenuto
    #                   Nota=indirizzo  Valore=1 accesa / 0 spenta
    #   Tipo=interesse  Nota=parola che fa salire una voce
    #   Tipo=esclusione Nota=parola che la fa buttare via
    @st.cache_data(ttl=120, show_spinner=False)
    def _cerca_file_fonti(_segno):
        if not SA:
            return None
        try:
            return DIARIO.trova_file(
                dict(SA), [secret("drive_folder_id_diario", ""),
                           secret("drive_folder_id_progetti", ""),
                           secret("drive_folder_id", "")],
                "Quadro_Fonti.xlsx")
        except Exception:
            return None

    FILE_FONTI = _cerca_file_fonti(st.session_state.get("cerca_archivio", 0))

    @st.cache_data(ttl=60, show_spinner=False)
    def _leggi_fonti(_f, _segno):
        return DIARIO.leggi_xlsx(dict(SA), _f)

    def _da_drive():
        """(fonti, interessi, esclusioni) dal file su Drive, o None."""
        if not FILE_FONTI:
            return None
        try:
            d = _leggi_fonti(FILE_FONTI, st.session_state.get("fonti_segno", 0))
        except Exception:
            return None
        if d.empty:
            return None
        fonti, inter, escl = [], [], []
        for _, r in d.iterrows():
            if r["Tipo"] == "fonte" and r["Nota"].strip():
                if str(r["Valore"]) in ("0", "0.0"):
                    continue
                pezzi = (r["Strumento"] or "altro|en|articolo").split("|")
                pezzi += ["altro", "en", "articolo"][len(pezzi):]
                fonti.append({"nome": r["Attivita"], "url": r["Nota"].strip(),
                              "tipo": pezzi[0], "lingua": pezzi[1],
                              "contenuto": pezzi[2]})
            elif r["Tipo"] == "interesse" and r["Nota"].strip():
                inter.append(r["Nota"].strip())
            elif r["Tipo"] == "esclusione" and r["Nota"].strip():
                escl.append(r["Nota"].strip())
        if not fonti:
            return None
        return fonti, inter or RCFG.get("interessi", []), \
            escl or RCFG.get("esclusioni", [])

    DA_DRIVE = _da_drive()
    if DA_DRIVE:
        FONTI, INTERESSI, ESCLUSIONI = DA_DRIVE
        DOVE_FONTI = "drive"
    else:
        FONTI = RCFG.get("fonti", [])
        INTERESSI = RCFG.get("interessi", [])
        ESCLUSIONI = RCFG.get("esclusioni", [])
        DOVE_FONTI = "file"

    def salva_fonti(fonti, interessi, esclusioni):
        righe = []
        for f in fonti:
            righe.append(DIARIO.riga(
                "fonte", f.get("nome", ""),
                f"{f.get('tipo', 'altro')}|{f.get('lingua', 'en')}|"
                f"{f.get('contenuto', 'articolo')}",
                0, 1 if f.get("attiva", True) else 0, f.get("url", "")))
        for p in interessi:
            righe.append(DIARIO.riga("interesse", "", "", 0, None, p))
        for p in esclusioni:
            righe.append(DIARIO.riga("esclusione", "", "", 0, None, p))
        DIARIO.sostituisci_xlsx(dict(SA), FILE_FONTI, righe, "Fonti")
        st.session_state["fonti_segno"] = \
            st.session_state.get("fonti_segno", 0) + 1
        st.cache_data.clear()

    @st.cache_data(ttl=3600, show_spinner=False)
    def _raccogli_radar(_segno, giorni, minimo, _n_fonti):
        return RAD.raccogli(FONTI, INTERESSI, ESCLUSIONI, giorni, minimo,
                            RCFG.get("bonus_lingua", {}))

    with st.spinner("Sto guardando le fonti…"):
        tutte_r, problemi_r = _raccogli_radar(
            st.session_state.get("radar_segno", 0), 60,
            RCFG.get("punteggio_minimo", 1), len(FONTI))

    # ------------------------------------------------------- l'archivio ----
    # Lo storico non può partire da giugno: i feed pubblicano solo le ultime
    # voci, fra le dieci e le sessanta, e quello che è uscito prima non è più
    # scaricabile da nessuna parte. Quello che si può fare è cominciare ad
    # archiviare da adesso, e da qui in avanti lo storico cresce da solo.
    @st.cache_data(ttl=120, show_spinner=False)
    def _cerca_file_radar(_segno):
        if not SA:
            return None
        try:
            return DIARIO.trova_file(
                dict(SA), [secret("drive_folder_id_diario", ""),
                           secret("drive_folder_id_progetti", ""),
                           secret("drive_folder_id", "")],
                "Quadro_Radar.xlsx")
        except Exception:
            return None

    FILE_RAD = _cerca_file_radar(st.session_state.get("cerca_archivio", 0))

    @st.cache_data(ttl=300, show_spinner=False)
    def _leggi_archivio(_f, _segno):
        return DIARIO.leggi_xlsx(dict(SA), _f)

    def archivio_radar():
        if not FILE_RAD:
            return st.session_state.get("radar_locale", DIARIO.vuoto())
        try:
            return _leggi_archivio(FILE_RAD,
                                   st.session_state.get("radar_arch_segno", 0))
        except Exception:
            return st.session_state.get("radar_locale", DIARIO.vuoto())

    ARCH = archivio_radar()

    # Archiviazione automatica: appena il Radar carica, quello che non c'è
    # ancora entra nell'archivio. Si fa una volta per sessione per non
    # riscrivere il file a ogni clic, e solo se l'archivio è collegato.
    AUTO_ARCH = st.session_state.get("radar_auto_fatto")

    def archivia(voci):
        """Aggiunge all'archivio solo quello che non c'è già."""
        gia = set(ARCH["Nota"].str.split(" :: ").str[0]) if not ARCH.empty else set()
        nuove = [v for v in voci if v["titolo"] not in gia]
        if not nuove:
            return 0
        righe = [DIARIO.riga("voce", v["fonte"],
                             f"{v['tipologia']}/{v['lingua']}", 0, v["punti"],
                             f"{v['titolo']} :: {v['link']}",
                             quando=dt.datetime.combine(
                                 v["data"] or DIARIO.oggi(), dt.time(12, 0)))
                 for v in nuove[:300]]
        if FILE_RAD:
            DIARIO.aggiungi_xlsx(dict(SA), FILE_RAD, righe)
            st.session_state["radar_arch_segno"] = \
                st.session_state.get("radar_arch_segno", 0) + 1
        else:
            loc = st.session_state.get("radar_locale", DIARIO.vuoto())
            st.session_state["radar_locale"] = DIARIO._sistema(
                pd.concat([loc, pd.DataFrame(righe)], ignore_index=True))
        return len(righe)

    if (FILE_RAD and not AUTO_ARCH and tutte_r
            and RCFG.get("archivia_da_solo", True)):
        try:
            n_auto = archivia(tutte_r)
            st.session_state["radar_auto_fatto"] = True
            if n_auto:
                st.caption(f"✓ {n_auto} voci nuove aggiunte all'archivio.")
        except Exception:
            st.session_state["radar_auto_fatto"] = True   # non riprovare

    # ---------------------------------------------------------- i filtri ---
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        ambiti = sorted({f.get("tipo", "altro") for f in FONTI})
        sel_amb = c1.multiselect("Argomento", ambiti, default=[],
                                 placeholder="tutti gli argomenti")
        NOMI_L = {"it": "italiano", "es": "spagnolo", "en": "inglese",
                  "?": "non riconosciuta"}
        sel_ling = c2.multiselect(
            "Lingua", list(NOMI_L.keys()), default=[],
            format_func=lambda k: NOMI_L[k], placeholder="tutte le lingue")
        sel_tipo = c3.multiselect(
            "Tipo", ["articolo", "video", "podcast", "corso"], default=[],
            placeholder="tutti i tipi")

        d1, d2 = st.columns([2, 1])
        giorni_r = d1.select_slider(
            "Periodo", [3, 7, 14, 30, 60], value=RCFG.get("giorni", 14),
            format_func=lambda g: f"ultimi {g} giorni")
        if d2.button("🔄 Aggiorna ora", width='stretch'):
            st.session_state["radar_segno"] = st.session_state.get("radar_segno", 0) + 1
            st.cache_data.clear()
            st.rerun()
        cerca_r = st.text_input("Cerca nel testo",
                                placeholder="es. ferrite, idroponica, ESP32",
                                key="radar_cerca")
        f_r1, f_r2 = st.columns(2)
        sel_fonte_r = f_r1.multiselect(
            "Fonte", sorted({v["fonte"] for v in tutte_r}), default=[],
            placeholder="tutte le fonti", key="radar_fonte")
        autore_r = f_r2.text_input("Autore", placeholder="nome dell'autore o del canale",
                                   key="radar_autore")

    limite_r = DIARIO.oggi() - dt.timedelta(days=giorni_r)
    voci_r = [v for v in tutte_r if not v["data"] or v["data"] >= limite_r]
    if sel_amb:
        voci_r = [v for v in voci_r if v["ambito"] in sel_amb]
    if sel_ling:
        voci_r = [v for v in voci_r if v["lingua"] in sel_ling]
    if sel_tipo:
        voci_r = [v for v in voci_r if v["tipologia"] in sel_tipo]
    if cerca_r.strip():
        q = cerca_r.strip().lower()
        voci_r = [v for v in voci_r
                  if q in (v["titolo"] + " " + v["testo"]).lower()]
    if sel_fonte_r:
        voci_r = [v for v in voci_r if v["fonte"] in sel_fonte_r]
    if autore_r.strip():
        q_a = autore_r.strip().lower()
        voci_r = [v for v in voci_r
                  if q_a in ((v.get("autore") or "") + " " + v["fonte"]).lower()]

    k = st.columns(4)
    k[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
    k[0].metric("Con questi filtri", len(voci_r))
    k[1].metric("In italiano", sum(1 for v in voci_r if v["lingua"] == "it"))
    k[2].metric("Fonti lette", len(FONTI) - len(problemi_r))
    k[3].metric("In archivio", len(ARCH))

    RT = st.tabs(["📰 Le novità", "🤖 Assistente", "🎓 Eventi e seminari",
                  "📚 Riviste", "⭐ Messe da parte", "🗄️ Archivio",
                  "⚙️ Le fonti", "🏛️ Bandi e agevolazioni"])

    # ------------------------------- le novità ------------------------------
    with RT[0]:
        if not voci_r:
            st.info("Niente con questi filtri. Allarga il periodo o togli "
                    "qualche filtro.")
        else:
            b1, b2 = st.columns(2)
            if b1.button("📝 Riassumimi tutto in dieci righe", width='stretch',
                         type="primary"):
                elenco = "\n".join(f"- [{v['fonte']}] {v['titolo']}"
                                   for v in voci_r[:60])
                stato_r = st.empty()
                try:
                    with st.spinner("Sto leggendo…"):
                        st.session_state["radar_digest"] = AI.chiedi(
                            "Questa persona è un ingegnere industriale, maker e "
                            "formatore: elettronica, microcontrollori, energia, "
                            "agritech, misure di campi elettromagnetici, "
                            "didattica tecnica.\n\nEcco i titoli usciti di "
                            f"recente sulle sue fonti:\n{elenco}\n\n"
                            "Scrivi un riassunto di dieci righe che dica quali "
                            "sono i due o tre filoni di cui si sta parlando in "
                            "questo periodo e cosa, fra questi, tocca "
                            "direttamente i suoi campi. Niente elenco dei "
                            "titoli: una lettura d'insieme. Italiano, frasi brevi.",
                            chiave_ai(), modello_ai(),
                            al_tentativo=lambda m: stato_r.info(m))
                    stato_r.empty()
                except AI.ErroreAI as e:
                    stato_r.empty()
                    st.error(e.messaggio)

            if b2.button(f"🗄️ Archivia queste {len(voci_r)} voci",
                         width='stretch'):
                try:
                    n = archivia(voci_r)
                    conferma(f"Archiviate {n} voci nuove"
                             if n else "Erano già tutte in archivio")
                    st.rerun()
                except Exception as e:
                    st.error(f"Non sono riuscito a scrivere l'archivio: {e}")

            if st.session_state.get("radar_digest"):
                with st.container(border=True):
                    st.markdown("##### Di cosa si sta parlando")
                    st.markdown(st.session_state["radar_digest"])
                    pulsante_ascolta(re.sub(r"[*#_`]", "",
                                            st.session_state["radar_digest"]),
                                     "🔊 Ascolta il riassunto")
                    if st.button("Nascondi"):
                        st.session_state.pop("radar_digest", None)
                        st.rerun()

            st.divider()
            pulsante_ascolta("Ecco le novità. " + ". ".join(
                v["titolo"] for v in voci_r[:15]), "🔊 Leggi i primi 15 titoli")
            gia_salvati = set(DIA[DIA["Tipo"] == "radar"]["Nota"]
                              .str.split(" :: ").str[0]) \
                if not DIA[DIA["Tipo"] == "radar"].empty else set()
            BANDIERA = {"it": "🇮🇹", "es": "🇪🇸", "en": "🇬🇧", "?": "🏳️"}
            SEGNO = {"articolo": "📄", "video": "▶️", "podcast": "🎧",
                     "corso": "🎓"}

            for i_v, v in enumerate(voci_r[:50]):
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    quando_v = f"{v['data']:%d/%m}" if v["data"] else "—"
                    c1.markdown(f"{SEGNO.get(v['tipologia'], '📄')} "
                                f"{BANDIERA.get(v['lingua'], '')} **{v['titolo']}**")
                    c1.caption(f"{v['fonte']}"
                               + (f" · {v['autore']}" if v.get("autore") else "")
                               + f" · {v['ambito']} · {quando_v}"
                               + (f" · {', '.join(v['parole'])}" if v["parole"] else ""))
                    if v["testo"]:
                        c1.markdown(f"<span style='opacity:.78'>{v['testo'][:260]}…</span>",
                                    unsafe_allow_html=True)
                    pulsante_ascolta(f"{v['titolo']}. {v['testo']}")
                    if v["link"]:
                        c2.link_button("Apri ↗", v["link"], width='stretch')
                    if v["titolo"] in gia_salvati:
                        c2.caption("⭐ salvata")
                    elif c2.button("⭐ Dopo", key=f"rad_{i_v}", width='stretch'):
                        diario_scrivi(DIARIO.riga(
                            "radar", v["fonte"], "Radar", 0, v["punti"],
                            f"{v['titolo']} :: {v['link']}"))
                        conferma("Messa da parte")
                        st.rerun()

                    if c2.button("💡 Di che parla", key=f"spieg_{i_v}",
                                 width='stretch'):
                        st.session_state["radar_spiega"] = i_v
                    if st.session_state.get("radar_spiega") == i_v:
                        stato_s = st.empty()
                        try:
                            with st.spinner("…"):
                                st.info(AI.chiedi(
                                    "Spiega in tre frasi, a un ingegnere, di "
                                    "cosa parla questa notizia e perché "
                                    "potrebbe interessargli. Se dal titolo e "
                                    "dal riassunto non si capisce abbastanza, "
                                    "dillo invece di inventare.\n\n"
                                    f"Titolo: {v['titolo']}\n"
                                    f"Riassunto: {v['testo']}\n"
                                    f"Fonte: {v['fonte']}",
                                    chiave_ai(), modello_ai(),
                                    al_tentativo=lambda m: stato_s.info(m)))
                            stato_s.empty()
                        except AI.ErroreAI as e:
                            stato_s.empty()
                            st.error(e.messaggio)

            if len(voci_r) > 50:
                st.caption(f"…e altre {len(voci_r) - 50}. Restringi i filtri.")

            tab_r = pd.DataFrame([{"Data": v["data"], "Lingua": v["lingua"],
                                   "Tipo": v["tipologia"], "Ambito": v["ambito"],
                                   "Fonte": v["fonte"], "Titolo": v["titolo"],
                                   "Link": v["link"]} for v in voci_r])
            scarica_tabella(tab_r, "radar", "⬇️ Scarica l'elenco")

    # ------------------------------ assistente ------------------------------
    with RT[1]:
        st.caption("Chiedi quello che vuoi su quello che è uscito: lui ha "
                   "davanti i titoli e i riassunti di tutte le voci che "
                   "passano i filtri che hai messo.")
        esempi = ["C'è qualcosa sull'ESP32 che non so già?",
                  "Cosa mi conviene leggere se ho venti minuti?",
                  "Qualcosa di utile per le lezioni di questa settimana?",
                  "Riassumimi solo quello che riguarda l'energia"]
        st.caption("Per esempio: " + " · ".join(f"«{e}»" for e in esempi))

        dom_r = st.chat_input("Chiedi al Radar…", key="radar_chat_input")
        chat_r = st.session_state.setdefault("radar_chat", [])
        if dom_r:
            chat_r.append(("io", dom_r))
            contesto = "\n".join(
                f"- [{v['fonte']} · {v['lingua']} · {v['tipologia']} · "
                f"{v['data'] or ''}] {v['titolo']} — {v['testo'][:140]}"
                for v in voci_r[:70])
            scambio = "\n".join(("Lui: " if r == "io" else "Tu: ") + t
                                for r, t in chat_r[-6:])
            stato_c = st.empty()
            try:
                with st.spinner("Sto guardando…"):
                    risp_c = AI.chiedi(
                        "Aiuti un ingegnere industriale, maker e formatore a "
                        "orientarsi fra le novità che il suo radar ha "
                        "raccolto. Rispondi SOLO su quello che trovi "
                        "nell'elenco qui sotto: se una cosa non c'è, dillo "
                        "invece di inventarla.\n\n"
                        f"Le voci disponibili:\n{contesto}\n\n"
                        f"La conversazione:\n{scambio}\n\n"
                        "Rispondi in italiano, frasi brevi, citando i titoli "
                        "di cui parli.",
                        chiave_ai(), modello_ai(),
                        al_tentativo=lambda m: stato_c.info(m))
                stato_c.empty()
                chat_r.append(("ai", risp_c))
            except AI.ErroreAI as e:
                stato_c.empty()
                st.error(e.messaggio)
            st.session_state["radar_chat"] = chat_r
            st.rerun()

        for ruolo, testo_c in chat_r:
            with st.chat_message("user" if ruolo == "io" else "assistant"):
                st.markdown(testo_c)
        if chat_r and st.button("🗑️ Pulisci la conversazione"):
            st.session_state.pop("radar_chat", None)
            st.rerun()

    # --------------------------- eventi e seminari --------------------------
    with RT[2]:
        st.warning("**Gli atenei non pubblicano un feed.** Ho ricontrollato: "
                   "le pagine esistono — e gli indirizzi che ti avevo dato la "
                   "volta scorsa erano sbagliati, quelli giusti stanno su "
                   "`web.unisa.it`, non `www.unisa.it` — ma nessuna dichiara "
                   "un elenco in formato leggibile. Senza quello non c'è "
                   "niente da raccogliere in automatico: vanno aperte.")
        zone = sorted({p.get("zona", "") for p in RCFG.get("pagine_da_guardare", [])})
        for z in zone:
            st.markdown(f"##### {z or 'Altro'}")
            for p in RCFG.get("pagine_da_guardare", []):
                if p.get("zona", "") != z:
                    continue
                with st.container(border=True):
                    e1, e2 = st.columns([4, 1])
                    e1.markdown(f"**{p['nome']}**")
                    if p.get("nota"):
                        e1.caption(p["nota"])
                    e2.link_button("Apri ↗", p["url"], width='stretch')

        st.divider()
        st.markdown("##### Segna un evento a cui vuoi andare")
        with st.form("radar_evento", clear_on_submit=True):
            ev1, ev2 = st.columns([3, 1])
            nome_ev = ev1.text_input("Cosa",
                                     placeholder="es. seminario agritech, UNISA")
            data_ev = ev2.date_input("Quando", value=DIARIO.oggi(),
                                     format="DD/MM/YYYY")
            link_ev = st.text_input("Collegamento (facoltativo)")
            if st.form_submit_button("💾 Segna in agenda", type="primary"):
                if nome_ev.strip():
                    diario_scrivi(DIARIO.riga(
                        "evento", nome_ev.strip()[:60], "Radar", 0, None,
                        f"{nome_ev.strip()} :: {link_ev.strip()}",
                        quando=dt.datetime.combine(data_ev, dt.time(9, 0))))
                    conferma(f"Segnato: {nome_ev.strip()[:40]}")
                    st.rerun()

        eventi = DIA[DIA["Tipo"] == "evento"].sort_values("Data")
        if not eventi.empty:
            futuri = eventi[eventi["Data"] >= pd.Timestamp(DIARIO.oggi())]
            passati = eventi[eventi["Data"] < pd.Timestamp(DIARIO.oggi())]
            if not futuri.empty:
                st.markdown("##### In arrivo")
                for _, r in futuri.iterrows():
                    gg = (r["Data"] - pd.Timestamp(DIARIO.oggi())).days
                    quando_e = "oggi" if gg == 0 else (
                        "domani" if gg == 1 else f"fra {gg} giorni")
                    titolo_e, _, link_e = r["Nota"].partition(" :: ")
                    v1, v2 = st.columns([4, 1])
                    v1.markdown(f"**{r['Data']:%d/%m/%Y}** — {titolo_e}  "
                                f"<small style='opacity:.6'>({quando_e})</small>",
                                unsafe_allow_html=True)
                    if link_e.strip():
                        v2.link_button("Apri ↗", link_e.strip(), width='stretch')
            if not passati.empty:
                with st.expander(f"Già passati ({len(passati)})"):
                    for _, r in passati.sort_values("Data", ascending=False).iterrows():
                        st.markdown(f"**{r['Data']:%d/%m/%Y}** — "
                                    f"{r['Nota'].split(' :: ')[0]}")

    # -------------------------------- riviste -------------------------------
    with RT[3]:
        riv = RCFG.get("riviste", {})
        st.warning(riv.get("_nota", ""))
        coll = riv.get("collegamento")
        if coll:
            st.link_button(f"📰 {coll['nome']} ↗", coll["url"])
        st.markdown("##### Come si fa, in pratica")
        st.markdown(
            "1. Prendi una rivista che segui su Readly.\n"
            "2. Cerca su internet «*nome della rivista* rss»: quasi tutte le "
            "testate hanno un feed del sito.\n"
            "3. Aggiungila alle fonti in `radar.json` con `\"contenuto\": "
            "\"articolo\"` e la lingua giusta.\n\n"
            "Da quel momento il Radar ti dice quando escono articoli nuovi, e "
            "il numero completo lo apri su Readly. Non è la stessa cosa che "
            "sapere quando esce il fascicolo — quello Readly non lo dice a "
            "nessuno — ma è il massimo ottenibile senza che te ne accorga a "
            "mano.")

    # --------------------------- messe da parte -----------------------------
    with RT[4]:
        salvate_r = DIA[DIA["Tipo"] == "radar"]
        if salvate_r.empty:
            st.info("Niente messo da parte. Il pulsante ⭐ Dopo le raccoglie qui.")
        else:
            for _, r in salvate_r.sort_values("Data", ascending=False).iterrows():
                titolo_s, _, link_s = r["Nota"].partition(" :: ")
                with st.container(border=True):
                    s1, s2 = st.columns([5, 1])
                    s1.markdown(f"**{titolo_s}**")
                    s1.caption(f"{r['Attivita']} · {r['Data']:%d/%m/%Y}")
                    if link_s.strip():
                        s2.link_button("Apri ↗", link_s.strip(), width='stretch')
            tab_s3 = salvate_r[["Data", "Attivita", "Nota"]].copy()
            tab_s3["Data"] = tab_s3["Data"].dt.strftime("%d/%m/%Y")
            scarica_tabella(tab_s3.rename(columns={"Attivita": "Fonte",
                                                   "Nota": "Titolo"}),
                            "radar_salvate", "⬇️ Scarica")

    # -------------------------------- archivio ------------------------------
    with RT[5]:
        st.info("**Lo storico non può partire da giugno, e il motivo è nelle "
                "fonti, non in Quadro.** Un feed pubblica solo le ultime "
                "voci — fra le dieci e le sessanta — e quello che è uscito "
                "prima non è più scaricabile da nessuna parte. Quello che si "
                "può fare è cominciare ad archiviare da oggi: ogni volta che "
                "premi «Archivia» le voci nuove si aggiungono, e da qui in "
                "avanti lo storico cresce.")

        if not FILE_RAD:
            with st.expander("Come collegare l'archivio"):
                st.markdown(
                    "Scarica il file qui sotto e caricalo in una cartella "
                    "Drive che Quadro già conosce, condivisa come **Editor**. "
                    "È un file a parte dal diario: le voci del Radar sono "
                    "tante e non devono mescolarsi con le tue sessioni.")
                st.download_button("⬇️ Scarica Quadro_Radar.xlsx",
                                   DIARIO.modello_xlsx("Radar", guida=False),
                                   "Quadro_Radar.xlsx",
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet", type="primary")
            st.caption("Finché non lo colleghi, l'archivio vive solo in questa "
                       "sessione.")

        # Una sola funzione scrive l'archivio, in tutti e due i modi in cui
        # può stare: nel file su Drive o, se non è collegato, in memoria.
        def _scrivi_archivio(righe_nuove=None, sostituisci=None):
            if FILE_RAD:
                if sostituisci is not None:
                    DIARIO.sostituisci_xlsx(dict(SA), FILE_RAD, sostituisci, "Radar")
                else:
                    DIARIO.aggiungi_xlsx(dict(SA), FILE_RAD, righe_nuove)
                st.session_state["radar_arch_segno"] = \
                    st.session_state.get("radar_arch_segno", 0) + 1
            else:
                if sostituisci is not None:
                    st.session_state["radar_locale"] = DIARIO._sistema(
                        pd.DataFrame(sostituisci, columns=DIARIO.COLONNE))
                else:
                    loc = st.session_state.get("radar_locale", DIARIO.vuoto())
                    st.session_state["radar_locale"] = DIARIO._sistema(
                        pd.concat([loc, pd.DataFrame(righe_nuove)], ignore_index=True))

        with st.expander("➕ Aggiungi una voce a mano"):
            with st.form("arch_nuova", clear_on_submit=True):
                a1, a2 = st.columns([3, 1])
                t_a = a1.text_input("Titolo")
                d_a = a2.date_input("Data", value=DIARIO.oggi(), format="DD/MM/YYYY")
                a3, a4 = st.columns(2)
                f_a = a3.text_input("Fonte", placeholder="es. Canale YouTube X")
                l_a = a4.text_input("Link", placeholder="https://...")
                if st.form_submit_button("💾 Archivia", type="primary"):
                    if t_a.strip():
                        try:
                            _scrivi_archivio(righe_nuove=[DIARIO.riga(
                                "voce", f_a.strip() or "a mano", "manuale", 0, None,
                                f"{t_a.strip()} :: {l_a.strip()}",
                                quando=dt.datetime.combine(d_a, dt.time(12, 0)))])
                            conferma("Voce archiviata")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Non sono riuscito a scrivere l'archivio: {e}")
                    else:
                        st.warning("Serve almeno il titolo.")

        if ARCH.empty:
            st.caption("Archivio ancora vuoto.")
        else:
            a1, a2, a3 = st.columns(3)
            a1.metric("Voci archiviate", len(ARCH))
            a2.metric("Dal", f"{ARCH['Data'].min():%d/%m/%Y}")
            a3.metric("Fonti diverse", ARCH["Attivita"].nunique())

            per_mese_a = ARCH.groupby(
                ARCH["Data"].dt.to_period("M").dt.to_timestamp()).size()
            figa = go.Figure()
            figa.add_bar(x=per_mese_a.index, y=per_mese_a.values,
                         marker=dict(color=PALETTE[0], line=dict(width=0)),
                         hovertemplate="%{x|%m/%Y}<br>%{y} voci<extra></extra>")
            st.plotly_chart(style(figa, 260, "Voci archiviate per mese"),
                            width='stretch')

            def _separa(nota):
                parti = str(nota).split(" :: ")
                return parti[0], (parti[1] if len(parti) > 1 else "")

            base_a = ARCH.sort_values("Data", ascending=False).reset_index(drop=True)
            modifica_a = pd.DataFrame({
                "Data": base_a["Data"].dt.date,
                "Fonte": base_a["Attivita"],
                "Tipo e lingua": base_a["Strumento"],
                "Titolo": base_a["Nota"].map(lambda n: _separa(n)[0]),
                "Link": base_a["Nota"].map(lambda n: _separa(n)[1]),
                "Punti": base_a["Valore"],
            })

            cerca_a = st.text_input("Cerca nell'archivio",
                                    placeholder="una parola qualsiasi",
                                    key="arch_cerca")
            if cerca_a.strip():
                # con la ricerca attiva la tabella è di sola lettura: modificare
                # solo le voci trovate salverebbe via tutte le altre
                trovate = modifica_a[modifica_a["Titolo"].str.contains(
                    cerca_a.strip(), case=False, na=False)
                    | modifica_a["Fonte"].str.contains(cerca_a.strip(), case=False, na=False)]
                st.caption(f"{len(trovate)} voci trovate. Togli la ricerca per modificare.")
                st.dataframe(trovate, width='stretch', hide_index=True, height=420,
                             column_config={"Link": st.column_config.LinkColumn(
                                 "Link", display_text="apri"),
                                 "Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
            else:
                st.markdown("##### Modifica l'archivio")
                st.caption("Cambia direttamente nella tabella. Per cancellare "
                           "una voce selezionala a sinistra e premi il cestino. "
                           "Quando hai finito, premi **Salva**.")
                editata_a = st.data_editor(
                    modifica_a, hide_index=True, num_rows="dynamic",
                    width='stretch', height=460, key="editor_archivio",
                    column_config={
                        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "Link": st.column_config.LinkColumn("Link", display_text="apri"),
                        "Punti": st.column_config.NumberColumn("Punti", disabled=True),
                    })
                if st.button("💾 Salva le modifiche all'archivio", type="primary"):
                    nuove_a = []

                    def _t(x):
                        # una casella vuota di una riga nuova arriva come NaN, non come ""
                        return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
                    for _, r_a in editata_a.iterrows():
                        titolo_r = _t(r_a["Titolo"])
                        if not titolo_r:
                            continue
                        quando_r = r_a["Data"]
                        if quando_r is None or pd.isna(quando_r):
                            quando_r = DIARIO.oggi()
                        punti_r = r_a["Punti"]
                        nuove_a.append(DIARIO.riga(
                            "voce", _t(r_a["Fonte"]) or "a mano",
                            _t(r_a["Tipo e lingua"]), 0,
                            None if pd.isna(punti_r) else float(punti_r),
                            f"{titolo_r} :: {_t(r_a['Link'])}",
                            quando=dt.datetime.combine(quando_r, dt.time(12, 0))))
                    try:
                        _scrivi_archivio(sostituisci=nuove_a)
                        conferma(f"Archivio salvato: {len(nuove_a)} voci")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Non sono riuscito a salvare l'archivio: {e}")

            scarica_tabella(modifica_a[["Data", "Fonte", "Tipo e lingua", "Titolo", "Link"]],
                            "radar_archivio", "⬇️ Scarica l'archivio")

    # ------------------------------- le fonti -------------------------------
    with RT[6]:
        if DOVE_FONTI == "file":
            st.warning("**Le fonti stanno ancora dentro `radar.json`, nella "
                       "repository.** Da lì si leggono ma non si modificano: "
                       "Streamlit ricostruisce il disco a ogni riavvio, "
                       "quindi quello che cambi qui sparirebbe al primo "
                       "Reboot.")
            with st.expander("Come spostarle su Drive, una volta sola",
                             expanded=True):
                st.markdown(
                    "Scarica `Quadro_Fonti.xlsx` qui sotto, caricalo in una "
                    "cartella Drive condivisa come **Editor** (quella dei "
                    "progetti va bene), poi premi **Aggiorna tutto da Drive** "
                    "nella barra a sinistra.\n\nQuando Quadro lo trova, "
                    "questa pagina diventa modificabile e il pulsante qui "
                    "sotto ci copia dentro le fonti di partenza.")
                st.download_button(
                    "⬇️ Scarica Quadro_Fonti.xlsx",
                    DIARIO.modello_xlsx("Fonti", guida=False),
                    "Quadro_Fonti.xlsx",
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet", type="primary")
        else:
            st.success(f"Fonti e parole chiave su Drive, in "
                       f"**Quadro_Fonti.xlsx** · {len(FONTI)} fonti attive. "
                       "Quello che cambi qui resta.")

        if FILE_FONTI and DOVE_FONTI == "file":
            if st.button("📥 Copia le fonti di partenza nel file su Drive",
                         type="primary"):
                try:
                    salva_fonti(
                        [dict(f, attiva=True) for f in RCFG.get("fonti", [])],
                        RCFG.get("interessi", []), RCFG.get("esclusioni", []))
                    conferma("Fonti copiate su Drive")
                    st.rerun()
                except Exception as e:
                    st.error(f"Non sono riuscito a scrivere: {e}")

        modificabile = (DOVE_FONTI == "drive")

        FT = st.tabs(["📡 Le fonti", "🔤 Parole chiave", "➕ Aggiungi"])

        # ------------------------------- elenco ---------------------------
        with FT[0]:
            in_errore = {n for n, _ in problemi_r}
            righe_f = [{"Attiva": True, "Nome": f["nome"],
                        "Ambito": f.get("tipo", "altro"),
                        "Lingua": f.get("lingua", "en"),
                        "Contenuto": f.get("contenuto", "articolo"),
                        "Indirizzo": f["url"],
                        "Stato": "🔴 non risponde" if f["nome"] in in_errore
                                 else "🟢 ok"} for f in FONTI]
            df_f = pd.DataFrame(righe_f)

            c1, c2 = st.columns([2, 1])
            filtro_f = c1.text_input("Cerca fra le fonti",
                                     placeholder="nome o indirizzo")
            solo_rotte = c2.toggle("Solo quelle che non rispondono")
            vista = df_f
            if filtro_f.strip():
                q = filtro_f.strip().lower()
                vista = vista[vista.apply(
                    lambda r: q in (r["Nome"] + r["Indirizzo"]).lower(), axis=1)]
            if solo_rotte:
                vista = vista[vista["Stato"].str.startswith("🔴")]

            if modificabile:
                st.caption("Togli la spunta per spegnere una fonte senza "
                           "cancellarla. Per eliminarla davvero, seleziona la "
                           "riga col quadratino a sinistra e premi il cestino "
                           "che compare in alto nella tabella.")
                nuova_f = st.data_editor(
                    vista, width='stretch', hide_index=True, num_rows="dynamic",
                    key="editor_fonti", height=430,
                    column_config={
                        "Attiva": st.column_config.CheckboxColumn("On"),
                        "Ambito": st.column_config.SelectboxColumn(
                            options=sorted({f.get("tipo", "altro") for f in FONTI}
                                           | {"maker", "tecnologia", "scienza",
                                              "informatica", "agritech",
                                              "ricerca", "notizie"})),
                        "Lingua": st.column_config.SelectboxColumn(
                            options=["it", "es", "en"]),
                        "Contenuto": st.column_config.SelectboxColumn(
                            options=["articolo", "video", "podcast", "corso"]),
                        "Indirizzo": st.column_config.LinkColumn(),
                        "Stato": st.column_config.TextColumn(disabled=True),
                    })
                if st.button("💾 Salva le fonti", type="primary"):
                    try:
                        salva_fonti(
                            [{"nome": r["Nome"], "url": r["Indirizzo"],
                              "tipo": r["Ambito"], "lingua": r["Lingua"],
                              "contenuto": r["Contenuto"],
                              "attiva": bool(r["Attiva"])}
                             for _, r in nuova_f.iterrows()
                             if str(r["Nome"]).strip() and str(r["Indirizzo"]).strip()],
                            INTERESSI, ESCLUSIONI)
                        conferma("Fonti salvate su Drive")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Non sono riuscito a salvare: {e}")
            else:
                st.dataframe(vista, width='stretch', hide_index=True,
                             height=430,
                             column_config={"Indirizzo":
                                            st.column_config.LinkColumn(
                                                display_text="apri")})

            if problemi_r:
                st.markdown("##### Fonti che non hanno risposto")
                for nome_p, errore_p in problemi_r:
                    st.markdown(f"🔴 **{nome_p}** — {errore_p}")
                st.caption("Un errore isolato capita. Se una resta in rosso "
                           "per giorni ha tolto il feed: spegnila o eliminala.")
            else:
                st.success(f"Tutte e {len(FONTI)} le fonti hanno risposto.")

        # ---------------------------- parole chiave ------------------------
        with FT[1]:
            st.caption("Le parole di sinistra fanno **salire** una voce: nel "
                       "titolo valgono due punti, nel riassunto uno. Quelle "
                       "di destra la fanno **buttare via** comunque. Una per "
                       "riga.")
            p1, p2 = st.columns(2)
            testo_int = p1.text_area("Parole che ti interessano",
                                     "\n".join(INTERESSI), height=360,
                                     disabled=not modificabile)
            testo_esc = p2.text_area("Parole da escludere",
                                     "\n".join(ESCLUSIONI), height=360,
                                     disabled=not modificabile)
            if modificabile and st.button("💾 Salva le parole chiave",
                                          type="primary"):
                try:
                    salva_fonti(
                        [dict(f, attiva=True) for f in FONTI],
                        [x.strip() for x in testo_int.splitlines() if x.strip()],
                        [x.strip() for x in testo_esc.splitlines() if x.strip()])
                    conferma("Parole chiave salvate")
                    st.rerun()
                except Exception as e:
                    st.error(f"Non sono riuscito a salvare: {e}")

            bonus = RCFG.get("bonus_lingua", {})
            st.caption("Punti in più per la lingua: "
                       + ", ".join(f"{NOMI_L.get(k, k)} +{v}"
                                   for k, v in bonus.items() if v)
                       + ". Si cambiano in `radar.json`, campo `bonus_lingua`.")

        # ------------------------------ aggiungi ---------------------------
        with FT[2]:
            if not modificabile:
                st.info("Per aggiungere fonti dall'interfaccia serve prima il "
                        "file su Drive: le istruzioni sono in cima a questa "
                        "pagina.")
            else:
                st.markdown("##### Una fonte alla volta")
                with st.form("nuova_fonte"):
                    n1, n2 = st.columns([2, 3])
                    nome_nf = n1.text_input("Come si chiama")
                    url_nf = n2.text_input("Indirizzo del feed RSS",
                                           placeholder="https://.../feed/")
                    n3, n4, n5 = st.columns(3)
                    amb_nf = n3.selectbox("Ambito",
                                          ["maker", "tecnologia", "scienza",
                                           "informatica", "agritech",
                                           "ricerca", "notizie"])
                    lin_nf = n4.selectbox("Lingua", ["it", "es", "en"])
                    con_nf = n5.selectbox("Contenuto",
                                          ["articolo", "video", "podcast",
                                           "corso"])
                    prova_nf = st.form_submit_button("🔎 Prova e aggiungi",
                                                     type="primary")
                if prova_nf:
                    if not (nome_nf.strip() and url_nf.strip()):
                        st.warning("Servono nome e indirizzo.")
                    else:
                        try:
                            with st.spinner("Provo l'indirizzo…"):
                                prova_voci = RAD.leggi_feed(
                                    RAD._scarica(url_nf.strip()), nome_nf.strip())
                            if not prova_voci:
                                st.error("L'indirizzo risponde ma non contiene "
                                         "un elenco leggibile: probabilmente "
                                         "non è un feed RSS.")
                            else:
                                salva_fonti(
                                    [dict(f, attiva=True) for f in FONTI]
                                    + [{"nome": nome_nf.strip(),
                                        "url": url_nf.strip(), "tipo": amb_nf,
                                        "lingua": lin_nf, "contenuto": con_nf,
                                        "attiva": True}],
                                    INTERESSI, ESCLUSIONI)
                                conferma(f"«{nome_nf.strip()}» aggiunta "
                                         f"({len(prova_voci)} voci trovate)")
                                st.rerun()
                        except Exception as e:
                            st.error(f"L'indirizzo non risponde: {e}")

                st.divider()
                st.markdown("##### Un canale YouTube, dal suo indirizzo")
                st.caption("Incolla il link del canale, quello con «@nome» oppure "
                           "quello con «/channel/UC…». Quadro trova il feed e il "
                           "nome da solo.")
                with st.form("nuovo_canale_yt", clear_on_submit=True):
                    y1, y2 = st.columns([3, 1])
                    url_yt = y1.text_input("Indirizzo del canale",
                                           placeholder="https://www.youtube.com/@nomecanale")
                    amb_yt1 = y2.selectbox("Ambito", ["maker", "tecnologia", "scienza",
                                                      "informatica", "agritech",
                                                      "ricerca"])
                    if st.form_submit_button("🔎 Trova e aggiungi", type="primary"):
                        if not url_yt.strip():
                            st.warning("Incolla l'indirizzo del canale.")
                        else:
                            try:
                                with st.spinner("Cerco il canale…"):
                                    nome_yt1, url_feed_yt, n_yt = RAD.canale_youtube(
                                        url_yt.strip())
                                if n_yt == 0:
                                    st.error("Ho trovato il canale, ma il feed non "
                                             "contiene video.")
                                else:
                                    salva_fonti(
                                        [dict(f, attiva=True) for f in FONTI]
                                        + [{"nome": f"YouTube — {nome_yt1}",
                                            "url": url_feed_yt, "tipo": amb_yt1,
                                            "lingua": "?", "contenuto": "video",
                                            "attiva": True}],
                                        INTERESSI, ESCLUSIONI)
                                    conferma(f"«{nome_yt1}» aggiunto ({n_yt} video trovati)")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Non riesco ad aggiungere il canale: {e}")

                st.divider()
                st.markdown("##### I canali YouTube che segui, tutti insieme")
                st.caption("Su **Google Takeout** chiedi l'esportazione di "
                           "YouTube limitata alle iscrizioni: ti arriva un "
                           "file `subscriptions.csv`. Caricalo qui e ogni "
                           "canale diventa una fonte. Niente accessi, niente "
                           "password: il collegamento al feed dei video "
                           "YouTube lo pubblica per tutti i canali.")
                csv_yt = st.file_uploader("subscriptions.csv", type=["csv"])
                if csv_yt is not None:
                    import csv as _csv
                    import io as _io
                    testo_csv = csv_yt.getvalue().decode("utf-8", "replace")
                    lettore = _csv.reader(_io.StringIO(testo_csv))
                    canali = []
                    for riga_c in lettore:
                        if len(riga_c) < 3 or not riga_c[0].startswith("UC"):
                            continue
                        canali.append((riga_c[2].strip() or riga_c[0],
                                       riga_c[0].strip()))
                    if not canali:
                        st.error("Non ho trovato canali in questo file. "
                                 "Dev'essere il `subscriptions.csv` di "
                                 "Takeout, con l'identificativo del canale "
                                 "nella prima colonna.")
                    else:
                        st.success(f"Trovati {len(canali)} canali.")
                        scelti_yt = st.multiselect(
                            "Quali aggiungere", [c[0] for c in canali],
                            default=[c[0] for c in canali[:20]])
                        amb_yt = st.selectbox(
                            "Che ambito dare a questi canali",
                            ["maker", "tecnologia", "scienza", "informatica",
                             "agritech", "ricerca"], key="amb_yt")
                        if st.button("➕ Aggiungi i canali scelti",
                                     type="primary"):
                            nuovi = [
                                {"nome": f"YouTube — {nome_c}",
                                 "url": "https://www.youtube.com/feeds/"
                                        f"videos.xml?channel_id={id_c}",
                                 "tipo": amb_yt, "lingua": "?",
                                 "contenuto": "video", "attiva": True}
                                for nome_c, id_c in canali
                                if nome_c in scelti_yt]
                            try:
                                salva_fonti(
                                    [dict(f, attiva=True) for f in FONTI] + nuovi,
                                    INTERESSI, ESCLUSIONI)
                                conferma(f"Aggiunti {len(nuovi)} canali")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Non sono riuscito a salvare: {e}")

                st.divider()
                st.markdown("##### I podcast che segui")
                st.caption("Quasi tutte le app di podcast esportano un file "
                           "**OPML** con gli abbonamenti: cercalo nelle loro "
                           "impostazioni, di solito sotto «esporta».")
                opml = st.file_uploader("Il file OPML", type=["opml", "xml"])
                if opml is not None:
                    import re as _re
                    testo_o = opml.getvalue().decode("utf-8", "replace")
                    trovati = _re.findall(
                        r'<outline[^>]*text="([^"]*)"[^>]*xmlUrl="([^"]*)"',
                        testo_o) or _re.findall(
                        r'<outline[^>]*xmlUrl="([^"]*)"[^>]*text="([^"]*)"',
                        testo_o)
                    if not trovati:
                        st.error("Non ho trovato abbonamenti in questo file.")
                    else:
                        st.success(f"Trovati {len(trovati)} podcast.")
                        scelti_po = st.multiselect(
                            "Quali aggiungere", [t[0] for t in trovati],
                            default=[t[0] for t in trovati[:20]])
                        if st.button("➕ Aggiungi i podcast scelti",
                                     type="primary"):
                            nuovi = [{"nome": f"Podcast — {n}", "url": u,
                                      "tipo": "scienza", "lingua": "?",
                                      "contenuto": "podcast", "attiva": True}
                                     for n, u in trovati if n in scelti_po]
                            try:
                                salva_fonti(
                                    [dict(f, attiva=True) for f in FONTI] + nuovi,
                                    INTERESSI, ESCLUSIONI)
                                conferma(f"Aggiunti {len(nuovi)} podcast")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Non sono riuscito a salvare: {e}")

    # -------------------------------- bandi e agevolazioni -------------------
    # Le notizie si cercano su Google Notizie: ogni volta che premi «Cerca
    # adesso» si leggono le più recenti su ogni ricerca di bandi.json. Non è
    # un controllo automatico: lo fai tu quando apri la pagina, e una volta
    # a settimana basta per non perdere niente.
    with RT[7]:
        BANDI = _carica_json("bandi.json", _mtime("bandi.json"))
        if "_errore" in BANDI:
            st.error(f"Non riesco a leggere `bandi.json`: {BANDI['_errore']}")
        else:
            st.caption(BANDI.get("_nota", ""))
            ricerche_b = list(BANDI.get("ricerche", []))
            zona_b = [z.lower() for z in BANDI.get("zona_vicina", [])]

            cb1, cb2 = st.columns([3, 1])
            cb1.markdown("**Prima le notizie di oggi su bandi e incentivi**, poi le "
                         "pagine ufficiali da tenere d'occhio.")
            if cb2.button("🔄 Cerca adesso", type="primary", width='stretch'):
                with st.spinner("Cerco le notizie sui bandi…"):
                    st.session_state["bandi_voci"] = RAD.cerca_notizie(ricerche_b, giorni=30)
                    st.session_state["bandi_ora"] = DIARIO.adesso()

            voci_b = st.session_state.get("bandi_voci")
            if voci_b is None:
                st.info("Premi «Cerca adesso»: prende le notizie più recenti su "
                        "ognuna delle ricerche della lista.")
            elif not voci_b:
                st.warning("Nessuna notizia sui bandi negli ultimi 30 giorni. "
                           "Può essere che non ci sia niente di nuovo, oppure che "
                           "Google Notizie non abbia risposto: riprova tra un "
                           "po' e, se resta vuoto, dimmelo.")
            else:
                for v in voci_b:
                    v["vicino"] = any(z in (v["titolo"] + " " + v["testo"]).lower()
                                      for z in zona_b)
                solo_vicino = st.toggle("Solo quelle vicino a me (Vallo di Diano, "
                                        "Salerno, Campania…)", value=True,
                                        key="bandi_vicino")
                mostra_b = [v for v in voci_b if v["vicino"]] if solo_vicino else voci_b
                ora_b = st.session_state.get("bandi_ora")
                st.caption(f"Aggiornato alle {ora_b:%d/%m %H:%M} · "
                           f"{len(mostra_b)} notizie"
                           if ora_b else f"{len(mostra_b)} notizie")
                if not mostra_b:
                    st.info("Niente di vicino a te in questo momento. Togli il "
                            "filtro per vedere il nazionale.")
                for v in mostra_b[:40]:
                    with st.container(border=True):
                        b1, b2 = st.columns([5, 1])
                        quando_b = f"{v['data']:%d/%m/%Y}" if v["data"] else "—"
                        b1.markdown(("📍 " if v["vicino"] else "") + f"**{v['titolo']}**")
                        b1.caption(f"{v['fonte']} · {quando_b}")
                        if v["link"]:
                            b2.link_button("Apri ↗", v["link"], width='stretch')
                        pulsante_ascolta(f"{v['titolo']}. {v['testo']}")

            st.divider()
            st.markdown("##### Pagine ufficiali da tenere d'occhio")
            zone_ord = ["Locale", "Provincia", "Regione", "Nazionale", "Europa"]
            tutte_zone = {p.get("zona", "") for p in BANDI.get("pagine", [])}
            for z in [z for z in zone_ord if z in tutte_zone] + sorted(tutte_zone - set(zone_ord)):
                st.markdown(f"###### {z}")
                for p in BANDI.get("pagine", []):
                    if p.get("zona", "") != z:
                        continue
                    with st.container(border=True):
                        p1, p2 = st.columns([4, 1])
                        p1.markdown(f"**{p['nome']}**")
                        if p.get("nota"):
                            p1.caption(p["nota"])
                        p2.link_button("Apri ↗", p["url"], width='stretch')

# ============================================================================
# TAB 11 - EQUILIBRIO  (respiro, presenza, leggimelo, aforismi, stile di vita,
#                      crescita: tutto il codice sta in equilibrio.py)
# ============================================================================
with TAB[11]:
    mostra_conferma()
    EQ.mostra(CTX)

# ============================================================================
# TAB 12 - TARATURA  (sezione riservata: vedi taratura.py per la password)
# ============================================================================
with TAB[12]:
    import taratura as TAR

    SBLOCCO = "tar_aperta_alle"
    if TAR.scaduta(st.session_state.get(SBLOCCO)):
        st.session_state.pop(SBLOCCO, None)

    if SBLOCCO not in st.session_state:
        st.markdown("#### ⚙️ Taratura")
        st.caption("Sezione riservata.")
        with st.form("tar_ingresso"):
            pw = st.text_input("Password", type="password",
                               label_visibility="collapsed",
                               placeholder="Password")
            entra = st.form_submit_button("Apri", type="primary")
        if entra:
            if TAR.password_giusta(pw, secret("taratura_password", "")):
                st.session_state[SBLOCCO] = DIARIO.adesso()
                st.rerun()
            else:
                st.error("Password errata.")
    else:
        # ---- l'archivio separato, così non si mescola con il resto ----------
        @st.cache_data(ttl=120, show_spinner=False)
        def _cerca_file_taratura(_segno):
            if not SA:
                return None
            cartelle = [secret("drive_folder_id_taratura", ""),
                        secret("drive_folder_id_diario", ""),
                        secret("drive_folder_id_progetti", ""),
                        secret("drive_folder_id", "")]
            try:
                return DIARIO.trova_file(dict(SA), cartelle, "Quadro_Taratura.xlsx")
            except Exception:
                return None

        FILE_TAR = _cerca_file_taratura(st.session_state.get("cerca_archivio", 0))

        @st.cache_data(ttl=30, show_spinner=False)
        def _leggi_taratura(_f, _segno):
            return DIARIO.leggi_xlsx(dict(SA), _f)

        def taratura_corrente():
            if not FILE_TAR:
                return st.session_state.get("tar_locale", DIARIO.vuoto())
            try:
                return _leggi_taratura(FILE_TAR,
                                       st.session_state.get("tar_segno", 0))
            except Exception:
                return st.session_state.get("tar_locale", DIARIO.vuoto())

        def taratura_scrivi(r):
            if FILE_TAR:
                try:
                    DIARIO.aggiungi_xlsx(dict(SA), FILE_TAR, [r])
                    st.session_state["tar_segno"] = st.session_state.get("tar_segno", 0) + 1
                    return True
                except Exception as e:
                    st.warning(f"Non sono riuscito a scrivere nell'archivio: {e}")
            loc = st.session_state.get("tar_locale", DIARIO.vuoto())
            st.session_state["tar_locale"] = DIARIO._sistema(
                pd.concat([loc, pd.DataFrame([r])], ignore_index=True))
            return False

        TARD = taratura_corrente()
        voci_tar = TARD[TARD["Tipo"] == "voce"].sort_values("Data", ascending=False)

        t_alto = st.columns([4, 1])
        t_alto[0].markdown("#### ⚙️ Taratura")
        if t_alto[1].button("🔒 Chiudi", width='stretch'):
            st.session_state.pop(SBLOCCO, None)
            st.rerun()
        st.caption(f"Aperta per {TAR.MINUTI_DI_APERTURA} minuti, poi si "
                   "richiude da sola e la password va ridigitata.")

        if not FILE_TAR:
            st.warning("**Archivio non collegato**: quello che scrivi adesso "
                       "resta solo in questa sessione.")
            with st.expander("Come collegarlo"):
                st.markdown(
                    "Scarica il file qui sotto e caricalo in una cartella di "
                    "Drive **tua, condivisa solo con il service account come "
                    "Editor** — non in una cartella che condividi con altri. "
                    "Se la metti in una cartella a parte, aggiungi nei Secrets "
                    "`drive_folder_id_taratura` con il suo ID.\n\n"
                    "È un file separato dal diario normale apposta: quello che "
                    "scrivi qui non si mescola con le sessioni di studio.")
                if st.button("🔄 Ho appena caricato il file: cercalo di nuovo",
                             key="ricerca_tar"):
                    st.cache_data.clear()
                    st.session_state["cerca_archivio"] = st.session_state.get("cerca_archivio", 0) + 1
                    st.rerun()
                st.download_button("⬇️ Scarica Quadro_Taratura.xlsx",
                                   DIARIO.modello_xlsx("Taratura", guida=False),
                                   "Quadro_Taratura.xlsx",
                                   "application/vnd.openxmlformats-officedocument."
                                   "spreadsheetml.sheet", type="primary")

        mostra_conferma()
        pannello_riepilogo('taratura')
        TT = st.tabs(["✍️ Oggi", "🧘 Benessere", "📖 Quello che hai scritto",
                      "📈 Andamento"])

        # ------------------------------ oggi --------------------------------
        with TT[0]:
            chat_t = st.session_state.setdefault("tar_chat", [])

            if not chat_t:
                umore = st.slider("Come stai oggi, da 1 a 10", 1, 10, 6,
                                  help="1 = giornata pessima · 10 = ottima")
                st.session_state["tar_umore"] = umore
                testo_tar = VOCE.campo(
                    "Scrivi quello che vuoi", "tar_testo",
                    chiave_ai(), modello_ai(), altezza=220,
                    suggerimento="Cosa è successo, cosa ti è rimasto addosso, "
                                 "cosa è andato meglio di quanto pensassi. "
                                 "Non deve essere ordinato.")

                b1, b2 = st.columns(2)
                if b1.button("💾 Salva e basta", width='stretch'):
                    if testo_tar.strip():
                        dove_ok = taratura_scrivi(DIARIO.riga(
                            "voce", "diario", "", 0, umore, testo_tar.strip()))
                        conferma("Voce salvata nel tuo archivio" if dove_ok
                                 else "Voce salvata solo in questa sessione")
                        VOCE.svuota("tar_testo")
                        st.rerun()
                    else:
                        st.warning("Scrivi qualcosa prima di salvare.")

                if b2.button("💬 Salva e parlane", width='stretch',
                             type="primary"):
                    if not testo_tar.strip():
                        st.warning("Scrivi qualcosa prima.")
                    else:
                        taratura_scrivi(DIARIO.riga(
                            "voce", "diario", "", 0, umore, testo_tar.strip()))
                        st.session_state["tar_chat"] = [("io", testo_tar.strip())]
                        st.session_state["tar_rispondi"] = True
                        VOCE.svuota("tar_testo")
                        st.rerun()
            else:
                umore = st.session_state.get("tar_umore", 6)
                c1, c2 = st.columns([3, 1])
                c1.caption(f"Conversazione di oggi · umore {umore}/10")
                if c2.button("✖️ Chiudi", width='stretch'):
                    st.session_state.pop("tar_chat", None)
                    st.rerun()

            # ---- la risposta, quando è il suo turno -------------------------
            if st.session_state.pop("tar_rispondi", False):
                storico = [(r["Data"], r["Valore"], r["Nota"])
                           for _, r in voci_tar.head(5).iterrows()]
                scambio = "\n\n".join(
                    ("Lui: " if r == "io" else "Tu: ") + t
                    for r, t in st.session_state["tar_chat"][-8:])
                stato_t = st.empty()
                try:
                    with st.spinner("Sto leggendo…"):
                        risp_t = AI.chiedi(
                            TAR.prompt(scambio, umore, storico,
                                       contesto="Questa è una conversazione "
                                                "che sta andando avanti: "
                                                "rispondi all'ultima cosa che "
                                                "ti ha detto, non "
                                                "ricominciare da capo."),
                            chiave_ai(), modello_ai(),
                            al_tentativo=lambda m: stato_t.info(m))
                    stato_t.empty()
                    st.session_state["tar_chat"].append(("ai", risp_t))
                except AI.ErroreAI as e:
                    stato_t.empty()
                    st.error(e.messaggio)
                    if e.dettaglio:
                        st.caption(e.dettaglio)

            # ---- la conversazione -------------------------------------------
            if chat_t:
                for ruolo, testo_c in chat_t:
                    with st.chat_message("user" if ruolo == "io"
                                         else "assistant"):
                        st.markdown(testo_c)

                segue_t = st.chat_input("Scrivi…", key="tar_chat_input")
                if segue_t:
                    chat_t.append(("io", segue_t))
                    st.session_state["tar_chat"] = chat_t
                    st.session_state["tar_rispondi"] = True
                    st.rerun()

                st.caption("Questo è un interlocutore, non uno psicologo. Se "
                           "una cosa pesa e non si muove, parlarne con una "
                           "persona vera vale più di qualsiasi schermo.")

                s1, s2 = st.columns(2)
                if s1.button("💾 Salva tutta la conversazione",
                             width='stretch', type="primary"):
                    testo_tot = "\n\n".join(
                        ("IO: " if r == "io" else "AI: ") + t for r, t in chat_t)
                    taratura_scrivi(DIARIO.riga(
                        "conversazione", "diario", "", 0, umore, testo_tot))
                    conferma("Conversazione salvata")
                    st.session_state.pop("tar_chat", None)
                    st.rerun()
                if s2.button("🗑️ Scarta la conversazione", width='stretch',
                             help="La prima cosa che hai scritto resta "
                                  "salvata: si butta solo lo scambio."):
                    st.session_state.pop("tar_chat", None)
                    st.rerun()

        # --------------------------- benessere ------------------------------
        with TT[1]:
            st.caption("Pratica, appuntamenti e promemoria dei medicinali, in "
                       "un posto solo e sotto la stessa password. Serve a te "
                       "per vedere l'andamento nel tempo, e serve da portare a "
                       "chi ti segue: sotto trovi come scaricarlo.")

            BB = st.radio("Cosa registri", ["Pratica", "Appuntamento",
                                            "Medicinali"],
                          horizontal=True, label_visibility="collapsed",
                          key="tar_benessere_sezione")

            # ---------------------------- pratica ---------------------------
            if BB == "Pratica":
                with st.form("tar_pratica", clear_on_submit=True):
                    p1, p2 = st.columns([2, 1])
                    tipo_p = p1.selectbox("Cosa hai fatto", TAR.PRATICHE)
                    min_p = p2.number_input("Minuti", 5, 300, 60, step=5)
                    q1, q2 = st.columns(2)
                    qual_p = q1.slider("Com'è andata", 1, 5, 3,
                                       help="1 faticosa · 5 ottima")
                    calma_p = q2.slider("Quanto eri presente", 1, 5, 3,
                                        help="quanto sei riuscito a stare lì "
                                             "invece che altrove con la testa")
                    nota_p = st.text_input("Una riga (facoltativa)",
                                           placeholder="com'era il corpo, cosa "
                                                       "hai notato")
                    if st.form_submit_button("💾 Registra la pratica",
                                             type="primary"):
                        taratura_scrivi(DIARIO.riga(
                            "pratica", tipo_p, "", min_p, qual_p,
                            f"[presenza {calma_p}/5] {nota_p.strip()}"))
                        conferma(f"{tipo_p}: {min_p} minuti registrati")
                        st.rerun()

                prat = TARD[TARD["Tipo"] == "pratica"].sort_values("Data")
                if prat.empty:
                    st.info("Nessuna pratica registrata finora.")
                else:
                    w1, w2, w3 = st.columns(3)
                    w1.metric("Sedute", len(prat))
                    w2.metric("Ore in tutto", f"{prat['Minuti'].sum() / 60:.1f}")
                    w3.metric("Qualità media", f"{prat['Valore'].mean():.1f}/5")

                    per_mese = prat.groupby(
                        prat["Data"].dt.to_period("M").dt.to_timestamp())["Minuti"].sum()
                    figw = go.Figure()
                    figw.add_bar(x=per_mese.index, y=per_mese.values / 60,
                                 marker=dict(color=PALETTE[0], line=dict(width=0)),
                                 hovertemplate="%{x|%m/%Y}<br>%{y:.1f} ore<extra></extra>")
                    st.plotly_chart(style(figw, 280, "Ore di pratica al mese"),
                                    width='stretch')

                    tab_w = prat[["Data", "Attivita", "Minuti", "Valore", "Nota"]].copy()
                    tab_w["Data"] = tab_w["Data"].dt.strftime("%d/%m/%Y")
                    tab_w = tab_w.rename(columns={"Attivita": "Pratica",
                                                  "Valore": "Qualità"})
                    with st.expander("Tutte le sedute"):
                        st.dataframe(tab_w, width='stretch', hide_index=True)
                    scarica_tabella(tab_w, "pratica_benessere",
                                    "⬇️ Scarica le pratiche")

            # ------------------------- appuntamenti -------------------------
            elif BB == "Appuntamento":
                st.caption("Qui si annota **che** c'è stato un incontro e come "
                           "ti sei sentito prima e dopo. Di cosa avete parlato "
                           "scrivilo nella scheda Oggi, se ti va: questa serve "
                           "a vedere l'andamento.")
                with st.form("tar_seduta", clear_on_submit=True):
                    s1, s2 = st.columns([2, 1])
                    chi_s = s1.text_input("Con chi", placeholder="es. dott. ___")
                    quando_s = s2.date_input("Quando", value=DIARIO.oggi(),
                                             format="DD/MM/YYYY")
                    u1, u2 = st.columns(2)
                    prima_s = u1.slider("Come stavi prima", 1, 10, 5)
                    dopo_s = u2.slider("Come stavi dopo", 1, 10, 6)
                    nota_s = st.text_input("Una riga per ricordartene",
                                           placeholder="facoltativa")
                    if st.form_submit_button("💾 Registra l'incontro",
                                             type="primary"):
                        taratura_scrivi(DIARIO.riga(
                            "seduta", (chi_s.strip() or "incontro"), "", 0,
                            dopo_s - prima_s,
                            f"prima {prima_s} · dopo {dopo_s} · {nota_s.strip()}",
                            quando=dt.datetime.combine(quando_s,
                                                       dt.time(12, 0))))
                        conferma("Incontro registrato")
                        st.rerun()

                sed = TARD[TARD["Tipo"] == "seduta"].sort_values("Data")
                if sed.empty:
                    st.info("Nessun incontro registrato finora.")
                else:
                    y1, y2 = st.columns(2)
                    y1.metric("Incontri", len(sed))
                    y2.metric("Variazione media",
                              f"{sed['Valore'].mean():+.1f}",
                              help="quanto cambia come stai fra prima e dopo")
                    figs2 = go.Figure()
                    figs2.add_bar(x=sed["Data"], y=sed["Valore"],
                                  marker=dict(color=[VERDE if v >= 0 else "#C0392B"
                                                     for v in sed["Valore"]],
                                              line=dict(width=0)),
                                  hovertemplate="%{x|%d/%m/%Y}<br>%{y:+.0f}<extra></extra>")
                    st.plotly_chart(
                        style(figs2, 260, "Quanto cambia come stai, prima → dopo"),
                        width='stretch')
                    tab_s2 = sed[["Data", "Attivita", "Valore", "Nota"]].copy()
                    tab_s2["Data"] = tab_s2["Data"].dt.strftime("%d/%m/%Y")
                    tab_s2 = tab_s2.rename(columns={"Attivita": "Con chi",
                                                    "Valore": "Differenza"})
                    scarica_tabella(tab_s2, "incontri", "⬇️ Scarica gli incontri")

            # --------------------------- medicinali -------------------------
            else:
                st.info("**Questo è un promemoria, non un consiglio.** Serve a "
                        "segnare cosa hai preso e quando, così quando vai "
                        "dallo specialista non devi ricordartelo a memoria. "
                        "L'assistente di questa sezione non commenta "
                        "medicinali, dosi o effetti: su quello la persona da "
                        "sentire è chi te li ha prescritti.")
                with st.form("tar_farmaco", clear_on_submit=True):
                    f1, f2 = st.columns([2, 1])
                    nome_f = f1.text_input(
                        "Cosa",
                        placeholder="il nome o anche solo «quella della sera»")
                    quando_f = f2.date_input("Quando", value=DIARIO.oggi(),
                                             format="DD/MM/YYYY")
                    preso_f = st.radio("Preso?", ["Sì", "No", "In ritardo"],
                                       horizontal=True)
                    nota_f = st.text_input("Nota per lo specialista",
                                           placeholder="facoltativa")
                    if st.form_submit_button("💾 Segna", type="primary"):
                        if nome_f.strip():
                            taratura_scrivi(DIARIO.riga(
                                "medicinale", nome_f.strip(), preso_f, 0,
                                {"Sì": 1, "In ritardo": 0.5, "No": 0}[preso_f],
                                nota_f.strip(),
                                quando=dt.datetime.combine(quando_f,
                                                           dt.time(12, 0))))
                            conferma(f"Segnato: {nome_f.strip()} — {preso_f}")
                            st.rerun()
                        else:
                            st.warning("Scrivi almeno un nome.")

                med = TARD[TARD["Tipo"] == "medicinale"].sort_values("Data")
                if med.empty:
                    st.info("Niente segnato finora.")
                else:
                    ultimi = med[med["Data"] >= pd.Timestamp(DIARIO.oggi())
                                 - pd.Timedelta(days=29)]
                    z1, z2 = st.columns(2)
                    z1.metric("Segnati in 30 giorni", len(ultimi))
                    if not ultimi.empty:
                        z2.metric("Presi regolarmente",
                                  f"{100 * ultimi['Valore'].mean():.0f}%")
                    tab_m = med[["Data", "Attivita", "Strumento", "Nota"]].copy()
                    tab_m["Data"] = tab_m["Data"].dt.strftime("%d/%m/%Y")
                    tab_m = tab_m.rename(columns={"Attivita": "Cosa",
                                                  "Strumento": "Preso"})
                    with st.expander("Tutto quello che hai segnato"):
                        st.dataframe(tab_m, width='stretch', hide_index=True)
                    scarica_tabella(tab_m, "promemoria_medicinali",
                                    "⬇️ Scarica da portare allo specialista")
        # --------------------------- lo storico -----------------------------
        with TT[2]:
            if voci_tar.empty:
                st.info("Ancora niente. La prima volta è la più difficile.")
            else:
                cerca_t = st.text_input("Cerca fra quello che hai scritto",
                                        placeholder="una parola qualsiasi")
                mostra = voci_tar
                if cerca_t.strip():
                    mostra = mostra[mostra["Nota"].str.contains(
                        cerca_t.strip(), case=False, na=False)]
                    st.caption(f"{len(mostra)} voci su {len(voci_tar)}")
                for _, r in mostra.head(60).iterrows():
                    with st.expander(f"{r['Data']:%d/%m/%Y} · umore "
                                     f"{r['Valore']:.0f}/10 — {r['Nota'][:60]}…"):
                        st.markdown(r["Nota"])

        # --------------------------- andamento ------------------------------
        with TT[3]:
            if len(voci_tar) < 2:
                st.info("Servono almeno due voci per vedere un andamento.")
            else:
                ordinate = voci_tar.sort_values("Data")
                figt = go.Figure()
                figt.add_scatter(x=ordinate["Data"], y=ordinate["Valore"],
                                 mode="lines+markers", name="umore",
                                 line=dict(color=PALETTE[0], width=2),
                                 hovertemplate="%{x|%d/%m/%Y}<br>%{y:.0f}/10<extra></extra>")
                if len(ordinate) >= 5:
                    mm = ordinate["Valore"].rolling(5, min_periods=1).mean()
                    figt.add_scatter(x=ordinate["Data"], y=mm, mode="lines",
                                     name="media su 5",
                                     line=dict(color=VERDE_SCURO, width=2, dash="dot"))
                figt.update_yaxes(range=[0, 10.5])
                st.plotly_chart(style(figt, 300, "Come sei stato"),
                                width='stretch')

                ris = TAR.riassunto_periodo(
                    [(r["Data"], r["Valore"], r["Nota"])
                     for _, r in voci_tar.iterrows()])
                if ris:
                    q = st.columns(3)
                    q[0].metric("Voci scritte", ris["voci"])
                    q[1].metric("Media ultime 7", f"{ris['media_recente']:.1f}/10")
                    q[2].metric("Media precedente", f"{ris['media_prima']:.1f}/10")
                    delta = ris["media_recente"] - ris["media_prima"]
                    if abs(delta) >= 0.8:
                        st.markdown(
                            ("🟢 &nbsp;Le ultime giornate stanno andando meglio "
                             f"di prima, di {delta:+.1f} punti in media."
                             if delta > 0 else
                             "🟡 &nbsp;Le ultime giornate sono più pesanti della "
                             f"media precedente, di {delta:+.1f} punti. Se "
                             "continua, vale la pena parlarne con qualcuno."),
                            unsafe_allow_html=True)

# ============================================================================
# TAB 5 - LAVORO  (clienti, fatture e scadenze: da freelance)
# ============================================================================
with TAB[5]:
    import lavoro as LAV

    mostra_conferma()
    st.markdown("#### 💼 Lavoro")
    st.caption("Clienti, preventivi, fatture e scadenze in un posto solo. Ogni "
               "cambiamento aggiunge una riga al diario: non si perde niente, "
               "e vince sempre l'ultima.")

    oggi_l = DIARIO.oggi()
    CLI = LAV.clienti(DIA)
    FAT = LAV.fatture(DIA)
    SCA = LAV.scadenze(DIA, oggi_l, giorni=60)
    OBI = LAV.obiettivo(DIA)

    def _eur(x):
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _scrivi_lavoro(riga_l, messaggio):
        diario_scrivi(riga_l)
        conferma(messaggio)
        st.rerun()

    LT = st.tabs(["📊 Il mese", "👥 Clienti", "🧾 Fatture", "⏰ Scadenze"])

    # ----------------------------------------------------------- il mese ---
    with LT[0]:
        fatt_m = LAV.fatturato_mese(DIA, oggi_l.year, oggi_l.month)
        inc_m = LAV.mese_di(DIA, "incasso", oggi_l.year, oggi_l.month)
        da_inc = LAV.da_incassare(FAT)
        m1, m2, m3 = st.columns(3)
        m1.metric("Fatturato questo mese", f"{_eur(fatt_m)} €")
        m2.metric("Incassato questo mese", f"{_eur(inc_m)} €")
        m3.metric("Ancora da incassare", f"{_eur(da_inc)} €")

        # quanto rende davvero un'ora: spesso non è il cliente che paga di più
        VO = LAV.valore_orario(FAT)
        if not VO.empty:
            with st.expander("💶 Quanto guadagni davvero all'ora, cliente per cliente", expanded=True):
                tot_e, tot_h = VO["Fatturato"].sum(), VO["Ore"].sum()
                st.metric("In media", f"{_eur(tot_e / tot_h)} € all'ora",
                          help="Fatturato diviso le ore scritte nelle fatture")
                st.dataframe(VO, hide_index=True, width='stretch', column_config={
                    "Fatturato": st.column_config.NumberColumn(format="%.0f €"),
                    "Euro all'ora": st.column_config.NumberColumn(format="%.2f €/h")})
                st.caption("Contano solo le fatture con le ore scritte. Se un cliente rende molto meno "
                           "degli altri, è il primo da rinegoziare.")

        if OBI > 0:
            st.progress(min(fatt_m / OBI, 1.0),
                        text=f"Obiettivo del mese {_eur(OBI)} € · fatturato "
                             f"{fatt_m / OBI * 100:.0f}%")

        avvisi = []
        scaduti_l = LAV.richiami_scaduti(CLI, oggi_l)
        if not scaduti_l.empty:
            avvisi.append("Da richiamare: " + ", ".join(scaduti_l["Cliente"].astype(str)))
        if not SCA.empty and (SCA["Quando"] <= oggi_l + dt.timedelta(days=7)).any():
            avvisi.append("Scadenze entro una settimana: " + ", ".join(
                SCA[SCA["Quando"] <= oggi_l + dt.timedelta(days=7)]["Cosa"].astype(str)))
        if not FAT.empty and FAT["Aperta"].any():
            scadute = FAT[FAT["Aperta"] & FAT["Scadenza"].notna()
                          & (FAT["Scadenza"] < oggi_l)]
            if not scadute.empty:
                avvisi.append(f"Fatture non pagate oltre la scadenza: {len(scadute)}")
        for a in avvisi:
            st.warning(a)

        with st.form("obiettivo_lav"):
            ob_nuovo = st.number_input("Quanto vuoi fatturare al mese (€)",
                                       min_value=0.0, value=float(OBI), step=100.0,
                                       help="0 vuol dire non impostato.")
            if st.form_submit_button("💾 Salva l'obiettivo"):
                _scrivi_lavoro(DIARIO.riga("obiettivo", "Obiettivo", "", 0,
                                           float(ob_nuovo), "entrata mensile"),
                               "Obiettivo salvato")

    # ---------------------------------------------------------- clienti ---
    with LT[1]:
        mostra_chiusi = st.toggle("Mostra anche i persi", value=False, key="lav_chiusi")
        vista_c = CLI if mostra_chiusi else CLI[CLI["Stato"] != "perso"] if not CLI.empty else CLI
        if vista_c.empty:
            st.caption("Ancora nessun cliente. Aggiungine uno qui sotto.")
        else:
            st.dataframe(vista_c, width='stretch', hide_index=True,
                         column_config={
                             "Importo": st.column_config.NumberColumn("Importo", format="%.0f €"),
                             "Richiamo": st.column_config.DateColumn("Richiamo", format="DD/MM/YYYY"),
                         })

        st.markdown("##### Aggiungi o aggiorna un cliente")
        st.caption("Scrivi il nome di un cliente già in elenco per cambiarne lo stato.")
        with st.form("cliente_nuovo", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            nome_c = c1.text_input("Cliente")
            stato_c = c2.selectbox("Stato", LAV.STATI_CLIENTE)
            c3, c4, c5 = st.columns([2, 1, 1])
            passo_c = c3.text_input("Prossimo passo", placeholder="es. inviare il preventivo rivisto")
            importo_c = c4.number_input("Importo stimato (€)", min_value=0.0, step=100.0)
            richiamo_c = c5.date_input("Richiamo", value=oggi_l + dt.timedelta(days=7),
                                       format="DD/MM/YYYY")
            if st.form_submit_button("💾 Salva", type="primary"):
                if nome_c.strip():
                    _scrivi_lavoro(DIARIO.riga(
                        "cliente", nome_c.strip()[:80], stato_c, 0, float(importo_c),
                        f"{passo_c.strip()} :: {richiamo_c:%Y-%m-%d}"),
                        f"Cliente aggiornato: {nome_c.strip()}")
                else:
                    st.warning("Serve il nome del cliente.")

    # ---------------------------------------------------------- fatture ---
    with LT[2]:
        st.markdown("##### Fatture aperte")
        aperte_f = FAT[FAT["Aperta"]] if not FAT.empty else FAT
        if aperte_f.empty:
            st.caption("Nessuna fattura aperta.")
        for i_f, r_f in aperte_f.iterrows():
            with st.container(border=True):
                x1, x2 = st.columns([4, 1])
                resto_f = float(r_f["Importo"] - r_f["Incassato"])
                scad_f = (f" · pagamento entro {r_f['Scadenza']:%d/%m/%Y}"
                          if r_f["Scadenza"] else "")
                x1.markdown(f"**{r_f['Cliente']}** · fattura {r_f['Numero']}")
                x1.caption(f"{_eur(resto_f)} € da incassare{scad_f}")
                if x2.button("Incassata", key=f"inc_{i_f}", width='stretch'):
                    _scrivi_lavoro(DIARIO.riga(
                        "incasso", str(r_f["Cliente"]), str(r_f["Numero"]), 0,
                        resto_f, "incasso"), "Fattura segnata come incassata")

        with st.form("fattura_nuova", clear_on_submit=True):
            st.markdown("##### Nuova fattura")
            f1, f2 = st.columns([2, 1])
            cli_f = f1.text_input("Cliente")
            num_f = f2.text_input("Numero", placeholder="es. 12/2026")
            f3, f4, f5, f6 = st.columns(4)
            imp_f = f3.number_input("Importo (€)", min_value=0.0, step=50.0)
            ore_f = f6.number_input("Ore impiegate", min_value=0.0, step=0.5,
                                    help="Il tempo che ti è costato questo lavoro, tutto: "
                                         "serve a sapere quanto guadagni davvero all'ora.")
            dat_f = f4.date_input("Data emissione", value=oggi_l, format="DD/MM/YYYY")
            scad_pf = f5.date_input("Pagamento entro", value=oggi_l + dt.timedelta(days=30),
                                    format="DD/MM/YYYY")
            if st.form_submit_button("💾 Registra la fattura", type="primary"):
                if not cli_f.strip() or not num_f.strip():
                    st.warning("Servono il cliente e il numero.")
                elif (not FAT.empty) and (FAT["Numero"] == num_f.strip()).any():
                    st.warning(f"Il numero {num_f.strip()} c'è già: usane un altro.")
                else:
                    _scrivi_lavoro(DIARIO.riga(
                        "fattura", cli_f.strip()[:80], num_f.strip(), int(round(ore_f * 60)), float(imp_f),
                        f"{scad_pf:%Y-%m-%d}",
                        quando=dt.datetime.combine(dat_f, dt.time(12, 0))),
                        f"Fattura {num_f.strip()} registrata")

        if not FAT.empty:
            with st.expander(f"Tutte le fatture ({len(FAT)})"):
                st.dataframe(FAT, width='stretch', hide_index=True,
                             column_config={
                                 "Importo": st.column_config.NumberColumn(format="%.2f €"),
                                 "Incassato": st.column_config.NumberColumn(format="%.2f €"),
                                 "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                 "Scadenza": st.column_config.DateColumn(format="DD/MM/YYYY"),
                             })

    # -------------------------------------------------------- scadenze ----
    with LT[3]:
        st.markdown("##### Da fare nei prossimi due mesi")
        if SCA.empty:
            st.caption("Nessuna scadenza in arrivo.")
        for i_s, r_s in SCA.iterrows():
            with st.container(border=True):
                s1, s2 = st.columns([4, 1])
                extra = f" · {_eur(r_s['Importo'])} €" if r_s["Importo"] else ""
                s1.markdown(f"**{r_s['Cosa']}**")
                s1.caption(f"{r_s['Quando']:%d/%m/%Y} · {r_s['Stato']}{extra}")
                if s2.button("Fatta", key=f"sca_{i_s}", width='stretch'):
                    _scrivi_lavoro(DIARIO.riga(
                        "scadenza_fatta", str(r_s["Cosa"]), r_s["Quando"].isoformat(), 0, None, "fatta",
                        quando=dt.datetime.combine(oggi_l, dt.time(12, 0))),
                        "Scadenza segnata come fatta")

        with st.form("scadenza_nuova", clear_on_submit=True):
            st.markdown("##### Nuova scadenza")
            t1, t2, t3 = st.columns([3, 1, 1])
            cosa_s = t1.text_input("Cosa", placeholder="es. dichiarazione IVA, rinnovo dominio")
            quando_s = t2.date_input("Quando", value=oggi_l + dt.timedelta(days=7),
                                     format="DD/MM/YYYY")
            imp_s = t3.number_input("Importo (€, facoltativo)", min_value=0.0, step=10.0)
            if st.form_submit_button("💾 Aggiungi", type="primary"):
                if cosa_s.strip():
                    _scrivi_lavoro(DIARIO.riga(
                        "scadenza", cosa_s.strip()[:120], "", 0,
                        float(imp_s) if imp_s else None, "",
                        quando=dt.datetime.combine(quando_s, dt.time(9, 0))),
                        "Scadenza aggiunta")
                else:
                    st.warning("Scrivi cosa scade.")
        st.caption("Una scadenza è «fatta» quando la segni con il pulsante: il nome "
                   "deve restare lo stesso, così la riconosco.")

# ============================================================================
# TAB 1 - SEGRETARIA  (avatar, chat a voce, azioni, notifiche: vedi segretaria.py)
# ============================================================================
with TAB[1]:
    import segretaria as SEG
    mostra_conferma()
    try:
        SEG.mostra(CTX)
    except Exception as _e_sg:
        st.error(f"La Segreteria ha avuto un problema: {_e_sg}")
        st.caption("Il resto di Quadro funziona. Se si ripete, mandami questo messaggio.")

# ============================================================================
# TAB 4 - LABORATORIO  (magazzino, progetti e prezzi, calcolatori: laboratorio.py)
# ============================================================================
with TAB[4]:
    import laboratorio as LAB
    mostra_conferma()
    LAB.mostra(CTX)

# ============================================================================
# TAB 13 - GUIDA  (come si usa e come si modifica: il testo sta in guida.json)
# ============================================================================
with TAB[13]:
    pannello_riepilogo('guida')
    # La guida vive in guida.py (come si mostra) e guida.json (cosa dice)
    import guida as GUIDA
    G = GUIDA.carica()
    if "_errore" in G:
        st.error(f"Non riesco a leggere `guida.json`: {G['_errore']}")
        st.caption("Di solito è una virgola di troppo o una virgoletta mancante: incollalo su "
                   "jsonlint.com e ti dice la riga.")
    else:
        GUIDA.mostra(G, CTX)
