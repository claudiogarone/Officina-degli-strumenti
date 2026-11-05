"""
guida.py — la scheda ❓ Guida, più viva di un elenco di domande.

    🗺️ LE SCHEDE     una scheda per ogni scheda di Quadro: cosa c'è dentro, come
                     si fanno le cose passo per passo, e il pulsante per andarci
    🆕 NOVITÀ        cosa è cambiato, con il pulsante per provarlo
    ❓ DOMANDE       le domande e i problemi di sempre (Secrets, diario, errori…)
    🔎 CERCA         una parola, e cerca dappertutto
    🤖 CHIEDI        una domanda in parole tue: l'AI risponde usando SOLO la guida

Il contenuto sta in guida.json, così lo cambi senza toccare il codice:
    "schede":  [{"scheda", "in_breve", "cosa_trovi": [...], "come_si_fa": [
                 {"domanda", "passi": [...], "apri": {"scheda", "chiave", "valore"}}],
                 "sottopagine": [...], "pagina"}]
    "novita":  [{"quando", "titolo", "testo", "apri"}]
    "sezioni": [{"icona", "titolo", "voci": [{"domanda", "risposta"}]}]   (come prima)

«apri» dice dove portarti: "scheda" è il nome della scheda così come appare in
alto; "chiave" e "valore", facoltativi, scelgono anche la sotto-scheda (per
esempio "studio_sezione" e "📖 Leggimelo"). La stessa guida la legge anche la
segretaria quando le chiedi «come si fa…».
"""

import json
import os

import streamlit as st


@st.cache_data(show_spinner=False)
def _leggi(_segno):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "guida.json"), encoding="utf-8") as f:
        return json.load(f)


def carica():
    """La guida da guida.json (si rilegge quando il file cambia)."""
    percorso = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guida.json")
    try:
        return _leggi(os.path.getmtime(percorso))
    except Exception as e:
        return {"_errore": str(e)}


def destinazioni(G):
    """I posti dove la guida (e la segretaria) sanno portarti: nome → dove."""
    d = {}
    for s in G.get("schede", []):
        d[s["scheda"]] = {"scheda": s["scheda"]}
        for sp in s.get("sottopagine", []):
            d[sp["nome"]] = {"scheda": s["scheda"], "chiave": sp["chiave"], "valore": sp["valore"]}
    return d


def vai(dove):
    """
    Chiede di portarti in una scheda (e sotto-scheda). Si usa come on_click.

    Le schede di Quadro le sceglie il browser, non Python: cambiare il valore
    in st.session_state non le sposta. Quindi qui si prende solo nota, e al
    giro dopo `naviga_se_serve` mette nella pagina tre righe di JavaScript che
    «cliccano» la scheda giusta, come faresti tu.
    """
    if dove and dove.get("scheda"):
        st.session_state["__gd_vai__"] = dove


def naviga_se_serve():
    """Da chiamare a ogni giro, fuori dalle schede (app.py lo fa): apre la scheda chiesta."""
    dove = st.session_state.pop("__gd_vai__", None)
    if not dove:
        return
    # i nomi vengono da guida.json, non dall'AI; json.dumps li rende testo sicuro
    d = json.dumps({"scheda": dove.get("scheda", ""), "sotto": dove.get("valore") or ""},
                   ensure_ascii=False).replace("</", "<\\/")
    script = f"""<script>
(function () {{
  const D = {d};
  const nome = el => (el.innerText || el.textContent || '').trim();
  // una scheda visibile (non dentro una scheda chiusa, che Streamlit marca «inert»)
  const trova = t => [...document.querySelectorAll('[role=tab]')].find(x => nome(x) === t && !x.closest('[inert]'));
  function prova(t, poi, n) {{
    const x = trova(t);
    if (x) {{ x.click(); if (poi) setTimeout(poi, 250); return; }}
    if (n < 40) setTimeout(() => prova(t, poi, n + 1), 150);
  }}
  prova(D.scheda, D.sotto ? () => prova(D.sotto, null, 0) : null, 0);
}})();
</script>"""
    try:
        st.html(script, unsafe_allow_javascript=True)
    except TypeError:
        # Streamlit più vecchio, senza JavaScript in st.html: lo stesso script in un
        # riquadro invisibile, che arriva alla pagina attraverso «parent»
        st.iframe(script.replace("document.", "parent.document."), height=1)


def testo_per_ai(G, massimo=9000):
    """La guida in testo semplice: per «Chiedi alla guida» e per la segretaria."""
    parti = []
    for s in G.get("schede", []):
        parti.append(f"\n## {s['scheda']} — {s.get('in_breve', '')}")
        parti += [f"- {c}" for c in s.get("cosa_trovi", [])]
        for h in s.get("come_si_fa", []):
            parti.append(f"Come: {h['domanda']} → " + " → ".join(h.get("passi", [])))
    for sez in G.get("sezioni", []):
        for v in sez.get("voci", []):
            parti.append(f"\nD: {v['domanda']}\nR: {v['risposta']}")
    return "\n".join(parti)[:massimo]


def _trova(G, q):
    """Cerca q dappertutto. Restituisce (schede, passi, novità, voci) che contengono q."""
    q = q.lower()
    dentro = lambda *t: any(q in str(x).lower() for x in t)
    schede = [s for s in G.get("schede", [])
              if dentro(s["scheda"], s.get("in_breve", ""), *s.get("cosa_trovi", []))]
    passi = [(s, h) for s in G.get("schede", []) for h in s.get("come_si_fa", [])
             if dentro(h["domanda"], *h.get("passi", []))]
    novita = [n for n in G.get("novita", []) if dentro(n["titolo"], n.get("testo", ""))]
    voci = [(sez, v) for sez in G.get("sezioni", []) for v in sez.get("voci", [])
            if dentro(sez["titolo"], v["domanda"], v["risposta"])]
    return schede, passi, novita, voci


def _passi(h, chiave, aperto=False):
    with st.expander(f"👉 {h['domanda']}", expanded=aperto):
        st.markdown("\n".join(f"{i}. {p}" for i, p in enumerate(h.get("passi", []), 1)))
        if h.get("apri"):
            st.button("➜ Portami lì", key=chiave, on_click=vai, args=(h["apri"],))


def _scheda(s, i, aperta=False):
    with st.container(border=True):
        st.markdown(f"##### {s['scheda']}")
        st.caption(s.get("in_breve", ""))
        with st.expander("Cosa trovi", expanded=aperta):
            st.markdown("\n".join(f"- {c}" for c in s.get("cosa_trovi", [])))
        for j, h in enumerate(s.get("come_si_fa", [])):
            _passi(h, f"gd_{i}_{j}", aperto=aperta)
        if s["scheda"] != "❓ Guida":
            st.button(f"➜ Apri {s['scheda']}", key=f"gd_apri_{i}", on_click=vai,
                      args=({"scheda": s["scheda"]},), width="stretch")


def _chiedi(G, ctx):
    with st.container(border=True):
        st.markdown("**🤖 Chiedi alla guida**")
        c1, c2 = st.columns([5, 1])
        domanda = c1.text_input("La tua domanda", key="gd_domanda", label_visibility="collapsed",
                                placeholder="es. come faccio a farmi leggere un PDF? dove cambio la voce di Sofia?")
        if c2.button("Chiedi", key="gd_chiedi", type="primary", width="stretch",
                     disabled=not (ctx and ctx.chiave_ai)) and domanda.strip():
            prompt = ("Sei la guida di Quadro, una dashboard personale. Rispondi in italiano, breve, con passi "
                      "numerati, dicendo in quale scheda e sotto-scheda si fa. Usa SOLO la guida qui sotto: se la "
                      "risposta non c'è, dillo chiaramente e suggerisci la scheda più vicina.\n\n"
                      f"GUIDA:\n{testo_per_ai(G, 14000)}\n\nDOMANDA: {domanda.strip()}")
            with st.spinner("Cerco nella guida…"):
                try:
                    st.session_state["gd_risposta"] = ctx.AI.chiedi(prompt, ctx.chiave_ai, ctx.modello_ai)
                except Exception as e:
                    st.session_state["gd_risposta"] = None
                    st.error(getattr(e, "messaggio", None) or str(e))
        if st.session_state.get("gd_risposta"):
            st.markdown(st.session_state["gd_risposta"])
            st.caption("Puoi chiederlo anche a Sofia, nell'angolo: conosce questa guida e ti porta nella scheda giusta.")


def mostra(G, ctx=None):
    st.markdown("#### ❓ Guida")
    st.caption(G.get("intro", ""))
    q = st.text_input("Cerca nella guida", key="gd_cerca", label_visibility="collapsed",
                      placeholder="🔎 cerca: per esempio leggimelo, telegram, fattura, secrets, 503, voce").strip()
    _chiedi(G, ctx)

    if q:
        schede, passi, novita, voci = _trova(G, q)
        n = len(schede) + len(passi) + len(novita) + len(voci)
        st.caption(f"{n} risultati per «{q}»")
        for k, (s, h) in enumerate(passi):
            st.markdown(f"**{s['scheda']}**")
            _passi(h, f"gd_r_p_{k}", aperto=True)
        for k, s in enumerate(schede):
            _scheda(s, f"r{k}", aperta=True)
        for sez, v in voci:
            with st.expander(f"{sez.get('icona', '')} {v['domanda']}", expanded=True):
                st.markdown(v["risposta"])
        for k, nv in enumerate(novita):
            st.markdown(f"🆕 **{nv['titolo']}** — {nv.get('testo', '')}")
        if not n:
            st.warning("Niente con questa parola. Prova una parola più corta, o chiedilo alla guida qui sopra.")
        return

    T = st.tabs(["🗺️ Le schede", "🆕 Novità", "❓ Domande e problemi"], key="gd_sezione")
    with T[0]:
        schede = G.get("schede", [])
        for riga in range(0, len(schede), 2):
            colonne = st.columns(2)
            for k, s in enumerate(schede[riga:riga + 2]):
                with colonne[k]:
                    _scheda(s, riga + k)
    with T[1]:
        for k, nv in enumerate(G.get("novita", [])):
            with st.container(border=True):
                st.caption(nv.get("quando", ""))
                st.markdown(f"**{nv['titolo']}**  \n{nv.get('testo', '')}")
                if nv.get("apri"):
                    st.button("➜ Provalo", key=f"gd_nov_{k}", on_click=vai, args=(nv["apri"],))
    with T[2]:
        for sez in G.get("sezioni", []):
            st.markdown(f"##### {sez.get('icona', '')} {sez['titolo']}")
            for v in sez.get("voci", []):
                with st.expander(v["domanda"]):
                    st.markdown(v["risposta"])
        st.divider()
        st.caption("La guida sta in `guida.json`: puoi aggiungere schede, passi, novità e domande "
                   "senza toccare il codice (lo schema è scritto in cima a `guida.py`).")
