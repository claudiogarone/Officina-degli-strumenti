"""
collaboratrice.py — 🤝 Claudio Assistant: il lavoro della segretaria reale, in Segreteria.

Quadro non scrive niente nel file della segretaria: lo LEGGE e ti mostra i numeri.
Il file è il Foglio Google della promozione (MakerHub, libri, corsi), quello con
i fogli dei contatti, Registro ore, Compensi, Pagamenti, Andamento e Controlli
qualità. Si cambia solo lì.

    I NUMERI       ore registrate e approvate, invii, risposte, risultati, invii
                   per ora, controlli OK e voto medio, nel periodo che scegli
    LA SETTIMANA   un grafico settimana per settimana
    TOCCA A TE     le attività che il file passa a te (Chi la fa = Claudio) e
                   le ore da approvare
    COSA HA FATTO  gli ultimi blocchi di lavoro del Registro ore
    QUALITÀ        i controlli che fai tu, e quelli ancora da correggere
    RESOCONTO      due righe scritte dall'AI su com'è andata, con cosa dirle

COME SI COLLEGA (una volta): apri il Foglio Google → Condividi → aggiungi
l'indirizzo del service account di Quadro come «Visualizzatore» → incolla il
link nella pagina. Quadro scarica il file al massimo ogni 15 minuti.

COME LEGGE IL FILE: per nome delle colonne (riga 5 di ogni foglio), non per
lettera; se aggiungi colonne, continua a funzionare. Conta da sé invii,
risposte e risultati dalle date scritte a mano, così i numeri tornano anche
se le formule del file non sono ancora state ricalcolate.
"""

import datetime as dt
import io
import json
import re

import pandas as pd
import streamlit as st

NOME = "Claudio Assistant"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FOGLI_ARGOMENTO = ["Elettronica e PCB", "Stampa 3D", "CNC Legno e Officina", "Domotica IoT Raspberry",
                   "Robotica Droni Modellismo", "Scuola e STEM", "Fab Lab e Associazioni", "Radio e Astronomia",
                   "Riviste e Media"]
POSITIVI = {"MakerHub": {"Risposta positiva"},
            "Editori": {"Interessato", "Chiede materiale", "Offerta ricevuta", "Contratto firmato"},
            "Corsi": {"Interessato", "Accordo raggiunto"}}
RISULTATO = {"Editori": "Contratto firmato", "Corsi": "Accordo raggiunto"}
NOMI_COLONNA = {"nome": ["Gruppo o organizzazione", "Editore", "Sito, organizzazione o allievo"],
                "inviato": ["Inviato?", "Inviato o pubblicato?"], "data_invio": ["Data invio"],
                "riscontro": ["Riscontro"], "data_riscontro": ["Data riscontro"],
                "data_sollecito": ["Data sollecito"], "pubblicato": ["Pubblicato?"],
                "data_pubblicazione": ["Data pubblicazione"], "prossima": ["Prossima attività"],
                "scadenza": ["Scadenza"], "stato": ["Stato scadenza"], "chi": ["Chi la fa"],
                "nuovi": ["Nuovi iscritti MakerHub", "Nuovi allievi"], "clic": ["Clic sul link"]}


# ================================================================ leggere ===
def id_da_link(testo):
    """L'id di un file Google da un link (o l'id stesso)."""
    testo = (testo or "").strip()
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", testo) or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", testo)
    if m:
        return m.group(1)
    return testo if re.fullmatch(r"[A-Za-z0-9_-]{20,}", testo) else ""


@st.cache_data(ttl=900, show_spinner=False)
def _scarica(_info_json, file_id, segno):
    """Il file come .xlsx (un Foglio Google si esporta, un .xlsx si scarica)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    cred = service_account.Credentials.from_service_account_info(
        json.loads(_info_json), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=cred, cache_discovery=False)
    meta = drive.files().get(fileId=file_id, fields="name,mimeType,modifiedTime",
                             supportsAllDrives=True).execute()
    if meta.get("mimeType") == "application/vnd.google-apps.spreadsheet":
        dati = drive.files().export(fileId=file_id, mimeType=XLSX).execute()
    else:
        dati = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    return meta, dati


@st.cache_data(ttl=900, show_spinner=False)
def _letti(_info_json, file_id, segno):
    """Scaricato e già letto: la pagina si ridisegna a ogni clic in Quadro, il file si legge una volta."""
    meta, grezzo = _scarica(_info_json, file_id, segno)
    return meta, leggi(grezzo)


def _data(x):
    if x is None or x == "":
        return pd.NaT
    if isinstance(x, (int, float)) and not isinstance(x, bool):      # numero di serie di Excel
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(x))
    return pd.to_datetime(x, errors="coerce", dayfirst=True)


def _ore(r):
    """Le ore di una riga del registro: quelle calcolate dal file, o da inizio, fine e pausa."""
    try:
        if r.get("Ore") not in (None, ""):
            return float(r["Ore"])
    except (TypeError, ValueError):
        pass
    i, f = r.get("Inizio"), r.get("Fine")
    if isinstance(i, dt.time) and isinstance(f, dt.time):
        a = i.hour * 60 + i.minute
        b = f.hour * 60 + f.minute
        minuti = (b - a) % (24 * 60)
        try:
            minuti -= float(r.get("Pausa in minuti") or 0)
        except (TypeError, ValueError):
            pass
        return round(max(0, minuti) / 60, 2)
    return 0.0


def _righe(ws):
    """(intestazioni della riga 5, righe dalla 6 in giù) di un foglio, come dizionari."""
    righe = list(ws.iter_rows(min_row=5, values_only=True))
    if not righe:
        return [], []
    testa = [str(x).strip() if x is not None else "" for x in righe[0]]
    return testa, [dict(zip(testa, r)) for r in righe[1:]]


def leggi(dati):
    """Dai byte del file ai tre elenchi che servono: contatti, registro ore, controlli."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(dati), data_only=True, read_only=True)
    contatti = []
    for foglio in FOGLI_ARGOMENTO + ["Editori", "Corsi"]:
        if foglio not in wb.sheetnames:
            continue
        area = foglio if foglio in ("Editori", "Corsi") else "MakerHub"
        testa, righe = _righe(wb[foglio])
        dove = {k: next((n for n in nomi if n in testa), None) for k, nomi in NOMI_COLONNA.items()}
        if not dove["nome"]:
            continue
        for r in righe:
            nome = r.get(dove["nome"])
            if not nome:
                continue
            g = lambda k: r.get(dove[k]) if dove[k] else None
            riscontro = str(g("riscontro") or "")
            d_risc = _data(g("data_riscontro"))
            if area == "MakerHub":
                risultato = str(g("pubblicato") or "") == "Sì"
                d_ris = _data(g("data_pubblicazione"))
            else:
                risultato = riscontro == RISULTATO[area]
                d_ris = d_risc if risultato else pd.NaT
            contatti.append({
                "foglio": foglio, "area": area, "nome": str(nome),
                "inviato": str(g("inviato") or "") == "Sì", "data_invio": _data(g("data_invio")),
                "riscontro": riscontro, "data_riscontro": d_risc, "positivo": riscontro in POSITIVI[area],
                "data_sollecito": _data(g("data_sollecito")),
                "risultato": risultato, "data_risultato": d_ris,
                "prossima": str(g("prossima") or ""), "scadenza": _data(g("scadenza")),
                "stato": str(g("stato") or ""), "chi": str(g("chi") or ""),
                "nuovi": pd.to_numeric(g("nuovi"), errors="coerce")})
    registro = []
    if "Registro ore" in wb.sheetnames:
        _, righe = _righe(wb["Registro ore"])
        for r in righe:
            d = _data(r.get("Data"))
            if pd.isna(d):
                continue
            registro.append({"data": d, "ore": _ore(r), "area": str(r.get("Area") or ""),
                             "cosa": str(r.get("Cosa ha fatto") or ""),
                             "contatti": pd.to_numeric(r.get("Contatti lavorati"), errors="coerce"),
                             "esito": str(r.get("Esito") or ""), "approvata": str(r.get("Approvata?") or "") == "Sì",
                             "note": str(r.get("Note di Claudio") or "")})
    controlli = []
    if "Controlli qualità" in wb.sheetnames:
        _, righe = _righe(wb["Controlli qualità"])
        for r in righe:
            d = _data(r.get("Data"))
            if pd.isna(d):
                continue
            controlli.append({"data": d, "foglio": str(r.get("Foglio") or ""), "id": str(r.get("ID o gruppo") or ""),
                              "cosa": str(r.get("Cosa hai controllato") or ""), "esito": str(r.get("Esito") or ""),
                              "voto": pd.to_numeric(r.get("Voto (1-5)"), errors="coerce"),
                              "nota": str(r.get("Nota per la segretaria") or ""),
                              "corretto": str(r.get("Corretto?") or "") == "Sì"})
    tariffa = None
    if "Compensi" in wb.sheetnames:
        try:
            tariffa = float(wb["Compensi"]["C4"].value)
        except (TypeError, ValueError):
            tariffa = None
    wb.close()
    return {"contatti": pd.DataFrame(contatti), "registro": pd.DataFrame(registro),
            "controlli": pd.DataFrame(controlli), "tariffa": tariffa}


# =================================================================== numeri ===
def _nel(serie, dal, al):
    return serie.notna() & (serie >= dal) & (serie < al)


def numeri(D, dal, al):
    """I numeri del periodo [dal, al)."""
    c, r, q = D["contatti"], D["registro"], D["controlli"]
    n = {}
    n["ore"] = float(r.loc[_nel(r["data"], dal, al), "ore"].sum()) if not r.empty else 0.0
    n["ore_approvate"] = float(r.loc[_nel(r["data"], dal, al) & r["approvata"], "ore"].sum()) if not r.empty else 0.0
    if c.empty:
        n.update(invii=0, solleciti=0, risposte=0, positive=0, risultati=0)
    else:
        n["invii"] = int(_nel(c["data_invio"], dal, al).sum())
        n["solleciti"] = int(_nel(c["data_sollecito"], dal, al).sum())
        n["risposte"] = int(_nel(c["data_riscontro"], dal, al).sum())
        n["positive"] = int((_nel(c["data_riscontro"], dal, al) & c["positivo"]).sum())
        n["risultati"] = int((_nel(c["data_risultato"], dal, al) & c["risultato"]).sum())
    n["invii_ora"] = n["invii"] / n["ore"] if n["ore"] else None
    if q.empty:
        n.update(controlli=0, ok=None, voto=None)
    else:
        qq = q[_nel(q["data"], dal, al)]
        n["controlli"] = len(qq)
        n["ok"] = (qq["esito"] == "OK").mean() if len(qq) else None
        n["voto"] = qq["voto"].mean() if qq["voto"].notna().any() else None
    n["costo"] = n["ore_approvate"] * D["tariffa"] if D.get("tariffa") else None
    n["costo_risultato"] = n["costo"] / n["risultati"] if n["costo"] and n["risultati"] else None
    return n


def settimane(D, quante=12, oggi=None):
    oggi = pd.Timestamp(oggi or dt.date.today())
    lun = oggi - pd.Timedelta(days=oggi.weekday())
    righe = []
    for i in range(quante - 1, -1, -1):
        dal = lun - pd.Timedelta(weeks=i)
        n = numeri(D, dal, dal + pd.Timedelta(days=7))
        righe.append({"settimana": dal, "Invii": n["invii"], "Risposte positive": n["positive"],
                      "Risultati": n["risultati"], "Ore": round(n["ore"], 2)})
    return pd.DataFrame(righe)


def tocca_a_te(D, oggi):
    c = D["contatti"]
    if c.empty:
        return c
    t = c[(c["chi"] == "Claudio") & c["stato"].isin(["Scaduta", "Oggi", "In arrivo"])]
    return t.sort_values("scadenza")[["stato", "scadenza", "prossima", "foglio", "nome"]]


def arretrato_suo(D):
    c = D["contatti"]
    if c.empty:
        return 0
    return int(((c["chi"] == "Segretaria") & (c["stato"] == "Scaduta")).sum())


# ================================================================ la pagina ===
def _impostazioni(ctx):
    return ctx.impostazione(ctx.DIA, "assistente_reale", {"foglio": "", "nome": NOME})


def dati(ctx, silenzioso=False):
    """(dati letti, meta, errore). Usa la cache: al massimo un download ogni 15 minuti."""
    imp = _impostazioni(ctx)
    fid = imp.get("foglio") or ""
    if not fid or not ctx.SA:
        return None, None, None
    try:
        meta, D = _letti(json.dumps(dict(ctx.SA)), fid, st.session_state.get("col_segno", 0))
        st.session_state["col_riassunto"] = per_segretaria(D, ctx.DIARIO.oggi())
        return D, meta, None
    except Exception as e:
        testo = str(e)
        if "404" in testo or "notFound" in testo:
            testo = "non trovo il file: controlla il link e che sia condiviso con il service account"
        elif "403" in testo:
            testo = "il file non è condiviso con il service account di Quadro"
        return None, None, testo


def per_segretaria(D, oggi):
    """Le poche cose che la segretaria virtuale (e Telegram) sanno del lavoro di quella reale."""
    oggi_ts = pd.Timestamp(oggi)
    n = numeri(D, oggi_ts - pd.Timedelta(days=7), oggi_ts + pd.Timedelta(days=1))
    r = D["registro"]
    return {"tocca_a_te": int(len(tocca_a_te(D, oggi))),
            "ore_da_approvare": round(float(r.loc[~r["approvata"], "ore"].sum()), 2) if not r.empty else 0,
            "invii_7_giorni": n["invii"], "risposte_positive_7_giorni": n["positive"],
            "risultati_7_giorni": n["risultati"], "sue_attivita_scadute": arretrato_suo(D)}


def _collega(ctx, imp):
    email = (dict(ctx.SA) if ctx.SA else {}).get("client_email", "(l'indirizzo del service account, nei Secrets)")
    st.markdown("**Collega il suo file, una volta sola**")
    st.markdown("1. Apri il Foglio Google della promozione → **Condividi**\n"
                "2. Aggiungi questo indirizzo come **Visualizzatore** (Quadro legge e basta):")
    st.code(email, language="text")
    st.markdown("3. Copia il link del foglio (dalla barra degli indirizzi) e incollalo qui sotto.")
    with st.form("col_collega"):
        link = st.text_input("Link del Foglio Google", imp.get("foglio") and
                             f"https://docs.google.com/spreadsheets/d/{imp['foglio']}" or "",
                             placeholder="https://docs.google.com/spreadsheets/d/…")
        nome = st.text_input("Come la chiami", imp.get("nome") or NOME)
        if st.form_submit_button("💾 Collega", type="primary"):
            fid = id_da_link(link)
            if not fid:
                st.error("Non riconosco il link: deve contenere /d/ e un codice lungo.")
            else:
                ctx.diario_scrivi(ctx.DIARIO.riga("impostazione", "assistente_reale", "Segreteria", 0, None,
                                                  json.dumps({"foglio": fid, "nome": nome.strip() or NOME},
                                                             ensure_ascii=False)))
                st.session_state["col_segno"] = st.session_state.get("col_segno", 0) + 1
                ctx.conferma("Collegato")
                st.rerun()


def mostra(ctx, sofia=None):
    imp = _impostazioni(ctx)
    nome = imp.get("nome") or NOME
    st.caption(f"Il lavoro di {nome}, la segretaria reale: Quadro legge il suo Foglio Google della promozione "
               "e ti mostra ore, invii, risposte, risultati e qualità. Il file si cambia solo lì: qui si guarda.")
    if not ctx.SA:
        st.warning("Manca il service account nei Secrets: senza, Quadro non può leggere il file.")
        return
    if not imp.get("foglio"):
        _collega(ctx, imp)
        return
    with st.spinner("Leggo il suo file…"):
        D, meta, errore = dati(ctx)
    a1, a2, a3 = st.columns([2, 1, 1])
    a2.link_button("📄 Apri il foglio", f"https://docs.google.com/spreadsheets/d/{imp['foglio']}",
                   width="stretch")
    if a3.button("🔄 Rileggi adesso", key="col_rileggi", width="stretch"):
        st.session_state["col_segno"] = st.session_state.get("col_segno", 0) + 1
        st.rerun()
    if errore:
        st.error(f"Non riesco a leggere il file: {errore}")
        with st.expander("🔗 Cambia il collegamento"):
            _collega(ctx, imp)
        return
    if meta:
        a1.caption(f"📄 {meta.get('name', '')} · modificato {str(meta.get('modifiedTime', ''))[:16].replace('T', ' ')} "
                   "(Quadro lo rilegge ogni 15 minuti)")

    oggi = pd.Timestamp(ctx.DIARIO.oggi())
    giorni = st.radio("Periodo", [7, 30, 90, 3650], index=1, horizontal=True, key="col_giorni",
                      format_func=lambda g: {7: "7 giorni", 30: "30 giorni", 90: "3 mesi", 3650: "da sempre"}[g])
    n = numeri(D, oggi - pd.Timedelta(days=giorni - 1), oggi + pd.Timedelta(days=1))
    k = st.columns(4)
    k[0].metric("Ore registrate", f"{n['ore']:.1f}", help=f"Approvate: {n['ore_approvate']:.1f}")
    k[1].metric("Invii", n["invii"], help=f"Solleciti: {n['solleciti']}")
    k[2].metric("Risposte positive", n["positive"], help=f"Risposte in tutto: {n['risposte']}")
    k[3].metric("Risultati", n["risultati"], help="Post pubblicati, contratti, accordi per i corsi")
    k = st.columns(4)
    k[0].metric("Invii per ora", f"{n['invii_ora']:.1f}" if n["invii_ora"] else "—")
    k[1].metric("Controlli OK", f"{n['ok']:.0%}" if n["ok"] is not None else "—",
                help=f"Su {n['controlli']} controlli che hai fatto tu")
    k[2].metric("Voto medio", f"{n['voto']:.1f}" if n["voto"] is not None else "—")
    k[3].metric("Costo per risultato", f"{n['costo_risultato']:.2f} €" if n["costo_risultato"] else "—",
                help="Ore approvate × tariffa (da Compensi) ÷ risultati")

    s = settimane(D, 12, oggi)
    if s[["Invii", "Risposte positive", "Risultati", "Ore"]].to_numpy().sum():
        import plotly.graph_objects as go
        fig = go.Figure()
        for col, colore in (("Invii", "#0f5d47"), ("Risposte positive", "#1baf7a"), ("Risultati", "#e0a526")):
            fig.add_bar(x=s["settimana"], y=s[col], name=col, marker_color=colore)
        fig.add_scatter(x=s["settimana"], y=s["Ore"], name="Ore", yaxis="y2", mode="lines+markers",
                        line=dict(color="#8a5a2b"))
        fig.update_layout(barmode="group", height=280, margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h", y=-0.2), xaxis=dict(tickformat="%d/%m"),
                          yaxis2=dict(overlaying="y", side="right", showgrid=False, title="ore"))
        st.plotly_chart(fig, width="stretch", key="col_grafico")
    else:
        st.info(f"Ancora nessun lavoro registrato: i numeri compaiono quando {nome} comincia a segnare "
                "invii, risposte e ore nel file.")

    st.markdown("##### 🧑‍💼 Tocca a te")
    t = tocca_a_te(D, oggi)
    r = D["registro"]
    da_appr = r[~r["approvata"] & (r["ore"] > 0)] if not r.empty else r
    if t.empty and da_appr.empty:
        st.caption("Niente: il file non ti passa attività e non ci sono ore da approvare.")
    if not t.empty:
        st.dataframe(t, hide_index=True, width="stretch",
                     column_config={"scadenza": st.column_config.DateColumn("Scadenza", format="DD/MM")})
    if not da_appr.empty:
        st.warning(f"⏳ {da_appr['ore'].sum():.1f} ore da approvare ({len(da_appr)} righe): nel file, "
                   "Registro ore → colonna Approvata?")
    arr = arretrato_suo(D)
    if arr:
        st.caption(f"Sul suo tavolo: {arr} attività scadute da fare (Chi la fa = Segretaria).")

    st.markdown(f"##### 📋 Cosa ha fatto {nome}")
    if r.empty:
        st.caption("Il Registro ore è ancora vuoto.")
    else:
        st.dataframe(r.sort_values("data", ascending=False).head(15), hide_index=True, width="stretch",
                     column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

    st.markdown("##### ✅ La qualità")
    q = D["controlli"]
    if q.empty:
        st.caption("Nessun controllo ancora. Una volta a settimana guarda 5-10 righe a caso e segna l'esito nel "
                   "foglio «Controlli qualità» del file: è la misura di quanto lavora bene, non solo di quanto.")
    else:
        aperti = q[(q["esito"] != "OK") & ~q["corretto"]]
        if len(aperti):
            st.caption(f"{len(aperti)} controlli da correggere, non ancora corretti.")
        st.dataframe(q.sort_values("data", ascending=False).head(10), hide_index=True, width="stretch",
                     column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

    if sofia:
        st.markdown("##### 🆚 Le due segretarie, negli ultimi 30 giorni")
        s1, s2 = st.columns(2)
        with s1.container(border=True):
            st.markdown("**🤖 La segretaria virtuale**")
            for etichetta, valore in sofia.items():
                st.markdown(f"- {etichetta}: **{valore}**")
        n30 = numeri(D, oggi - pd.Timedelta(days=29), oggi + pd.Timedelta(days=1))
        with s2.container(border=True):
            st.markdown(f"**🤝 {nome}**")
            st.markdown(f"- Ore: **{n30['ore']:.1f}**\n- Invii: **{n30['invii']}**\n"
                        f"- Risposte positive: **{n30['positive']}**\n- Risultati: **{n30['risultati']}**\n"
                        f"- Controlli OK: **{'—' if n30['ok'] is None else format(n30['ok'], '.0%')}**")

    st.markdown("##### 🧐 Il resoconto")
    if st.button("🧐 Scrivimi com'è andata e cosa dirle", key="col_resoconto", disabled=not ctx.chiave_ai):
        n7 = numeri(D, oggi - pd.Timedelta(days=6), oggi + pd.Timedelta(days=1))
        lavoro = r.sort_values("data").tail(15).to_dict("records") if not r.empty else []
        controlli = q.sort_values("data").tail(10).to_dict("records") if not q.empty else []
        prompt = (f"Sei il consulente di Claudio, che ha una collaboratrice part-time ({nome}) per la promozione di "
                  "MakerHub, dei suoi libri e dei suoi corsi. Ecco i numeri e il lavoro registrato.\n"
                  f"Ultimi 7 giorni: {json.dumps(n7, default=str, ensure_ascii=False)}\n"
                  f"Ultimi {giorni} giorni: {json.dumps(n, default=str, ensure_ascii=False)}\n"
                  f"Ultimi blocchi di lavoro: {json.dumps(lavoro, default=str, ensure_ascii=False)}\n"
                  f"Controlli qualità: {json.dumps(controlli, default=str, ensure_ascii=False)}\n"
                  f"Attività passate a Claudio: {len(t)}; scadute sue: {arr}.\n\n"
                  "Scrivi in italiano, breve, in markdown: ### Com'è andata (3 righe, con i numeri) · "
                  "### Cosa va bene · ### Cosa migliorare · ### Cosa dirle (2-3 frasi pronte, gentili e "
                  "concrete). Non inventare dati che non vedi; se i dati sono pochi, dillo.")
        with st.spinner("Scrivo il resoconto…"):
            try:
                st.session_state["col_testo"] = ctx.AI.chiedi(prompt, ctx.chiave_ai, ctx.modello_ai)
            except Exception as e:
                st.error(getattr(e, "messaggio", None) or str(e))
    if st.session_state.get("col_testo"):
        with st.container(border=True):
            st.markdown(st.session_state["col_testo"])
    with st.expander("🔗 Cambia il collegamento al file"):
        _collega(ctx, imp)
