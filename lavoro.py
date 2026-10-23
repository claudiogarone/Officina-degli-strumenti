"""
lavoro.py — il registro del lavoro da freelance: clienti, fatture, scadenze.

Usa lo stesso Quadro_Diario.xlsx delle altre sezioni, con altri tipi di riga.
Il diario si aggiunge soltanto in fondo, quindi cambiare uno stato (un cliente
che passa da «preventivo» ad «acquisito», una fattura incassata) vuol dire
aggiungere una riga nuova. Vince sempre l'ultima. È più lento da leggere a
mano, ma non si perde mai niente: lo storico resta intero.

Tipi di riga usati:
  cliente          Attivita=nome, Strumento=stato, Valore=importo stimato,
                   Nota=prossimo passo :: data di richiamo (AAAA-MM-GG)
  fattura          Attivita=cliente, Strumento=numero, Valore=importo,
                   Nota=data di scadenza del pagamento (AAAA-MM-GG)
  incasso          Strumento=numero della fattura, Valore=importo incassato
  scadenza         Attivita=cosa, Valore=importo (facoltativo), Data=quando
  scadenza_fatta   Attivita=cosa (come nella scadenza), Data=quando è stata fatta
  obiettivo        Valore=entrata mensile che ti sei dato
"""

import datetime as dt

import pandas as pd

STATI_CLIENTE = ["contattato", "preventivo inviato", "in trattativa",
                 "acquisito", "perso"]
STATI_APERTI = {"contattato", "preventivo inviato", "in trattativa"}


def _valori(df, tipo):
    if df is None or df.empty:
        return pd.DataFrame()
    return df[df["Tipo"] == tipo].copy()


def _num(x):
    """Un numero, o zero: vuoto, None e NaN diventano zero."""
    try:
        v = float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v != v else v      # v != v è vero solo per NaN


def _data_nota(testo):
    """La data scritta in fondo alla Nota, se c'è (AAAA-MM-GG)."""
    try:
        return dt.date.fromisoformat(str(testo).strip()[:10])
    except ValueError:
        return None


# ------------------------------------------------------------- clienti ----
def clienti(df):
    """Un cliente per riga, con l'ultimo stato registrato."""
    c = _valori(df, "cliente")
    colonne = ["Cliente", "Stato", "Importo", "Prossimo passo", "Richiamo"]
    if c.empty:
        return pd.DataFrame(columns=colonne)
    c = c.sort_values("Data")
    ultimi = c.groupby("Attivita", sort=False).tail(1)
    righe = []
    for _, r in ultimi.iterrows():
        prossimo, _, richiamo = str(r["Nota"]).partition(" :: ")
        righe.append({
            "Cliente": r["Attivita"],
            "Stato": r["Strumento"],
            "Importo": _num(r["Valore"]),
            "Prossimo passo": prossimo.strip(),
            "Richiamo": _data_nota(richiamo),
        })
    return pd.DataFrame(righe, columns=colonne)


def richiami_scaduti(tabella_clienti, oggi):
    """I clienti con un richiamo già passato, ancora aperti."""
    if tabella_clienti.empty:
        return tabella_clienti
    m = (tabella_clienti["Richiamo"].notna()
         & (tabella_clienti["Richiamo"] <= oggi)
         & tabella_clienti["Stato"].isin(STATI_APERTI))
    return tabella_clienti[m]


# ------------------------------------------------------------- fatture ----
def fatture(df):
    """Ogni fattura con quanto è già stato incassato e se è chiusa."""
    f = _valori(df, "fattura")
    colonne = ["Data", "Cliente", "Numero", "Importo", "Incassato",
               "Scadenza", "Aperta"]
    if f.empty:
        return pd.DataFrame(columns=colonne)
    inc = _valori(df, "incasso")
    incassi = {}
    if not inc.empty:
        for _, r in inc.iterrows():
            numero = str(r["Strumento"]).strip()
            incassi[numero] = incassi.get(numero, 0.0) + _num(r["Valore"])
    righe = []
    for _, r in f.sort_values("Data").iterrows():
        numero = str(r["Strumento"]).strip()
        importo = _num(r["Valore"])
        incassato = incassi.get(numero, 0.0)
        righe.append({
            "Data": r["Data"].date() if pd.notna(r["Data"]) else None,
            "Cliente": r["Attivita"],
            "Numero": numero,
            "Importo": importo,
            "Incassato": incassato,
            "Scadenza": _data_nota(r["Nota"]),
            "Aperta": incassato + 0.005 < importo,
        })
    return pd.DataFrame(righe, columns=colonne)


def da_incassare(tabella_fatture):
    if tabella_fatture.empty:
        return 0.0
    aperte = tabella_fatture[tabella_fatture["Aperta"]]
    return float((aperte["Importo"] - aperte["Incassato"]).sum())


def mese_di(df, tipo, anno, mese):
    """Somma dei Valori di un tipo nel mese dato (per data della riga)."""
    v = _valori(df, tipo)
    if v.empty:
        return 0.0
    m = (v["Data"].dt.year == anno) & (v["Data"].dt.month == mese)
    return float(v.loc[m, "Valore"].map(_num).sum())


def fatturato_mese(df, anno, mese):
    """Emesso nel mese: le fatture datate in quel mese."""
    f = _valori(df, "fattura")
    if f.empty:
        return 0.0
    m = (f["Data"].dt.year == anno) & (f["Data"].dt.month == mese)
    return float(f.loc[m, "Valore"].map(_num).sum())


def obiettivo(df):
    o = _valori(df, "obiettivo")
    if o.empty:
        return 0.0
    return _num(o.sort_values("Data").iloc[-1]["Valore"])


# ----------------------------------------------------------- scadenze -----
def scadenze(df, oggi, giorni=30):
    """
    Le scadenze non ancora fatte, con quelle in ritardo per prime.
    Una scadenza è «fatta» se esiste una riga scadenza_fatta con lo stesso testo.
    """
    s = _valori(df, "scadenza")
    if s.empty:
        return pd.DataFrame(columns=["Quando", "Cosa", "Importo", "Stato"])
    fatte = set(_valori(df, "scadenza_fatta")["Attivita"].astype(str))
    righe = []
    for _, r in s.sort_values("Data").iterrows():
        if str(r["Attivita"]) in fatte:
            continue
        quando = r["Data"].date() if pd.notna(r["Data"]) else None
        if quando is None:
            continue
        gg = (quando - oggi).days
        if gg > giorni:
            continue
        righe.append({
            "Quando": quando,
            "Cosa": r["Attivita"],
            "Importo": _num(r["Valore"]),
            "Stato": "in ritardo" if gg < 0 else
                     ("oggi" if gg == 0 else f"fra {gg} giorni"),
        })
    return pd.DataFrame(righe, columns=["Quando", "Cosa", "Importo", "Stato"])
