"""
laboratorio.py — la scheda 🛠️ Laboratorio, per il lavoro da maker.

    📦 Magazzino       cosa hai, quanto, dove; cosa ricomprare
    🧾 Progetti        dall'idea alla vendita, con la distinta dei componenti,
                       il costo vero e il prezzo da chiedere
    🧮 Calcolatori     Ohm, LED, partitore, batteria, sezione dei cavi, 555,
                       filtro RC, costo di una stampa 3D, AWG
    📓 Diario          cosa hai provato al banco e com'è andata
    🤖 Ingegnere AI    componenti, rischi, piano di test, costi, da prototipo
                       a prodotto: con davanti il progetto vero

DOVE STANNO I DATI
    Magazzino e progetti: Quadro_Laboratorio.json su Drive (da caricare una
    volta, Quadro te lo fa scaricare). Senza, restano solo nella sessione.
    Diario di laboratorio: nel diario normale, Tipo=laboratorio.

I calcolatori sono formule da manuale, senza AI: i numeri sono esatti, ma
restano un aiuto al progetto, non un collaudo. Per impianti a 230 V e per
la sicurezza elettrica vale la norma e la verifica di un professionista.
"""

import datetime as dt
import json
import math

import pandas as pd
import streamlit as st

import drive_json as DJ

FILE_LAB = "Quadro_Laboratorio.json"
STATI = ["idea", "progetto", "prototipo", "test", "brevetto", "prodotto", "in vendita", "archiviato"]
CATEGORIE = ["microcontrollori", "sensori", "attuatori", "alimentazione", "passivi", "connettori",
             "cavi", "meccanica", "stampa 3D", "attrezzi", "altro"]
VUOTO = {"magazzino": [], "progetti": [],
         "impostazioni": {"tariffa_oraria": 25.0, "margine": 30.0, "euro_kwh": 0.30}}
E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
SEZIONI_MM2 = [0.25, 0.5, 0.75, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0, 35.0, 50.0]
AWG = {30: 0.051, 28: 0.081, 26: 0.129, 24: 0.205, 22: 0.326, 20: 0.518, 18: 0.823, 16: 1.31,
       14: 2.08, 12: 3.31, 10: 5.26, 8: 8.37, 6: 13.3, 4: 21.2, 2: 33.6}
RAME = 0.0175     # resistività del rame, ohm·mm²/m a 20 °C


# =============================================================== i calcoli ===
def valore_e12(r, sopra=True):
    """Il valore commerciale E12 più vicino (sopra, per non superare la corrente)."""
    if r <= 0:
        return 0.0
    decade = 10 ** math.floor(math.log10(r))
    candidati = [v * decade for v in E12] + [E12[0] * decade * 10]
    if sopra:
        return min(v for v in candidati if v >= r - 1e-9)
    return min(candidati, key=lambda v: abs(v - r))


def resistenza_led(vs, vf, i_ma):
    """(R esatta, R commerciale, corrente vera in mA, potenza in W)."""
    r = (vs - vf) / (i_ma / 1000)
    rc = valore_e12(r)
    i_vera = (vs - vf) / rc * 1000
    return r, rc, i_vera, (vs - vf) * i_vera / 1000


def sezione_cavo(lunghezza_m, corrente_a, tensione_v, caduta_pct):
    """Sezione minima di rame (andata e ritorno) per stare sotto la caduta di tensione."""
    caduta_v = tensione_v * caduta_pct / 100
    s = 2 * lunghezza_m * corrente_a * RAME / caduta_v
    commerciale = next((x for x in SEZIONI_MM2 if x >= s), SEZIONI_MM2[-1])
    caduta_vera = 2 * lunghezza_m * corrente_a * RAME / commerciale
    return s, commerciale, caduta_vera


def autonomia(mah, attivo_ma, sonno_ma=0.0, attivo_pct=100.0, efficienza_pct=85.0):
    media = attivo_ma * attivo_pct / 100 + sonno_ma * (100 - attivo_pct) / 100
    return (mah * efficienza_pct / 100) / media if media > 0 else float("inf"), media


def costi_progetto(p, imp, pezzi=1):
    mat = sum(float(r.get("quantita") or 0) * float(r.get("prezzo") or 0) for r in p.get("distinta", []))
    ore = float(p.get("ore") or 0)
    tariffa = float(p.get("tariffa") or imp.get("tariffa_oraria", 25))
    margine = float(p.get("margine") if p.get("margine") not in (None, "") else imp.get("margine", 30))
    # le ore di progetto si spalmano sui pezzi; quelle di montaggio no
    montaggio = float(p.get("ore_pezzo") or 0)
    costo_pezzo = mat + (ore * tariffa) / max(1, pezzi) + montaggio * tariffa
    return {"materiali": mat, "ore": ore, "tariffa": tariffa, "margine": margine,
            "costo_pezzo": costo_pezzo, "prezzo_pezzo": costo_pezzo * (1 + margine / 100)}


def mancanti(p, magazzino, pezzi=1):
    scorte = {str(m.get("nome", "")).strip().lower(): float(m.get("quantita") or 0) for m in magazzino}
    out = []
    for r in p.get("distinta", []):
        nome = str(r.get("componente", "")).strip()
        serve = float(r.get("quantita") or 0) * pezzi
        ho = scorte.get(nome.lower(), 0.0)
        if nome and ho < serve:
            out.append({"Componente": nome, "Serve": serve, "Ho": ho, "Mancano": serve - ho})
    return out


# =========================================================== i dati su Drive ===
@st.cache_data(ttl=300, show_spinner=False)
def _id(_info_json, cartelle, segno):
    return DJ.trova(json.loads(_info_json), list(cartelle), FILE_LAB)


def _fid(ctx):
    if not ctx.SA:
        return None
    try:
        return _id(json.dumps(dict(ctx.SA)), tuple(ctx.cartelle), st.session_state.get("cerca_archivio", 0))
    except Exception:
        return None


def _completo(dati):
    dati = dati if isinstance(dati, dict) else {}
    return {k: dati.get(k, json.loads(json.dumps(v))) for k, v in VUOTO.items()}


def carica(ctx):
    """Il laboratorio, letto da Drive. Si rilegge quando premi «Aggiorna tutto da Drive»."""
    segno = st.session_state.get("cerca_archivio", 0)
    if "lab" not in st.session_state or st.session_state.get("lab_segno") != segno:
        dati = None
        fid = _fid(ctx)
        if fid:
            try:
                dati = DJ.leggi(dict(ctx.SA), fid)
            except Exception as e:
                st.warning(f"Non riesco a leggere {FILE_LAB}: {e}")
        st.session_state["lab"] = _completo(dati)
        st.session_state["lab_segno"] = segno
    return st.session_state["lab"]


def salva(ctx, modifica, messaggio):
    """
    Salva cambiando solo quello che `modifica` tocca, partendo dalla versione
    più recente su Drive: se nel frattempo hai cambiato qualcosa dal telefono,
    non si perde. Restituisce True se è andato a buon fine.
    """
    fid = _fid(ctx)
    if fid:
        try:
            fresco = _completo(DJ.leggi(dict(ctx.SA), fid))
            modifica(fresco)
            DJ.scrivi(dict(ctx.SA), fid, fresco)
            st.session_state["lab"] = fresco
            ctx.conferma(messaggio)
            return True
        except Exception as e:
            st.error(f"Non sono riuscito a salvare su Drive: {e}")
            return False
    modifica(st.session_state["lab"])
    ctx.conferma(messaggio + " (solo in questa sessione)")
    return True


def _pulito(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return v


# ============================================================== la scheda ===
def mostra(ctx):
    st.markdown("#### 🛠️ Laboratorio")
    lab = carica(ctx)
    if not _fid(ctx):
        with st.expander(f"⚠️ {FILE_LAB} non è su Drive: quello che scrivi resta solo in questa sessione",
                         expanded=False):
            st.markdown("Scarica il file qui sotto e caricalo nella cartella di Quadro_Diario.xlsx "
                        "(condivisa come Editor), poi premi «Aggiorna tutto da Drive» a sinistra.")
            st.download_button(f"⬇️ Scarica {FILE_LAB}", json.dumps(VUOTO, ensure_ascii=False, indent=1),
                               FILE_LAB, "application/json", key="lab_vuoto")
    T = st.tabs(["📦 Magazzino", "🧾 Progetti e prezzi", "🧮 Calcolatori", "📓 Diario di laboratorio",
                 "🤖 Ingegnere AI"], key="lab_sezione")
    with T[0]:
        _magazzino(ctx, lab)
    with T[1]:
        _progetti(ctx, lab)
    with T[2]:
        _calcolatori(lab)
    with T[3]:
        _diario(ctx, lab)
    with T[4]:
        _ingegnere(ctx, lab)


def _magazzino(ctx, lab):
    mag = pd.DataFrame(lab["magazzino"], columns=["nome", "categoria", "quantita", "minimo", "posizione",
                                                  "prezzo", "fornitore", "link"])
    if not mag.empty:
        q = pd.to_numeric(mag["quantita"], errors="coerce").fillna(0)
        mn = pd.to_numeric(mag["minimo"], errors="coerce").fillna(0)
        pr = pd.to_numeric(mag["prezzo"], errors="coerce").fillna(0)
        k = st.columns(3)
        k[0].metric("Articoli", len(mag))
        k[1].metric("Valore del magazzino", f"{(q * pr).sum():,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        sotto = mag[(q <= mn) & (mn > 0)]
        k[2].metric("Da ricomprare", len(sotto))
        if not sotto.empty:
            st.warning("Sotto la scorta minima: " + ", ".join(f"**{r['nome']}** ({_pulito(r['quantita'])})"
                                                             for _, r in sotto.iterrows()))
            lista = sotto.assign(da_comprare=(mn - q + mn).clip(lower=1))[["nome", "da_comprare", "fornitore", "link"]]
            st.download_button("⬇️ Lista della spesa (CSV)", lista.to_csv(index=False).encode("utf-8-sig"),
                               "lista_spesa_laboratorio.csv", "text/csv", key="lab_spesa")
    filtro = st.text_input("🔎 Cerca", key="lab_mag_cerca", placeholder="es. ESP32, resistenze, PLA")
    vista = mag
    if filtro.strip():
        f = filtro.strip().lower()
        vista = mag[mag.apply(lambda r: f in " ".join(str(x) for x in r.values).lower(), axis=1)]
        st.caption("Con la ricerca attiva la tabella è di sola lettura.")
        st.dataframe(vista, hide_index=True, width='stretch')
        return
    nuovo = st.data_editor(mag, num_rows="dynamic", hide_index=True, width='stretch', key="lab_mag_ed",
                           column_config={
                               "nome": st.column_config.TextColumn("Componente", required=True),
                               "categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIE),
                               "quantita": st.column_config.NumberColumn("Q.tà", min_value=0, step=1),
                               "minimo": st.column_config.NumberColumn("Minimo", min_value=0, step=1,
                                                                        help="Sotto questa quantità finisce nella lista della spesa"),
                               "posizione": st.column_config.TextColumn("Dove sta"),
                               "prezzo": st.column_config.NumberColumn("€ cad.", min_value=0.0, format="%.2f"),
                               "fornitore": st.column_config.TextColumn("Fornitore"),
                               "link": st.column_config.LinkColumn("Link / datasheet")})
    if st.button("💾 Salva il magazzino", type="primary", key="lab_mag_salva"):
        righe = [{k: _pulito(v) for k, v in r.items()} for r in nuovo.to_dict("records")
                 if str(_pulito(r.get("nome"))).strip()]
        if salva(ctx, lambda d: d.update(magazzino=righe), "Magazzino salvato"):
            st.rerun()


def _progetti(ctx, lab):
    imp = lab["impostazioni"]
    with st.expander("⚙️ Tariffa e margine di partenza"):
        c = st.columns(3)
        t = c[0].number_input("Tariffa oraria (€)", 0.0, 500.0, float(imp.get("tariffa_oraria", 25)), 1.0, key="lab_tar")
        m = c[1].number_input("Margine (%)", 0.0, 500.0, float(imp.get("margine", 30)), 5.0, key="lab_mar")
        k = c[2].number_input("€ al kWh", 0.0, 2.0, float(imp.get("euro_kwh", 0.30)), 0.01, key="lab_kwh")
        if st.button("💾 Salva", key="lab_imp_salva"):
            if salva(ctx, lambda d: d.update(impostazioni={"tariffa_oraria": t, "margine": m, "euro_kwh": k}),
                     "Impostazioni salvate"):
                st.rerun()

    # la bacheca: un colpo d'occhio su dove sta ogni progetto
    prog = lab["progetti"]
    if prog:
        st.markdown("##### La bacheca")
        attivi = [s for s in STATI if s != "archiviato" and any(p.get("stato") == s for p in prog)]
        if attivi:
            colonne = st.columns(len(attivi))
            for col, s in zip(colonne, attivi):
                with col.container(border=True):
                    st.markdown(f"**{s.capitalize()}**")
                    for p in prog:
                        if p.get("stato") == s:
                            st.caption(f"• {p['nome']}")

    nomi = [p["nome"] for p in prog]
    if "__lab_prog__" in st.session_state:          # il progetto appena salvato resta scelto
        st.session_state["lab_prog_scelta"] = st.session_state.pop("__lab_prog__")
    scelta = st.selectbox("Progetto", ["➕ Nuovo progetto"] + nomi, key="lab_prog_scelta")
    p = next((x for x in prog if x["nome"] == scelta), None) or \
        {"nome": "", "stato": "idea", "descrizione": "", "ore": 0, "ore_pezzo": 0, "tariffa": "",
         "margine": "", "distinta": []}
    chiave = f"lab_p_{abs(hash(scelta)) % 10**8}"
    with st.form(f"{chiave}_form"):
        a1, a2 = st.columns([2, 1])
        nome = a1.text_input("Nome", p["nome"])
        stato = a2.selectbox("A che punto è", STATI, index=STATI.index(p.get("stato", "idea")) if p.get("stato") in STATI else 0)
        descr = st.text_area("Cos'è e a cosa serve", p.get("descrizione", ""), height=90)
        b = st.columns(4)
        ore = b[0].number_input("Ore di progetto", 0.0, 5000.0, float(p.get("ore") or 0), 1.0,
                                help="Progettazione, prove, documentazione: si dividono sui pezzi")
        ore_pezzo = b[1].number_input("Ore di montaggio per pezzo", 0.0, 100.0, float(p.get("ore_pezzo") or 0), 0.25)
        tariffa = b[2].number_input("Tariffa (€/h)", 0.0, 500.0, float(p.get("tariffa") or imp.get("tariffa_oraria", 25)), 1.0)
        margine = b[3].number_input("Margine (%)", 0.0, 500.0,
                                    float(p.get("margine") if p.get("margine") not in (None, "") else imp.get("margine", 30)), 5.0)
        st.markdown("**Distinta dei componenti**")
        dist = st.data_editor(pd.DataFrame(p.get("distinta", []), columns=["componente", "quantita", "prezzo", "note"]),
                              num_rows="dynamic", hide_index=True, width='stretch', key=f"{chiave}_dist",
                              column_config={"componente": st.column_config.TextColumn("Componente"),
                                             "quantita": st.column_config.NumberColumn("Q.tà per pezzo", min_value=0.0, step=1.0),
                                             "prezzo": st.column_config.NumberColumn("€ cad.", min_value=0.0, format="%.2f"),
                                             "note": st.column_config.TextColumn("Note")})
        if st.form_submit_button("💾 Salva il progetto", type="primary"):
            if not nome.strip():
                st.warning("Serve un nome.")
            elif nome.strip() != p["nome"] and nome.strip() in nomi:
                st.warning(f"C'è già un progetto che si chiama «{nome.strip()}»: sceglilo dal menu "
                           "per modificarlo, o usa un altro nome.")
            else:
                nuovo = {"nome": nome.strip(), "stato": stato, "descrizione": descr, "ore": ore,
                         "ore_pezzo": ore_pezzo, "tariffa": tariffa, "margine": margine,
                         "aggiornato": ctx.DIARIO.oggi().isoformat(),
                         "distinta": [{k: _pulito(v) for k, v in r.items()} for r in dist.to_dict("records")
                                      if str(r.get("componente") or "").strip()]}
                vecchio = p["nome"]

                def aggiorna(d):
                    d["progetti"] = [x for x in d["progetti"] if x["nome"] not in (vecchio, nuovo["nome"])] + [nuovo]
                if salva(ctx, aggiorna, f"Progetto «{nome.strip()}» salvato"):
                    st.session_state["__lab_prog__"] = nome.strip()
                    st.rerun()

    if not p["nome"]:
        return
    st.markdown("##### 💶 Quanto costa e quanto chiedere")
    pezzi = st.select_slider("Quanti pezzi", [1, 2, 5, 10, 20, 50, 100, 500], value=1, key=f"{chiave}_pezzi")
    c = costi_progetto(p, imp, pezzi)
    eur = lambda x: f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    k = st.columns(4)
    k[0].metric("Materiali a pezzo", eur(c["materiali"]))
    k[1].metric("Costo a pezzo", eur(c["costo_pezzo"]), help="Materiali + ore di progetto divise sui pezzi + montaggio")
    k[2].metric("Prezzo suggerito", eur(c["prezzo_pezzo"]), help=f"Costo + {c['margine']:.0f}% di margine")
    k[3].metric(f"Ricavo su {pezzi}", eur(c["prezzo_pezzo"] * pezzi))
    st.caption("Il prezzo suggerito copre i costi e il margine: non tiene conto di IVA, spedizione, "
               "commissioni dei marketplace né di quanto il mercato è disposto a pagare.")
    manca = mancanti(p, lab["magazzino"], pezzi)
    if manca:
        st.warning(f"Per {pezzi} pezz{'o' if pezzi == 1 else 'i'} mancano in magazzino:")
        st.dataframe(pd.DataFrame(manca), hide_index=True, width='stretch')
    elif p.get("distinta"):
        st.success(f"In magazzino c'è tutto per {pezzi} pezz{'o' if pezzi == 1 else 'i'}.")
        if st.button(f"📦 Ne ho montati {pezzi}: scala i componenti dal magazzino", key=f"{chiave}_scala"):
            distinta = p["distinta"]

            def scala(d):
                for r in distinta:
                    for m in d["magazzino"]:
                        if str(m.get("nome", "")).strip().lower() == str(r.get("componente", "")).strip().lower():
                            m["quantita"] = max(0, float(m.get("quantita") or 0) - float(r.get("quantita") or 0) * pezzi)
            if salva(ctx, scala, "Magazzino aggiornato"):
                st.rerun()
    if p.get("distinta"):
        st.download_button("⬇️ Distinta (CSV)", pd.DataFrame(p["distinta"]).to_csv(index=False).encode("utf-8-sig"),
                           f"distinta_{p['nome']}.csv", "text/csv", key=f"{chiave}_csv")


def _calcolatori(lab):
    st.caption("Formule da manuale, senza AI. Per impianti a 230 V vale la norma.")
    with st.expander("⚡ Legge di Ohm e potenza", expanded=True):
        c = st.columns(3)
        v = c[0].number_input("Tensione V", 0.0, 100000.0, 0.0, key="oh_v")
        i = c[1].number_input("Corrente A", 0.0, 10000.0, 0.0, key="oh_i", format="%.4f")
        r = c[2].number_input("Resistenza Ω", 0.0, 1e9, 0.0, key="oh_r")
        dati = sum(x > 0 for x in (v, i, r))
        if dati == 2:
            if v and i:
                r = v / i
            elif v and r:
                i = v / r
            else:
                v = i * r
            st.success(f"V = **{v:.4g} V** · I = **{i * 1000:.4g} mA** · R = **{r:.4g} Ω** · P = **{v * i:.4g} W**")
        else:
            st.caption("Scrivi due valori su tre, lascia a zero quello che cerchi.")
    with st.expander("💡 Resistenza per un LED"):
        c = st.columns(3)
        vs = c[0].number_input("Alimentazione V", 0.1, 400.0, 5.0, key="led_vs")
        vf = c[1].number_input("Tensione del LED V", 0.1, 50.0, 2.0, key="led_vf",
                               help="Rosso ~2, verde/blu/bianco ~3")
        ima = c[2].number_input("Corrente mA", 0.1, 2000.0, 15.0, key="led_i")
        if vs > vf:
            r, rc, iv, p = resistenza_led(vs, vf, ima)
            st.success(f"R calcolata **{r:.1f} Ω** → commerciale **{rc:g} Ω** (E12) · corrente vera "
                       f"**{iv:.1f} mA** · potenza **{p * 1000:.0f} mW** → resistenza da "
                       f"**{'1/4 W' if p < 0.125 else '1/2 W' if p < 0.25 else '1 W' if p < 0.5 else f'{math.ceil(p * 2)} W'}**")
        else:
            st.error("L'alimentazione deve essere più alta della tensione del LED.")
    with st.expander("➗ Partitore di tensione"):
        c = st.columns(3)
        vin = c[0].number_input("Vin V", 0.0, 1000.0, 12.0, key="pt_vin")
        r1 = c[1].number_input("R1 (in alto) Ω", 1.0, 1e8, 10000.0, key="pt_r1")
        r2 = c[2].number_input("R2 (in basso) Ω", 1.0, 1e8, 3300.0, key="pt_r2")
        vout = vin * r2 / (r1 + r2)
        st.success(f"Vout = **{vout:.3f} V** · corrente nel partitore **{vin / (r1 + r2) * 1000:.3f} mA**")
        obiettivo = st.number_input("Vout che vuoi ottenere (per calcolare R2)", 0.0, 1000.0, 3.3, key="pt_ob")
        if 0 < obiettivo < vin:
            r2c = r1 * obiettivo / (vin - obiettivo)
            r2e = valore_e12(r2c, sopra=False)
            st.info(f"R2 = **{r2c:.0f} Ω** → commerciale **{r2e:g} Ω**, che dà **{vin * r2e / (r1 + r2e):.3f} V**")
    with st.expander("🔋 Autonomia di una batteria"):
        c = st.columns(3)
        mah = c[0].number_input("Capacità mAh", 1.0, 1e6, 2500.0, key="bt_mah")
        att = c[1].number_input("Consumo acceso mA", 0.0, 1e5, 80.0, key="bt_att")
        son = c[2].number_input("Consumo in sleep mA", 0.0, 1e4, 0.02, key="bt_son", format="%.3f")
        d = st.columns(2)
        pct = d[0].slider("Tempo acceso %", 0.1, 100.0, 5.0, key="bt_pct")
        eff = d[1].slider("Efficienza %", 50, 100, 85, key="bt_eff",
                          help="Perdite del regolatore e capacità che non si usa davvero")
        ore, media = autonomia(mah, att, son, pct, eff)
        st.success(f"Consumo medio **{media:.3f} mA** → autonomia **{ore:.0f} ore** "
                   f"(**{ore / 24:.1f} giorni**)")
    with st.expander("🔌 Sezione di un cavo (rame, caduta di tensione)"):
        c = st.columns(4)
        lun = c[0].number_input("Lunghezza m (sola andata)", 0.1, 1000.0, 5.0, key="cv_l")
        cor = c[1].number_input("Corrente A", 0.01, 500.0, 5.0, key="cv_i")
        ten = c[2].number_input("Tensione V", 1.0, 1000.0, 12.0, key="cv_v")
        cad = c[3].number_input("Caduta max %", 0.5, 10.0, 3.0, key="cv_c")
        s, comm, cv = sezione_cavo(lun, cor, ten, cad)
        awg = next((a for a, mm in sorted(AWG.items(), key=lambda x: x[1]) if mm >= s), None)
        st.success(f"Sezione minima **{s:.2f} mm²** → commerciale **{comm:g} mm²** "
                   f"(caduta vera **{cv:.2f} V**, {cv / ten * 100:.1f}%)"
                   + (f" · in AWG: **{awg}**" if awg else ""))
        st.caption("Considera solo la caduta di tensione: la portata del cavo e la protezione vanno "
                   "verificate a parte, e per i 230 V vale la norma impianti.")
    with st.expander("⏱️ NE555 astabile"):
        c = st.columns(3)
        ra = c[0].number_input("R1 Ω", 1.0, 1e8, 1000.0, key="n5_r1")
        rb = c[1].number_input("R2 Ω", 1.0, 1e8, 10000.0, key="n5_r2")
        cc = c[2].number_input("C µF", 0.0001, 10000.0, 10.0, key="n5_c", format="%.4f")
        f = 1.44 / ((ra + 2 * rb) * cc * 1e-6)
        st.success(f"Frequenza **{f:.3f} Hz** · periodo **{1 / f * 1000:.1f} ms** · duty cycle "
                   f"**{(ra + rb) / (ra + 2 * rb) * 100:.1f}%**")
    with st.expander("〰️ Filtro RC"):
        c = st.columns(2)
        rr = c[0].number_input("R Ω", 1.0, 1e9, 10000.0, key="rc_r")
        cf = c[1].number_input("C nF", 0.001, 1e7, 100.0, key="rc_c")
        tau = rr * cf * 1e-9
        st.success(f"Frequenza di taglio **{1 / (2 * math.pi * tau):.2f} Hz** · costante di tempo "
                   f"**{tau * 1000:.3f} ms** (al 99% dopo 5τ = {5 * tau * 1000:.2f} ms)")
    with st.expander("🖨️ Costo di una stampa 3D"):
        c = st.columns(4)
        g = c[0].number_input("Grammi", 0.0, 10000.0, 50.0, key="s3_g")
        ekg = c[1].number_input("€ al kg di filamento", 0.0, 500.0, 20.0, key="s3_e")
        hh = c[2].number_input("Ore di stampa", 0.0, 500.0, 3.0, key="s3_h")
        w = c[3].number_input("Potenza media W", 0.0, 2000.0, 120.0, key="s3_w")
        kwh = float(lab["impostazioni"].get("euro_kwh", 0.30))
        mat, en = g / 1000 * ekg, hh * w / 1000 * kwh
        usura = hh * 0.10
        st.success(f"Filamento **{mat:.2f} €** + energia **{en:.2f} €** + usura **{usura:.2f} €** "
                   f"= **{mat + en + usura:.2f} €** (energia a {kwh:.2f} €/kWh, usura 0,10 €/ora)")
    with st.expander("📏 AWG e millimetri quadrati"):
        st.dataframe(pd.DataFrame([{"AWG": a, "mm²": mm, "Ø mm": round(2 * math.sqrt(mm / math.pi), 2)}
                                   for a, mm in AWG.items()]), hide_index=True, width='stretch')


def _diario(ctx, lab):
    progetti = [p["nome"] for p in lab["progetti"]]
    st.caption("Cosa hai provato al banco, com'è andata, cosa fai dopo. Fra sei mesi è oro.")
    pulito = st.session_state.pop("__lab_svuota__", False)
    if pulito:
        st.session_state["lab_d_passo"] = ""
    c1, c2 = st.columns(2)
    prog = c1.selectbox("Progetto", progetti + ["altro"], key="lab_d_prog")
    esito = c2.selectbox("Com'è andata", ["✅ funziona", "⚠️ in parte", "❌ non funziona", "🔬 da capire"],
                         key="lab_d_esito")
    testo = ctx.VOCE.campo("Cosa hai fatto (puoi dettarlo)", "lab_d_testo", ctx.chiave_ai, ctx.modello_ai, altezza=110)
    passo = st.text_input("Prossimo passo", key="lab_d_passo")
    if st.button("💾 Salva nel diario di laboratorio", type="primary", key="lab_d_salva"):
        if (testo or "").strip():
            ctx.diario_scrivi(ctx.DIARIO.riga("laboratorio", prog, esito, 0, None,
                                              json.dumps({"testo": testo.strip(), "passo": passo.strip()},
                                                         ensure_ascii=False)))
            ctx.VOCE.svuota("lab_d_testo")
            st.session_state["__lab_svuota__"] = True
            ctx.conferma("Annotato")
            st.rerun()
        else:
            st.warning("Scrivi cosa hai fatto.")
    voci = ctx.DIA[ctx.DIA["Tipo"] == "laboratorio"].sort_values(["Data", "Ora"], ascending=False) \
        if not ctx.DIA.empty else ctx.DIA
    if voci.empty:
        return
    filtro = st.multiselect("Mostra", sorted(voci["Attivita"].unique()), key="lab_d_filtro", placeholder="tutti i progetti")
    if filtro:
        voci = voci[voci["Attivita"].isin(filtro)]
    for _, r in voci.head(50).iterrows():
        try:
            d = json.loads(r["Nota"])
        except (json.JSONDecodeError, TypeError):
            d = {"testo": r["Nota"], "passo": ""}
        with st.container(border=True):
            st.markdown(f"**{r['Data']:%d/%m/%Y} · {r['Attivita']}** · {r['Strumento']}")
            st.markdown(d.get("testo", ""))
            if d.get("passo"):
                st.caption(f"➡️ {d['passo']}")


DOMANDE_INGEGNERE = {
    "🔩 Suggerisci i componenti": "Proponi i componenti adatti (microcontrollore, sensori, alimentazione, "
                                  "protezioni), con alternative economiche e i punti critici di ciascuno.",
    "⚠️ Analisi dei rischi": "Fai un'analisi dei rischi tecnici e di sicurezza: cosa può guastarsi, cosa può "
                            "essere pericoloso, come prevenirlo. Ordina per gravità.",
    "🧪 Piano di test": "Scrivi un piano di test pratico, da banco: cosa misurare, con quale strumento, "
                       "quali valori aspettarsi, quando dire che è superato.",
    "💶 Come ridurre i costi": "Guarda la distinta e proponi come ridurre il costo per pezzo senza perdere "
                              "affidabilità: componenti alternativi, semplificazioni, acquisti in quantità.",
    "🏭 Da prototipo a prodotto": "Cosa manca per passare da prototipo a prodotto vendibile in Italia/UE: "
                                  "ingegnerizzazione, documentazione, marcature e conformità da verificare "
                                  "(indica quali normative probabilmente si applicano e di verificarle con un "
                                  "consulente), assistenza, imballo.",
    "💡 Cosa c'è di nuovo da proteggere": "Quali aspetti di questo progetto sembrano originali e potrebbero valere "
                                          "una tutela (brevetto, modello di utilità, design)? Dì chiaramente che va "
                                          "verificato con un consulente in proprietà industriale e una ricerca di anteriorità.",
}


def _ingegnere(ctx, lab):
    if not ctx.chiave_ai:
        st.error("Serve la chiave di Google AI Studio nei Secrets.")
        return
    progetti = [p["nome"] for p in lab["progetti"]]
    scelta = st.selectbox("Su quale progetto", ["(nessuno, domanda libera)"] + progetti, key="lab_ai_prog")
    p = next((x for x in lab["progetti"] if x["nome"] == scelta), None)
    st.caption("Ha davanti la descrizione, la distinta e le ultime note di laboratorio del progetto.")
    cols = st.columns(3)
    richiesta = None
    for i, (et, dom) in enumerate(DOMANDE_INGEGNERE.items()):
        if cols[i % 3].button(et, key=f"lab_ai_{i}", width='stretch', disabled=p is None):
            richiesta = dom
    libera = st.text_area("Oppure chiedi quello che vuoi", key="lab_ai_libera", height=80,
                          placeholder="es. meglio un INA219 o un ACS712 per misurare 3 A a 12 V?")
    if st.button("Chiedi", key="lab_ai_chiedi", type="primary") and libera.strip():
        richiesta = libera.strip()
    if richiesta:
        note = ""
        if p is not None and not ctx.DIA.empty:
            nn = ctx.DIA[(ctx.DIA["Tipo"] == "laboratorio") & (ctx.DIA["Attivita"] == p["nome"])].tail(8)
            note = "\n".join(f"- {r['Data']:%d/%m} {r['Strumento']}: {r['Nota']}" for _, r in nn.iterrows())
        contesto = (f"Progetto: {json.dumps(p, ensure_ascii=False)}\nNote di laboratorio:\n{note or '(nessuna)'}"
                    if p else "Nessun progetto selezionato.")
        prompt = ("Sei un ingegnere elettronico e meccanico esperto, che aiuta un maker e ingegnere industriale "
                  "italiano. Rispondi in italiano, concreto, con numeri e sigle dei componenti quando servono. "
                  "Se un'informazione non c'è nel progetto, dillo e fai un'ipotesi esplicita. Per tutto ciò che "
                  "riguarda sicurezza elettrica, 230 V e normative, invita a verificare con le norme e un "
                  f"professionista.\n\n{contesto}\n\nRichiesta: {richiesta}")
        try:
            with st.spinner("Ci ragiono…"):
                st.session_state["lab_ai_risposta"] = ctx.AI.chiedi(prompt, ctx.chiave_ai, ctx.modello_ai)
        except Exception as e:
            st.error(getattr(e, "messaggio", None) or str(e))
    if st.session_state.get("lab_ai_risposta"):
        with st.container(border=True):
            st.markdown(st.session_state["lab_ai_risposta"])
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Scarica la risposta", st.session_state["lab_ai_risposta"], "ingegnere_ai.md",
                           "text/markdown", key="lab_ai_scarica", width='stretch')
        if c2.button("📓 Salva nel diario di laboratorio", key="lab_ai_salva", width='stretch', disabled=p is None):
            ctx.diario_scrivi(ctx.DIARIO.riga("laboratorio", p["nome"], "🤖 consiglio AI", 0, None,
                                              json.dumps({"testo": st.session_state["lab_ai_risposta"][:20000], "passo": ""},
                                                         ensure_ascii=False)))
            ctx.conferma("Salvato nel diario di laboratorio")
            st.rerun()
