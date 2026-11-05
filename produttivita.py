"""
produttivita.py — «Tempo ed energia», in fondo alla Scrivania.

Quattro strumenti, tutti costruiti sulle sessioni che registri già:

    ⚡ Mappa dell'energia   in che ore lavori meglio, dai voti delle sessioni
    🗓️ Piano di domani      le cose da fare messe nelle ore giuste, e un file
                            da importare nel calendario del telefono (con
                            l'avviso cinque minuti prima di ogni blocco)
    🧭 Urgente/importante   per decidere cosa fare, cosa spostare, cosa lasciare
    📊 La settimana         i numeri degli ultimi sette giorni contro i sette prima

COME SI LEGGE UNA SESSIONE NEL DIARIO
    Tipo=sessione, Data e Ora = quando l'hai chiusa, Minuti = quanto è durata,
    Valore = il voto da 1 a 5. L'ora di inizio quindi è «Ora meno Minuti».
    Le interruzioni stanno in una riga a parte (Tipo=interruzioni) scritta
    nello stesso momento, con lo stesso nome di attività.
"""

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ======================================================== i dati ==========
# Le tabelle modificabili mettono «NaN» nelle caselle vuote, e NaN in Python è
# «vero»: `NaN or 0` resta NaN. Queste due funzioni lo trasformano nel vuoto.
def _numero(x):
    n = pd.to_numeric(x, errors="coerce")
    return 0 if pd.isna(n) else n


def _testo(x):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()


def _spunta(x):
    return False if x is None or (isinstance(x, float) and pd.isna(x)) else bool(x)

def sessioni(dia, giorni=60, oggi=None):
    """Le sessioni degli ultimi giorni, con ora di inizio e interruzioni."""
    vuota = pd.DataFrame(columns=["inizio", "ora", "minuti", "voto", "attivita",
                                  "interruzioni"])
    if dia is None or dia.empty:
        return vuota
    oggi = oggi or dt.date.today()
    d = dia[dia["Data"] >= pd.Timestamp(oggi) - pd.Timedelta(days=giorni)]
    s = d[d["Tipo"] == "sessione"].copy()
    if s.empty:
        return vuota
    fine = pd.to_datetime(s["Data"].dt.strftime("%Y-%m-%d") + " "
                          + s["Ora"].fillna("12:00").astype(str).str[:5],
                          errors="coerce")
    s["inizio"] = fine - pd.to_timedelta(s["Minuti"].fillna(0), unit="m")
    s = s[s["inizio"].notna()]
    inter = d[d["Tipo"] == "interruzioni"][["Data", "Ora", "Attivita", "Valore"]]
    s = s.merge(inter.rename(columns={"Valore": "interruzioni"}),
                on=["Data", "Ora", "Attivita"], how="left")
    return pd.DataFrame({
        "inizio": s["inizio"], "ora": s["inizio"].dt.hour,
        "minuti": s["Minuti"].fillna(0), "voto": pd.to_numeric(s["Valore"], errors="coerce"),
        "attivita": s["Attivita"], "interruzioni": s["interruzioni"].fillna(0),
    })


def mappa_energia(ses):
    """Per ogni ora di inizio: quante sessioni, voto medio, interruzioni all'ora."""
    if ses.empty:
        return pd.DataFrame(columns=["sessioni", "minuti", "voto", "interruzioni_ora"])
    g = ses.groupby("ora").agg(sessioni=("voto", "size"), minuti=("minuti", "sum"),
                               voto=("voto", "mean"), interruzioni=("interruzioni", "sum"))
    g["interruzioni_ora"] = (g["interruzioni"] / g["minuti"].where(g["minuti"] > 0) * 60).fillna(0)
    return g.drop(columns="interruzioni")


def ore_migliori(mappa, minimo=2, quante=2, voto_minimo=3.5):
    """Le ore con il voto più alto e meno interruzioni, se ci sono abbastanza dati."""
    m = mappa[(mappa["sessioni"] >= minimo) & (mappa["voto"] >= voto_minimo)]
    if m.empty:
        return []
    punteggio = m["voto"] - 0.3 * m["interruzioni_ora"]
    return [int(h) for h in punteggio.sort_values(ascending=False).index[:quante]]


# ================================================= il piano di domani =====
def pianifica(cose, inizio, fine, pranzo=None, blocco=50, pausa=10, ore_buone=None):
    """
    Mette le cose nella giornata, a blocchi.

    cose: lista di dict con «Cosa», «Minuti», «Impegno» (alto/medio/basso).
    Le cose di impegno alto vanno a partire dalla prima ora buona, se c'è;
    le altre riempiono gli spazi liberi dal mattino. Ogni blocco dura al più
    `blocco` minuti ed è seguito da `pausa` minuti liberi.

    Restituisce (blocchi, avanzate): i blocchi in ordine di orario e le cose
    che non ci stavano.
    """
    giorno = dt.date(2000, 1, 1)
    t0 = dt.datetime.combine(giorno, inizio)
    durata = int((dt.datetime.combine(giorno, fine) - t0).total_seconds() // 60)
    libero = [True] * max(0, durata)
    if pranzo:
        a = int((dt.datetime.combine(giorno, pranzo[0]) - t0).total_seconds() // 60)
        b = int((dt.datetime.combine(giorno, pranzo[1]) - t0).total_seconds() // 60)
        for m in range(max(0, a), min(durata, b)):
            libero[m] = False

    def primo_spazio(da, lungo):
        """Il primo minuto da cui ci sono `lungo` minuti liberi di fila."""
        m = max(0, da)
        while m + lungo <= durata:
            if all(libero[m:m + lungo]):
                return m
            m += 5
        return None

    ordine = {"alto": 0, "medio": 1, "basso": 2}
    elenco = sorted([dict(c, Cosa=_testo(c.get("Cosa")), Minuti=int(_numero(c.get("Minuti"))))
                     for c in cose if _testo(c.get("Cosa")) and _numero(c.get("Minuti")) > 0],
                    key=lambda c: ordine.get(c.get("Impegno"), 1))
    partenza_alto = 0
    if ore_buone:
        h = min(ore_buone)
        partenza_alto = max(0, (h * 60) - (inizio.hour * 60 + inizio.minute))

    blocchi, avanzate = [], []
    for c in elenco:
        resto = int(c["Minuti"])
        da = partenza_alto if c.get("Impegno") == "alto" else 0
        while resto > 0:
            # un avanzo di pochi minuti non diventa un blocco a sé: si allunga
            # l'ultimo blocco fino a un quarto d'ora
            lungo = resto if resto <= blocco + 15 else blocco
            m = primo_spazio(da, lungo)
            if m is None and da > 0:
                m = primo_spazio(0, lungo)      # l'ora buona era piena
            if m is None:
                avanzate.append(f"{c['Cosa']} ({resto} min)")
                break
            for k in range(m, min(durata, m + lungo + pausa)):
                libero[k] = False
            blocchi.append({"Inizio": (t0 + dt.timedelta(minutes=m)).time(),
                            "Fine": (t0 + dt.timedelta(minutes=m + lungo)).time(),
                            "Cosa": c["Cosa"],
                            "Impegno": _testo(c.get("Impegno")) or "medio"})
            resto -= lungo
            da = m + lungo + pausa
    blocchi.sort(key=lambda b: b["Inizio"])
    return blocchi, avanzate


def calendario_ics(blocchi, giorno, avviso_minuti=5):
    """
    Un file .ics: importato nel calendario del telefono, ogni blocco diventa
    un evento con la notifica qualche minuto prima. Gli orari sono «locali»
    (senza fuso), quindi valgono per l'ora del telefono.
    """
    adesso = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    righe = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ENESTAR Quadro//IT",
             "CALSCALE:GREGORIAN"]
    for i, b in enumerate(blocchi):
        inizio = dt.datetime.combine(giorno, b["Inizio"]).strftime("%Y%m%dT%H%M%S")
        fine = dt.datetime.combine(giorno, b["Fine"]).strftime("%Y%m%dT%H%M%S")
        titolo = b["Cosa"].replace(",", "\\,").replace(";", "\\;").replace("\n", " ")
        righe += ["BEGIN:VEVENT", f"UID:quadro-{giorno:%Y%m%d}-{i}@enestar",
                  f"DTSTAMP:{adesso}", f"DTSTART:{inizio}", f"DTEND:{fine}",
                  f"SUMMARY:{titolo}", "BEGIN:VALARM", "ACTION:DISPLAY",
                  f"DESCRIPTION:{titolo}", f"TRIGGER:-PT{int(avviso_minuti)}M",
                  "END:VALARM", "END:VEVENT"]
    righe.append("END:VCALENDAR")
    return "\r\n".join(righe) + "\r\n"


# ====================================================== la settimana ======
def numeri_settimana(dia, oggi):
    """I numeri degli ultimi 7 giorni e dei 7 prima, per confrontarli."""
    def tratto(da, a):
        if dia is None or dia.empty:
            d = pd.DataFrame(columns=["Tipo", "Minuti", "Valore", "Attivita"])
        else:
            d = dia[(dia["Data"] >= pd.Timestamp(da)) & (dia["Data"] < pd.Timestamp(a))]
        ses = d[d["Tipo"] == "sessione"]
        inter = d[d["Tipo"] == "interruzioni"]
        pr = d[d["Tipo"] == "priorita"]
        minuti = float(ses["Minuti"].sum()) if not ses.empty else 0.0
        return {
            "minuti": minuti,
            "sessioni": len(ses),
            "voto": float(pd.to_numeric(ses["Valore"], errors="coerce").mean())
            if not ses.empty else None,
            "interruzioni_ora": float(inter["Valore"].sum()) / minuti * 60 if minuti else None,
            "fatte": int((pr["Attivita"] == "fatta").sum()) if not pr.empty else 0,
            "rinviate": int((pr["Attivita"] == "rinviata").sum()) if not pr.empty else 0,
        }
    fine = oggi + dt.timedelta(days=1)
    return tratto(fine - dt.timedelta(days=7), fine), \
        tratto(fine - dt.timedelta(days=14), fine - dt.timedelta(days=7))


# ========================================================== la parte ======
SEZIONI = ["⚡ Mappa dell'energia", "🗓️ Piano di domani", "🧭 Urgente/importante",
           "📊 La settimana"]


def mostra(ctx):
    st.markdown("### ⏱️ Tempo ed energia")
    T = st.tabs(SEZIONI, key="prod_sezione")
    oggi = ctx.DIARIO.oggi()
    ses = sessioni(ctx.DIA, 60, oggi)
    mappa = mappa_energia(ses)
    buone = ore_migliori(mappa)
    with T[0]:
        _energia(ses, mappa, buone)
    with T[1]:
        _piano(ctx, buone, oggi)
    with T[2]:
        _matrice(ctx)
    with T[3]:
        _settimana(ctx, oggi)


def _aperte(ctx):
    """Le «tre cose» ancora aperte, per partire da lì."""
    try:
        p = ctx.DIARIO.priorita(ctx.DIA)
        return [] if p.empty else p[p["Stato"] != "fatta"]["Cosa"].tolist()
    except Exception:
        return []


def _energia(ses, mappa, buone):
    st.caption("Dalle sessioni degli ultimi due mesi: a che ora le cominci, "
               "che voto dai e quante interruzioni hai. Serve per mettere le "
               "cose difficili nelle ore in cui rendi di più.")
    if len(ses) < 6:
        st.info(f"Servono almeno sei sessioni registrate per vedere qualcosa "
                f"(ora ce ne sono {len(ses)}). Usa il pulsante Comincia qui sopra "
                "e, alla fine, dai il voto.")
        return
    fig = go.Figure()
    fig.add_bar(x=[f"{h:02d}:00" for h in mappa.index], y=mappa["voto"],
                text=[f"{n} sess." for n in mappa["sessioni"]], textposition="outside",
                marker_color=["#1baf7a" if h in buone else "#9cc7b8" for h in mappa.index],
                hovertemplate="%{x}<br>voto medio %{y:.1f}<extra></extra>", name="voto")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis=dict(range=[0, 5.6], title="voto medio"),
                      title="Com'è andata, per ora di inizio")
    st.plotly_chart(fig, width='stretch')
    if buone:
        st.success("Le tue ore migliori: " + " e ".join(f"**{h:02d}:00**" for h in sorted(buone))
                   + ". Mettici le cose che richiedono testa.")
    peggio = mappa[mappa["sessioni"] >= 2].sort_values("interruzioni_ora", ascending=False)
    if not peggio.empty and peggio.iloc[0]["interruzioni_ora"] >= 1:
        h = int(peggio.index[0])
        st.warning(f"Alle **{h:02d}:00** ti interrompi di più: "
                   f"{peggio.iloc[0]['interruzioni_ora']:.1f} volte all'ora. Lì "
                   "vanno meglio le cose brevi.")


def _piano(ctx, buone, oggi):
    st.caption("Scrivi cosa vuoi fare e quanto ci vuole: Quadro lo dispone a "
               "blocchi, con le pause, mettendo le cose impegnative nelle tue "
               "ore migliori. Il file per il calendario porta anche gli avvisi "
               "sul telefono.")
    c1, c2, c3 = st.columns(3)
    giorno = c1.date_input("Giorno", value=oggi + dt.timedelta(days=1),
                           format="DD/MM/YYYY", key="prod_giorno")
    inizio = c2.time_input("Inizio", dt.time(8, 30), key="prod_inizio", step=900)
    fine = c3.time_input("Fine", dt.time(18, 0), key="prod_fine", step=900)
    p1, p2, p3 = st.columns(3)
    con_pranzo = p1.checkbox("Pausa pranzo 13-14", True, key="prod_pranzo")
    blocco = p2.select_slider("Blocco massimo", [25, 45, 50, 60, 90], value=50,
                              key="prod_blocco", format_func=lambda m: f"{m} min")
    pausa = p3.select_slider("Pausa tra blocchi", [5, 10, 15], value=10,
                             key="prod_pausa", format_func=lambda m: f"{m} min")

    if "prod_cose" not in st.session_state:
        st.session_state["prod_cose"] = pd.DataFrame(
            [{"Cosa": c, "Minuti": 50, "Impegno": "alto" if i == 0 else "medio"}
             for i, c in enumerate(_aperte(ctx))]
            or [{"Cosa": "", "Minuti": 50, "Impegno": "medio"}])
    cose = st.data_editor(
        st.session_state["prod_cose"], num_rows="dynamic", hide_index=True,
        width='stretch', key="prod_editor",
        column_config={
            "Cosa": st.column_config.TextColumn("Cosa", width="large"),
            "Minuti": st.column_config.NumberColumn("Minuti", min_value=5, max_value=480, step=5),
            "Impegno": st.column_config.SelectboxColumn("Impegno", options=["alto", "medio", "basso"]),
        })

    if inizio >= fine:
        st.warning("L'ora di fine deve venire dopo quella di inizio.")
        return
    blocchi, avanzate = pianifica(
        cose.to_dict("records"), inizio, fine,
        (dt.time(13, 0), dt.time(14, 0)) if con_pranzo else None,
        int(blocco), int(pausa), buone)
    if not blocchi:
        st.caption("Scrivi almeno una cosa con i minuti.")
        return
    tab = pd.DataFrame([{"Dalle": b["Inizio"].strftime("%H:%M"), "Alle": b["Fine"].strftime("%H:%M"),
                         "Cosa": b["Cosa"], "Impegno": b["Impegno"]} for b in blocchi])
    st.dataframe(tab, hide_index=True, width='stretch')
    if avanzate:
        st.warning("Non ci stanno: " + "; ".join(avanzate)
                   + ". Togli qualcosa, o è il segnale che la giornata è troppo piena.")
    occupati = sum((dt.datetime.combine(giorno, b["Fine"]) - dt.datetime.combine(giorno, b["Inizio"])
                    ).seconds // 60 for b in blocchi)
    st.caption(f"{occupati} minuti di lavoro pianificati, in {len(blocchi)} blocchi.")
    st.download_button("📅 Scarica per il calendario (.ics)", calendario_ics(blocchi, giorno),
                       f"piano_{giorno:%Y%m%d}.ics", "text/calendar", type="primary",
                       key="prod_ics")
    st.caption("Sul telefono: apri il file e scegli «Aggiungi al calendario». "
               "Ogni blocco ti avvisa cinque minuti prima.")


def _matrice(ctx):
    st.caption("Spunta cosa è urgente e cosa è importante. La regola è vecchia "
               "ma funziona: l'importante non urgente è quello che viene "
               "sempre rimandato, ed è quello che conta di più.")
    if "prod_matrice" not in st.session_state:
        st.session_state["prod_matrice"] = pd.DataFrame(
            [{"Cosa": c, "Urgente": False, "Importante": True} for c in _aperte(ctx)]
            or [{"Cosa": "", "Urgente": False, "Importante": False}])
    m = st.data_editor(st.session_state["prod_matrice"], num_rows="dynamic",
                       hide_index=True, width='stretch', key="prod_matrice_editor",
                       column_config={"Urgente": st.column_config.CheckboxColumn(default=False),
                                      "Importante": st.column_config.CheckboxColumn(default=False)})
    quadranti = {
        (True, True): ("🔥 Falla adesso", "Oggi, nella prima ora buona."),
        (False, True): ("📌 Pianificala", "Dalle un orario preciso: è quella che si perde."),
        (True, False): ("🔁 Delegala o accorciala", "Urgente per qualcun altro: falla in fretta o passala."),
        (False, False): ("🗑️ Lasciala andare", "Se non è né urgente né importante, forse non va fatta."),
    }
    gruppi = {}
    for r in m.to_dict("records"):
        if _testo(r.get("Cosa")):
            gruppi.setdefault((_spunta(r.get("Urgente")), _spunta(r.get("Importante"))), []).append(_testo(r["Cosa"]))
    if not gruppi:
        return
    cols = st.columns(2)
    for i, chiave in enumerate([(True, True), (False, True), (True, False), (False, False)]):
        titolo, nota = quadranti[chiave]
        with cols[i % 2].container(border=True):
            st.markdown(f"**{titolo}**")
            st.caption(nota)
            for cosa in gruppi.get(chiave, []):
                st.markdown(f"- {cosa}")


def _settimana(ctx, oggi):
    ora, prima = numeri_settimana(ctx.DIA, oggi)

    def delta(a, b, fmt="{:+.0f}"):
        return None if a is None or b is None else fmt.format(a - b)

    c = st.columns(3)
    c[0].metric("Minuti di lavoro", f"{ora['minuti']:.0f}", delta(ora["minuti"], prima["minuti"]))
    c[1].metric("Sessioni", ora["sessioni"], delta(ora["sessioni"], prima["sessioni"]))
    c[2].metric("Voto medio", f"{ora['voto']:.1f}" if ora["voto"] is not None else "—",
                delta(ora["voto"], prima["voto"], "{:+.1f}"))
    d = st.columns(3)
    d[0].metric("Interruzioni all'ora",
                f"{ora['interruzioni_ora']:.1f}" if ora["interruzioni_ora"] is not None else "—",
                delta(ora["interruzioni_ora"], prima["interruzioni_ora"], "{:+.1f}"),
                delta_color="inverse")
    d[1].metric("Cose fatte", ora["fatte"], delta(ora["fatte"], prima["fatte"]))
    d[2].metric("Rinvii", ora["rinviate"], delta(ora["rinviate"], prima["rinviate"]),
                delta_color="inverse")
    st.caption("Ultimi sette giorni, confrontati con i sette prima.")

    if st.button("✨ Un suggerimento per la prossima settimana", key="prod_ai"):
        if not ctx.chiave_ai:
            st.error("Serve la chiave di Google AI Studio nei Secrets.")
        else:
            ses = sessioni(ctx.DIA, 7, oggi)
            per_att = ses.groupby("attivita")["minuti"].sum().sort_values(ascending=False).to_dict() \
                if not ses.empty else {}
            prompt = (
                "Ecco i numeri di lavoro di una persona, ultimi 7 giorni e i 7 "
                f"precedenti:\nora: {ora}\nprima: {prima}\nminuti per attività: {per_att}\n\n"
                "Dai UN solo suggerimento pratico per la prossima settimana, in "
                "italiano, in tre o quattro frasi, basato solo su questi numeri. "
                "Se i dati sono pochi, dillo. Niente frasi motivazionali.")
            try:
                with st.spinner("Guardo i numeri…"):
                    st.session_state["prod_consiglio"] = ctx.AI.chiedi(
                        prompt, ctx.chiave_ai, ctx.modello_ai)
            except Exception as e:
                st.error(getattr(e, "messaggio", None) or str(e))
    if st.session_state.get("prod_consiglio"):
        with st.container(border=True):
            st.markdown(st.session_state["prod_consiglio"])
            ctx.ascolta(st.session_state["prod_consiglio"], "🔊 Ascolta")
