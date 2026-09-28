# -*- coding: utf-8 -*-
"""
Dashboard Registri Lezioni Private
Autore: Claudio Vincenzo Garone - ENESTAR Maker Lab
Legge automaticamente tutti i registri (Google Sheets nativi e .xlsx)
contenuti in una cartella di Google Drive e ne ricava una dashboard interattiva.
"""

import io
import re
import datetime as dt
from typing import Optional

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ============================================================================
# CONFIGURAZIONE PAGINA
# ============================================================================

st.set_page_config(
    page_title="Registri Lezioni - Dashboard",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
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

def secret(key, default=None):
    """Accesso ai secrets a prova di file mancante (app non ancora configurata)."""
    try:
        return st.secrets[key]
    except Exception:
        return default


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
        st.warning("⚠️ Credenziali Google non configurate. Aggiungi il blocco "
                   "`[gcp_service_account]` nei **Secrets** dell'app (vedi la guida), "
                   "oppure usa il caricamento manuale dalla barra laterale.")
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
k[0].metric("Lezioni", f"{tot_lez:,}".replace(",", "."))
k[1].metric("Ore totali", f"{tot_ore:,.1f}".replace(",", "."))
k[2].metric("Allievi", n_all)
k[3].metric("Incassato", f"€ {incassato:,.0f}".replace(",", "."))
k[4].metric("Da incassare", f"€ {da_incassare:,.0f}".replace(",", "."),
            delta=None if da_incassare == 0 else "in sospeso", delta_color="inverse")
k[5].metric("Tariffa oraria media", f"€ {tariffa:,.1f}".replace(",", "."))

st.divider()

TAB = st.tabs(["📊 Panoramica", "👥 Allievi", "💶 Economia", "🎓 Didattica", "📋 Dettaglio"])


# ============================================================================
# TAB 1 - PANORAMICA
# ============================================================================
with TAB[0]:
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
with TAB[1]:
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
with TAB[2]:
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
with TAB[3]:
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
with TAB[4]:
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
