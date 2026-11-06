"""
aforismi.py — un aforisma sempre diverso, scelto come vuoi tu, e la tua raccolta.

    FILTRI     argomento · tradizione (stoici, zen, scienziati, inventori…) ·
               epoca · tono · lunghezza · lingua · autori che ami · cosa evitare
    ASCOLTO    voce del browser, oppure un file audio con la voce di Gemini
    RACCOLTA   ogni aforisma salvato porta voto da 1 a 5, note, spunti,
               etichette e la spunta «utile alla segretaria». Si cerca, si
               filtra, si modifica, si esporta.

I voti non restano lì: quando chiedi un aforisma nuovo, l'AI riceve gli
autori e i temi che hai votato meglio, e quelli che non ti sono piaciuti, e
ne tiene conto. La segretaria legge la stessa raccolta.

DOVE SI VEDE: quello del momento in cima alla 🧭 Scrivania; preferenze e
raccolta nella scheda 👩‍💼 Segreteria → 🤖 Segretaria virtuale → ✨ Aforismi.

DOVE STA: nel diario, Tipo=aforisma. Nota contiene un piccolo JSON con il
testo e le tue annotazioni; Valore è il voto. Modificare vuol dire scrivere
una riga nuova con lo stesso testo: vince l'ultima, come nel resto di Quadro.
"""

import json
import random
import re

import pandas as pd
import streamlit as st

PREDEFINITE = {
    "temi": ["tempo e priorità", "calma e presenza"], "altri": "", "minuti": 60,
    "tradizioni": [], "epoca": "qualsiasi", "tono": "qualsiasi",
    "lunghezza": "breve", "lingua": "solo italiano", "autori": "", "evita": "",
    "in_scrivania": True, "voce_audio": "Sulafat",
}
TRADIZIONI = ["stoici", "zen e taoismo", "filosofi greci", "scienziati", "inventori e ingegneri",
              "scrittori italiani", "poeti", "imprenditori", "proverbi e detti popolari",
              "spiritualità orientale", "psicologi e pensatori moderni"]
EPOCHE = ["qualsiasi", "antichità", "medioevo e rinascimento", "dal 1600 al 1800",
          "dal 1800 al 1950", "contemporanea"]
TONI = ["qualsiasi", "sereno", "motivante", "riflessivo", "ironico", "pratico"]
LUNGHEZZE = {"breve": "al massimo una riga", "media": "due o tre righe"}
LINGUE = ["solo italiano", "originale con traduzione"]
INTERVALLI = {5: "ogni 5 minuti", 15: "ogni 15 minuti", 30: "ogni mezz'ora",
              60: "ogni ora", 180: "ogni tre ore", 1440: "uno al giorno"}


# ============================================================ la raccolta ===
def _leggi_nota(r):
    """Le righe vecchie avevano solo il testo; le nuove un JSON."""
    try:
        d = json.loads(r["Nota"])
        if isinstance(d, dict) and d.get("testo"):
            return d
    except (json.JSONDecodeError, TypeError):
        pass
    return {"testo": str(r["Nota"] or ""), "autore": r["Attivita"]}


def _quando(r):
    """Data e ora di una riga del diario, per sapere cosa viene prima."""
    try:
        return pd.Timestamp(r["Data"]) + pd.to_timedelta(str(r["Ora"] or "00:00")[:5] + ":00")
    except (ValueError, TypeError):
        return pd.Timestamp(r["Data"])


def raccolta(dia):
    """Un aforisma per riga, con l'ultima versione delle tue annotazioni."""
    colonne = ["testo", "autore", "fonte", "tema", "voto", "nota", "spunti", "tag",
               "segretaria", "originale", "salvato"]
    if dia is None or dia.empty:
        return pd.DataFrame(columns=colonne)
    a = dia[dia["Tipo"] == "aforisma"].sort_values(["Data", "Ora"], kind="stable")
    # tolto vale solo se è successo DOPO l'ultimo salvataggio: se lo risalvi, torna
    tolti = {}
    for _, r in dia[dia["Tipo"] == "aforisma_rimosso"].iterrows():
        tolti[r["Nota"]] = max(tolti.get(r["Nota"], pd.Timestamp.min), _quando(r))
    righe, quando = {}, {}
    for _, r in a.iterrows():
        d = _leggi_nota(r)
        voto = pd.to_numeric(r["Valore"], errors="coerce")
        righe[d["testo"]] = {
            "testo": d["testo"], "autore": d.get("autore") or r["Attivita"] or "",
            "fonte": d.get("fonte", ""), "tema": d.get("tema") or r["Strumento"] or "",
            "voto": None if pd.isna(voto) else int(voto), "nota": d.get("nota", ""),
            "spunti": d.get("spunti", ""), "tag": d.get("tag", []),
            "segretaria": bool(d.get("segretaria", False)), "originale": d.get("originale", ""),
            "salvato": r["Data"]}
        quando[d["testo"]] = _quando(r)
    t = pd.DataFrame([v for k, v in righe.items() if k not in tolti or quando[k] > tolti[k]],
                     columns=colonne)
    return t.sort_values("salvato", ascending=False) if not t.empty else t


def riga(DIARIO, a, voto=None, nota="", spunti="", tag=None, segretaria=False):
    dati = {"testo": a["testo"], "autore": a.get("autore", ""), "fonte": a.get("fonte", ""),
            "tema": a.get("tema", ""), "originale": a.get("originale", ""), "nota": nota,
            "spunti": spunti, "tag": list(tag or []), "segretaria": bool(segretaria)}
    return DIARIO.riga("aforisma", (a.get("autore") or "")[:60], (a.get("tema") or "")[:60],
                       0, voto, json.dumps(dati, ensure_ascii=False))


def gusti(dia):
    """Cosa ti piace e cosa no, dai voti: arriva all'AI e alla segretaria."""
    r = raccolta(dia)
    if r.empty or r["voto"].isna().all():
        return {"piace": [], "non_piace": []}
    votati = r.dropna(subset=["voto"])
    bello = votati[votati["voto"] >= 4]
    brutto = votati[votati["voto"] <= 2]
    return {"piace": sorted(set(bello["autore"]) | set(bello["tema"]) - {""})[:12],
            "non_piace": sorted(set(brutto["autore"]) | set(brutto["tema"]) - {""})[:12]}


# ===================================================== uno nuovo ===========
def _segno_tempo(minuti, ora):
    if minuti >= 1440:
        return ora.strftime("%Y-%m-%d")
    return str(int(ora.timestamp() // (minuti * 60)))


def prompt_nuovo(imp, gia, piace):
    temi = list(imp.get("temi", [])) + [t.strip() for t in imp.get("altri", "").split(",") if t.strip()]
    filtri = [f"Temi: {', '.join(temi) or 'la vita quotidiana'}."]
    if imp.get("tradizioni"):
        filtri.append(f"Da queste tradizioni o categorie di autori: {', '.join(imp['tradizioni'])}.")
    if imp.get("epoca", "qualsiasi") != "qualsiasi":
        filtri.append(f"Epoca: {imp['epoca']}.")
    if imp.get("tono", "qualsiasi") != "qualsiasi":
        filtri.append(f"Tono: {imp['tono']}.")
    filtri.append(f"Lunghezza: {LUNGHEZZE.get(imp.get('lunghezza', 'breve'), 'breve')}.")
    if imp.get("autori", "").strip():
        filtri.append(f"Autori che preferisce: {imp['autori']}.")
    if imp.get("evita", "").strip():
        filtri.append(f"Da evitare: {imp['evita']}.")
    if piace["piace"]:
        filtri.append(f"Ha votato bene: {', '.join(piace['piace'])}.")
    if piace["non_piace"]:
        filtri.append(f"Non gli sono piaciuti: {', '.join(piace['non_piace'])}.")
    originale = imp.get("lingua") == "originale con traduzione"
    return (
        "Proponi UN aforisma o una citazione breve. " + " ".join(filtri) + "\n"
        "Regola importante: se attribuisci la frase a un autore, deve essere una "
        "citazione vera e nota di cui sei sicuro, con la fonte se la conosci. Se "
        "non sei sicuro dell'autore, scrivi una riflessione tua e metti come "
        "autore «riflessione». Non inventare fonti.\n"
        f"Non ripetere questi: {' | '.join(gia[-30:])}\n"
        "Rispondi SOLO con JSON: {\"testo\": \"in italiano\", \"autore\": \"...\", "
        "\"fonte\": \"opera o vuoto\", \"tema\": \"una o due parole\""
        + (", \"originale\": \"il testo nella lingua originale, se non è italiano\"" if originale else "")
        + "}")


def nuovo(ctx, imp):
    gia = st.session_state.setdefault("af_storia", [])
    gia_salvati = list(raccolta(ctx.DIA)["testo"])
    if ctx.chiave_ai:
        try:
            testo = ctx.AI.chiedi(prompt_nuovo(imp, gia + gia_salvati[:20], gusti(ctx.DIA)),
                                  ctx.chiave_ai, ctx.modello_ai)
            m = re.search(r"\{.*\}", testo or "", re.S)
            d = json.loads(m.group(0)) if m else None
            if d and d.get("testo"):
                gia.append(d["testo"])
                return d
        except Exception:
            pass                                  # si ripiega sulla scorta
    scorta = ctx.cfg.get("aforismi_di_scorta", []) or [{"testo": "Respira.", "autore": "", "fonte": ""}]
    liberi = [a for a in scorta if a["testo"] not in gia] or scorta
    scelta = dict(random.choice(liberi))
    gia.append(scelta["testo"])
    return scelta


def _breve(a):
    return {k: a.get(k, "") or "" for k in ("testo", "autore", "fonte", "tema", "originale")}


def _vota(ctx, a, voto, segretaria):
    ctx.diario_scrivi(riga(ctx.DIARIO, a, voto, segretaria=segretaria))
    if voto >= 4:
        ctx.conferma(f"Salvato con {voto} stelle")
    corrente(ctx, forza=True)


def _altro(ctx):
    corrente(ctx, forza=True)


def _togli(ctx, a):
    ctx.diario_scrivi(ctx.DIARIO.riga("aforisma_rimosso", (a.get("autore") or "")[:60], "", 0, None, a["testo"]))


def corrente(ctx, forza=False):
    imp = ctx.impostazione(ctx.DIA, "aforismi", PREDEFINITE)
    segno = _segno_tempo(int(imp.get("minuti", 60)), ctx.DIARIO.adesso())
    salvato = st.session_state.get("af_ora")
    if forza or not salvato or salvato[0] != segno:
        st.session_state["af_ora"] = (segno, nuovo(ctx, imp))
    return st.session_state["af_ora"][1]


# ================================================================ il riquadro ===
def _audio_file(ctx, testo, voce, chiave):
    """Il file audio con la voce di Gemini (usa lettura.py)."""
    import lettura
    try:
        st.session_state[f"{chiave}_audio"] = lettura.audio_da_testo(ctx.chiave_ai, testo, voce, "calmo", "mp3")
        st.session_state.pop(f"{chiave}_audio_errore", None)
    except Exception as e:
        st.session_state[f"{chiave}_audio_errore"] = getattr(e, "messaggio", None) or str(e)


def _salva_annotazioni(ctx, a, k):
    s = st.session_state
    ctx.diario_scrivi(riga(ctx.DIARIO, a, s[f"{k}_v"], s[f"{k}_n"].strip(), s[f"{k}_s"].strip(),
                           [x.strip() for x in s[f"{k}_t"].split(",") if x.strip()], s[f"{k}_sg"]))
    ctx.conferma("Aforisma salvato nella raccolta")


def modulo_annotazioni(ctx, a, chiave, voto=4, nota="", spunti="", tag=None, segretaria=True,
                       etichetta="💾 Salva nella raccolta"):
    """Il modulo per salvare (o modificare) un aforisma con le tue annotazioni.
    L'aforisma viaggia con il pulsante: si salva quello che vedi, anche se nel
    frattempo in cima ne è comparso un altro."""
    a = _breve(a)
    k = f"{chiave}_{abs(hash(a['testo'])) % 10**6}"     # caselle nuove per ogni aforisma
    voto = 3 if voto is None or pd.isna(voto) else int(voto)
    with st.form(f"{k}_form", clear_on_submit=False):
        st.select_slider("Quanto ti piace", [1, 2, 3, 4, 5], value=voto, key=f"{k}_v",
                         format_func=lambda x: "★" * x + "☆" * (5 - x))
        st.text_area("Note", nota or "", height=70, key=f"{k}_n",
                     placeholder="perché ti colpisce, dove l'hai sentita…")
        st.text_area("Spunti", spunti or "", height=70, key=f"{k}_s",
                     placeholder="cosa ti fa venire in mente di fare, un'idea, un collegamento…")
        st.text_input("Etichette, separate da virgola", ", ".join(tag or []), key=f"{k}_t",
                      placeholder="lavoro, lezioni, mattino")
        st.checkbox("Utile alla segretaria (può citarlo e usarlo per conoscerti)", bool(segretaria), key=f"{k}_sg")
        st.form_submit_button(etichetta, type="primary", on_click=_salva_annotazioni, args=(ctx, a, k))


def riquadro(ctx, chiave="eq", compatto=False):
    """L'aforisma del momento, con ascolto, audio, voto rapido e salvataggio."""
    a = corrente(ctx)
    # il testo arriva dall'AI: si rende innocuo prima di metterlo nella pagina
    from html import escape
    testo_h, orig_h = escape(str(a.get("testo", ""))), escape(str(a.get("originale") or ""))
    autore = a.get("autore") or ""
    fonte = f", {escape(str(a['fonte']))}" if a.get("fonte") else ""
    with st.container(border=True):
        st.markdown(f"<div style='font-size:1.08rem;font-style:italic'>«{testo_h}»</div>"
                    + (f"<div style='opacity:.6;font-size:.9rem;margin-top:2px'>{orig_h}</div>"
                       if orig_h else "")
                    + (f"<div style='opacity:.7;margin-top:4px'>— {escape(autore)}{fonte}</div>" if autore else ""),
                    unsafe_allow_html=True)
        if compatto:
            return
        c = st.columns([1.2, 1, 0.6, 0.6, 1.2, 1])
        with c[0]:
            ctx.ascolta(f"{a['testo']}. {autore}", "🔊 Ascolta")
        voce = ctx.impostazione(ctx.DIA, "aforismi", PREDEFINITE).get("voce_audio", "Sulafat")
        c[1].button("🎧 Audio", key=f"{chiave}_af_audio", width='stretch', disabled=not ctx.chiave_ai,
                    help="Un file audio con la voce di Gemini, da riascoltare",
                    on_click=_audio_file, args=(ctx, f"{a['testo']} — {autore}", voce, chiave))
        c[2].button("👍", key=f"{chiave}_af_si", width='stretch', help="Mi piace: lo salvo con 4 stelle",
                    on_click=_vota, args=(ctx, _breve(a), 4, True))
        c[3].button("👎", key=f"{chiave}_af_no", width='stretch',
                    help="Non mi piace: lo segno, così non ne arrivano di simili",
                    on_click=_vota, args=(ctx, _breve(a), 1, False))
        with c[4].popover("⭐ Annota", width='stretch', key=f"{chiave}_af_pop"):
            modulo_annotazioni(ctx, a, f"{chiave}_af_nota")
        c[5].button("🔄 Altro", key=f"{chiave}_af_altro", width='stretch', on_click=_altro, args=(ctx,))
        if st.session_state.get(f"{chiave}_audio_errore"):
            st.error(st.session_state[f"{chiave}_audio_errore"])
        if st.session_state.get(f"{chiave}_audio"):
            st.audio(bytes(st.session_state[f"{chiave}_audio"]), format="audio/mpeg")


# ============================================================ le preferenze ===
def preferenze(ctx):
    imp = ctx.impostazione(ctx.DIA, "aforismi", PREDEFINITE)
    st.caption("Scegli su cosa, da chi, con che tono e ogni quanto. L'aforisma in cima "
               "alla Scrivania cambia da solo; lo stesso arriva su Telegram se lo attivi "
               "nelle notifiche, e la segretaria tiene conto di quelli che ami.")
    temi_tutti = list(dict.fromkeys(ctx.cfg.get("temi_aforismi", []) + list(imp.get("temi", []))))
    with st.form("af_preferenze"):
        temi = st.multiselect("Argomenti", temi_tutti,
                              default=[t for t in imp.get("temi", []) if t in temi_tutti])
        altri = st.text_input("Altri argomenti, separati da virgola", imp.get("altri", ""),
                              placeholder="es. elettronica, insegnare, olivi, imprenditoria")
        trad = st.multiselect("Da quali autori o tradizioni", TRADIZIONI,
                              default=[t for t in imp.get("tradizioni", []) if t in TRADIZIONI],
                              placeholder="tutte")
        c1, c2, c3 = st.columns(3)
        epoca = c1.selectbox("Epoca", EPOCHE, index=EPOCHE.index(imp.get("epoca", "qualsiasi"))
                             if imp.get("epoca") in EPOCHE else 0)
        tono = c2.selectbox("Tono", TONI, index=TONI.index(imp.get("tono", "qualsiasi"))
                            if imp.get("tono") in TONI else 0)
        lunghezza = c3.selectbox("Lunghezza", list(LUNGHEZZE),
                                 index=list(LUNGHEZZE).index(imp.get("lunghezza", "breve"))
                                 if imp.get("lunghezza") in LUNGHEZZE else 0)
        d1, d2 = st.columns(2)
        lingua = d1.selectbox("Lingua", LINGUE, index=LINGUE.index(imp.get("lingua", "solo italiano"))
                              if imp.get("lingua") in LINGUE else 0)
        chiavi = list(INTERVALLI)
        minuti = d2.selectbox("Ogni quanto cambia", chiavi,
                              index=chiavi.index(int(imp.get("minuti", 60)))
                              if int(imp.get("minuti", 60)) in chiavi else 3,
                              format_func=INTERVALLI.get)
        autori = st.text_input("Autori che ami", imp.get("autori", ""),
                               placeholder="es. Seneca, Leonardo, Feynman, Tiziano Terzani")
        evita = st.text_input("Da evitare", imp.get("evita", ""),
                              placeholder="es. frasi da poster motivazionale, politica")
        import lettura
        voci = list(lettura.VOCI_GEMINI)
        voce = st.selectbox("Voce dei file audio", voci,
                            index=voci.index(imp.get("voce_audio", "Sulafat"))
                            if imp.get("voce_audio") in voci else 0,
                            format_func=lambda v: f"{v} · {lettura.VOCI_GEMINI[v]}")
        in_scr = st.checkbox("Mostralo in cima alla Scrivania", bool(imp.get("in_scrivania", True)))
        if st.form_submit_button("💾 Salva le preferenze", type="primary"):
            nuove = {"temi": temi, "altri": altri, "tradizioni": trad, "epoca": epoca,
                     "tono": tono, "lunghezza": lunghezza, "lingua": lingua,
                     "minuti": int(minuti), "autori": autori, "evita": evita,
                     "voce_audio": voce, "in_scrivania": in_scr}
            ctx.diario_scrivi(ctx.DIARIO.riga("impostazione", "aforismi", "Equilibrio", 0, None,
                                              json.dumps(nuove, ensure_ascii=False)))
            st.session_state.pop("af_ora", None)
            ctx.conferma("Preferenze salvate: il prossimo aforisma le segue già")
            st.rerun()


# ============================================================ la raccolta =====
def _esporta(t):
    from docx import Document
    import io
    d = Document()
    d.add_heading("I miei aforismi", level=1)
    for _, r in t.iterrows():
        d.add_paragraph(f"«{r['testo']}»", style="Intense Quote")
        d.add_paragraph(f"— {r['autore']}" + (f", {r['fonte']}" if r["fonte"] else "")
                        + (f"   {'★' * int(r['voto'])}" if pd.notna(r["voto"]) else ""))
        if r["nota"]:
            d.add_paragraph(f"Note: {r['nota']}")
        if r["spunti"]:
            d.add_paragraph(f"Spunti: {r['spunti']}")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def mostra_raccolta(ctx):
    r = raccolta(ctx.DIA)
    if r.empty:
        st.info("La raccolta è vuota. Salva un aforisma con 👍 o ⭐ Annota.")
        return
    st.markdown(f"##### ⭐ La tua raccolta · {len(r)}")
    f1, f2, f3 = st.columns([2, 1, 1])
    cerca = f1.text_input("🔎 Cerca", key="af_cerca", placeholder="parola, autore, nota…")
    tutti_tag = sorted({t for ts in r["tag"] for t in (ts or [])})
    tag = f2.multiselect("Etichette", tutti_tag, key="af_tag", placeholder="tutte")
    minimo = f3.select_slider("Voto minimo", [0, 1, 2, 3, 4, 5], value=0, key="af_min",
                              format_func=lambda x: "tutti" if x == 0 else "★" * x)
    g1, g2 = st.columns(2)
    autori = g1.multiselect("Autori", sorted({a for a in r["autore"] if a}), key="af_aut",
                            placeholder="tutti")
    ordine = g2.selectbox("Ordina per", ["più recenti", "voto più alto", "autore"], key="af_ord")
    t = r.copy()
    if cerca.strip():
        q = cerca.strip().lower()
        t = t[t.apply(lambda x: q in " ".join(str(x[c]) for c in
                                               ("testo", "autore", "nota", "spunti", "tema")).lower(), axis=1)]
    if tag:
        t = t[t["tag"].apply(lambda ts: bool(set(ts or []) & set(tag)))]
    if minimo:
        t = t[t["voto"].fillna(0) >= minimo]
    if autori:
        t = t[t["autore"].isin(autori)]
    if ordine == "voto più alto":
        t = t.sort_values("voto", ascending=False, na_position="last")
    elif ordine == "autore":
        t = t.sort_values("autore")
    st.caption(f"{len(t)} aforismi con questi filtri.")

    for i, (_, a) in enumerate(t.head(80).iterrows()):
        stelle = "★" * int(a["voto"]) if a["voto"] is not None and pd.notna(a["voto"]) else "—"
        with st.expander(f"{stelle}  «{a['testo'][:70]}{'…' if len(a['testo']) > 70 else ''}» — {a['autore']}"):
            st.markdown(f"*«{a['testo']}»*  \n— **{a['autore']}**" + (f", {a['fonte']}" if a["fonte"] else ""))
            if a["originale"]:
                st.caption(a["originale"])
            if a["nota"]:
                st.markdown(f"**Note:** {a['nota']}")
            if a["spunti"]:
                st.markdown(f"**Spunti:** {a['spunti']}")
            if a["tag"]:
                st.caption("🏷️ " + " · ".join(a["tag"]))
            if a["segretaria"]:
                st.caption("👩‍💼 utile alla segretaria")
            b1, b2 = st.columns([1, 1])
            with b1:
                ctx.ascolta(f"{a['testo']}. {a['autore']}", "🔊 Ascolta")
            b2.button("🗑️ Togli dalla raccolta", key=f"af_via_{i}", width='stretch',
                      on_click=_togli, args=(ctx, _breve(a)))
            st.markdown("**✏️ Modifica le annotazioni**")
            modulo_annotazioni(ctx, a.to_dict(), f"af_mod_{i}", a["voto"], a["nota"], a["spunti"],
                               a["tag"], a["segretaria"], "💾 Salva le modifiche")

    e1, e2 = st.columns(2)
    csv = t.assign(tag=t["tag"].apply(lambda x: ", ".join(x or []))).drop(columns=["salvato"])
    e1.download_button("⬇️ Esporta in Excel/CSV", csv.to_csv(index=False).encode("utf-8-sig"),
                       "aforismi.csv", "text/csv", width='stretch', key="af_csv")
    e2.download_button("⬇️ Esporta in Word", _esporta(t), "aforismi.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       width='stretch', key="af_docx")
