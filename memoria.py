"""
memoria.py — 🧠 Memoria: il rito quotidiano per ricordare, in 📚 Studio.

    🌅 IL RITO DI OGGI    i cinque passi, uno dopo l'altro, su una cosa da ricordare:
                          1 CREDERE      lo dici, ad alta voce, con convinzione
                          2 VOLERE       scegli cosa ricordare e perché ti serve
                          3 VISUALIZZARE tag mentale · etichetta · immagine buffa ·
                                         immagine dei concetti chiave
                          4 COMANDARE    il comando che collega lo spunto al ricordo
                          5 RIVEDERE     Quadro te lo ripropone domani, fra 3, 7, 14, 30 giorni
    🔁 RIPASSO            le cose da rivedere oggi: vedi lo spunto, ricordi, poi controlli
    ⚡ ALLENAMENTO LAMPO   cinque parole a caso, una storia buffa, e le richiami (anche la sera)
    📈 PROGRESSI          giorni di fila, quanto ricordi, a che punto è ogni cosa
    📖 LE TECNICHE        cosa fa ogni passo e come farlo bene

PERCHÉ FUNZIONA (in breve, senza magia)
    Decidere di ricordare e sapere perché ti serve fa prestare più attenzione.
    Un'immagine concreta, strana e in movimento si ricorda meglio di una frase.
    Il tag e l'etichetta danno al ricordo un nome e un cassetto da cui ripescarlo.
    Il comando è uno spunto preciso che riporta su il ricordo.
    E soprattutto: richiamarlo a intervalli crescenti (prima di rileggerlo) è
    la cosa che più di tutte lo fa restare. Per questo il Ripasso chiede prima
    di ricordare e solo dopo mostra la risposta.

DOVE FINISCONO I DATI: nel diario, come il resto di Quadro.
    memoria          una cosa da ricordare (Nota = JSON con tag, etichetta, immagini…)
    memoria_ripasso  un ripasso: ricordato o no, la scatola nuova, la prossima data
    memoria_rimossa  una cosa tolta dal ripasso
    memoria_rito     il rito fatto (Valore = quanti passi su cinque)
    memoria_lampo    un allenamento lampo (Valore = parte ricordata, da 0 a 1)
"""

import datetime as dt
import json
import random
import re
import uuid

import pandas as pd
import streamlit as st

INTERVALLI = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}      # scatola → giorni al prossimo ripasso
AFFERMAZIONE = "La mia memoria funziona: quello che decido di ricordare, lo ricordo."
PASSI = [("💪", "Credere"), ("🎯", "Volere"), ("🖼️", "Visualizzare"), ("🗣️", "Comandare"), ("🔁", "Rivedere")]

# parole concrete e facili da immaginare, per l'allenamento lampo
PAROLE = """
ombrello giraffa chitarra pentola cactus razzo bicicletta formaggio pinguino martello lampadina
ancora scarpone trombetta cuscino vulcano pizza orologio delfino scopa forbici tamburo candela
banana elefante valigia coccodrillo ombrellone trattore farfalla gelato pagliaccio castello
pomodoro aquilone balena cappello robot uovo fragola sedia treno luna cavallo cipolla specchio
tromba nave carota zebra mongolfiera arancia chiave orso cannone tazza serpente pianoforte
fungo spazzolino ape canotto ferro_da_stiro gallina televisore bottiglia drago mela sirena
lucchetto tartaruga fisarmonica cammello olio limone gufo trapano pallone corona salame
carriola telescopio aragosta frigorifero violino ragno cuore spada piuma secchio canguro
bussola panettone motosega maiale ventaglio mappamondo lumaca saldatore matita uva tenda
""".split()


# ================================================================ i dati ====
def _nota(t):
    try:
        d = json.loads(t or "{}")
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _data(x):
    try:
        return dt.date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def voci(dia, oggi):
    """
    Le cose da ricordare, una per riga, con la scatola e il prossimo ripasso.
    Vince l'ultima riga per ogni id; i ripassi spostano scatola e data.
    """
    colonne = ["id", "cosa", "etichetta", "tag", "buffa", "concetti", "comando", "perche",
               "creata", "scatola", "prossima", "ripassi", "ricordate"]
    if dia is None or dia.empty:
        return pd.DataFrame(columns=colonne)
    d = dia.sort_values(["Data", "Ora"], kind="stable")
    tolte = set(d[d["Tipo"] == "memoria_rimossa"]["Attivita"])
    righe = {}
    for _, r in d[d["Tipo"] == "memoria"].iterrows():
        n = _nota(r["Nota"])
        i = n.get("id")
        if not i or i in tolte:
            continue
        prima = righe.get(i, {})
        righe[i] = {"id": i, "cosa": n.get("testo") or r["Attivita"], "etichetta": n.get("etichetta", ""),
                    "tag": n.get("tag", ""), "buffa": n.get("buffa", ""), "concetti": n.get("concetti", ""),
                    "comando": n.get("comando", ""), "perche": n.get("perche", ""),
                    "creata": prima.get("creata") or (r["Data"].date() if pd.notna(r["Data"]) else oggi),
                    "scatola": prima.get("scatola", 1),
                    "prossima": prima.get("prossima") or _data(n.get("prossima")) or oggi,
                    "ripassi": prima.get("ripassi", 0), "ricordate": prima.get("ricordate", 0)}
    for _, r in d[d["Tipo"] == "memoria_ripasso"].iterrows():
        i = r["Attivita"]
        if i not in righe:
            continue
        v = righe[i]
        v["ripassi"] += 1
        if r["Strumento"] == "ricordato":
            v["ricordate"] += 1
        try:
            v["scatola"] = int(float(r["Valore"]))
        except (TypeError, ValueError):
            pass
        v["prossima"] = _data(_nota(r["Nota"]).get("prossima")) or v["prossima"]
    return pd.DataFrame(list(righe.values()), columns=colonne)


def da_rivedere(dia, oggi):
    v = voci(dia, oggi)
    return v[v["prossima"] <= oggi] if not v.empty else v


def giorni_attivi(dia):
    """I giorni in cui hai fatto qualcosa per la memoria (rito, ripasso, lampo)."""
    if dia is None or dia.empty:
        return set()
    m = dia[dia["Tipo"].isin(["memoria_rito", "memoria_ripasso", "memoria_lampo", "memoria"])]
    return {x.date() for x in m["Data"].dropna()}


def serie(dia, oggi):
    """Quanti giorni di fila, fino a oggi (o fino a ieri, se oggi non hai ancora fatto)."""
    giorni = giorni_attivi(dia)
    g = oggi if oggi in giorni else oggi - dt.timedelta(days=1)
    n = 0
    while g in giorni:
        n += 1
        g -= dt.timedelta(days=1)
    return n


def rito_fatto(dia, oggi):
    if dia is None or dia.empty:
        return False
    r = dia[(dia["Tipo"] == "memoria_rito")]
    return bool(len(r[r["Data"].dt.date == oggi]))


def per_segretaria(dia, oggi):
    """Quello che la segretaria (e Telegram) sanno della memoria."""
    return {"da_rivedere": int(len(da_rivedere(dia, oggi))), "rito_oggi": rito_fatto(dia, oggi),
            "giorni_di_fila": serie(dia, oggi)}


def riga_nuova(ctx, cosa, etichetta="", tag="", buffa="", concetti="", comando="", perche=""):
    oggi = ctx.DIARIO.oggi()
    n = {"id": uuid.uuid4().hex[:8], "testo": cosa.strip(), "etichetta": etichetta.strip(), "tag": tag.strip(),
         "buffa": buffa.strip(), "concetti": concetti.strip(), "comando": comando.strip(), "perche": perche.strip(),
         "prossima": (oggi + dt.timedelta(days=INTERVALLI[1])).isoformat()}
    return ctx.DIARIO.riga("memoria", cosa.strip()[:80], etichetta.strip(), 0, 1, json.dumps(n, ensure_ascii=False))


def _impostazioni(ctx):
    return ctx.impostazione(ctx.DIA, "memoria", {"affermazione": AFFERMAZIONE, "parole_lampo": 5})


# ================================================================ la scheda ===
def mostra(ctx):
    oggi = ctx.DIARIO.oggi()
    v = voci(ctx.DIA, oggi)
    dovute = v[v["prossima"] <= oggi] if not v.empty else v
    fatto = rito_fatto(ctx.DIA, oggi)
    c = st.columns(4)
    c[0].metric("Giorni di fila", serie(ctx.DIA, oggi))
    c[1].metric("Rito di oggi", "✅ fatto" if fatto else "da fare")
    c[2].metric("Da rivedere oggi", len(dovute))
    c[3].metric("Cose in memoria", len(v))
    # nomi fissi: se cambiassero (per esempio con il numero da rivedere) la scheda tornerebbe alla prima
    T = st.tabs(["🌅 Il rito di oggi", "🔁 Ripasso", "⚡ Allenamento lampo", "📈 Progressi",
                 "📖 Le tecniche"], key="mem_sezione")
    with T[0]:
        _rito(ctx, v)
    with T[1]:
        _ripasso(ctx, v, dovute)
    with T[2]:
        _lampo(ctx)
    with T[3]:
        _progressi(ctx, v)
    with T[4]:
        st.markdown(TECNICHE)


# ------------------------------------------------------------- il rito ---
CAMPI = ["mem_cosa", "mem_perche", "mem_tag", "mem_etichetta", "mem_buffa", "mem_concetti", "mem_comando"]


def _aiuto_ai(ctx):
    cosa = st.session_state.get("mem_cosa", "").strip()
    if not cosa:
        st.session_state["mem_avviso"] = "Scrivi prima, al passo 2, cosa vuoi ricordare."
        return
    prompt = (
        "Aiuti una persona a memorizzare con queste tecniche: un TAG mentale (1-3 parole concrete che danno un "
        "nome al ricordo), un'ETICHETTA (il cassetto o la categoria in cui archiviarlo), un'IMMAGINE BUFFA "
        "(una scena assurda, esagerata, in movimento, con colori, suoni o odori, che collega il tag al "
        "contenuto) e l'IMMAGINE DEI CONCETTI CHIAVE (un'immagine concreta per ciascun concetto chiave, al massimo "
        "cinque, legate in una mini-storia nell'ordine giusto). Poi il COMANDO: una frase breve, in prima persona, "
        "che dice alla mente quale spunto deve riportare su il ricordo.\n"
        f"Da ricordare: «{cosa}»\nPerché gli serve: «{st.session_state.get('mem_perche', '')}»\n"
        "Rispondi in italiano, SOLO con JSON valido: {\"tag\": \"...\", \"etichetta\": \"...\", "
        "\"buffa\": \"...\", \"concetti\": \"...\", \"comando\": \"...\"}. Frasi brevi e molto visive.")
    try:
        import lettura
        d = lettura._json(ctx.AI.chiedi(prompt, ctx.chiave_ai, ctx.modello_ai))
    except Exception as e:
        st.session_state["mem_avviso"] = getattr(e, "messaggio", None) or str(e)
        return
    if not isinstance(d, dict):
        st.session_state["mem_avviso"] = "L'AI non ha risposto come serviva: riprova."
        return
    # i campi si riempiono al giro dopo, prima che le caselle esistano
    st.session_state["__mem_prefill__"] = {f"mem_{k}": str(d.get(k, "")) for k in
                                           ("tag", "etichetta", "buffa", "concetti", "comando")}


def _rito(ctx, v):
    imp = _impostazioni(ctx)
    if "__mem_prefill__" in st.session_state:
        for k, val in st.session_state.pop("__mem_prefill__").items():
            st.session_state[k] = val
    if st.session_state.pop("__mem_svuota__", False):
        for k in CAMPI + ["mem_creduto", "mem_comandato"]:
            st.session_state.pop(k, None)
    for k in CAMPI:
        st.session_state.setdefault(k, "")
    st.caption("Cinque passi, cinque minuti, su una cosa che vuoi ricordare davvero: un concetto di studio, "
               "un nome, un numero, i punti di un discorso. Fallo ogni giorno, anche su una cosa piccola: "
               "è la ripetizione del rito che lo rende automatico.")
    fatti = sum([bool(st.session_state.get("mem_creduto")), bool(st.session_state["mem_cosa"].strip()),
                 bool(st.session_state["mem_tag"].strip() and st.session_state["mem_buffa"].strip()),
                 bool(st.session_state.get("mem_comandato")), False])
    st.progress(fatti / 5, text=f"{fatti} passi su 5")

    with st.container(border=True):
        st.markdown("**1 · 💪 Credere** — dillo ad alta voce, lentamente, e credici")
        st.markdown(f"> *{imp.get('affermazione') or AFFERMAZIONE}*")
        a1, a2 = st.columns([1, 3])
        with a1:
            ctx.ascolta(imp.get("affermazione") or AFFERMAZIONE, "🔊 Ascoltala")
        a2.checkbox("L'ho detta, con convinzione", key="mem_creduto")

    with st.container(border=True):
        st.markdown("**2 · 🎯 Volere** — scegli cosa ricordare e perché ti serve")
        st.text_area("Cosa voglio ricordare", key="mem_cosa", height=90,
                     placeholder="es. le 4 fasi del ciclo di Carnot; il nome del direttore del GAL; i 3 punti del pitch")
        st.text_input("Perché mi serve (una riga: dà la spinta)", key="mem_perche",
                      placeholder="es. lo spiego all'allievo giovedì")

    with st.container(border=True):
        st.markdown("**3 · 🖼️ Visualizzare** — dai al ricordo un nome, un cassetto e un'immagine")
        b1, b2 = st.columns(2)
        b1.text_input("🏷️ Tag mentale (1-3 parole concrete)", key="mem_tag", placeholder="es. pistone che respira")
        etichette = sorted({e for e in v["etichetta"] if e}) if not v.empty else []
        b2.text_input("🗂️ Etichetta, il cassetto" + (f" (già usate: {', '.join(etichette[:6])})" if etichette else ""),
                      key="mem_etichetta", placeholder="es. Termodinamica · Persone · Discorsi")
        st.text_area("🤪 Immagine buffa: assurda, esagerata, in movimento, con un suono o un odore",
                     key="mem_buffa", height=80,
                     placeholder="es. un pistone gigante con i baffi che respira come un mantice e starnutisce vapore")
        st.text_area("🧩 Immagini dei concetti chiave: una per concetto, legate in una storia", key="mem_concetti",
                     height=80, placeholder="es. 1 un sub che si gonfia (espansione) → 2 … → 3 … → 4 …")
        st.button("✨ Aiutami a inventarle", key="mem_ai", on_click=_aiuto_ai, args=(ctx,),
                  disabled=not ctx.chiave_ai, help="L'AI propone tag, etichetta, immagini e comando: poi li cambi tu.")
        if st.session_state.get("mem_avviso"):
            st.warning(st.session_state.pop("mem_avviso"))
        st.caption("Chiudi gli occhi e guarda la scena per dieci secondi: più è strana e viva, più resta.")

    with st.container(border=True):
        st.markdown("**4 · 🗣️ Comandare** — dai l'ordine alla mente: quale spunto riporta su il ricordo")
        if not st.session_state["mem_comando"] and st.session_state["mem_tag"]:
            st.session_state["mem_comando"] = (f"Quando penso a «{st.session_state['mem_tag']}», "
                                               "rivedo la scena e ricordo tutto.")
        st.text_input("Il comando", key="mem_comando",
                      placeholder="es. Quando penso a «pistone che respira», ricordo le quattro fasi.")
        c1, c2 = st.columns([1, 3])
        with c1:
            if st.session_state["mem_comando"]:
                ctx.ascolta(st.session_state["mem_comando"], "🔊 Ascoltalo")
        c2.checkbox("L'ho dato, a voce, guardando la scena", key="mem_comandato")

    with st.container(border=True):
        st.markdown("**5 · 🔁 Rivedere** — domani, poi fra 3, 7, 14 e 30 giorni")
        st.caption("Quadro te lo ripropone in «🔁 Ripasso»: prima provi a ricordare dal tag e dall'etichetta, "
                   "poi controlli. Ogni volta che lo ricordi, il ripasso dopo si allontana.")
        pronto = bool(st.session_state["mem_cosa"].strip())
        if st.button("💾 Salva e mettilo in ripasso", type="primary", key="mem_salva", disabled=not pronto):
            passi = sum([bool(st.session_state.get("mem_creduto")), True,
                         bool(st.session_state["mem_tag"].strip() and st.session_state["mem_buffa"].strip()),
                         bool(st.session_state.get("mem_comandato")), True])
            righe = [riga_nuova(ctx, st.session_state["mem_cosa"], st.session_state["mem_etichetta"],
                                st.session_state["mem_tag"], st.session_state["mem_buffa"],
                                st.session_state["mem_concetti"], st.session_state["mem_comando"],
                                st.session_state["mem_perche"]),
                     ctx.DIARIO.riga("memoria_rito", "rito", "", 5, passi, json.dumps({"passi": passi}))]
            ctx.diario_scrivi(righe)
            ctx.conferma(f"In memoria: primo ripasso domani ({passi} passi su 5)")
            st.session_state["__mem_svuota__"] = True
            st.rerun()
        if not pronto:
            st.caption("Per salvare basta aver scritto, al passo 2, cosa vuoi ricordare.")


# ------------------------------------------------------------ il ripasso ---
def _ripasso(ctx, v, dovute):
    oggi = ctx.DIARIO.oggi()
    if dovute.empty:
        if v.empty:
            st.info("Ancora niente da rivedere: fai il rito di oggi su una cosa da ricordare.")
        else:
            prossima = v["prossima"].min()
            st.success(f"Tutto rivisto. Il prossimo ripasso è il {prossima:%d/%m}.")
    else:
        x = dovute.sort_values(["prossima", "scatola"]).iloc[0]
        st.caption(f"{len(dovute)} da rivedere oggi. Prima prova a ricordare, poi guarda: è il richiamo che fissa.")
        with st.container(border=True):
            st.markdown(f"#### 🏷️ {x['tag'] or '(senza tag)'}")
            st.caption(f"🗂️ {x['etichetta'] or 'senza etichetta'} · scatola {int(x['scatola'])} di 5")
            if x["comando"]:
                st.markdown(f"🗣️ *{x['comando']}*")
            chiave = f"mem_vedi_{x['id']}"
            if not st.session_state.get(chiave):
                st.text_area("Scrivi (o dì a te stesso) quello che ricordi", key=f"mem_prova_{x['id']}", height=80)
                if st.button("👀 Mostra la risposta", key=f"mem_mostra_{x['id']}", type="primary"):
                    st.session_state[chiave] = True
                    st.rerun()
            else:
                st.markdown(f"**Da ricordare:** {x['cosa']}")
                if x["buffa"]:
                    st.markdown(f"🤪 {x['buffa']}")
                if x["concetti"]:
                    st.markdown(f"🧩 {x['concetti']}")
                r1, r2 = st.columns(2)
                for col, esito, etichetta, tipo in ((r1, "ricordato", "✅ Ricordato", "primary"),
                                                    (r2, "non ricordato", "❌ Non ricordato", "secondary")):
                    if col.button(etichetta, key=f"mem_{esito}_{x['id']}", type=tipo, width="stretch"):
                        scatola = min(5, int(x["scatola"]) + 1) if esito == "ricordato" else 1
                        prossima = oggi + dt.timedelta(days=INTERVALLI[scatola])
                        ctx.diario_scrivi(ctx.DIARIO.riga("memoria_ripasso", x["id"], esito, 0, scatola,
                                                          json.dumps({"prossima": prossima.isoformat()})))
                        st.session_state.pop(chiave, None)
                        ctx.conferma(f"Prossimo ripasso il {prossima:%d/%m}")
                        st.rerun()

    if not v.empty:
        with st.expander(f"🗂️ Tutte le cose in memoria ({len(v)})"):
            e = sorted({x for x in v["etichetta"] if x})
            scelta = st.multiselect("Etichetta", e, key="mem_filtro", placeholder="tutte")
            t = v[v["etichetta"].isin(scelta)] if scelta else v
            st.dataframe(t[["tag", "etichetta", "cosa", "scatola", "prossima", "ripassi", "ricordate"]],
                         hide_index=True, width="stretch")
            togli = st.selectbox("Togli dal ripasso", ["—"] + [f"{r['tag'] or r['cosa'][:40]} · {r['id']}"
                                                              for _, r in t.iterrows()], key="mem_togli")
            if togli != "—" and st.button("🗑️ Togli", key="mem_togli_bt"):
                ctx.diario_scrivi(ctx.DIARIO.riga("memoria_rimossa", togli.rsplit(" · ", 1)[-1], "", 0, None, ""))
                ctx.conferma("Tolta dal ripasso")
                st.rerun()


# ------------------------------------------------------- allenamento lampo ---
def _lampo(ctx):
    imp = _impostazioni(ctx)
    quante = st.select_slider("Quante parole", [5, 7, 10], value=int(imp.get("parole_lampo", 5)), key="mem_l_n")
    st.caption("Ti do delle parole a caso. Le leghi in una storia buffa, una scena dopo l'altra, poi le "
               "nascondi e le richiami in ordine. Stasera te le richiedo: è lì che si vede.")
    oggi = ctx.DIARIO.oggi().isoformat()
    if st.button("🎲 Nuove parole", key="mem_l_nuove", type="primary"):
        st.session_state["mem_l_parole"] = [p.replace("_", " ") for p in random.sample(PAROLE, quante)]
        st.session_state["mem_l_nascoste"] = False
    parole = st.session_state.get("mem_l_parole")
    if parole:
        if not st.session_state.get("mem_l_nascoste"):
            st.markdown("### " + " → ".join(parole))
            st.caption("Una scena per coppia: la prima parola fa qualcosa di assurdo alla seconda, e così via.")
            if st.button("🙈 Le ho legate: nascondile", key="mem_l_nascondi"):
                st.session_state["mem_l_nascoste"] = True
                st.rerun()
        else:
            scritte = st.text_area("Scrivile in ordine, una per riga o separate da virgole", key="mem_l_risposta")
            if st.button("✔️ Controlla", key="mem_l_controlla"):
                punti = _punteggio(parole, scritte)
                ctx.diario_scrivi(ctx.DIARIO.riga("memoria_lampo", "subito", "", 0, round(punti, 2),
                                                  json.dumps({"parole": parole, "giorno": oggi}, ensure_ascii=False)))
                st.session_state["mem_l_esito"] = (punti, parole)
                st.session_state.pop("mem_l_parole", None)
                st.rerun()
    if st.session_state.get("mem_l_esito"):
        punti, parole_ = st.session_state["mem_l_esito"]
        st.success(f"{punti:.0%} al posto giusto. Le parole erano: {', '.join(parole_)}")

    # il richiamo della sera: le parole dell'ultimo allenamento di oggi
    dia = ctx.DIA
    if dia is not None and not dia.empty:
        l = dia[dia["Tipo"] == "memoria_lampo"].sort_values(["Data", "Ora"], kind="stable")
        di_oggi = l[l["Data"].dt.date == ctx.DIARIO.oggi()]
        if len(di_oggi) and (di_oggi.iloc[-1]["Attivita"] == "subito"):
            n = _nota(di_oggi.iloc[-1]["Nota"])
            with st.container(border=True):
                st.markdown("**🌙 Il richiamo della sera** — le parole di prima, senza guardarle")
                serali = st.text_area("Quelle che ricordi, in ordine", key="mem_l_sera")
                if st.button("✔️ Controlla il richiamo", key="mem_l_sera_bt"):
                    punti = _punteggio(n.get("parole", []), serali)
                    ctx.diario_scrivi(ctx.DIARIO.riga("memoria_lampo", "sera", "", 0, round(punti, 2),
                                                      json.dumps(n, ensure_ascii=False)))
                    ctx.conferma(f"Richiamo della sera: {punti:.0%}")
                    st.rerun()


def _punteggio(parole, scritte):
    """La parte di parole ricordate al posto giusto (da 0 a 1)."""
    date = [p.strip().lower() for p in re.split(r"[,\n;]+", scritte or "") if p.strip()]
    giuste = [p.lower() for p in parole]
    return sum(1 for i, p in enumerate(giuste) if i < len(date) and date[i] == p) / max(1, len(giuste))


# ------------------------------------------------------------ i progressi ---
def _progressi(ctx, v):
    oggi = ctx.DIARIO.oggi()
    dia = ctx.DIA
    giorni = giorni_attivi(dia)
    ultimi = [oggi - dt.timedelta(days=i) for i in range(27, -1, -1)]
    st.markdown("**Le ultime quattro settimane** (🟩 = hai fatto qualcosa per la memoria)")
    st.markdown(" ".join("🟩" if g in giorni else "⬜" for g in ultimi))
    if dia is not None and not dia.empty:
        rip = dia[(dia["Tipo"] == "memoria_ripasso") & (dia["Data"] >= pd.Timestamp(oggi - dt.timedelta(days=30)))]
        lam = dia[(dia["Tipo"] == "memoria_lampo") & (dia["Data"] >= pd.Timestamp(oggi - dt.timedelta(days=30)))]
        k = st.columns(3)
        k[0].metric("Ripassi in 30 giorni", len(rip))
        k[1].metric("Ricordate al ripasso", f"{(rip['Strumento'] == 'ricordato').mean():.0%}" if len(rip) else "—")
        k[2].metric("Allenamento lampo, media", f"{pd.to_numeric(lam['Valore'], errors='coerce').mean():.0%}"
                    if len(lam) else "—")
    if not v.empty:
        st.markdown("**A che punto è ogni cosa** (scatola 5 = la sai da settimane)")
        st.bar_chart(v["scatola"].value_counts().reindex([1, 2, 3, 4, 5], fill_value=0).rename("cose"), height=180)

    st.markdown("##### ⚙️ Il tuo rito")
    imp = _impostazioni(ctx)
    with st.form("mem_impostazioni"):
        aff = st.text_input("La tua frase per «Credere»", imp.get("affermazione") or AFFERMAZIONE)
        n = st.select_slider("Parole dell'allenamento lampo", [5, 7, 10], value=int(imp.get("parole_lampo", 5)))
        if st.form_submit_button("💾 Salva"):
            ctx.diario_scrivi(ctx.DIARIO.riga("impostazione", "memoria", "Memoria", 0, None,
                                              json.dumps({"affermazione": aff.strip() or AFFERMAZIONE,
                                                          "parole_lampo": n}, ensure_ascii=False)))
            ctx.conferma("Salvato")
            st.rerun()
    st.caption("Per un promemoria quotidiano su Telegram: Segreteria → 🤖 Segretaria virtuale → 🔔 Notifiche e Telegram, aggiungi una riga "
               "di tipo «memoria» all'ora che preferisci (per esempio 08:45 e 21:00 per il richiamo della sera).")


# ============================================================ le tecniche ====
TECNICHE = """
#### I cinque passi

**1 · 💪 Credere.** Prima di cominciare ti dici, ad alta voce, che ricorderai. Non è magia: chi parte
convinto di dimenticare smette di prestare attenzione. La frase serve a mettere la testa in modalità
«adesso registro». Dilla lentamente, guardando nel vuoto, come un pilota che fa la checklist.

**2 · 🎯 Volere.** Decidi *che cosa* vuoi ricordare, preciso, e *perché* ti serve. Una cosa che sai a cosa
ti servirà la elabori di più, e quello che elabori di più resta. Meglio una cosa piccola ricordata bene
che dieci lette di corsa.

**3 · 🖼️ Visualizzare.** Trasformi la cosa in immagini, con quattro attrezzi:
- **🏷️ Il tag mentale**: un nome breve e concreto da dare al ricordo, che lo «chiama». *Pistone che respira*
  per il ciclo di Carnot. È la maniglia con cui lo tiri fuori.
- **🗂️ L'etichetta**: il cassetto in cui lo metti (*Termodinamica*, *Persone*, *Discorsi*). Le cose
  archiviate insieme si ritrovano insieme, e il cassetto è già metà dello spunto.
- **🤪 L'immagine buffa**: una scena assurda, esagerata, che si muove, con un colore, un suono o un odore,
  e che lega il tag al contenuto. Il cervello butta via il normale e tiene lo strano.
- **🧩 L'immagine dei concetti chiave**: un'immagine per ogni concetto, legate in una storia nell'ordine
  giusto (la prima fa qualcosa alla seconda…). Se vuoi, mettile lungo un percorso che conosci bene: la
  porta di casa, l'ingresso, la cucina.

**4 · 🗣️ Comandare.** Dai alla mente un ordine preciso: *«Quando penso a "pistone che respira", rivedo la
scena e ricordo le quattro fasi»*. Collega uno spunto (il tag, un luogo, un momento della giornata) al
ricordo. Più lo spunto è preciso, più il ricordo torna da solo quando serve.

**5 · 🔁 Rivedere.** È il passo che conta di più. Non si rilegge: si **richiama**, prima di guardare, a
intervalli che si allungano: domani, fra 3, 7, 14, 30 giorni. Ogni richiamo riuscito sposta il ricordo
un po' più in profondità; ogni errore lo riporta all'inizio, ed è giusto così.

#### Ogni giorno, in pratica
- **Mattina, 5 minuti:** il rito su una cosa nuova (🌅) e i ripassi del giorno (🔁).
- **Quando hai 2 minuti:** l'allenamento lampo (⚡) — cinque parole, una storia buffa.
- **Sera, 1 minuto:** il richiamo delle parole del mattino. È l'esercizio che allena davvero.

#### Errori da evitare
- Immagini piatte o realistiche: se non ti fanno sorridere, non bastano.
- Tag astratti («energia», «processo»): devono essere cose che si possono toccare.
- Rileggere invece di richiamare: rileggere dà l'impressione di sapere, richiamare fa sapere.
- Saltare i ripassi: meglio due minuti ogni giorno che un'ora la domenica.
"""


# ========================================================= sulla Scrivania ===
def promemoria_scrivania(ctx, vai=None):
    """Una riga sulla Scrivania, solo se c'è qualcosa da fare oggi."""
    oggi = ctx.DIARIO.oggi()
    try:
        info = per_segretaria(ctx.DIA, oggi)
    except Exception:
        return
    if info["rito_oggi"] and not info["da_rivedere"]:
        return
    parti = []
    if not info["rito_oggi"]:
        parti.append("il rito di oggi è ancora da fare")
    if info["da_rivedere"]:
        parti.append(f"{info['da_rivedere']} cose da rivedere")
    c1, c2 = st.columns([4, 1])
    c1.info(f"🧠 Memoria: {' e '.join(parti)}"
            + (f" · {info['giorni_di_fila']} giorni di fila" if info["giorni_di_fila"] else "") + ".")
    if vai:
        c2.button("➜ Allenati", key="mem_scr_vai", on_click=vai,
                  args=({"scheda": "📚 Studio", "chiave": "studio_sezione", "valore": "🧠 Memoria"},),
                  width="stretch")
