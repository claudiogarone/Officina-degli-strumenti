"""
diario.py — la memoria della Scrivania.

Quadro finora leggeva e basta. Per tenere il conto di quello che fai serve
scrivere, e quel posto deve sopravvivere al riavvio dell'app.

ATTENZIONE a un'idea che sembra buona e non lo è: salvare "sul server".
Streamlit Cloud ricostruisce la macchina a ogni riavvio e a ogni modifica del
codice, e tutto quello che l'app aveva scritto su disco sparisce. Non è un
limite aggirabile: è come funziona. Quindi i dati devono stare fuori.

Ci sono tre modi, in ordine di comodità. Quadro li prova tutti e usa il primo
che trova:

  1. UN FILE EXCEL NELLA TUA CARTELLA DRIVE  ← il più semplice, consigliato
     Metti il file `Quadro_Diario.xlsx` (te l'ho preparato io, con le colonne
     già a posto) dentro una cartella Drive che Quadro già conosce, e
     condividi quella cartella con il service account come **Editor**.
     Nessun Secret nuovo da scrivere: lo trova da solo cercandolo per nome.

  2. UN FOGLIO DI GOOGLE
     Se preferisci un foglio nativo, metti il suo ID nei Secrets come
     `diario_sheet_id`. Funziona uguale.

  3. SOLO IN MEMORIA
     Se non configuri niente, la Scrivania funziona lo stesso ma si ricorda
     le cose finché la pagina resta aperta, e ti fa scaricare l'archivio.

Le righe hanno tutte la stessa forma. La colonna Tipo dice cosa sono:
  sessione  → una sessione di lavoro o allenamento (con i minuti)
  anomalia  → una riga del taccuino delle anomalie
  problema  → uno dei problemi aperti della tua lista
  esercizio → un esercizio del giorno completato
  tappa     → una tappa di un percorso di studio segnata come fatta
  corso     → un aggiornamento di avanzamento su un corso (Udemy e simili)
"""

import datetime as dt
import io
import json

import pandas as pd

COLONNE = ["Data", "Ora", "Tipo", "Attivita", "Strumento",
           "Minuti", "Valore", "Nota"]

NOME_FILE = "Quadro_Diario.xlsx"

AMBITO_FOGLI = ["https://www.googleapis.com/auth/spreadsheets"]
AMBITO_DRIVE = ["https://www.googleapis.com/auth/drive"]

MIME_XLSX = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")


# ============================================================== comune =======
def vuoto():
    return _sistema(pd.DataFrame(columns=COLONNE))


def _sistema(df):
    df = df.copy()
    for c in COLONNE:
        if c not in df.columns:
            df[c] = ""
    df = df[COLONNE]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Minuti"] = pd.to_numeric(df["Minuti"], errors="coerce").fillna(0)
    df["Valore"] = pd.to_numeric(df["Valore"], errors="coerce")
    for c in ("Tipo", "Attivita", "Strumento", "Nota", "Ora"):
        df[c] = df[c].astype(str).replace({"nan": "", "None": "", "NaT": ""})
    return df.dropna(subset=["Data"]).sort_values("Data").reset_index(drop=True)


def riga(tipo, attivita="", strumento="", minuti=0, valore=None, nota="",
         quando=None):
    """Costruisce una riga nel formato giusto, senza ricordarsi l'ordine."""
    q = quando or dt.datetime.now()
    return {"Data": q.strftime("%Y-%m-%d"), "Ora": q.strftime("%H:%M"),
            "Tipo": tipo, "Attivita": attivita, "Strumento": strumento,
            "Minuti": minuti, "Valore": "" if valore is None else valore,
            "Nota": nota}


def modello_xlsx(titolo="Diario", guida=True):
    """Il file Excel vuoto ma già impostato, da mettere su Drive."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = titolo
    ws.append(COLONNE)

    testa = Font(bold=True, color="FFFFFF")
    sfondo = PatternFill("solid", fgColor="0E7A54")
    for cella in ws[1]:
        cella.font = testa
        cella.fill = sfondo
        cella.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"

    larghezze = {"A": 12, "B": 8, "C": 12, "D": 34, "E": 20,
                 "F": 9, "G": 9, "H": 70}
    for col, w in larghezze.items():
        ws.column_dimensions[col].width = w

    tipi = DataValidation(
        type="list",
        formula1='"sessione,anomalia,problema,esercizio,tappa,corso"',
        allow_blank=True)
    ws.add_data_validation(tipi)
    tipi.add(f"C2:C5000")

    if not guida:
        buf0 = io.BytesIO()
        wb.save(buf0)
        return buf0.getvalue()

    guida = wb.create_sheet("Come si usa")
    for r in [
        ["Questo file è il diario di ENESTAR Quadro."],
        [""],
        ["Mettilo in una cartella di Drive condivisa con il service account "
         "COME EDITOR."],
        ["Quadro lo trova da solo cercandolo per nome: non rinominarlo."],
        [""],
        ["Puoi aprirlo e correggerlo a mano quando vuoi. Regole:"],
        ["· non cambiare l'ordine né i nomi delle colonne del foglio «Diario»"],
        ["· la Data si scrive come 2026-10-14 (anno-mese-giorno)"],
        ["· l'Ora come 09:30"],
        ["· Minuti e Valore sono numeri; Valore va da 1 a 5 per le sessioni"],
        [""],
        ["Cosa vuol dire la colonna Tipo:"],
        ["sessione", "una sessione di lavoro o allenamento, con i minuti"],
        ["anomalia", "una riga del taccuino delle anomalie"],
        ["problema", "uno dei problemi aperti della tua lista"],
        ["esercizio", "un esercizio del giorno completato"],
        ["tappa", "una tappa di un percorso di studio segnata come fatta"],
        ["corso", "un avanzamento su un corso: in Valore la percentuale"],
    ]:
        guida.append(r)
    guida.column_dimensions["A"].width = 16
    guida.column_dimensions["B"].width = 70
    guida["A1"].font = Font(bold=True, size=13)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ================================================== 1) file Excel su Drive ===
def _servizio_drive(info):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        dict(info), scopes=AMBITO_DRIVE)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def trova_file(info, cartelle, nome=None):
    """Cerca il file per nome nelle cartelle indicate. Restituisce l'id."""
    nome = nome or NOME_FILE
    svc = _servizio_drive(info)
    for cid in [c for c in cartelle if (c or "").strip()]:
        res = svc.files().list(
            q=f"'{cid}' in parents and trashed = false and name = '{nome}'",
            fields="files(id,name)", pageSize=5,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        trovati = res.get("files", [])
        if trovati:
            return trovati[0]["id"]
    return None


def leggi_xlsx(info, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    svc = _servizio_drive(info)
    buf = io.BytesIO()
    scarico = MediaIoBaseDownload(
        buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True))
    fine = False
    while not fine:
        _, fine = scarico.next_chunk()
    buf.seek(0)
    df = pd.read_excel(buf, sheet_name=0, dtype=str)
    return _sistema(df)


def aggiungi_xlsx(info, file_id, righe):
    """Scarica, aggiunge in fondo, ricarica. L'unico modo con un file Excel."""
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    from openpyxl import load_workbook
    svc = _servizio_drive(info)

    buf = io.BytesIO()
    scarico = MediaIoBaseDownload(
        buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True))
    fine = False
    while not fine:
        _, fine = scarico.next_chunk()
    buf.seek(0)

    wb = load_workbook(buf)
    ws = wb.worksheets[0]
    if ws.max_row == 1 and all(c.value is None for c in ws[1]):
        ws.append(COLONNE)
    for r in righe:
        ws.append([r.get(c, "") for c in COLONNE])

    fuori = io.BytesIO()
    wb.save(fuori)
    fuori.seek(0)
    svc.files().update(
        fileId=file_id, supportsAllDrives=True,
        media_body=MediaIoBaseUpload(fuori, mimetype=MIME_XLSX,
                                     resumable=False)).execute()
    return len(righe)


# ==================================================== 2) foglio di Google ====
def _servizio_fogli(info):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        dict(info), scopes=AMBITO_FOGLI)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def leggi_foglio(info, foglio_id):
    svc = _servizio_fogli(info)
    res = svc.spreadsheets().values().get(
        spreadsheetId=foglio_id, range="A:H").execute()
    valori = res.get("values", [])
    if len(valori) < 2:
        return vuoto()
    testa = valori[0]
    righe = [r + [""] * (len(testa) - len(r)) for r in valori[1:]]
    return _sistema(pd.DataFrame(righe, columns=testa))


def aggiungi_foglio(info, foglio_id, righe):
    svc = _servizio_fogli(info)
    valori = [[r.get(c, "") for c in COLONNE] for r in righe]
    svc.spreadsheets().values().append(
        spreadsheetId=foglio_id, range="A:H",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": valori}).execute()
    return len(valori)


# ========================================================= archivio JSON =====
def esporta(df):
    d = df.copy()
    d["Data"] = d["Data"].dt.strftime("%Y-%m-%d")
    return json.dumps({"versione": 1,
                       "esportato": dt.datetime.now().isoformat(timespec="seconds"),
                       "righe": d.to_dict(orient="records")},
                      ensure_ascii=False, indent=1).encode("utf-8")


def importa(contenuto):
    dati = json.loads(contenuto.decode("utf-8"))
    return _sistema(pd.DataFrame(dati.get("righe", [])))


# ============================================================== calcoli ======
PASSI = {"Giorno": "D", "Settimana": "W-MON", "Mese": "MS", "Anno": "YS"}


TIPI_TEMPO = ("sessione", "parlachiaro")   # righe che contano come tempo


def serie_minuti(df, dal, al, passo="Giorno", tipo=TIPI_TEMPO):
    """
    Minuti sommati nel periodo scelto, raggruppati per giorno, settimana,
    mese o anno. I buchi diventano zeri, altrimenti il grafico mente.
    """
    if tipo:
        ammessi = (tipo,) if isinstance(tipo, str) else tuple(tipo)
        d = df[df["Tipo"].isin(ammessi)]
    else:
        d = df
    d = d[(d["Data"] >= pd.Timestamp(dal)) & (d["Data"] <= pd.Timestamp(al))]
    freq = PASSI.get(passo, "D")

    # l'asse completo del periodo chiesto, buchi compresi: un grafico che
    # salta i giorni vuoti racconta una costanza che non c'è
    if freq.startswith("W"):
        # i lunedì: si parte dal lunedì della settimana in cui cade «dal»
        primo = pd.Timestamp(dal).normalize()
        primo -= pd.Timedelta(days=primo.weekday())
        pieno = pd.date_range(primo, pd.Timestamp(al), freq="7D")
    else:
        periodi = {"D": "D", "MS": "M", "YS": "Y"}[freq]
        pieno = pd.period_range(pd.Timestamp(dal), pd.Timestamp(al),
                                freq=periodi).to_timestamp()

    if d.empty:
        return pd.Series([0] * len(pieno), index=pieno, name="Minuti")

    # per le settimane l'etichetta deve essere il lunedì di PARTENZA, non
    # quello di arrivo: «settimana del 12/10» si capisce, «del 19/10» no
    extra = {"label": "left", "closed": "left"} if freq.startswith("W") else {}
    serie = d.set_index("Data")["Minuti"].resample(freq, **extra).sum()
    return serie.reindex(pieno, fill_value=0).rename("Minuti")


def etichette(indice, passo):
    """Come si scrive un punto dell'asse: 14/10, sett. del 12/10, ott 2026…"""
    mesi = ["gen", "feb", "mar", "apr", "mag", "giu",
            "lug", "ago", "set", "ott", "nov", "dic"]
    if passo == "Giorno":
        return [d.strftime("%d/%m/%Y") for d in indice]
    if passo == "Settimana":
        return [f"sett. del {d:%d/%m/%Y}" for d in indice]
    if passo == "Mese":
        return [f"{mesi[d.month - 1]} {d.year}" for d in indice]
    return [str(d.year) for d in indice]


def andamento(df, giorni=56):
    oggi = pd.Timestamp(dt.date.today())
    return serie_minuti(df, oggi - pd.Timedelta(days=giorni - 1), oggi, "Giorno")


def striscia(df):
    """Da quanti giorni di fila fai almeno una sessione."""
    giorni = set(df[df["Tipo"].isin(TIPI_TEMPO)]["Data"].dt.date)
    if not giorni:
        return 0
    oggi = dt.date.today()
    partenza = oggi if oggi in giorni else oggi - dt.timedelta(days=1)
    if partenza not in giorni:
        return 0
    n, g = 0, partenza
    while g in giorni:
        n += 1
        g -= dt.timedelta(days=1)
    return n


def corsi(df):
    """Un riepilogo per corso: ultima percentuale, minuti totali, ultima data."""
    c = df[df["Tipo"] == "corso"]
    if c.empty:
        return pd.DataFrame(columns=["Corso", "Piattaforma", "Avanzamento",
                                     "Minuti", "Ultimo aggiornamento",
                                     "Ultima lezione"])
    fuori = []
    for nome, g in c.groupby("Attivita"):
        g = g.sort_values("Data")
        ultima = g.iloc[-1]
        fuori.append({
            "Corso": nome,
            "Piattaforma": ultima["Strumento"] or "—",
            "Avanzamento": float(ultima["Valore"]) if pd.notna(ultima["Valore"]) else 0.0,
            "Minuti": float(g["Minuti"].sum()),
            "Ultimo aggiornamento": ultima["Data"],
            "Ultima lezione": ultima["Nota"],
        })
    return (pd.DataFrame(fuori)
            .sort_values("Avanzamento", ascending=False)
            .reset_index(drop=True))


def tappe_fatte(df, percorso=None):
    """I nomi delle tappe già segnate come fatte, per un percorso o per tutti."""
    t = df[df["Tipo"] == "tappa"]
    if percorso is not None:
        t = t[t["Attivita"] == percorso]
    return set(t["Nota"])
