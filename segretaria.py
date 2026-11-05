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
    È SEMPRE LÌ    in un angolo di Quadro, su tutte le schede: si rimpicciolisce
                   a un bottone col suo nome. Le scrivi o le parli senza che il
                   resto di Quadro si ricarichi.
    HA UNA VOCE    naturale, quella di Gemini, con la bocca che segue la voce.
                   Quando le voci gratuite del giorno finiscono (sono poche),
                   passa da sola alla voce del dispositivo.
    GLI AFORISMI   preferenze e raccolta stanno qui, in «✨ Aforismi».

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

import base64
import datetime as dt
import html
import json
import os
import re
import time
import types
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
    "voce_motore": "gemini", "voce_gemini": "Sulafat", "angolo": "automatico", "lato": "destra",
    "registro": True, "registro_testi": True,
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
          "promemoria": "📲 Promemoria su Telegram", "nota": "📝 Salva la nota",
          "apri": "➜ Portami lì"}

# Quando la domanda è su come si usa Quadro, lei riceve anche la guida
# (guida.json) e può proporre l'azione «apri» per portarti nella scheda giusta.
_COME_SI_FA = re.compile(r"\b(come (si |faccio|posso|funziona|uso|attivo|configuro|cambio|imposto|aggiungo)|"
                         r"dove (trovo|si trova|sta|stanno|metto|vedo|cambio)|portami|aprimi|apri la|vai a|"
                         r"in quale scheda|che scheda|guida|quadro)", re.I)


def _guida_prompt(domanda):
    if not _COME_SI_FA.search(domanda or ""):
        return ""
    import guida as GUIDA
    G = GUIDA.carica()
    if "_errore" in G:
        return ""
    return ("Ti sta chiedendo come si usa Quadro: rispondi con i passi presi dalla guida qui sotto, "
            "dicendo la scheda. Se serve, proponi l'azione «apri» con testo uguale a uno di questi "
            f"posti: {', '.join(GUIDA.destinazioni(G))}.\n"
            f"GUIDA DI QUADRO:\n{GUIDA.testo_per_ai(G, 7000)}\n\n")


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


# ========================================================== il registro =====
# Ogni domanda e risposta finisce nel diario come riga «sg_scambio»: da dove
# (angolo, scheda, telegram, desktop), com'è andata, quanti secondi ci ha
# messo, le azioni che ha proposto, che voce ha usato e, se vuoi, il testo.
# I tuoi 👍/👎 sono righe «sg_voto» (vince l'ultima per ogni risposta), le
# azioni confermate o rifiutate righe «sg_azione». Da qui escono i numeri di
# «📈 Come lavora», e i 👎 con un commento diventano le sue «lezioni»: le
# rilegge ogni volta che ti risponde, per non ripetere lo stesso errore.
def _numero(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _nota_json(testo):
    try:
        d = json.loads(testo or "{}")
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def voti(dia):
    """id della risposta → (voto +1/-1, commento). Vince l'ultimo dato."""
    if dia is None or dia.empty:
        return {}
    v = dia[dia["Tipo"] == "sg_voto"].sort_values(["Data", "Ora"], kind="stable")
    return {r["Attivita"]: (_numero(r["Valore"]), _nota_json(r["Nota"]).get("c", "")) for _, r in v.iterrows()}


COLONNE_REGISTRO = ["quando", "canale", "esito", "secondi", "domanda", "risposta", "azioni",
                    "voce", "voto", "commento", "errore", "id"]


def registro(dia, da_posta=()):
    """Tutte le chiacchierate, dal diario e (non ancora archiviate) dalla posta."""
    righe = []
    if dia is not None and not dia.empty:
        for _, r in dia[dia["Tipo"] == "sg_scambio"].iterrows():
            n = _nota_json(r["Nota"])
            righe.append({"quando": _quando(r), "canale": r["Attivita"], "esito": r["Strumento"],
                          "secondi": _numero(r["Valore"]), "domanda": n.get("d", ""),
                          "risposta": n.get("r", ""), "azioni": ", ".join(n.get("azioni", [])),
                          "voce": n.get("voce", ""), "errore": n.get("errore", ""), "id": n.get("id", "")})
    for v in da_posta:
        try:
            quando = pd.Timestamp(str(v.get("quando"))[:16])
        except ValueError:
            quando = pd.NaT
        righe.append({"quando": quando, "canale": str(v.get("da", "Telegram")).lower(),
                      "esito": "errore" if v.get("errore") else "ok", "secondi": _numero(v.get("secondi")),
                      "domanda": str(v.get("testo", "")), "risposta": str(v.get("risposta", "")),
                      "azioni": v.get("azione") or "", "voce": "", "errore": str(v.get("errore") or ""),
                      "id": v.get("id", "")})
    df = pd.DataFrame(righe, columns=[c for c in COLONNE_REGISTRO if c not in ("voto", "commento")])
    vt = voti(dia)
    df["voto"] = df["id"].map(lambda i: vt.get(i, (None, ""))[0])
    df["commento"] = df["id"].map(lambda i: vt.get(i, (None, ""))[1])
    return df[COLONNE_REGISTRO].sort_values("quando", kind="stable").reset_index(drop=True)


def azioni_decise(dia):
    if dia is None or dia.empty:
        return pd.DataFrame(columns=["quando", "tipo", "decisione", "canale", "testo"])
    a = dia[dia["Tipo"] == "sg_azione"]
    return pd.DataFrame([{"quando": _quando(r), "tipo": r["Attivita"], "decisione": r["Strumento"],
                          "canale": _nota_json(r["Nota"]).get("canale", ""),
                          "testo": _nota_json(r["Nota"]).get("testo", "")} for _, r in a.iterrows()],
                        columns=["quando", "tipo", "decisione", "canale", "testo"])


def lezioni(dia, quante=8):
    """I 👎 con un commento: cosa non ti è piaciuto, in parole tue."""
    reg = registro(dia)
    if reg.empty:
        return []
    neg = reg[(reg["voto"] < 0) & (reg["commento"].fillna("").str.strip() != "")].tail(quante)
    return [f"alla domanda «{r['domanda'][:120]}» hai risposto «{r['risposta'][:160]}»: "
            f"non gli è piaciuto perché «{r['commento']}»" for _, r in neg.iterrows()]


def _registra_scambio(ctx, imp, canale, domanda, m, secondi, voce, errore=""):
    if not imp.get("registro", True):
        return
    m = m or {}
    nota = {"id": m.get("id", ""), "azioni": [a["tipo"] for a in m.get("azioni", [])],
            "voce": voce, "umore": m.get("umore", "")}
    if imp.get("registro_testi", True):
        nota["d"], nota["r"] = domanda[:400], str(m.get("testo", ""))[:800]
    if errore:
        nota["errore"] = str(errore)[:300]
    try:
        ctx.diario_scrivi(ctx.DIARIO.riga("sg_scambio", canale, "errore" if errore else "ok", 0,
                                          round(float(secondi), 1), json.dumps(nota, ensure_ascii=False)))
    except Exception:
        pass                       # il registro non deve mai fermare la conversazione


def _vota(ctx, chiave, mid, canale):
    """Il 👍/👎 sotto una risposta: si salva subito, il commento eventuale dopo."""
    val = st.session_state.get(chiave)
    if val is None:
        return
    commento = st.session_state.get(chiave + "_nota", "")
    try:
        ctx.diario_scrivi(ctx.DIARIO.riga("sg_voto", mid, canale, 0, 1 if val == 1 else -1,
                                          json.dumps({"c": commento}, ensure_ascii=False)))
        st.session_state.setdefault("sg_voti_sessione", {})[mid] = (1 if val == 1 else -1, commento)
    except Exception:
        pass


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


def _lezioni_prompt(ctx):
    lez = lezioni(ctx.DIA)
    if not lez:
        return ""
    return ("Risposte tue che non gli sono piaciute: tienine conto e non ripeterle così.\n"
            + "\n".join(f"- {x}" for x in lez) + "\n\n")


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
        + _lezioni_prompt(ctx)
        + _guida_prompt(domanda)
        + f"La situazione in Quadro:\n{json.dumps(contesto(ctx, imp.get('mostra_benessere')), ensure_ascii=False, default=str)}\n\n"
        "La conversazione finora:\n"
        + "\n".join(("Lui: " if m["ruolo"] == "io" else "Tu: ") + m["testo"] for m in storia[-12:])
        + f"\nLui: {domanda}\n\n"
        "Rispondi SOLO con JSON valido:\n"
        '{"risposta": "quello che dici", "umore": "felice | pensa | riposo", '
        '"azioni": [{"tipo": "priorita | scadenza | idea | ricordo | obiettivo | promemoria | nota | apri", '
        '"testo": "...", "data": "AAAA-MM-GG o vuoto", "ora": "HH:MM o vuoto", "importo": null}]}\n'
        "Proponi azioni solo quando te le chiede o sono chiaramente utili: le conferma lui.")


def rispondi(ctx, imp, domanda, canale="scheda"):
    """Chiede la risposta all'AI e la aggiunge alla conversazione.
    `canale` dice da dove è arrivata la domanda: scheda o angolo."""
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
                   "azioni": azioni, "id": uuid.uuid4().hex[:8], "canale": canale})


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
    if t == "apri":
        # solo navigazione: niente da scrivere nel diario
        import guida as GUIDA
        posti = GUIDA.destinazioni(GUIDA.carica())
        basso = testo.lower()
        nome = (next((n for n in posti if n.lower() == basso), None)
                or next((n for n in posti if basso and (basso in n.lower() or n.lower().split(" ", 1)[-1] in basso)), None))
        if not nome:
            return f"Non so dove sia «{testo}»: guarda nella ❓ Guida"
        GUIDA.vai(posti[nome])
        return f"Eccoci in {nome}"
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


def posta(ctx, scambi=False):
    """
    Le cose arrivate da Telegram o dall'app desktop, non ancora importate.
    Con scambi=True, invece, solo il registro delle chiacchierate fatte là
    (tipo «scambio»): quelle non sono cose da rivedere, ma numeri per
    «📈 Come lavora».
    """
    fid = id_file(ctx, FILE_POSTA)
    if not fid:
        return None, []
    try:
        dati = _leggi_posta(json.dumps(dict(ctx.SA)), fid, st.session_state.get("sg_posta_segno", 0))
    except Exception:
        return fid, []
    voci = dati.get("voci", []) if isinstance(dati, dict) else (dati if isinstance(dati, list) else [])
    gia = set(ctx.DIA[ctx.DIA["Tipo"] == "importato"]["Attivita"]) if not ctx.DIA.empty else set()
    voci = [v for v in voci if isinstance(v, dict) and v.get("id") not in gia]
    return fid, [v for v in voci if (v.get("tipo") == "scambio") == scambi]


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
        elif tipo == "scambio":
            # una chiacchierata fatta su Telegram o sul desktop: va nel registro
            nota = {"id": v.get("id", ""), "d": testo[:400], "r": str(v.get("risposta", ""))[:800],
                    "azioni": [v["azione"]] if v.get("azione") else [], "voce": ""}
            if v.get("errore"):
                nota["errore"] = str(v["errore"])[:300]
            righe.append(D.riga("sg_scambio", str(v.get("da", "Telegram")).lower(),
                                "errore" if v.get("errore") else "ok", 0, _numero(v.get("secondi")),
                                json.dumps(nota, ensure_ascii=False), quando=quando))
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

# Dove l'avatar guarda se lei «ci sta pensando» (c'è una rotellina che gira lì)
_ATTESA = {"angolo": ".st-key-sg_pannello", "scheda": ".st-key-sg_chat_scheda"}


def _motore():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar_motore.js"),
              encoding="utf-8") as f:
        return f.read()


def html_avatar(imp, canale=None, fumetto=True, mostra_nome=True):
    """
    La pagina dell'avatar. NON contiene i messaggi: così resta la stessa a ogni
    ricaricamento e Streamlit non la ricrea (niente scatti, niente attese).

    Le risposte le prende da sola: Quadro scrive l'ultima risposta in un
    elemento nascosto della pagina (vedi `_segnale`), con l'audio di Gemini se
    c'è, e questa pagina — che sta nello stesso sito — lo legge ogni 0,3
    secondi. Quando trova una risposta nuova la dice: con l'audio di Gemini e
    la bocca che segue la voce, oppure con la voce del dispositivo.

    `canale` distingue le due segretarie («scheda» e «angolo»): ognuna dice
    solo le risposte date a lei, così non parlano in due. Senza canale è
    un'anteprima ferma (in «Come la vuoi»).
    """
    op = dict(imp["avatar"], nome=imp["nome"], voce=imp.get("voce", ""),
              velocita=imp.get("velocita", 1), tono=imp.get("tono", 1.05))
    js = lambda v: json.dumps(v, ensure_ascii=False).replace("</", "<\\/")
    fondo = "transparent" if op["sfondo"] == "trasparente" else op["sfondo"]
    nome = html.escape(op["nome"])
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
<div id="scena"></div>{'<div id="nome">' + nome + '</div>' if mostra_nome else ''}
<div class="bt"><button id="ascolta" title="Ascolta di nuovo">🔊</button><button id="ferma" title="Basta così">⏹</button><button id="ciao" title="Saluta">👋</button></div>
<div id="fumetto"></div>
<script type="importmap">{json.dumps(IMPORTMAP)}</script>
<script type="module">
{_motore()}
const OP = {js(op)}, CANALE = {js(canale or "")}, FUMETTO = {js(bool(fumetto))}, ATTESA = {js(_ATTESA.get(canale or "", ""))};
const av = await creaAvatar(document.getElementById('scena'), OP);
const f = document.getElementById('fumetto'), bt = document.getElementById('ascolta');
const chiave = 'sg_detto_' + CANALE;
let ultimo = null, detto = '', pensava = false;
try {{ detto = sessionStorage.getItem(chiave) || ''; }} catch (e) {{}}

// la dice: prima con l'audio di Gemini, se non va con la voce del dispositivo
async function parlaUltimo() {{
  if (!ultimo || !ultimo.testo) return;
  bt.textContent = '🔊';
  av.stato(ultimo.umore || 'riposo');
  if (ultimo.audio) {{
    const esito = await av.parlaAudio(ultimo.audio);
    if (esito !== 'errore') return;          // 'fatto', oppure 'muto': aspetta un tocco
  }}
  av.parla(ultimo.testo);
}}

function leggi() {{
  if (!CANALE) return;
  let el = null;
  try {{
    const tutti = parent.document.querySelectorAll('.sg-voce[data-canale="' + CANALE + '"]');
    el = tutti[tutti.length - 1];
    // la rotellina dell'attesa vicino alla chat: lei «pensa»
    const pensa = ATTESA && parent.document.querySelector(ATTESA + ' [data-testid="stSpinner"]');
    if (pensa && !av.parlando) {{ av.stato('pensa'); pensava = true; }}
    else if (!pensa && pensava) {{ pensava = false; if (!av.parlando) av.stato('riposo'); }}
  }} catch (e) {{ return; }}
  if (!el || !el.dataset.id) return;
  const d = el.dataset;
  if (ultimo && ultimo.id === d.id) return;
  ultimo = {{ id: d.id, testo: d.testo || '', umore: d.umore || 'riposo',
             audio: d.audio ? 'data:' + (d.mime || 'audio/mpeg') + ';base64,' + d.audio : null }};
  if (FUMETTO && ultimo.testo) {{ f.textContent = ultimo.testo; f.style.display = 'block'; }}
  av.stato(ultimo.umore);
  // parla da sola solo per una risposta nuova, non quando la pagina si ricarica
  if (ultimo.id !== detto) {{
    detto = ultimo.id;
    try {{ sessionStorage.setItem(chiave, detto); }} catch (e) {{}}
    setTimeout(parlaUltimo, 120);
  }}
}}

bt.onclick = () => parlaUltimo();
document.getElementById('ferma').onclick = () => av.zitta();
document.getElementById('ciao').onclick = () => av.saluta();
document.getElementById('scena').addEventListener('avatar-clic', () => av.saluta());
document.addEventListener('avatar-muto', () => {{ bt.textContent = '🔊 Tocca per sentirla'; }});
window.__sg = {{ av, ultimo: () => ultimo }};   // per le prove automatiche
leggi();
setInterval(leggi, 300);
if (!ultimo) setTimeout(() => av.saluta(), 600);
</script>"""


def _segnale(canale, m, audio=None):
    """
    L'elemento nascosto da cui l'avatar del `canale` legge l'ultima risposta.
    Il testo arriva dall'AI: va «escapato», così resta testo e non diventa HTML.
    L'audio (bytes, tipo) c'è solo nel giro in cui è stato appena fatto: nei
    giri dopo non serve, l'avatar l'ha già preso, e non si rimanda ogni volta.
    """
    a = lambda v: html.escape(str(v or ""), quote=True)
    m = m or {}
    b64, mime = ("", "")
    if audio:
        b64, mime = base64.b64encode(audio[0]).decode("ascii"), audio[1]
    st.html(f'<div class="sg-voce" data-canale="{a(canale)}" data-id="{a(m.get("id"))}" '
            f'data-umore="{a(m.get("umore"))}" data-testo="{a(m.get("testo"))}" '
            f'data-mime="{a(mime)}" data-audio="{b64}" hidden></div>')


# ========================================================= la voce di Gemini ===
# Un'indicazione di stile davanti al testo: il modello della voce la usa per il
# tono e non la legge. È in inglese perché così la segue meglio.
STILE_VOCE = {
    "cordiale e diretta": "Say in a warm, friendly and natural Italian voice: ",
    "formale ed elegante": "Say in a composed, elegant Italian voice: ",
    "ironica e brillante": "Say in a bright, playful Italian voice, with a smile: ",
    "calma e rassicurante": "Say in a calm, soothing Italian voice, unhurried: ",
    "energica e motivante": "Say in an energetic, encouraging Italian voice: ",
}
VOCE_PREDEFINITA = "Sulafat"
MASSIMO_VOCE = 1200          # oltre, la risposta la legge la voce del dispositivo


def _pulisci_per_voce(testo):
    testo = re.sub(r"[*_#`>|]", "", str(testo or ""))
    testo = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", testo)   # via le emoji
    return re.sub(r"\s+", " ", testo).strip()


def voce_naturale(ctx, imp, testo, voce=None, forza=False):
    """
    L'audio di `testo` con la voce di Gemini: (bytes, tipo) oppure None.
    None vuol dire «parla con la voce del dispositivo», e succede quando: hai
    scelto la voce del dispositivo, manca la chiave, il testo è lungo, oppure
    Gemini ha detto no. Se il no è perché le voci di oggi sono finite (errore
    429) non si riprova fino a domani; per gli altri errori si aspettano 10 minuti.
    Una prova sola, senza attese: meglio la voce del dispositivo subito che
    quella di Gemini fra venti secondi.
    """
    if not ctx.chiave_ai or (not forza and imp.get("voce_motore", "gemini") != "gemini"):
        return None
    testo = _pulisci_per_voce(testo)
    if not testo or len(testo) > MASSIMO_VOCE:
        return None
    adesso = ctx.DIARIO.adesso()
    pausa = st.session_state.get("sg_voce_pausa")
    if pausa and not forza:
        giorno, motivo, quando, _ = pausa
        if (motivo == "quota" and giorno == adesso.date().isoformat()) or \
                (motivo != "quota" and (adesso - quando).total_seconds() < 600):
            return None
    import lettura as LT
    try:
        pcm = LT._tts(ctx.chiave_ai, STILE_VOCE.get(imp.get("carattere"), "") + testo,
                      voce or imp.get("voce_gemini") or VOCE_PREDEFINITA, attese=(0,), timeout=40)
    except Exception as e:
        motivo = "quota" if "429" in str(e) else "errore"
        st.session_state["sg_voce_pausa"] = (adesso.date().isoformat(), motivo, adesso, str(e)[:240])
        return None
    st.session_state.pop("sg_voce_pausa", None)
    giorno, n = st.session_state.get("sg_voci_usate", ("", 0))
    oggi = adesso.date().isoformat()
    st.session_state["sg_voci_usate"] = (oggi, (n if giorno == oggi else 0) + 1)
    try:
        return LT._mp3(pcm), "audio/mpeg"
    except Exception:                    # senza lameenc: WAV, più pesante ma va
        return LT._wav(pcm), "audio/wav"


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

    T = st.tabs(["💬 Parla", "📈 Come lavora", "⚙️ Come la vuoi", "🧠 Cosa sa di te", "✨ Aforismi",
                 "🔔 Notifiche e Telegram", "📲 Telefono e desktop"], key="sg_sezione")
    with T[0]:
        _parla(ctx, imp)
    with T[1]:
        _come_lavora(ctx, imp)
    with T[2]:
        _aspetto(ctx, imp)
    with T[3]:
        _conoscenza(ctx, imp)
    with T[4]:
        _aforismi(ctx)
    with T[5]:
        _notifiche(ctx)
    with T[6]:
        _dispositivi(ctx, imp)


# ===================================================== la conversazione =====
# La stessa conversazione (st.session_state["sg_chat"]) si vede in due posti:
# qui nella scheda, in grande, e nell'angolo, in piccolo. Ogni risposta ricorda
# da dove è partita la domanda («canale»): la dice ad alta voce solo l'avatar
# di quel posto.
def _ultima(canale):
    return next((m for m in reversed(st.session_state.get("sg_chat", []))
                 if m["ruolo"] == "lei" and m.get("canale", "scheda") == canale), None)


def _messaggio(m, ctx=None, p="", canale="", vt=None):
    """Un messaggio della chat. Sotto le risposte di lei, 👍/👎 (e il perché, se 👎)."""
    with st.chat_message("user" if m["ruolo"] == "io" else "assistant",
                         avatar="🧑" if m["ruolo"] == "io" else "👩‍💼"):
        st.markdown(m["testo"])
        if ctx is None or m["ruolo"] != "lei" or not m.get("id"):
            return
        chiave = f"{p}_voto_{m['id']}"
        prima = (vt or {}).get(m["id"], (None, ""))[0]           # il voto già salvato, se c'è
        st.feedback("thumbs", key=chiave, on_change=_vota, args=(ctx, chiave, m["id"], canale),
                    default=None if prima is None else (1 if prima > 0 else 0))
        if st.session_state.get(chiave) == 0:
            st.text_input("Cosa non andava? (facoltativo, lo terrà a mente)", key=chiave + "_nota",
                          on_change=_vota, args=(ctx, chiave, m["id"], canale),
                          placeholder="es. troppo lunga, ha inventato una data, tono sbagliato")


def _domanda(ctx, valore, box):
    """Il testo della domanda: quello scritto, o la registrazione trascritta."""
    if isinstance(valore, str):
        return valore.strip()
    testo = (valore.get("text") or "").strip()
    audio = valore.get("audio")
    if audio is not None:
        with box:
            try:
                with st.spinner("Ascolto…"):
                    detto = ctx.VOCE.trascrivi_audio(audio.getvalue(), ctx.chiave_ai, ctx.modello_ai,
                                                     getattr(audio, "type", None) or "audio/wav")
                testo = (testo + " " + (detto or "")).strip()
            except Exception as e:
                st.error(f"Non ho capito l'audio: {e}")
    return testo


def _decisione(ctx, a, canale, decisione):
    return ctx.DIARIO.riga("sg_azione", a["tipo"], decisione, 0, None,
                           json.dumps({"testo": str(a.get("testo", ""))[:200], "canale": canale},
                                      ensure_ascii=False))


def _fai(ctx, a, canale):
    # Tutto in una scrittura sola (l'azione e il fatto che l'hai confermata):
    # ogni scrittura nel diario su Drive costa un paio di secondi.
    righe = []
    vicino = types.SimpleNamespace(**vars(ctx))
    vicino.diario_scrivi = lambda r: righe.extend(r if isinstance(r, list) else [r])
    messaggio = esegui(vicino, a)
    if a["tipo"] != "apri":            # portarti in una scheda non è un'azione da registrare
        righe.append(_decisione(ctx, a, canale, "fatta"))
    if righe:
        ctx.diario_scrivi(righe)
    ctx.conferma(messaggio)
    st.session_state.setdefault("sg_azioni_fatte", {})[a["id"]] = True
    st.session_state["sg_da_sincronizzare"] = True
    st.rerun()                 # tutto Quadro: la priorità, la scadenza… si vedono subito


def _no(ctx, a, canale):
    st.session_state.setdefault("sg_azioni_fatte", {})[a["id"]] = False
    try:
        ctx.diario_scrivi(_decisione(ctx, a, canale, "rifiutata"))
    except Exception:
        pass


def _azioni(ctx, canale, p):
    """Le azioni proposte nell'ultima risposta di questo canale, da confermare."""
    ultimo = _ultima(canale)
    if not ultimo or not ultimo.get("azioni"):
        return
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
            b1.button("✅ Fai", key=f"{p}_si_{a['id']}", type="primary", width='stretch',
                      on_click=_fai, args=(ctx, a, canale))
            b2.button("✖️ No", key=f"{p}_no_{a['id']}", width='stretch', on_click=_no, args=(ctx, a, canale))


def _chat(ctx, imp, canale, altezza):
    """Messaggi, azioni da confermare, voce e casella per scrivere o parlare."""
    p = "sg" if canale == "scheda" else "sga"
    storia = st.session_state.setdefault("sg_chat", [])
    if not ctx.chiave_ai:
        st.error("Per parlarle serve la chiave di Google AI Studio nei Secrets.")
        with st.container(key=f"sg_dato_{canale}"):
            _segnale(canale, None)
        return
    box = st.container(height=altezza, autoscroll=True, key=f"sg_chat_{canale}")
    with box:
        if not storia:
            st.caption("Scrivile, o tocca 🎙️ e parlale. Per esempio: «Cosa ho di importante "
                       "oggi?», «Ricordati che il GAL risponde a fine mese», «Aggiungi la "
                       "scadenza dell'IVA il 16», «Preparami la giornata».")
        vt = voti(ctx.DIA)
        for m in storia[-30:]:
            _messaggio(m, ctx, p, canale, vt)
    posto_azioni = st.container()
    posto_voce = st.container(key=f"sg_dato_{canale}")
    valore = st.chat_input(f"Scrivi o parla a {imp['nome']}…", key=f"{p}_scrivi",
                           accept_audio=True, submit_mode="disable")
    scambio = None                         # (domanda, secondi, errore) da mettere nel registro
    if valore:
        domanda = _domanda(ctx, valore, box)
        if domanda:
            with box:
                _messaggio({"ruolo": "io", "testo": domanda})
                inizio = time.time()
                try:
                    with st.spinner(f"{imp['nome']} ci pensa…"):
                        rispondi(ctx, imp, domanda, canale)
                    scambio = (domanda, time.time() - inizio, "")
                    _messaggio(storia[-1], ctx, p, canale)
                except Exception as e:
                    errore = getattr(e, "messaggio", None) or str(e)
                    scambio = (domanda, time.time() - inizio, errore)
                    st.error(errore)
    with posto_azioni:
        _azioni(ctx, canale, p)
    # la voce: si prepara una volta sola per risposta, appena arrivata
    m = _ultima(canale)
    audio = None
    if m and not m.get("voce_fatta"):
        m["voce_fatta"] = True
        if imp.get("voce_motore", "gemini") == "gemini":
            with box:
                with st.spinner("🎙️ …"):
                    audio = voce_naturale(ctx, imp, m["testo"])
    with posto_voce:
        _segnale(canale, m, audio)
    # nel registro dopo la voce: la scrittura su Drive non fa aspettare la risposta
    if scambio:
        voce = "gemini" if audio else "dispositivo"
        _registra_scambio(ctx, imp, canale, scambio[0], None if scambio[2] else m,
                          scambio[1], voce, scambio[2])
    return storia


def _parla(ctx, imp):
    sinistra, destra = st.columns([2, 3])
    with sinistra:
        ctx.pagina_html(html_avatar(imp, "scheda"), 430)
    with destra:
        _, arrivate = posta(ctx) if ctx.SA else (None, [])
        if arrivate:
            st.info(f"📥 {len(arrivate)} cose arrivate da Telegram o dal desktop: le trovi in "
                    "«Notifiche e Telegram».")
        storia = _chat(ctx, imp, "scheda", 330)
        if storia and st.button("🧹 Nuova conversazione", key="sg_pulisci"):
            st.session_state["sg_chat"] = []
            st.rerun()


# ================================================== la segretaria nell'angolo ===
MODI_ANGOLO = {"automatico": "aperta sul computer, chiusa sul telefono",
               "aperta": "sempre aperta quando apri Quadro",
               "chiusa": "chiusa: un tocco sul suo nome la apre",
               "nascosta": "non mostrarla nell'angolo"}


def _da_telefono():
    try:
        ua = st.context.headers.get("User-Agent", "") or ""
    except Exception:
        return False
    return bool(re.search(r"Android|iPhone|iPad|Mobile", ua))


def _css(imp, angolo_visibile):
    lato = "left" if imp.get("lato") == "sinistra" else "right"
    nascondi = """
[data-testid="stLayoutWrapper"]:has(> .st-key-sg_dato_angolo),
[data-testid="stLayoutWrapper"]:has(> .st-key-sg_dato_scheda),
[data-testid="stLayoutWrapper"]:has(> .st-key-gd_naviga),
.st-key-sg_dato_angolo, .st-key-sg_dato_scheda, .st-key-gd_naviga { display: none !important; }"""
    if not angolo_visibile:
        st.html(f"<style>{nascondi}</style>")
        return
    st.html(f"""<style>{nascondi}
/* bottom 70px: in basso a destra Streamlit Cloud mette il suo pulsante «Manage app»,
   che sta sopra la pagina e prenderebbe i clic al posto di lei */
.st-key-sg_angolo {{ position: fixed; {lato}: 14px; bottom: 70px; z-index: 999000;
  width: auto !important; max-width: calc(100vw - 28px); }}
/* nella scheda «Parla» c'è già lei in grande: l'angolo si fa da parte. Le schede
   non aperte restano nella pagina ma «inert»: conta solo se la si vede davvero */
.stApp:has(.st-key-sg_dato_scheda):not(:has([inert] .st-key-sg_dato_scheda)) .st-key-sg_angolo {{
  display: none !important; }}
.st-key-sg_pannello {{ width: min(370px, calc(100vw - 28px)); max-height: calc(100vh - 150px);
  overflow-y: auto; background: Canvas; border: 1px solid rgba(27,175,122,.45);
  border-radius: 18px; box-shadow: 0 14px 36px rgba(0,0,0,.28); padding: 8px 10px 10px; }}
.st-key-sg_pannello iframe {{ border-radius: 12px; }}
/* la riga col nome e ➖ resta in alto anche quando il riquadro scorre */
[data-testid="stLayoutWrapper"]:has(> .st-key-sga_testa) {{ position: sticky; top: -8px; z-index: 5;
  background: Canvas; padding-top: 4px; }}
.st-key-sga_apri button {{ border-radius: 999px; background: #0f5d47; color: #fff; border: none;
  box-shadow: 0 8px 24px rgba(0,0,0,.30); padding: 10px 18px; font-weight: 600; }}
.st-key-sga_apri button:hover {{ background: #1baf7a; color: #fff; }}
</style>""")


def angolo(ctx):
    """
    La segretaria in un angolo dello schermo, su tutte le schede di Quadro.
    app.py la chiama dentro un contenitore che sta fuori dalle schede; il CSS
    qui sopra la tiene ferma in basso. Si rimpicciolisce a un bottone con il
    suo nome, e il pezzo che si ricarica è solo il suo (un «fragment»): quando
    le scrivi, il resto di Quadro non si ricarica.
    """
    imp = impostazioni(ctx)
    modo = imp.get("angolo", "automatico")
    _css(imp, modo != "nascosta")
    if modo == "nascosta":
        return
    if "sg_angolo_aperta" not in st.session_state:
        st.session_state["sg_angolo_aperta"] = (modo == "aperta" or
                                                (modo == "automatico" and not _da_telefono()))
    _angolo(ctx)


def _apri_angolo(aperta):
    st.session_state["sg_angolo_aperta"] = aperta


@st.fragment
def _angolo(ctx):
    # se qualcosa va storto, l'errore si vede qui dentro e il resto di Quadro va avanti
    try:
        _angolo_dentro(ctx)
    except Exception as e:
        st.error(f"La segretaria nell'angolo ha avuto un problema: {e}")
        st.button("➖ Chiudi", key="sga_chiudi_errore", on_click=_apri_angolo, args=(False,))


def _angolo_dentro(ctx):
    imp = impostazioni(ctx)
    if not st.session_state.get("sg_angolo_aperta"):
        st.button(f"👩‍💼 {imp['nome']}", key="sga_apri", on_click=_apri_angolo, args=(True,),
                  help=f"Apri {imp['nome']}")
        return
    with st.container(key="sg_pannello"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="sga_testa"):
            st.markdown(f"**👩‍💼 {imp['nome']}**", width="stretch")
            st.button("➖", key="sga_chiudi", on_click=_apri_angolo, args=(False,),
                      help="Rimpicciolisci", width="content", type="tertiary")
        ctx.pagina_html(html_avatar(imp, "angolo", fumetto=False, mostra_nome=False), 170)
        _chat(ctx, imp, "angolo", 220)


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
        st.markdown("**La voce**")
        motori = {"gemini": "🎙️ Naturale, di Gemini: la bocca segue la voce",
                  "dispositivo": "📱 Del dispositivo: sempre gratis, senza limiti"}
        motore = st.radio("Quale voce", list(motori), format_func=motori.get, horizontal=True,
                          index=0 if imp.get("voce_motore", "gemini") == "gemini" else 1,
                          label_visibility="collapsed")
        import lettura as LT
        voci = list(LT.VOCI_GEMINI)
        attuale = imp.get("voce_gemini") or VOCE_PREDEFINITA
        voce_g = st.selectbox("Voce di Gemini", voci, index=voci.index(attuale) if attuale in voci else 0,
                              format_func=lambda v: f"{v} — {LT.VOCI_GEMINI[v]}",
                              help="Le provi qui sotto, fuori dal riquadro, prima di scegliere.")
        st.caption("La voce del dispositivo fa da riserva quando quelle di Gemini del giorno "
                   "sono finite. Per lei valgono questi tre:")
        v1, v2, v3 = st.columns(3)
        voce = v1.text_input("Nome della voce del dispositivo", imp.get("voce", ""),
                             help="Vuoto = la prima voce italiana femminile del dispositivo. I nomi "
                                  "li vedi nel lettore di 📚 Studio → «Leggimelo».")
        vel = v2.slider("Velocità", 0.6, 1.6, float(imp.get("velocita", 1.0)), 0.05)
        tono = v3.slider("Tono", 0.6, 1.6, float(imp.get("tono", 1.05)), 0.05)
        st.markdown("**Nell'angolo di Quadro**")
        a1, a2 = st.columns([3, 1])
        modi = list(MODI_ANGOLO)
        modo = a1.selectbox("Come la trovi quando apri Quadro", modi, format_func=MODI_ANGOLO.get,
                            index=modi.index(imp.get("angolo", "automatico"))
                            if imp.get("angolo", "automatico") in modi else 0)
        lato = a2.radio("Lato", ["destra", "sinistra"], horizontal=True,
                        index=1 if imp.get("lato") == "sinistra" else 0)
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
            # si parte dalle impostazioni di prima, così non si perde niente
            # che in questo riquadro non c'è
            nuove = dict(imp)
            nuove.update({"nome": nome.strip() or "Sofia", "chiamami": chiamami.strip() or "Claudio",
                     "carattere": car, "carattere_extra": extra, "risposte_brevi": brevi,
                     "voce": voce.strip(), "velocita": vel, "tono": tono,
                     "voce_motore": motore, "voce_gemini": voce_g, "angolo": modo, "lato": lato,
                     "avatar": {"pelle": pelle, "capelli": capelli, "occhi": occhi, "giacca": giacca,
                                "camicia": camicia, "labbra": labbra, "acconciatura": acconciatura,
                                "inquadratura": inquadratura, "occhiali": occhiali, "orecchini": orecchini,
                                "sfondo": "trasparente" if sf == "trasparente" else colore_sf,
                                "vrm": vrm.strip()}})
            _salva_impostazione(ctx, "segretaria", nuove)
            st.session_state["sg_da_sincronizzare"] = True
            st.session_state.pop("sg_angolo_aperta", None)     # vale subito il modo nuovo
            ctx.conferma("Segretaria aggiornata")
            st.rerun()
    _prova_voci(ctx, imp)
    st.markdown("**Com'è adesso**")
    ctx.pagina_html(html_avatar(imp, None), 380)


def _prova_voci(ctx, imp):
    import lettura as LT
    with st.expander("🎧 Prova le voci di Gemini"):
        giorno, n = st.session_state.get("sg_voci_usate", ("", 0))
        oggi = ctx.DIARIO.oggi().isoformat()
        st.caption("Ogni prova, come ogni risposta detta con la voce di Gemini, usa una delle "
                   "chiamate di voce del giorno. Nel piano gratuito sono poche (una decina, a "
                   "fine 2026) e le usa anche «Leggimelo» per i file audio: il numero esatto "
                   "per la tua chiave lo vedi su aistudio.google.com/rate-limit. Finite quelle, "
                   f"{imp['nome']} parla con la voce del dispositivo fino a domani.")
        if giorno == oggi and n:
            st.caption(f"Da questo dispositivo, oggi: {n} risposte con la voce di Gemini.")
        pausa = st.session_state.get("sg_voce_pausa")
        if pausa:
            st.warning(("Per oggi le voci di Gemini sono finite: torna domani."
                        if pausa[1] == "quota" else "L'ultima prova con Gemini non è andata: ")
                       + ("" if pausa[1] == "quota" else pausa[3]))
        voci = list(LT.VOCI_GEMINI)
        c1, c2 = st.columns([3, 1])
        attuale = imp.get("voce_gemini") or VOCE_PREDEFINITA
        scelta = c1.selectbox("Voce da provare", voci, index=voci.index(attuale) if attuale in voci else 0,
                              format_func=lambda v: f"{v} — {LT.VOCI_GEMINI[v]}", key="sg_prova_voce")
        if c2.button("▶️ Prova", key="sg_prova_bt", width="stretch"):
            with st.spinner("Preparo la voce…"):
                st.session_state["sg_prova_audio"] = voce_naturale(
                    ctx, imp, f"Ciao {imp['chiamami']}, sono {imp['nome']}. Quando vuoi, "
                              "ti preparo la giornata.", voce=scelta, forza=True)
            if not st.session_state["sg_prova_audio"]:
                st.error("Gemini non ha dato la voce. " + (st.session_state.get("sg_voce_pausa") or ("", "", "", ""))[3])
        if st.session_state.get("sg_prova_audio"):
            dati, tipo = st.session_state["sg_prova_audio"]
            st.audio(dati, format=tipo)
            st.caption("Se ti piace, sceglila nel riquadro sopra e premi «Salva».")


def _aforismi(ctx):
    import aforismi as AF
    st.caption("Quello del momento sta in cima alla 🧭 Scrivania e cambia da solo. Qui scegli "
               "come li vuoi e tieni la tua raccolta, con voti e note: la segretaria conosce "
               "quelli che ami e ne tiene conto quando ti parla.")
    AF.riquadro(ctx, "sg_af")
    with st.expander("🎛️ Come li vuoi: argomenti, autori, tono, ogni quanto"):
        AF.preferenze(ctx)
    st.divider()
    AF.mostra_raccolta(ctx)


# ======================================================== 📈 come lavora =====
CANALI = {"angolo": "🧭 Quadro, nell'angolo", "scheda": "👩‍💼 Quadro, scheda Parla",
          "telegram": "📨 Telegram", "desktop": "💻 Desktop"}


def _revisione_prompt(imp, reg, az):
    righe = []
    for _, r in reg.tail(40).iterrows():
        voto = {1: "👍", -1: "👎"}.get(r["voto"], "")
        righe.append(f"- [{r['canale']}] D: {r['domanda'][:200]} | R: {r['risposta'][:300]} | "
                     f"{voto} {r['commento'] or ''} | azioni: {r['azioni'] or '-'} | {r['esito']}")
    acc = az["decisione"].value_counts().to_dict() if not az.empty else {}
    return (f"Sei un revisore esigente ma giusto. Qui sotto ci sono le ultime conversazioni fra "
            f"{imp['chiamami']} e la sua segretaria virtuale {imp['nome']} (carattere: {imp['carattere']}), "
            f"con i voti che lui ha dato. Azioni proposte e decise: {json.dumps(acc, ensure_ascii=False)}.\n\n"
            + "\n".join(righe) +
            "\n\nScrivi in italiano, in markdown, breve e concreto, con questi titoli:\n"
            "### Cosa fa bene\n### Dove sbaglia o delude (con esempi presi da sopra)\n"
            "### Cosa cambiare\nNell'ultima parte proponi frasi pronte da aggiungere al suo profilo "
            "«chi sono» o ai suoi ricordi, e se serve un ritocco al carattere. Non inventare dati "
            "che non vedi sopra.")


def _come_lavora(ctx, imp):
    st.markdown("##### 📈 Come lavora la tua segretaria")
    st.caption("Ogni domanda e risposta finisce nel registro (nel diario): da dove le hai scritto, "
               "quanto ci ha messo, le azioni che ha proposto e cosa hai deciso tu, la voce usata e "
               "i tuoi 👍/👎. I 👎 con il perché diventano «lezioni» che rilegge ogni volta.")
    # Telegram e desktop: le chiacchierate arrivano nella posta; finché non le
    # archivi stanno lì (la posta tiene le ultime 500 voci), ma si contano lo stesso
    _, da_posta = posta(ctx, scambi=True) if ctx.SA else (None, [])
    reg = registro(ctx.DIA, da_posta)
    az = azioni_decise(ctx.DIA)

    c1, c2 = st.columns([3, 2])
    giorni = c1.radio("Periodo", [7, 30, 90, 365], index=1, horizontal=True, key="sg_mon_giorni",
                      format_func=lambda g: {7: "7 giorni", 30: "30 giorni", 90: "3 mesi", 365: "un anno"}[g])
    if da_posta and c2.button(f"📥 Archivia nel diario {len(da_posta)} chiacchierate da Telegram/desktop",
                              key="sg_mon_archivia", width="stretch"):
        ctx.conferma(f"Archiviate {importa(ctx, da_posta)} chiacchierate")
        st.session_state["sg_posta_segno"] = st.session_state.get("sg_posta_segno", 0) + 1
        st.rerun()

    if reg.empty:
        st.info("Ancora nessuna conversazione nel registro. Parlale un po' (dall'angolo, dalla "
                "scheda Parla, da Telegram o dal desktop) e torna qui.")
    else:
        dal = pd.Timestamp(ctx.DIARIO.oggi()) - pd.Timedelta(days=giorni - 1)
        r = reg[reg["quando"] >= dal]
        a = az[az["quando"] >= dal] if not az.empty else az
        n = len(r)
        votate = r["voto"].notna().sum()
        su = int((r["voto"] > 0).sum())
        proposte = int(r["azioni"].fillna("").str.len().gt(0).sum())
        fatte = int((a["decisione"] == "fatta").sum()) if not a.empty else 0
        rifiutate = int((a["decisione"] == "rifiutata").sum()) if not a.empty else 0
        quadro = r[r["canale"].isin(["angolo", "scheda"])]
        k = st.columns(5)
        k[0].metric("Conversazioni", n, help="Una domanda con la sua risposta")
        k[1].metric("Gradimento", f"{su / votate:.0%}" if votate else "—",
                    help=f"Sulle {votate} risposte che hai votato")
        k[2].metric("Azioni accettate", f"{fatte / (fatte + rifiutate):.0%}" if fatte + rifiutate else "—",
                    help=f"{fatte} fatte, {rifiutate} rifiutate, su {proposte} risposte con proposte")
        tempi = quadro["secondi"].dropna()
        k[3].metric("Risponde in", f"{tempi.median():.1f} s" if len(tempi) else "—",
                    help="Il valore tipico (mediana) delle risposte da Quadro")
        k[4].metric("Errori", int((r["esito"] == "errore").sum()))

        if n:
            import plotly.express as px
            per_giorno = (r.assign(giorno=r["quando"].dt.normalize(), dove=r["canale"].map(lambda c: CANALI.get(c, c)))
                          .groupby(["giorno", "dove"]).size().reset_index(name="conversazioni"))
            graf = px.bar(per_giorno, x="giorno", y="conversazioni", color="dove", height=240,
                          labels={"giorno": "", "dove": ""})
            graf.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.25),
                               xaxis=dict(tickformat="%d/%m"))
            st.plotly_chart(graf, width="stretch", key="sg_mon_grafico")
            v1, v2 = st.columns(2)
            with v1:
                st.markdown("**Da dove le parli**")
                st.dataframe(r["canale"].map(lambda c: CANALI.get(c, c)).value_counts().rename("conversazioni"),
                             width="stretch")
            with v2:
                st.markdown("**La voce delle risposte (da Quadro)**")
                if len(quadro):
                    st.dataframe(quadro["voce"].replace({"gemini": "🎙️ Gemini", "dispositivo": "📱 dispositivo"})
                                 .value_counts().rename("risposte"), width="stretch")
                    st.caption("«dispositivo» vuol dire anche: voci di Gemini del giorno finite.")
            if not a.empty:
                st.markdown("**Le azioni che ha proposto, e cosa hai deciso**")
                st.dataframe(a.pivot_table(index="tipo", columns="decisione", values="quando",
                                           aggfunc="count", fill_value=0), width="stretch")

        st.markdown("##### 👎 Da rivedere")
        neg = reg[reg["voto"] < 0].tail(15)
        if neg.empty:
            st.caption("Nessuna risposta bocciata. Quando una non ti piace, premi 👎 sotto la risposta "
                       "e scrivi il perché: lei lo legge e non lo rifà.")
        for _, x in neg.iloc[::-1].iterrows():
            with st.container(border=True):
                st.caption(f"{x['quando']:%d/%m %H:%M} · {CANALI.get(x['canale'], x['canale'])}")
                st.text(f"Tu: {x['domanda']}\n{imp['nome']}: {x['risposta']}")
                if x["commento"]:
                    st.caption(f"Perché: {x['commento']}")

        st.markdown("##### 🗂️ Tutte le conversazioni")
        f1, f2 = st.columns(2)
        dove = f1.multiselect("Da dove", list(CANALI), format_func=CANALI.get, key="sg_mon_dove",
                              placeholder="tutti")
        quali = f2.radio("Quali", ["tutte", "votate 👍", "votate 👎", "non votate", "con errori"],
                         horizontal=True, key="sg_mon_quali")
        t = reg.copy()
        if dove:
            t = t[t["canale"].isin(dove)]
        t = {"votate 👍": t[t["voto"] > 0], "votate 👎": t[t["voto"] < 0],
             "non votate": t[t["voto"].isna()], "con errori": t[t["esito"] == "errore"]}.get(quali, t)
        st.dataframe(t.iloc[::-1].drop(columns=["id"]), width="stretch", hide_index=True, height=300,
                     column_config={"quando": st.column_config.DatetimeColumn("Quando", format="DD/MM HH:mm"),
                                    "secondi": st.column_config.NumberColumn("Secondi", format="%.1f"),
                                    "voto": st.column_config.NumberColumn("Voto", help="1 = 👍, -1 = 👎")})
        st.download_button("⬇️ Scarica il registro (CSV, si apre con Excel)",
                           t.to_csv(index=False, sep=";").encode("utf-8-sig"), "registro_segretaria.csv",
                           "text/csv", key="sg_mon_csv")

        # votare anche le chiacchierate di Telegram e del desktop, a posteriori
        da_votare = reg[reg["voto"].isna() & reg["canale"].isin(["telegram", "desktop"])].tail(8)
        if not da_votare.empty:
            with st.expander(f"⭐ Vota le ultime chiacchierate di Telegram e del desktop ({len(da_votare)})"):
                for _, x in da_votare.iloc[::-1].iterrows():
                    st.text(f"{x['quando']:%d/%m %H:%M} · Tu: {x['domanda'][:200]}\n{imp['nome']}: {x['risposta'][:400]}")
                    chiave = f"sgm_voto_{x['id']}"
                    st.feedback("thumbs", key=chiave, on_change=_vota, args=(ctx, chiave, x["id"], x["canale"]))
                    if st.session_state.get(chiave) == 0:
                        st.text_input("Cosa non andava?", key=chiave + "_nota", on_change=_vota,
                                      args=(ctx, chiave, x["id"], x["canale"]))
                    st.divider()

        st.markdown("##### 🧐 Una revisione fatta dall'AI")
        st.caption("Legge le ultime 40 conversazioni con i tuoi voti e ti dice cosa va, cosa no e cosa "
                   "cambiare nel profilo, nei ricordi o nel carattere. Usa una chiamata all'AI.")
        if st.button("🧐 Fammi la revisione", key="sg_mon_rev", disabled=not ctx.chiave_ai):
            with st.spinner("Rileggo le conversazioni…"):
                try:
                    st.session_state["sg_mon_testo"] = ctx.AI.chiedi(_revisione_prompt(imp, reg, az),
                                                                     ctx.chiave_ai, ctx.modello_ai)
                except Exception as e:
                    st.error(getattr(e, "messaggio", None) or str(e))
        if st.session_state.get("sg_mon_testo"):
            with st.container(border=True):
                st.markdown(st.session_state["sg_mon_testo"])

    lez = lezioni(ctx.DIA)
    if lez:
        with st.expander(f"🧠 Le sue lezioni ({len(lez)}): le rilegge prima di risponderti"):
            for x in lez:
                st.markdown(f"- {x}")
    st.markdown("##### ⚙️ Il registro")

    def _salva_registro():
        _salva_impostazione(ctx, "segretaria", dict(impostazioni(ctx),
                                                    registro=st.session_state["sg_reg_on"],
                                                    registro_testi=st.session_state["sg_reg_testi"]))
    r1, r2 = st.columns(2)
    r1.toggle("Tieni il registro delle conversazioni", imp.get("registro", True), key="sg_reg_on",
              on_change=_salva_registro)
    r2.toggle("Salva anche il testo di domande e risposte", imp.get("registro_testi", True),
              key="sg_reg_testi", on_change=_salva_registro,
              help="Spento, restano solo i numeri: quando, quanto ci ha messo, azioni, voti.")


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
Quello che le dici con i comandi arriva qui, in «Arrivate da Telegram». Le chiacchierate
finiscono nel registro di «📈 Come lavora», dove le puoi anche votare.

**Aggiornare lo script** (quando ti mando una versione nuova): su script.google.com apri il
progetto, seleziona tutto il codice, incolla quello nuovo e premi 💾 Salva. Le chiavi restano;
non serve rifare `configura`.

**Costi:** zero. Google Apps Script è gratuito e lo script controlla i messaggi una volta
al minuto, ben dentro i limiti gratuiti.
"""

GUIDA_TELEFONO = """
- **Quadro e la segretaria come icona.** Apri Quadro in Chrome sul telefono, poi ⋮ →
  **Aggiungi a schermata Home**. Fallo due volte: una con l'indirizzo normale e una con
  `?pagina=segretaria` in fondo all'indirizzo, che apre direttamente lei (con
  `?pagina=leggimelo` apri invece il lettore, per farti leggere una pagina al volo). Si apre a tutto
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
