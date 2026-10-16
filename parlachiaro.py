"""
parlachiaro.py — il motore di ParlaChiaro, portato dal JavaScript al Python.

Qui dentro non c'è niente di grafico: solo i conti. L'analisi di un intervento
è la stessa dell'originale, regola per regola, così i punteggi vecchi e quelli
nuovi sono confrontabili.

Come funziona il punteggio (indice di efficacia, da 0 a 100):
  si parte da 40 e poi
    +8   se l'intervento supera le 25 parole (sotto non c'è niente da misurare)
    +12  se il ritmo sta fra 105 e 155 parole al minuto
    +10  se le frasi sono mediamente fra 6 e 20 parole
    +3   per ogni parola manageriale usata, fino a +15
    +7   se apri dichiarando il punto
    +8   se chiudi con una proposta
    -3   per ogni riempitivo («praticamente», «diciamo»…)
    -6   per ogni possibile errore di grammatica
  e il risultato si taglia fra 0 e 100.

I pesi sono quelli dell'originale. Se un giorno vuoi cambiarli, sono tutti
nella funzione `analizza`, scritti uno per riga apposta.

UNA DIFFERENZA VOLUTA rispetto alla versione in JavaScript. Là i controlli
sugli accenti non scattavano mai: «qual'è», «un pò» e «xchè» finiscono con
una lettera accentata, e il confine di parola del JavaScript considera le
lettere accentate come se non fossero lettere, quindi la ricerca non trovava
niente. Risultato: l'analisi non segnalava proprio gli errori che le carte
numero 8 e 9 insegnano a non fare. In Python il confine di parola funziona
anche con le accentate, quindi adesso quegli errori si vedono. Conseguenza
pratica: su un testo che contiene «qual'è» o «un pò» il punteggio esce più
basso di prima. Non è un peggioramento, è la misura che prima mancava.
"""

import base64
import re
import time

import requests


def _carica(cfg):
    """Compila una volta sola le espressioni di ricerca: sono tante."""
    compilati = {}
    for nome, regole in cfg.get("controlli_grammatica", {}).items():
        compilati[nome] = [re.compile(r, re.IGNORECASE) for r in regole]
    return compilati


def conta_riempitivi(testo_minuscolo, riempitivi):
    """
    Conta i riempitivi come parole intere. Il confine non può essere \\b
    perché le lettere accentate lo mandano in confusione: si guarda che
    prima e dopo non ci sia una lettera italiana.
    """
    trovati = []
    for f in riempitivi:
        schema = r"(?:^|[^a-zàèéìòù])" + f.replace(" ", r"\s+") + r"(?=$|[^a-zàèéìòù])"
        n = len(re.findall(schema, testo_minuscolo))
        if n:
            trovati.append((f, n))
    return trovati


def analizza(testo, secondi, cfg):
    """Restituisce un dizionario con tutte le misure e i consigli."""
    pulito = (testo or "").strip()
    parole = pulito.split() if pulito else []
    minuscolo = pulito.lower()
    frasi = [f for f in re.split(r"[.!?]+", pulito) if f.strip()]

    wpm = round(len(parole) / secondi * 60) if secondi > 4 else 0
    media_frase = round(len(parole) / len(frasi)) if frasi else 0

    lista_riemp = conta_riempitivi(minuscolo, cfg.get("riempitivi", []))
    riempitivi = sum(n for _, n in lista_riemp)

    manageriali = sum(1 for k in cfg.get("parole_manageriali", [])
                      if k in minuscolo)

    controlli = _carica(cfg)
    grammatica = {nome: sum(len(r.findall(pulito)) for r in regole)
                  for nome, regole in controlli.items()}
    errori_gram = sum(grammatica.values())

    apertura = 100 if re.search(cfg.get("apertura", "$^"), pulito, re.I) else 0
    chiusura = 100 if re.search(cfg.get("chiusura", "$^"), pulito, re.I) else 0

    sintesi = 0 if not media_frase else (100 if media_frase <= 20
                                         else 65 if media_frase <= 25 else 35)
    scorrevolezza = 0 if not wpm else (100 if 110 <= wpm <= 150
                                       else 70 if 95 <= wpm <= 165 else 40)

    punteggio = 40
    punteggio += 8 if len(parole) >= 25 else 0
    punteggio += 12 if 105 <= wpm <= 155 else 0
    punteggio += 10 if 6 <= media_frase <= 20 else 0
    punteggio += min(15, manageriali * 3)
    punteggio += 7 if apertura else 0
    punteggio += 8 if chiusura else 0
    punteggio -= riempitivi * 3
    punteggio -= errori_gram * 6
    punteggio = max(0, min(100, round(punteggio)))

    consigli = []
    for nome, n in grammatica.items():
        if n:
            consigli.append(("errore", f"Grammatica · {nome}: {n} possibile errore. "
                                       f"Ripassa la carta nella sezione Grammatica."))
    if riempitivi:
        elenco = ", ".join(f"«{f}» ×{n}" for f, n in lista_riemp)
        consigli.append(("", f"Riempitivi: {elenco}. Sostituiscili con una pausa."))
    if wpm > 155:
        consigli.append(("", f"Velocità {wpm} parole/min: rallenta verso 115–145 e "
                             f"fai una pausa dopo ogni dato."))
    if wpm and wpm < 95 and len(parole) > 15:
        consigli.append(("", f"Velocità {wpm} parole/min: prepara tre parole chiave "
                             f"e non cercare la frase perfetta."))
    if media_frase > 22:
        consigli.append(("", f"Frasi lunghe (media {media_frase} parole): una frase "
                             f"per ogni concetto."))
    if not apertura and len(parole) > 15:
        consigli.append(("", "Apri dichiarando il punto: «Il punto centrale è…»."))
    if not chiusura and len(parole) > 15:
        consigli.append(("", "Chiudi con una proposta: «La mia raccomandazione è…» "
                             "e indica la decisione richiesta."))
    if manageriali < 3 and len(parole) > 15:
        consigli.append(("", "Rafforza il registro manageriale: dato, impatto, "
                             "opzioni, raccomandazione, decisione."))

    migliorato = pulito
    for schema, sostituto in cfg.get("sostituzioni", []):
        migliorato = re.sub(schema, sostituto, migliorato, flags=re.IGNORECASE)
    if migliorato != pulito:
        consigli.append(("ok", f"Versione più professionale: «{migliorato}»"))

    if not consigli and len(parole) > 10:
        consigli.append(("ok", "Intervento ben impostato. Ripetilo riducendolo "
                               "del 20%."))

    return {"parole": len(parole), "wpm": wpm, "media_frase": media_frase,
            "riempitivi": riempitivi, "lista_riempitivi": lista_riemp,
            "manageriali": manageriali, "grammatica": grammatica,
            "errori_grammatica": errori_gram,
            "apertura": apertura, "chiusura": chiusura,
            "sintesi": sintesi, "scorrevolezza": scorrevolezza,
            "punteggio": punteggio, "consigli": consigli,
            "migliorato": migliorato if migliorato != pulito else ""}


def radar(ris):
    """Le cinque misure del grafico a ragnatela, tutte sulla stessa scala."""
    return {
        "Grammatica": max(0, 100 - ris["errori_grammatica"] * 25),
        "Sintesi": ris["sintesi"],
        "Ritmo": ris["scorrevolezza"],
        "Registro": min(100, ris["manageriali"] * 20),
        "Struttura": (ris["apertura"] + ris["chiusura"]) / 2,
    }


# ------------------------------------------------------------ trascrizione --
LIMITE_BYTE = 15 * 1024 * 1024       # oltre, l'invio non passa


class ErroreTrascrizione(Exception):
    pass


def trascrivi(audio, chiave, modello="gemini-flash-latest",
              mime="audio/wav", avvisa=None):
    """
    Manda l'audio a Gemini e si fa restituire il testo.

    Perché non il riconoscimento vocale del browser come nella versione
    vecchia: quello esiste solo dentro la pagina, qui l'audio arriva al
    server, e per il server l'unico modo è passarlo a un servizio. Il
    vantaggio è che la trascrizione viene molto meglio, soprattutto sui
    termini tecnici.
    """
    if not (chiave or "").strip():
        raise ErroreTrascrizione(
            "Manca la chiave dell'intelligenza artificiale nei Secrets "
            "(`google_api_key`): senza, non posso trascrivere.")
    if len(audio) > LIMITE_BYTE:
        raise ErroreTrascrizione(
            f"La registrazione è troppo lunga da inviare "
            f"({len(audio) / 1024 / 1024:.0f} MB, il limite è 15). "
            "Registra un pezzo più corto: per l'analisi bastano uno o due "
            "minuti, ed è anche il modo migliore di allenarsi.")

    corpo = {"contents": [{"parts": [
        {"text": "Trascrivi fedelmente in italiano quello che senti. "
                 "Scrivi solo la trascrizione, senza commenti e senza "
                 "virgolette. Metti la punteggiatura dove serve, ma non "
                 "correggere gli errori di chi parla: servono per "
                 "l'analisi."},
        {"inline_data": {"mime_type": mime,
                         "data": base64.b64encode(audio).decode()}}]}]}

    # Stessa logica del resto della dashboard: il 503 vuol dire «server pieno»
    # e passa da solo in pochi secondi, quindi si riprova invece di arrendersi.
    attese = [3, 6, 12]
    r = None
    for tentativo in range(len(attese) + 1):
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{modello}"
            f":generateContent",
            params={"key": chiave}, json=corpo, timeout=240)
        if r.status_code != 200 and r.status_code in (503, 429) \
                and tentativo < len(attese):
            if avvisa:
                avvisa(f"Il servizio è occupato. Riprovo fra {attese[tentativo]} "
                       f"secondi (tentativo {tentativo + 2} di {len(attese) + 1})…")
            time.sleep(attese[tentativo])
            continue
        break

    if r.status_code != 200:
        if r.status_code in (503, 429):
            raise ErroreTrascrizione(
                "Il servizio di trascrizione è occupato e non si è liberato "
                "dopo quattro tentativi. Riprova fra qualche minuto: non è un "
                "problema della tua chiave né della registrazione.")
        raise ErroreTrascrizione(f"Errore {r.status_code}: {r.text[:300]}")

    dati = r.json()
    try:
        return dati["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise ErroreTrascrizione(
            "Il servizio non ha restituito testo. Di solito vuol dire che "
            "nella registrazione non si sente parlato.")
