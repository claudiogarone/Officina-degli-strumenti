"""
assistente.py — una sola porta verso l'intelligenza artificiale.

Perché esiste questo file: la chiamata all'AI serviva in tre punti diversi
(Studio, Scrivania, Scienza) e ogni copia aveva i suoi difetti. Qui c'è una
funzione sola, con dentro le due cose che prima mancavano:

  * il RIPROVA. L'errore 503 («questo modello è molto richiesto in questo
    momento») non è un tuo errore: è il server di Google che è pieno. Dura
    pochi secondi. Prima la dashboard si arrendeva al primo tentativo, ora
    riprova tre volte aspettando 2, poi 4, poi 8 secondi.
  * il MODELLO DI RISERVA. Se dopo i tentativi il modello scelto è ancora
    occupato, prova con quelli di riserva in ordine. Così ti risponde lo
    stesso, magari con un modello un po' più piccolo.

Se vuoi cambiare i modelli di riserva, tocca la lista RISERVE qui sotto.
"""

import time
import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"

# provati in ordine quando quello scelto non risponde
RISERVE = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash"]

ATTESE = [2, 4, 8]          # secondi fra un tentativo e l'altro


class ErroreAI(Exception):
    """Errore che vale la pena mostrare all'utente, con un consiglio dentro."""

    def __init__(self, messaggio, dettaglio="", codice=None):
        super().__init__(messaggio)
        self.messaggio = messaggio
        self.dettaglio = dettaglio
        self.codice = codice


def _una_chiamata(modello, chiave, prompt, timeout=120):
    r = requests.post(
        f"{BASE}/models/{modello}:generateContent",
        params={"key": chiave},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=timeout)
    return r


def modelli_disponibili(chiave):
    """Elenco dei modelli che la tua chiave può davvero usare."""
    r = requests.get(f"{BASE}/models", params={"key": chiave}, timeout=30)
    if r.status_code != 200:
        raise ErroreAI("Non riesco a leggere l'elenco dei modelli",
                       r.text[:500], r.status_code)
    nomi = []
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            nomi.append(m["name"].replace("models/", ""))
    return nomi


def chiedi(prompt, chiave, modello, al_tentativo=None):
    """
    Manda il prompt e restituisce il testo della risposta.

    al_tentativo: funzione facoltativa chiamata a ogni nuovo tentativo con un
    messaggio da mostrare a schermo (serve a far vedere «riprovo…» invece di
    lasciare la pagina ferma).
    """
    if not (chiave or "").strip():
        raise ErroreAI("Manca la chiave dell'intelligenza artificiale",
                       "Mettila nei Secrets dell'app come `gemini_api_key`.")

    da_provare = [modello] + [m for m in RISERVE if m != modello]
    ultimo = None

    for i_modello, mod in enumerate(da_provare):
        for tentativo in range(len(ATTESE) + 1):
            try:
                r = _una_chiamata(mod, chiave, prompt)
            except requests.RequestException as e:
                ultimo = ErroreAI("Non sono riuscito a contattare il servizio", str(e))
                break

            if r.status_code == 200:
                dati = r.json()
                try:
                    return (dati["candidates"][0]["content"]["parts"][0]["text"])
                except (KeyError, IndexError):
                    motivo = (dati.get("candidates", [{}])[0]
                              .get("finishReason", "sconosciuto"))
                    raise ErroreAI(
                        "Il servizio ha risposto senza testo",
                        f"Motivo dichiarato: {motivo}. Di solito succede quando il "
                        "testo di partenza è troppo lungo o è stato bloccato dai "
                        "filtri: prova ad accorciarlo.")

            # --- 503 e 429: è pieno o sei andato oltre il limite: si riprova ---
            if r.status_code in (503, 429) and tentativo < len(ATTESE):
                attesa = ATTESE[tentativo]
                if al_tentativo:
                    quale = "è molto richiesto" if r.status_code == 503 else "ha chiesto una pausa"
                    al_tentativo(f"Il modello {quale}. Riprovo fra {attesa} secondi "
                                 f"(tentativo {tentativo + 2} di {len(ATTESE) + 1})…")
                time.sleep(attesa)
                continue

            # --- 404: nome del modello sbagliato: passa al prossimo di riserva ---
            if r.status_code == 404:
                ultimo = ErroreAI(
                    f"Il modello «{mod}» non esiste più",
                    r.text[:500],
                    404)
                break

            if r.status_code in (401, 403):
                raise ErroreAI(
                    "La chiave non è valida oppure non è abilitata",
                    r.text[:500], r.status_code)

            ultimo = ErroreAI(f"Errore {r.status_code}", r.text[:500], r.status_code)
            break

        # se c'è ancora un modello di riserva da provare, avvisa e continua
        if i_modello < len(da_provare) - 1 and al_tentativo:
            al_tentativo(f"«{mod}» non risponde: provo con "
                         f"«{da_provare[i_modello + 1]}»…")

    if ultimo and ultimo.codice == 503:
        ultimo.messaggio = "I modelli sono tutti occupati in questo momento"
        ultimo.dettaglio = ("Non è un problema tuo né della chiave: i server di "
                            "Google sono sotto carico. Succede soprattutto nelle "
                            "ore di punta. Riprova fra qualche minuto.")
    raise ultimo or ErroreAI("Nessun modello ha risposto",
                             "Prova a cambiare modello nelle impostazioni.")
