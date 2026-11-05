"""
segretaria.py — la scheda 👩‍💼 Segretaria.

    PARLA          chat scritta o a voce; risponde a voce con l'avatar 3D
    AGISCE         propone azioni (una priorità, una scadenza, un'idea, un
                   ricordo, un promemoria sul telefono…) che fai partire tu
                   con un clic. Non scrive mai niente da sola.
    TI CONOSCE     da un profilo «chi sono» che scrivi tu, dai ricordi che le
                   chiedi di tenere, e da un quadro aggiornato di Quadro: le
                   tre cose di oggi, scadenze, clienti, obiettivi, sessioni,
                   aforismi che ami. Cosa vede esattamente lo puoi leggere.
    TI AVVISA      le notifiche su Telegram, agli orari e nei giorni che vuoi.

=============================================================================
I TRE CORPI DELLA SEGRETARIA E IL FILE CHE LI TIENE INSIEME
=============================================================================
Quadro (questa scheda), il bot Telegram e l'app da desktop sono tre facce
della stessa segretaria. Si parlano attraverso due file su Drive:

    Quadro_Segretaria.json        lo scrive Quadro: impostazioni, avatar,
                                  profilo, ricordi, regole delle notifiche e
                                  il quadro aggiornato. Lo leggono gli altri.
    Quadro_Dalla_Segretaria.json  lo scrivono Telegram e l'app desktop: le
                                  note, le idee, le cose fatte che gli dici
                                  da fuori. Quadro le importa nel diario.

Così la configuri UNA volta qui, e vale ovunque.

=============================================================================
QUELLO CHE NON FA
=============================================================================
Vede solo quello che sta in Quadro e quello che le scrivi: non legge la tua
posta, il tuo calendario o i tuoi file. Su salute e farmaci non dà
indicazioni: rimanda al medico, come la Taratura.
"""

import datetime as dt
import json
import os
import re
import uuid

import pandas as pd
import streamlit as st

import drive_json as DJ

FILE_SEGRETARIA = "Quadro_Segretaria.json"
FILE_POSTA = "Quadro_Dalla_Segretaria.json"

PREDEFINITE = {
    "nome": "Sofia", "chiamami": "Claudio", "carattere": "cordiale e diretta",
    "carattere_extra": "", "risposte_brevi": True, "mostra_benessere": False,
    "velocita": 1.0, "tono": 1.05, "voce": "",
    "avatar": {"pelle": "#f1c7a5", "capelli": "#3b2a20", "giacca": "#0f5d47",
               "camicia": "#f7f7f2", "occhi": "#4a3426", "labbra": "#c45a5a",
               "acconciatura": "caschetto", "occhiali": False, "orecchini": True,
               "sfondo": "trasparente", "inquadratura": "busto", "vrm": ""},
}
CARATTERI = ["cordiale e diretta", "formale ed elegante", "ironica e brillante",
             "calma e rassicurante", "energica e motivante"]
TIPI_NOTIFICA = {
    "buongiorno": "le tre cose, le scadenze e i richiami del giorno, con un aforisma",
    "aforisma": "un aforisma secondo le tue preferenze (nei dettagli: temi diversi)",
    "consiglio": "un consiglio pratico sulla giornata o la settimana",
    "scadenze": "le scadenze dei prossimi giorni (solo se ce ne sono)",
    "respiro": "un invito a una pausa di respiro di un minuto",
    "sera": "il riepilogo della giornata e il promemoria del check-in",
    "ripasso": "le flashcard da ripassare oggi (solo se ce ne sono)",
    "promemoria": "un testo tuo (scrivilo nei dettagli)",
}
GIORNI = ["tutti", "feriali", "weekend", "lun", "mar", "mer", "gio", "ven", "sab", "dom"]
REGOLE_INIZIALI = [
    {"id": "r1", "attiva": True, "tipo": "buongiorno", "ora": "07:30", "giorni": "feriali", "dettagli": ""},
    {"id": "r2", "attiva": True, "tipo": "scadenze", "ora": "08:00", "giorni": "tutti", "dettagli": ""},
    {"id": "r3", "attiva": True, "tipo": "aforisma", "ora": "12:30", "giorni": "tutti", "dettagli": ""},
    {"id": "r4", "attiva": True, "tipo": "respiro", "ora": "15:30", "giorni": "feriali", "dettagli": ""},
    {"id": "r5", "attiva": True, "tipo": "sera", "ora": "21:30", "giorni": "tutti", "dettagli": ""},
    {"id": "r6", "attiva": False, "tipo": "ripasso", "ora": "18:00", "giorni": "tutti", "dettagli": ""},
]
AZIONI = {"priorita": "🎯 Aggiungi alle tre cose di oggi", "scadenza": "⏰ Aggiungi la scadenza",
          "idea": "💡 Salva l'idea", "ricordo": "🧠 Ricordatelo", "obiettivo": "🌱 Nuovo obiettivo del trimestre",
          "promemoria": "📲 Promemoria su Telegram", "nota": "📝 Salva la nota"}


# =========================================================== impostazioni ===
def impostazioni(ctx):
    imp = ctx.impostazione(ctx.DIA, "segretaria", PREDEFINITE)
    imp["avatar"] = {**PREDEFINITE["avatar"], **(imp.get("avatar") or {})}
    return imp


def profilo(ctx):
    return ctx.impostazione(ctx.DIA, "profilo", {"chi_sono": ""}).get("chi_sono", "")


def notifiche(ctx):
    n = ctx.impostazione(ctx.DIA, "notifiche", {"attive": True, "regole": REGOLE_INIZIALI})
    if not n.get("regole"):
        n["regole"] = REGOLE_INIZIALI
    return n


def _quando(r):
    try:
        return pd.Timestamp(r["Data"]) + pd.to_timedelta(str(r["Ora"] or "00:00")[:5] + ":00")
    except (ValueError, TypeError):
        return pd.Timestamp(r["Data"])


def ricordi(dia):
    """I ricordi in ordine. Uno dimenticato torna se glielo ridici dopo."""
    if dia is None or dia.empty:
        return []
    ultimo, tolto = {}, {}
    for _, r in dia[dia["Tipo"] == "ricordo"].sort_values(["Data", "Ora"], kind="stable").iterrows():
        if r["Nota"]:
            ultimo[r["Nota"]] = _quando(r)
    for _, r in dia[dia["Tipo"] == "ricordo_rimosso"].iterrows():
        tolto[r["Nota"]] = max(tolto.get(r["Nota"], pd.Timestamp.min), _quando(r))
    return [x for x, q in ultimo.items() if x not in tolto or q > tolto[x]]


def _salva_impostazione(ctx, nome, valore):
    ctx.diario_scrivi(ctx.DIARIO.riga("impostazione", nome, "Segretaria", 0, None,
                                      json.dumps(valore, ensure_ascii=False)))


# ============================================================== il quadro ===
def contesto(ctx, includi_benessere=False):
    """Quello che la segretaria sa di adesso. È anche quello che vedi in «Cosa vede»."""
    import aforismi as AF
    import equilibrio as EQ
    import lavoro as LAV
    oggi = ctx.DIARIO.oggi()
    dia = ctx.DIA
    c = {"oggi": oggi.isoformat(), "giorno": ["lunedì", "martedì", "mercoledì", "giovedì",
                                              "venerdì", "sabato", "domenica"][oggi.weekday()]}
    try:
        p = ctx.DIARIO.priorita(dia)
        c["tre_cose"] = [] if p.empty else [
            {"cosa": r["Cosa"], "rinvii": int(r["Rinvii"])} for _, r in p[p["Stato"] != "fatta"].iterrows()]
    except Exception:
        c["tre_cose"] = []
    try:
        sc = LAV.scadenze(dia, oggi, giorni=14)
        c["scadenze"] = [{"quando": r["Quando"].isoformat(), "cosa": r["Cosa"], "stato": r["Stato"]}
                         for _, r in sc.iterrows()]
        cli = LAV.clienti(dia)
        c["da_richiamare"] = [{"cliente": r["Cliente"], "passo": r["Prossimo passo"]}
                              for _, r in LAV.richiami_scaduti(cli, oggi).iterrows()]
        fat = LAV.fatture(dia)
        aperte = fat[fat["Aperta"]] if not fat.empty else fat
        c["fatture_aperte"] = {"quante": len(aperte), "da_incassare": round(LAV.da_incassare(fat), 2)}
    except Exception:
        pass
    ob = EQ.obiettivi(dia)
    c["obiettivi"] = [] if ob.empty else [{"obiettivo": r["Obiettivo"], "prossimo_passo": r["Prossimo passo"]}
                                          for _, r in ob[ob["Stato"] == "in corso"].iterrows()]
    if not dia.empty:
        sette = dia[(dia["Data"] >= pd.Timestamp(oggi) - pd.Timedelta(days=7)) & (dia["Tipo"] == "sessione")]
        c["lavoro_7_giorni"] = {k: int(v) for k, v in sette.groupby("Attivita")["Minuti"].sum().items()}
        rev = dia[dia["Tipo"] == "revisione"].sort_values(["Data", "Ora"], kind="stable")
        if not rev.empty:
            try:
                c["focus_settimana"] = json.loads(rev.iloc[-1]["Nota"]).get("focus", "")
            except (json.JSONDecodeError, TypeError):
                pass
        idee = dia[dia["Tipo"] == "idea"].sort_values("Data").tail(5)
        c["idee_recenti"] = idee["Attivita"].tolist()
    try:
        import lettura as LT
        carte = LT.carte(dia)
        c["flashcard_da_ripassare"] = int(((carte["Prossima"].isna()) | (carte["Prossima"] <= pd.Timestamp(oggi))).sum()) \
            if not carte.empty else 0
    except Exception:
        pass
    racc = AF.raccolta(dia)
    if not racc.empty:
        preferiti = racc[(racc["segretaria"]) | (racc["voto"].fillna(0) >= 4)].head(15)
        c["aforismi_preferiti"] = [f"«{r['testo']}» — {r['autore']}" for _, r in preferiti.iterrows()]
    c["gusti_aforismi"] = AF.gusti(dia)
    if includi_benessere and ctx.aperto():
        ci = EQ.checkin_tabella(ctx.privato_leggi())
        if not ci.empty:
            u = ci.tail(7)
            c["benessere_7_giorni"] = {"sonno_medio": round(float(u["sonno"].mean()), 1),
                                       "stress_medio": round(float(u["stress"].mean()), 1),
                                       "energia_media": round(float(u["energia"].mean()), 1)}
    return c


def prompt(ctx, imp, domanda, storia):
    adesso = ctx.DIARIO.adesso()
    brevi = ("Risposte brevi, da 1 a 4 frasi, adatte a essere ascoltate."
             if imp.get("risposte_brevi", True) else "Risposte complete ma senza giri di parole.")
    ric = ricordi(ctx.DIA)
    return (
        f"Sei {imp['nome']}, la segretaria personale di {imp['chiamami']}. Carattere: "
        f"{imp['carattere']}. {imp.get('carattere_extra', '')}\n"
        f"Parli in italiano e dai del tu. {brevi} Niente elenchi puntati se non servono davvero.\n"
        "Usa SOLO le informazioni qui sotto: se qualcosa non c'è, dillo, non inventare "
        "impegni, numeri o fatti. Non sei un medico né uno psicologo: su salute e farmaci "
        "rimanda con gentilezza al medico. Se ti chiede di ricordare qualcosa, proponi "
        "l'azione «ricordo».\n\n"
        f"Adesso: {adesso:%A %d/%m/%Y, ore %H:%M}.\n"
        f"Chi è {imp['chiamami']}, nelle sue parole:\n{profilo(ctx) or '(non ancora scritto)'}\n\n"
        f"Cose che ti ha chiesto di ricordare:\n" + ("\n".join(f"- {r}" for r in ric[-40:]) or "(nessuna)") + "\n\n"
        f"La situazione in Quadro:\n{json.dumps(contesto(ctx, imp.get('mostra_benessere')), ensure_ascii=False, default=str)}\n\n"
        "La conversazione finora:\n"
        + "\n".join(("Lui: " if m["ruolo"] == "io" else "Tu: ") + m["testo"] for m in storia[-12:])
        + f"\nLui: {domanda}\n\n"
        "Rispondi SOLO con JSON valido:\n"
        '{"risposta": "quello che dici", "umore": "felice | pensa | riposo", '
        '"azioni": [{"tipo": "priorita | scadenza | idea | ricordo | obiettivo | promemoria | nota", '
        '"testo": "...", "data": "AAAA-MM-GG o vuoto", "ora": "HH:MM o vuoto", "importo": null}]}\n'
        "Proponi azioni solo quando te le chiede o sono chiaramente utili: le conferma lui.")


def rispondi(ctx, imp, domanda):
    storia = st.session_state.setdefault("sg_chat", [])
    testo = ctx.AI.chiedi(prompt(ctx, imp, domanda, storia), ctx.chiave_ai, ctx.modello_ai)
    import lettura
    d = lettura._json(testo)
    if not isinstance(d, dict) or not d.get("risposta"):
        d = {"risposta": (testo or "").strip(), "umore": "riposo", "azioni": []}
    azioni = [a for a in (d.get("azioni") or []) if isinstance(a, dict) and a.get("tipo") in AZIONI and a.get("testo")]
    for a in azioni:
        a["id"] = uuid.uuid4().hex[:8]
    storia.append({"ruolo": "io", "testo": domanda})
    storia.append({"ruolo": "lei", "testo": str(d["risposta"]), "umore": d.get("umore", "riposo"),
                   "azioni": azioni, "id": uuid.uuid4().hex[:8]})


def esegui(ctx, a):
    """Fa davvero l'azione confermata. Restituisce la frase di conferma."""
    D = ctx.DIARIO
    testo = str(a.get("testo", "")).strip()
    data = None
    try:
        data = dt.date.fromisoformat(str(a.get("data") or "")[:10])
    except ValueError:
        pass
    t = a["tipo"]
    if t == "priorita":
        ctx.diario_scrivi(D.riga("priorita", "aperta", "", 0, None, testo))
        return f"Aggiunta alle tre cose: {testo}"
    if t == "scadenza":
        quando = dt.datetime.combine(data or D.oggi() + dt.timedelta(days=7), dt.time(9, 0))
        imp = a.get("importo")
        ctx.diario_scrivi(D.riga("scadenza", testo[:120], "", 0,
                                 float(imp) if isinstance(imp, (int, float)) else None, "", quando=quando))
        return f"Scadenza aggiunta per il {quando:%d/%m}"
    if t == "idea":
        ctx.diario_scrivi(D.riga("idea", testo[:80], "Segretaria", 0, None, testo))
        return "Idea salvata"
    if t == "ricordo":
        ctx.diario_scrivi(D.riga("ricordo", "", "Segretaria", 0, None, testo))
        return "Me lo ricorderò"
    if t == "obiettivo":
        import equilibrio as EQ
        ctx.diario_scrivi(D.riga("obiettivo_trim", testo[:80], "in corso", 0, None,
                                 json.dumps({"passo": "", "perche": "", "trimestre": EQ.trimestre(D.oggi())},
                                            ensure_ascii=False)))
        return "Obiettivo aggiunto"
    if t == "promemoria":
        n = notifiche(ctx)
        n["regole"] = list(n["regole"]) + [{
            "id": "p" + uuid.uuid4().hex[:6], "attiva": True, "tipo": "promemoria",
            "ora": (a.get("ora") or "09:00")[:5], "giorni": (data or D.oggi()).isoformat(),
            "dettagli": testo}]
        _salva_impostazione(ctx, "notifiche", n)
        st.session_state["sg_da_sincronizzare"] = True
        return f"Promemoria su Telegram il {(data or D.oggi()):%d/%m} alle {(a.get('ora') or '09:00')[:5]}"
    ctx.diario_scrivi(D.riga("nota", testo[:80], "Segretaria", 0, None, testo))
    return "Nota salvata"


# ================================================= sincronizzare su Drive ===
def _cartelle(ctx):
    return ctx.cartelle


def pacchetto(ctx):
    """Tutto quello che Telegram e l'app desktop devono sapere."""
    import aforismi as AF
    imp = impostazioni(ctx)
    pref_af = ctx.impostazione(ctx.DIA, "aforismi", AF.PREDEFINITE)
    return {
        "versione": 1, "aggiornato": ctx.DIARIO.adesso().isoformat(timespec="minutes"),
        "segretaria": imp, "profilo": profilo(ctx), "ricordi": ricordi(ctx.DIA)[-60:],
        "notifiche": notifiche(ctx),
        "aforismi": {"preferenze": pref_af, "gusti": AF.gusti(ctx.DIA),
                     "scorta": ctx.cfg.get("aforismi_di_scorta", [])},
        "pratiche_respiro": [r["nome"] for r in ctx.cfg.get("ritmi", [])],
        "modello_ai": ctx.modello_ai,
        "contesto": contesto(ctx, imp.get("mostra_benessere")),
    }


# «segno» fa parte della chiave: quando premi «Aggiorna tutto da Drive» cambia,
# e la ricerca del file riparte invece di usare il risultato vecchio
@st.cache_data(ttl=300, show_spinner=False)
def _id_file(_info_json, cartelle, nome, segno):
    return DJ.trova(json.loads(_info_json), list(cartelle), nome)


@st.cache_data(ttl=60, show_spinner=False)
def _leggi_posta(_info_json, fid, segno):
    return DJ.leggi(json.loads(_info_json), fid)


def id_file(ctx, nome):
    if not ctx.SA:
        return None
    try:
        return _id_file(json.dumps(dict(ctx.SA)), tuple(_cartelle(ctx)), nome,
                        st.session_state.get("cerca_archivio", 0))
    except Exception:
        return None


def sincronizza(ctx):
    """Scrive Quadro_Segretaria.json. Restituisce (riuscito, messaggio)."""
    fid = id_file(ctx, FILE_SEGRETARIA)
    if not fid:
        return False, f"non trovo {FILE_SEGRETARIA} su Drive"
    try:
        DJ.scrivi(dict(ctx.SA), fid, pacchetto(ctx))
        st.session_state["sg_sincronizzato"] = ctx.DIARIO.adesso()
        st.session_state.pop("sg_da_sincronizzare", None)
        st.session_state.pop("sg_sync_errore", None)
        return True, "sincronizzato"
    except Exception as e:
        # non si riprova a ogni clic: si aspetta qualche minuto, o il pulsante
        st.session_state["sg_sync_errore"] = (ctx.DIARIO.adesso(), str(e)[:200])
        return False, str(e)[:200]


def posta(ctx):
    """Le cose arrivate da Telegram o dall'app desktop, non ancora importate."""
    fid = id_file(ctx, FILE_POSTA)
    if not fid:
        return None, []
    try:
        dati = _leggi_posta(json.dumps(dict(ctx.SA)), fid, st.session_state.get("sg_posta_segno", 0))
    except Exception:
        return fid, []
    voci = dati.get("voci", []) if isinstance(dati, dict) else (dati if isinstance(dati, list) else [])
    gia = set(ctx.DIA[ctx.DIA["Tipo"] == "importato"]["Attivita"]) if not ctx.DIA.empty else set()
    return fid, [v for v in voci if isinstance(v, dict) and v.get("id") not in gia]


def importa(ctx, voci):
    D = ctx.DIARIO
    righe = []
    for v in voci:
        tipo, testo = v.get("tipo", "nota"), str(v.get("testo", "")).strip()
        try:
            quando = dt.datetime.fromisoformat(str(v.get("quando"))[:16])
        except ValueError:
            quando = D.adesso()
        if tipo in ("priorita", "fatto"):
            righe.append(D.riga("priorita", "aperta" if tipo == "priorita" else "fatta", "", 0, None, testo, quando=quando))
        elif tipo == "scadenza":
            try:
                giorno = dt.date.fromisoformat(str(v.get("data"))[:10])
            except ValueError:
                giorno = D.oggi() + dt.timedelta(days=7)
            righe.append(D.riga("scadenza", testo[:120], "", 0, None, "", quando=dt.datetime.combine(giorno, dt.time(9, 0))))
        elif tipo == "idea":
            righe.append(D.riga("idea", testo[:80], v.get("da", "Telegram"), 0, None, testo, quando=quando))
        elif tipo == "ricordo":
            righe.append(D.riga("ricordo", "", v.get("da", "Telegram"), 0, None, testo, quando=quando))
        else:
            righe.append(D.riga("nota", testo[:80], v.get("da", "Telegram"), 0, None, testo, quando=quando))
        righe.append(D.riga("importato", v.get("id", ""), v.get("da", "Telegram"), 0, None, tipo))
    if righe:
        ctx.diario_scrivi(righe)
    return len(voci)


# ============================================================ l'avatar ======
IMPORTMAP = {"imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/",
    "@pixiv/three-vrm": "https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@3.5.5/lib/three-vrm.module.min.js"}}


def _motore():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar_motore.js"),
              encoding="utf-8") as f:
        return f.read()


def html_avatar(imp, ultimo=None, altezza=420):
    """L'avatar con il fumetto dell'ultima risposta. Prova a parlare da sola;
    se il browser non lo permette, compare il pulsante per ascoltare."""
    op = dict(imp["avatar"], nome=imp["nome"], voce=imp.get("voce", ""),
              velocita=imp.get("velocita", 1), tono=imp.get("tono", 1.05))
    js = lambda v: json.dumps(v, ensure_ascii=False).replace("</", "<\\/")
    fondo = "transparent" if op["sfondo"] == "trasparente" else op["sfondo"]
    return f"""<!doctype html><meta charset="utf-8">
<style>
  body {{ margin:0; font-family:system-ui,sans-serif; background:{fondo}; overflow:hidden; }}
  #scena {{ position:absolute; inset:0; }}
  #fumetto {{ position:absolute; left:10px; right:10px; bottom:10px; background:rgba(15,42,36,.88);
             color:#eef7f3; border-radius:14px; padding:10px 12px; font-size:14.5px; line-height:1.4;
             max-height:38%; overflow-y:auto; display:none; }}
  #nome {{ position:absolute; top:8px; left:10px; font-weight:700; color:#0f5d47;
          background:rgba(255,255,255,.85); padding:3px 10px; border-radius:20px; font-size:13px; }}
  .bt {{ position:absolute; top:8px; right:10px; display:flex; gap:6px; }}
  button {{ border:1px solid #1baf7a; background:rgba(255,255,255,.9); color:#0f5d47; border-radius:20px;
           padding:4px 10px; cursor:pointer; font-size:13px; }}
</style>
<div id="scena"></div><div id="nome">{op['nome']}</div>
<div class="bt"><button id="ascolta" title="Ascolta la risposta">🔊</button><button id="ciao" title="Saluta">👋</button></div>
<div id="fumetto"></div>
<script type="importmap">{json.dumps(IMPORTMAP)}</script>
<script type="module">
{_motore()}
const OP = {js(op)}, ULTIMO = {js(ultimo or {})};
const av = await creaAvatar(document.getElementById('scena'), OP);
const f = document.getElementById('fumetto');
if (ULTIMO.testo) {{ f.textContent = ULTIMO.testo; f.style.display = 'block'; av.stato(ULTIMO.umore || 'riposo'); }}
document.getElementById('ascolta').onclick = () => ULTIMO.testo && av.parla(ULTIMO.testo);
document.getElementById('ciao').onclick = () => av.saluta();
document.getElementById('scena').addEventListener('avatar-clic', () => av.saluta());
// parla da sola solo per una risposta nuova, non a ogni ricaricamento
let detto = '';
try {{ detto = sessionStorage.getItem('sg_detto') || ''; }} catch (e) {{}}
if (ULTIMO.id && ULTIMO.id !== detto) {{
  try {{ sessionStorage.setItem('sg_detto', ULTIMO.id); }} catch (e) {{}}
  setTimeout(() => av.parla(ULTIMO.testo), 400);
}} else if (!ULTIMO.id) {{ setTimeout(() => av.saluta(), 600); }}
document.addEventListener('avatar-muto', () => {{ document.getElementById('ascolta').textContent = '🔊 Tocca per sentirla'; }});
</script>"""


# ============================================================ la scheda =====
def mostra(ctx):
    imp = impostazioni(ctx)
    st.markdown(f"#### 👩‍💼 {imp['nome']}, la tua segretaria")

    # una volta per sessione, e quando serve, Quadro aggiorna il file per
    # Telegram e l'app desktop
    ultimo_sync = st.session_state.get("sg_sincronizzato")
    errore = st.session_state.get("sg_sync_errore")
    in_pausa = errore and (ctx.DIARIO.adesso() - errore[0]).total_seconds() < 600
    if ctx.SA and not in_pausa and (st.session_state.get("sg_da_sincronizzare") or ultimo_sync is None
                                    or (ctx.DIARIO.adesso() - ultimo_sync).total_seconds() > 1800):
        if id_file(ctx, FILE_SEGRETARIA):
            sincronizza(ctx)

    T = st.tabs(["💬 Parla", "⚙️ Come la vuoi", "🧠 Cosa sa di te", "🔔 Notifiche e Telegram",
                 "📲 Telefono e desktop"], key="sg_sezione")
    with T[0]:
        _parla(ctx, imp)
    with T[1]:
        _aspetto(ctx, imp)
    with T[2]:
        _conoscenza(ctx, imp)
    with T[3]:
        _notifiche(ctx)
    with T[4]:
        _dispositivi(ctx, imp)


def _parla(ctx, imp):
    storia = st.session_state.setdefault("sg_chat", [])
    ultimo = next((m for m in reversed(storia) if m["ruolo"] == "lei"), None)
    sinistra, destra = st.columns([2, 3])
    with sinistra:
        ctx.pagina_html(html_avatar(imp, ultimo), 430)
    with destra:
        if not ctx.chiave_ai:
            st.error("Per parlarle serve la chiave di Google AI Studio nei Secrets.")
            return
        _, arrivate = posta(ctx) if ctx.SA else (None, [])
        if arrivate:
            st.info(f"📥 {len(arrivate)} cose arrivate da Telegram o dal desktop: le trovi in "
                    "«Notifiche e Telegram».")
        box = st.container(height=330)
        with box:
            if not storia:
                st.caption(f"Scrivile o parlale. Per esempio: «Cosa ho di importante oggi?», "
                           f"«Ricordati che il GAL risponde a fine mese», «Aggiungi la scadenza "
                           f"dell'IVA il 16», «Preparami la giornata».")
            for m in storia[-30:]:
                with st.chat_message("user" if m["ruolo"] == "io" else "assistant",
                                     avatar="🧑" if m["ruolo"] == "io" else "👩‍💼"):
                    st.markdown(m["testo"])
        # le azioni proposte nell'ultima risposta
        if ultimo and ultimo.get("azioni"):
            fatte = st.session_state.setdefault("sg_azioni_fatte", {})
            for a in ultimo["azioni"]:
                if a["id"] in fatte:
                    st.caption(f"{'✅' if fatte[a['id']] else '✖️'} {AZIONI[a['tipo']]}: {a['testo']}")
                    continue
                with st.container(border=True):
                    extra = " · ".join(x for x in (a.get("data") or "", a.get("ora") or "") if x)
                    # testo e data arrivano dall'AI: niente HTML, solo testo
                    st.markdown(f"**{AZIONI[a['tipo']]}**")
                    st.text(a["testo"])
                    if extra:
                        st.caption(extra)
                    b1, b2 = st.columns(2)
                    if b1.button("✅ Fai", key=f"sg_si_{a['id']}", type="primary", width='stretch'):
                        ctx.conferma(esegui(ctx, a))
                        fatte[a["id"]] = True
                        st.session_state["sg_da_sincronizzare"] = True
                        st.rerun()
                    if b2.button("✖️ No", key=f"sg_no_{a['id']}", width='stretch'):
                        fatte[a["id"]] = False
                        st.rerun()

        n_voce = st.session_state.get("sg_n_voce", 0)
        voce = st.audio_input("🎙️ Parlale", key=f"sg_voce_{n_voce}")
        domanda = st.chat_input(f"Scrivi a {imp['nome']}…", key="sg_scrivi")
        if voce is not None:
            # la registrazione si usa una volta sola, che vada bene o no:
            # altrimenti a ogni ricaricamento verrebbe rimandata all'AI
            st.session_state["sg_n_voce"] = n_voce + 1
            try:
                with st.spinner("Ascolto…"):
                    domanda = ctx.VOCE.trascrivi_audio(voce.getvalue(), ctx.chiave_ai, ctx.modello_ai,
                                                       getattr(voce, "type", None) or "audio/wav")
            except Exception as e:
                st.error(f"Non ho capito l'audio: {e}")
                domanda = None
        if domanda:
            try:
                with st.spinner(f"{imp['nome']} ci pensa…"):
                    rispondi(ctx, imp, domanda)
                st.rerun()
            except Exception as e:
                st.error(getattr(e, "messaggio", None) or str(e))
        if storia and st.button("🧹 Nuova conversazione", key="sg_pulisci"):
            st.session_state["sg_chat"] = []
            st.rerun()


def _aspetto(ctx, imp):
    st.caption("Come si chiama, come parla, che aspetto ha. Vale anche per Telegram e per "
               "l'app sul desktop.")
    a = imp["avatar"]
    with st.form("sg_aspetto"):
        n1, n2 = st.columns(2)
        nome = n1.text_input("Il suo nome", imp["nome"])
        chiamami = n2.text_input("Come ti chiama", imp["chiamami"])
        car = st.selectbox("Carattere", CARATTERI, index=CARATTERI.index(imp["carattere"])
                           if imp["carattere"] in CARATTERI else 0)
        extra = st.text_input("Qualcosa in più sul suo modo di fare", imp.get("carattere_extra", ""),
                              placeholder="es. ogni tanto una battuta da ingegnere, mai frasi fatte")
        brevi = st.checkbox("Risposte brevi (meglio da ascoltare)", imp.get("risposte_brevi", True))
        st.markdown("**La voce** (quella del dispositivo)")
        v1, v2, v3 = st.columns(3)
        voce = v1.text_input("Nome della voce, se vuoi sceglierla", imp.get("voce", ""),
                             help="Vuoto = la prima voce italiana femminile del dispositivo. I nomi "
                                  "li vedi nel lettore di «Leggimelo».")
        vel = v2.slider("Velocità", 0.6, 1.6, float(imp.get("velocita", 1.0)), 0.05)
        tono = v3.slider("Tono", 0.6, 1.6, float(imp.get("tono", 1.05)), 0.05)
        st.markdown("**L'aspetto**")
        c = st.columns(6)
        pelle = c[0].color_picker("Pelle", a["pelle"])
        capelli = c[1].color_picker("Capelli", a["capelli"])
        occhi = c[2].color_picker("Occhi", a["occhi"])
        giacca = c[3].color_picker("Giacca", a["giacca"])
        camicia = c[4].color_picker("Camicia", a["camicia"])
        labbra = c[5].color_picker("Labbra", a["labbra"])
        d = st.columns(4)
        acc = ["caschetto", "lunghi", "raccolti", "corti"]
        acconciatura = d[0].selectbox("Capelli", acc, index=acc.index(a["acconciatura"]) if a["acconciatura"] in acc else 0)
        inq = ["busto", "viso", "figura"]
        inquadratura = d[1].selectbox("Inquadratura", inq, index=inq.index(a["inquadratura"]) if a["inquadratura"] in inq else 0)
        occhiali = d[2].checkbox("Occhiali", a["occhiali"])
        orecchini = d[3].checkbox("Orecchini", a["orecchini"])
        sf = st.radio("Sfondo", ["trasparente", "colore"], horizontal=True,
                      index=0 if a["sfondo"] == "trasparente" else 1)
        colore_sf = st.color_picker("Colore dello sfondo", a["sfondo"] if a["sfondo"].startswith("#") else "#0f2a24")
        vrm = st.text_input("Personaggio VRM (facoltativo): indirizzo del file .vrm", a.get("vrm", ""),
                            help="Crealo gratis con VRoid Studio, esportalo in .vrm e mettilo in un "
                                 "repository GitHub PUBBLICO: incolla qui il link «raw». Se è vuoto o "
                                 "non si carica, resta la segretaria stilizzata.")
        if st.form_submit_button("💾 Salva", type="primary"):
            nuove = {"nome": nome.strip() or "Sofia", "chiamami": chiamami.strip() or "Claudio",
                     "carattere": car, "carattere_extra": extra, "risposte_brevi": brevi,
                     "mostra_benessere": imp.get("mostra_benessere", False),
                     "voce": voce.strip(), "velocita": vel, "tono": tono,
                     "avatar": {"pelle": pelle, "capelli": capelli, "occhi": occhi, "giacca": giacca,
                                "camicia": camicia, "labbra": labbra, "acconciatura": acconciatura,
                                "inquadratura": inquadratura, "occhiali": occhiali, "orecchini": orecchini,
                                "sfondo": "trasparente" if sf == "trasparente" else colore_sf,
                                "vrm": vrm.strip()}}
            _salva_impostazione(ctx, "segretaria", nuove)
            st.session_state["sg_da_sincronizzare"] = True
            ctx.conferma("Segretaria aggiornata")
            st.rerun()
    st.markdown("**Com'è adesso**")
    ctx.pagina_html(html_avatar(imp, None), 380)


def _conoscenza(ctx, imp):
    st.markdown("##### Chi sei, con parole tue")
    st.caption("Lavoro, progetti, come ti piace organizzarti, cosa ti mette in difficoltà, "
               "cosa vuoi ottenere quest'anno. Più è concreto, più ti aiuta bene. Puoi dettarlo.")
    if "__sg_profilo__" in st.session_state:
        st.session_state["sg_profilo"] = st.session_state.pop("__sg_profilo__")
    if "sg_profilo" not in st.session_state:
        st.session_state["sg_profilo"] = profilo(ctx)
    testo = ctx.VOCE.campo("Il tuo profilo", "sg_profilo", ctx.chiave_ai, ctx.modello_ai, altezza=220)
    if st.button("💾 Salva il profilo", type="primary", key="sg_salva_prof"):
        _salva_impostazione(ctx, "profilo", {"chi_sono": testo})
        st.session_state["sg_da_sincronizzare"] = True
        ctx.conferma("Profilo salvato")
        st.rerun()

    st.divider()
    st.markdown("##### 🧠 Le cose che ricorda")
    ric = ricordi(ctx.DIA)
    if not ric:
        st.caption("Ancora niente. Dille «ricordati che…» in chat, o aggiungilo qui.")
    for i, r in enumerate(ric):
        c1, c2 = st.columns([8, 1])
        c1.markdown(f"- {r}")
        if c2.button("🗑️", key=f"sg_ric_via_{i}", help="Dimentica"):
            ctx.diario_scrivi(ctx.DIARIO.riga("ricordo_rimosso", "", "Segretaria", 0, None, r))
            st.session_state["sg_da_sincronizzare"] = True
            st.rerun()
    with st.form("sg_nuovo_ricordo", clear_on_submit=True):
        nuovo = st.text_input("Un nuovo ricordo", placeholder="es. il martedì pomeriggio ho lezione di Excel")
        if st.form_submit_button("➕ Aggiungi") and nuovo.strip():
            ctx.diario_scrivi(ctx.DIARIO.riga("ricordo", "", "Segretaria", 0, None, nuovo.strip()))
            st.session_state["sg_da_sincronizzare"] = True
            st.rerun()

    st.divider()
    # si salva solo quando lo tocchi (on_change), non a ogni ricaricamento
    def _benessere():
        _salva_impostazione(ctx, "segretaria", dict(impostazioni(ctx), mostra_benessere=st.session_state["sg_benessere"]))
        st.session_state["sg_da_sincronizzare"] = True
    st.toggle("Può vedere anche il benessere (sonno, stress, energia degli ultimi 7 giorni)",
              imp.get("mostra_benessere", False), key="sg_benessere", on_change=_benessere,
              help="Solo le medie, e solo quando la Taratura è aperta.")
    with st.expander("👁️ Cosa vede adesso, esattamente"):
        st.json(contesto(ctx, imp.get("mostra_benessere")))


def _notifiche(ctx):
    n = notifiche(ctx)
    st.markdown("##### 🔔 Cosa ti manda su Telegram, e quando")
    st.caption("Ogni riga è una notifica. Ora nel formato 08:30. Giorni: tutti, feriali, weekend, "
               "uno o più giorni («lun,mer,ven») o una data («2026-11-20») per una volta sola. "
               "Nei dettagli: per l'aforisma i temi, per il promemoria il testo.")
    tab = pd.DataFrame(n["regole"])
    for c, v in (("attiva", True), ("tipo", "aforisma"), ("ora", "09:00"), ("giorni", "tutti"),
                 ("dettagli", ""), ("id", "")):
        if c not in tab.columns:
            tab[c] = v
    tab = tab[["attiva", "tipo", "ora", "giorni", "dettagli", "id"]]
    nuova = st.data_editor(tab, num_rows="dynamic", hide_index=True, width='stretch', key="sg_regole",
                           column_config={
                               "attiva": st.column_config.CheckboxColumn("On", default=True),
                               "tipo": st.column_config.SelectboxColumn("Cosa", options=list(TIPI_NOTIFICA)),
                               "ora": st.column_config.TextColumn("Ora", max_chars=5),
                               "giorni": st.column_config.TextColumn("Giorni"),
                               "dettagli": st.column_config.TextColumn("Dettagli", width="large"),
                               "id": None})
    with st.expander("Che cosa fa ogni tipo"):
        for k, v in TIPI_NOTIFICA.items():
            st.markdown(f"- **{k}**: {v}")
    attive = st.toggle("Notifiche accese", n.get("attive", True), key="sg_notif_on")
    if st.button("💾 Salva le notifiche", type="primary", key="sg_salva_notif"):
        # le caselle vuote di una riga nuova arrivano come NaN: qui diventano vuote,
        # perché un «NaN» nel file renderebbe illeggibili le impostazioni per Telegram
        def v(x, predefinito=""):
            return predefinito if x is None or (isinstance(x, float) and pd.isna(x)) else x
        regole, errori = [], []
        for r in nuova.to_dict("records"):
            ora = str(v(r.get("ora"))).strip()
            if not ora and not str(v(r.get("dettagli"))).strip():
                continue                                    # riga lasciata vuota
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", ora):
                errori.append(f"ora «{ora}» non valida")
                continue
            regole.append({"id": str(v(r.get("id"))) or "r" + uuid.uuid4().hex[:6],
                           "attiva": bool(v(r.get("attiva"), True)),
                           "tipo": str(v(r.get("tipo"), "aforisma")) or "aforisma", "ora": ora,
                           "giorni": str(v(r.get("giorni"), "tutti")).strip().lower() or "tutti",
                           "dettagli": str(v(r.get("dettagli")))})
        if errori:
            st.error("Da correggere: " + "; ".join(errori))
        else:
            _salva_impostazione(ctx, "notifiche", {"attive": attive, "regole": regole})
            st.session_state["sg_da_sincronizzare"] = True
            ctx.conferma("Notifiche salvate")
            st.rerun()

    st.divider()
    st.markdown("##### 🔄 Il collegamento con Telegram e il desktop")
    fid = id_file(ctx, FILE_SEGRETARIA) if ctx.SA else None
    if not fid:
        st.warning(f"Manca **{FILE_SEGRETARIA}** su Drive. Scaricalo qui sotto e caricalo nella "
                   "stessa cartella di Quadro_Diario.xlsx (condivisa come Editor), poi premi "
                   "«Aggiorna tutto da Drive» nella barra a sinistra.")
        st.download_button(f"⬇️ Scarica {FILE_SEGRETARIA}", "{}", FILE_SEGRETARIA, "application/json",
                           key="sg_scarica_vuoto")
    else:
        quando = st.session_state.get("sg_sincronizzato")
        st.success(f"Collegato. Ultimo aggiornamento: {quando:%d/%m %H:%M}" if quando else "Collegato.")
        if st.button("🔄 Sincronizza adesso", key="sg_sync"):
            ok, msg = sincronizza(ctx)
            (ctx.conferma if ok else st.error)("Sincronizzato" if ok else f"Non riuscito: {msg}")
            if ok:
                st.rerun()

    pid, arrivate = posta(ctx) if ctx.SA else (None, [])
    st.markdown("##### 📥 Arrivate da Telegram e dal desktop")
    if not pid:
        st.caption(f"{FILE_POSTA} lo crea il bot Telegram da solo, la prima volta che gli scrivi. "
                   "Se usi solo l'app desktop, scaricalo e caricalo su Drive accanto all'altro.")
        st.download_button(f"⬇️ Scarica {FILE_POSTA}", '{"voci": []}', FILE_POSTA, "application/json",
                           key="sg_scarica_posta")
    elif not arrivate:
        st.caption("Niente di nuovo.")
    else:
        for v in arrivate[:30]:
            st.markdown(f"- **{v.get('tipo', 'nota')}** · {str(v.get('quando', ''))[:16]} · {v.get('testo', '')}")
        if st.button(f"📥 Importa nel diario ({len(arrivate)})", type="primary", key="sg_importa"):
            ctx.conferma(f"Importate {importa(ctx, arrivate)} voci")
            st.session_state["sg_posta_segno"] = st.session_state.get("sg_posta_segno", 0) + 1
            st.rerun()

    with st.expander("🛠️ Come si attiva il bot Telegram (una volta sola, 15 minuti)"):
        st.markdown(GUIDA_TELEGRAM)
        percorso = os.path.join(os.path.dirname(os.path.abspath(__file__)), "segretaria_telegram.gs")
        if os.path.exists(percorso):
            codice = open(percorso, encoding="utf-8").read()
            st.download_button("⬇️ Scarica il codice del bot (segretaria_telegram.gs)", codice,
                               "segretaria_telegram.gs", "text/plain", key="sg_gs")
            st.code(codice, language="javascript")


def _dispositivi(ctx, imp):
    st.markdown("##### 📱 Sul telefono (Honor Magic V3)")
    st.markdown(GUIDA_TELEFONO)
    st.markdown("##### 💻 Sul desktop (Surface e PC HP)")
    st.markdown(GUIDA_DESKTOP)
    # se la cartella è nella repository, Quadro la impacchetta e te la fa scaricare
    cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), "segretaria_desktop")
    if os.path.isdir(cartella):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for nome in sorted(os.listdir(cartella)):
                percorso = os.path.join(cartella, nome)
                if os.path.isfile(percorso) and "service_account" not in nome:
                    z.write(percorso, os.path.join("segretaria_desktop", nome))
        st.download_button("⬇️ Scarica l'app per il desktop (zip)", buf.getvalue(),
                           "segretaria_desktop.zip", "application/zip", key="sg_zip_desktop")


# ============================================================== le guide ====
GUIDA_TELEGRAM = """
**1. Crea il bot** (2 minuti). In Telegram cerca **@BotFather**, scrivi `/newbot`, scegli
un nome (es. *Sofia – Quadro*) e un nome utente che finisce con `bot`. Ti dà un
**token**, una riga tipo `7123456789:AAH…`: tienilo da parte, è la chiave del bot.

**2. Crea lo script** (5 minuti). Vai su [script.google.com](https://script.google.com)
con lo stesso account Google di Drive → **Nuovo progetto**. Cancella quello che c'è e
incolla il codice qui sotto. In alto chiamalo *Segretaria Quadro*.

**3. Il fuso orario.** Ingranaggio ⚙️ *Impostazioni progetto* → *Fuso orario* →
**(GMT+01:00) Roma**.

**4. Le chiavi.** Sempre nelle impostazioni, in fondo, *Proprietà script* → aggiungi:
- `TELEGRAM_TOKEN` = il token del punto 1
- `GEMINI_KEY` = la stessa chiave di Google AI Studio dei Secrets di Quadro

**5. Avvio.** Torna all'editor, scegli la funzione **`configura`** nel menu in alto e
premi ▶ **Esegui**. Google chiede i permessi: *Rivedi autorizzazioni* → il tuo account
→ *Avanzate* → *Vai a Segretaria Quadro* → *Consenti*. Lo script è tuo, gira sul tuo account.

**6. Presentati.** In Telegram apri il tuo bot e scrivi `/start`. Entro un minuto ti
risponde: da quel momento parla solo con te.

Da lì: ti scrive agli orari delle notifiche, e tu puoi scriverle o mandarle **messaggi
vocali**. Comandi: `/oggi` · `/aforisma` · `/respira` · `/nota testo` · `/idea testo` ·
`/fatto testo` · `/priorita testo` · `/scadenza 2026-11-20 testo` · `/ricorda testo` · `/aiuto`.
Quello che le dici con i comandi arriva qui, in «Arrivate da Telegram».

**Costi:** zero. Google Apps Script è gratuito e lo script controlla i messaggi una volta
al minuto, ben dentro i limiti gratuiti.
"""

GUIDA_TELEFONO = """
- **Quadro e la segretaria come icona.** Apri Quadro in Chrome sul telefono, poi ⋮ →
  **Aggiungi a schermata Home**. Fallo due volte: una con l'indirizzo normale e una con
  `?pagina=segretaria` in fondo all'indirizzo, che apre direttamente lei. Si apre a tutto
  schermo, e lei è animata in 3D come qui.
- **Il widget vero sulla schermata Home** è quello di **Telegram**: tieni premuto sulla
  Home → *Widget* → *Telegram* → scegli la chat con il tuo bot. Vedi i suoi ultimi
  messaggi e le scrivi con un tocco.
- **Perché non un widget 3D animato:** i widget di Android sono piccole viste fatte
  dall'app che li possiede, non pagine web: un avatar 3D che si muove sulla Home
  richiederebbe un'app Android vera, da pubblicare. Le due strade sopra danno il 90%
  dell'effetto senza costi.
"""

GUIDA_DESKTOP = """
La cartella **`segretaria_desktop`** (te l'ho mandata come zip; se la metti nella repository
la scarichi anche da qui) è una piccola app per Windows
che mette la segretaria in 3D **sopra le altre finestre, con lo sfondo trasparente**.
La sposti trascinando la maniglia ⠿, ci clicchi sopra per scriverle, tieni premuto 🎙️ per
parlarle. Prende aspetto, nome, voce, profilo e ricordi da qui, attraverso Drive.

1. Installa **Node.js** (versione LTS) da nodejs.org — una volta per computer.
2. Scompatta lo zip sul PC (Surface e HP, uguale), per esempio in Documenti.
3. Copia dentro la cartella il file JSON del service account (lo stesso dei Secrets) e
   apri `config.json`: scrivi la chiave Gemini e l'id della cartella Drive.
4. Doppio clic su **`installa.bat`** (la prima volta, qualche minuto), poi su **`avvia.bat`**.
5. Dall'icona vicino all'orologio puoi farla partire da sola all'accensione.

Il file `LEGGIMI.md` nella cartella spiega tutto passo per passo.
"""
