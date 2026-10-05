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

st.set_page_config(
    page_title="Registri Lezioni - Dashboard",
    page_icon="📘",
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
  .stTabs [data-baseweb="tab"] {font-size: 0.95rem; font-weight: 550;}

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

st.sidebar.markdown("### 📘 Registri Lezioni")

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
    if st.sidebar.button("🔄 Aggiorna adesso", width='stretch', type="primary"):
        st.session_state.cache_key = dt.datetime.now().timestamp()
        st.cache_data.clear()
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

st.title("📘 Dashboard Registri Lezioni")
st.caption(f"Periodo {df['Data'].min():%d/%m/%Y} – {df['Data'].max():%d/%m/%Y} · "
           f"aggiornamento automatico dai fogli su Google Drive")

# --- controllo qualità dei dati -------------------------------------------
anno_ora = dt.date.today().year
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

k = st.columns(6)
k[0].markdown('<span class="kpi-mark"></span>', unsafe_allow_html=True)
k[0].metric("Lezioni", f"{tot_lez:,}".replace(",", "."))
k[1].metric("Ore totali", f"{tot_ore:,.1f}".replace(",", "."))
k[2].metric("Allievi", n_all)
k[3].metric("Incassato", f"€ {incassato:,.0f}".replace(",", "."))
k[4].metric("Da incassare", f"€ {da_incassare:,.0f}".replace(",", "."),
            delta=None if da_incassare == 0 else "in sospeso", delta_color="inverse")
k[5].metric("Tariffa oraria media", f"€ {tariffa:,.1f}".replace(",", "."))

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

TAB = st.tabs(["🧭 Scrivania", "📊 Panoramica", "👥 Allievi", "💶 Economia",
               "🎓 Didattica", "📋 Dettaglio", "🗂️ Progetti", "🖋️ Cancelleria",
               "📚 Studio"])


# ============================================================================
# TAB 0 - SCRIVANIA  (collegamenti rapidi e stato di salute)
# ============================================================================
with TAB[0]:
    oggi_ts = pd.Timestamp(dt.date.today())

    # ---------------- cose che richiedono attenzione ----------------------
    st.markdown("##### Cosa richiede attenzione")

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
    st.markdown("##### Collegamenti rapidi")

    @st.cache_data(show_spinner=False)
    def carica_collegamenti():
        import json as _json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "collegamenti.json"), encoding="utf-8") as f:
                return _json.load(f).get("collegamenti", [])
        except Exception:
            return []

    voci = [v for v in carica_collegamenti() if (v.get("url") or "").strip()]

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
# TAB 1 - PANORAMICA
# ============================================================================
with TAB[1]:
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


# ============================================================================
# TAB 2 - ALLIEVI
# ============================================================================
with TAB[2]:
    oggi = pd.Timestamp(dt.date.today())
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


# ============================================================================
# TAB 3 - ECONOMIA
# ============================================================================
with TAB[3]:
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
        tar = df[df["Incassato"] > 0].groupby("Allievo").apply(
            lambda g: g["Incassato"].sum() / g["OreLezione"].sum() if g["OreLezione"].sum() else 0,
            include_groups=False).reset_index(name="TariffaOraria")
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


# ============================================================================
# TAB 4 - DIDATTICA
# ============================================================================
with TAB[4]:
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


# ============================================================================
# TAB 5 - DETTAGLIO
# ============================================================================
with TAB[5]:
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
    tab["DataPagamento"] = tab["DataPagamento"].dt.strftime("%d/%m/%Y")
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
                       f"registro_lezioni_{dt.date.today():%Y%m%d}.csv", "text/csv",
                       width='stretch')
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        tab.to_excel(w, index=False, sheet_name="Lezioni")
    c2.download_button("⬇️ Scarica Excel", buf.getvalue(),
                       f"registro_lezioni_{dt.date.today():%Y%m%d}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width='stretch')


# ============================================================================
# TAB 6 - PROGETTI E CONSULENZE
# ============================================================================
with TAB[6]:
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
            oggi = pd.Timestamp(dt.date.today())
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
        st.download_button("⬇️ Scarica progetti in CSV",
                           t.to_csv(index=False).encode("utf-8-sig"),
                           f"progetti_{dt.date.today():%Y%m%d}.csv", "text/csv")

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

        # ---------------- piano contatti ----------------
        if not contatti.empty:
            with st.expander("📇 Piano contatti dei progetti"):
                st.dataframe(contatti, width='stretch', hide_index=True, height=340)
                if not esiti.empty:
                    st.markdown("**Registro esiti dei contatti**")
                    st.dataframe(esiti, width='stretch', hide_index=True)

        if not diag_p.empty:
            with st.expander("🔍 Diagnostica lettura progetti"):
                st.dataframe(diag_p, width='stretch', hide_index=True)


# ============================================================================
# TAB 7 - CANCELLERIA  (generatore di documenti e materiale intestato)
# ============================================================================
with TAB[7]:
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
        numero = p1.text_input("Numero", f"{dt.date.today():%Y}-001")
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
        numero = r1.text_input("Numero", f"{dt.date.today():%m}/{dt.date.today():%Y}")
        importo = r2.number_input("Importo €", 0.0, 1e6,
                                  float(pre.get("importo_allievo") or pre.get("importo") or 0.0),
                                  step=10.0)
        data_pag = r3.date_input("Data", dt.date.today())
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
        st.success("Documento pronto.")
        st.download_button("⬇️ Scarica il PDF", pdf_bytes, nome_file,
                           "application/pdf", type="primary")
        try:
            st.pdf(pdf_bytes, height=700)
        except Exception:
            st.caption("Anteprima non disponibile in questa versione di Streamlit: "
                       "scarica il file per vederlo.")


# ============================================================================
# TAB 8 - STUDIO  (percorsi, prontuari, strumenti AI, prompt pronti)
# ============================================================================
with TAB[8]:

    @st.cache_data(show_spinner=False)
    def carica_studio():
        import json as _json
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "studio.json"), encoding="utf-8") as f:
                return _json.load(f)
        except Exception as e:
            return {"_errore": str(e)}

    S = carica_studio()
    if "_errore" in S:
        st.error(f"Non riesco a leggere `studio.json`: {S['_errore']}")
        st.caption("Controlla che il file sia nella repo accanto ad app.py e che il "
                   "JSON sia valido (una virgola di troppo basta a invalidarlo).")
        st.stop()

    # ---------------- link rapidi -----------------------------------------
    link = [l for l in S.get("link_rapidi", []) if (l.get("url") or "").strip()]
    mancanti = [l["nome"] for l in S.get("link_rapidi", []) if not (l.get("url") or "").strip()]
    if link:
        cols = st.columns(min(4, len(link)))
        for col, l in zip(cols, link):
            col.link_button(f"{l.get('icona', '🔗')} {l['nome']}", l["url"],
                            width='stretch', help=l.get("nota", ""))
    if mancanti:
        st.caption("Senza indirizzo in `studio.json`, quindi non mostrati: "
                   + ", ".join(mancanti))

    st.divider()

    SEZ = st.tabs(["🎯 Percorsi", "🧰 Strumenti", "📋 Prontuari",
                   "🤖 Assistente", "💬 Prompt pronti"])

    # ================= PERCORSI ==========================================
    with SEZ[0]:
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

        livelli = p.get("livelli", [])
        if livelli:
            st.markdown("")
            LT = st.tabs([f"{i+1} · {l['nome']}" for i, l in enumerate(livelli)])
            for scheda, l in zip(LT, livelli):
                with scheda:
                    if l.get("traguardo"):
                        st.markdown(f"**Dove arrivi** — {l['traguardo']}")
                    c1, c2 = st.columns([3, 2])
                    with c1:
                        st.markdown("###### Le tappe, in ordine")
                        for i, t in enumerate(l.get("tappe", []), 1):
                            st.markdown(f"**{i}.** {t}")
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
    with SEZ[2]:
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
                           f"prontuari_{dt.date.today():%Y%m%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument."
                           "spreadsheetml.sheet", width='stretch')
        d2.download_button("⬇️ Scarica in CSV",
                           tab_pront.to_csv(index=False).encode("utf-8-sig"),
                           f"prontuari_{dt.date.today():%Y%m%d}.csv", "text/csv",
                           width='stretch')
        st.caption(f"{len(tab_pront)} comandi in {len(prontuari)} prontuari. "
                   "Nel file Excel trovi un foglio per prontuario più uno con tutto "
                   "insieme. Per aggiungerne, modifica `studio.json`.")

    # ================= ASSISTENTE IA =====================================
    with SEZ[3]:
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

            modello = st.text_input("Modello", MODELLO_DEF,
                                    help="Se ricevi un errore 404, il nome del "
                                         "modello non è più valido: usa il pulsante "
                                         "qui sotto e scegline uno dall'elenco.")
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
                    try:
                        with st.spinner("Sto pensando…"):
                            r = requests.post(
                                "https://generativelanguage.googleapis.com/v1beta/"
                                f"models/{modello}:generateContent",
                                params={"key": chiave},
                                json={"contents": [{"parts": [{"text": prompt}]}]},
                                timeout=120)
                        if r.status_code != 200:
                            st.error(f"Errore {r.status_code}")
                            st.code(r.text[:800], language="text")
                            if r.status_code == 404:
                                st.caption("Quasi certamente il nome del modello non "
                                           "è più valido: apri le impostazioni qui "
                                           "sopra e usa «Quali modelli posso usare».")
                            elif r.status_code in (401, 403):
                                st.caption("La chiave non è valida o non è abilitata.")
                            elif r.status_code == 429:
                                st.caption("Hai superato il limite gratuito: riprova "
                                           "fra qualche minuto.")
                        else:
                            dati = r.json()
                            risposta = (dati.get("candidates", [{}])[0]
                                        .get("content", {})
                                        .get("parts", [{}])[0].get("text", ""))
                            st.session_state["ultima_risposta"] = risposta
                            st.session_state["ultimo_compito"] = compito
                    except Exception as e:
                        st.error(f"Non sono riuscito a contattare il servizio: {e}")

            risposta = st.session_state.get("ultima_risposta", "")
            if risposta:
                st.divider()
                if st.session_state.get("ultimo_compito") == "Mappa concettuale":
                    codice = (risposta.replace("```mermaid", "")
                              .replace("```", "").strip())
                    import streamlit.components.v1 as components
                    components.html(f"""
<div class="mermaid">{codice}</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{startOnLoad:true, theme:'neutral'}});</script>
<style>body{{margin:0;font-family:Helvetica,Arial,sans-serif;background:transparent}}
.mermaid{{display:flex;justify-content:center}}</style>
""", height=560, scrolling=True)
                    with st.expander("Il codice della mappa"):
                        st.code(codice, language="text")
                        st.caption("Puoi incollarlo su mermaid.live per modificarlo "
                                   "e scaricarlo come immagine.")
                else:
                    st.markdown(risposta)

                st.download_button("⬇️ Scarica il risultato", risposta.encode("utf-8"),
                                   f"studio_{dt.date.today():%Y%m%d}.md",
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
    with SEZ[1]:
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
    with SEZ[4]:
        st.caption("Copia il testo, incollalo nell'assistente e sostituisci le parti "
                   "fra parentesi quadre. Sono scritti per farti **spiegare** le cose, "
                   "non per fartele risolvere.")
        for pr in S.get("prompt_pronti", []):
            with st.expander(f"💬 {pr['titolo']}"):
                if pr.get("quando"):
                    st.caption(f"*{pr['quando']}*")
                st.code(pr["testo"], language="text")
