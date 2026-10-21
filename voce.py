"""
voce.py — dettare invece di scrivere, e trascrivere la scrittura a mano.

Due cose, con la stessa idea dietro: il testo lo produce l'intelligenza
artificiale a partire da un file — un audio o un'immagine — e finisce dentro
una normale casella di testo di Quadro, dove lo puoi correggere.

=============================================================================
PERCHÉ NON C'È UN FOGLIO SU CUI SCRIVERE DIRETTAMENTE COL PENNINO
=============================================================================
Per disegnare dentro Streamlit servirebbe un componente aggiuntivo
(`streamlit-drawable-canvas`). L'ho installato e provato: con la versione di
Streamlit che usa Quadro non parte, si ferma con un errore di dichiarazione
del componente. Non è una cosa che si sistema da qui, dipende da loro.

Quindi la scrittura a mano passa da un'immagine: scrivi col pennino dove
preferisci — l'app di note del tablet, un foglio di carta fotografato — e
carichi l'immagine qui. Il risultato è lo stesso (testo digitale
modificabile), il passaggio in più è uno solo.

Vale la pena ricordare che per i quaderni veri hai già **Inchiostro**, che
fa esattamente questo mestiere e lo fa meglio: lì c'è la gestione dei fogli,
la ricerca, la lavagna. Questo serve per le due righe al volo dentro Quadro,
non per sostituirlo.
"""

import base64

import streamlit as st

LIMITE_AUDIO = 15 * 1024 * 1024
LIMITE_IMMAGINE = 12 * 1024 * 1024

ISTRUZIONI_AUDIO = (
    "Trascrivi fedelmente in italiano quello che senti. Scrivi solo la "
    "trascrizione, senza commenti e senza virgolette. Metti la punteggiatura "
    "dove serve. Se chi parla si corregge, tieni la versione corretta.")

ISTRUZIONI_MANO = (
    "In questa immagine c'è del testo scritto a mano. Trascrivilo "
    "fedelmente in italiano, rispettando gli a capo e gli elenchi. Scrivi "
    "solo la trascrizione, senza commenti. Dove una parola è davvero "
    "illeggibile metti [?] invece di inventarla. Se ci sono formule o "
    "simboli, scrivili come li vedi.")


def _chiedi_al_modello(dati, mime, istruzioni, chiave, modello):
    """Una chiamata sola a Gemini con un file allegato."""
    import requests
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modello}"
        f":generateContent",
        params={"key": chiave},
        json={"contents": [{"parts": [
            {"text": istruzioni},
            {"inline_data": {"mime_type": mime,
                             "data": base64.b64encode(dati).decode()}}]}]},
        timeout=240)
    if r.status_code != 200:
        if r.status_code in (503, 429):
            raise RuntimeError("Il servizio è occupato in questo momento. "
                               "Riprova fra un minuto: non dipende da te.")
        raise RuntimeError(f"Errore {r.status_code}: {r.text[:220]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError("Il servizio non ha restituito testo. Di solito "
                           "vuol dire che nel file non c'è niente da leggere.")


def trascrivi_audio(dati, chiave, modello, mime="audio/wav"):
    if len(dati) > LIMITE_AUDIO:
        raise RuntimeError(
            f"La registrazione è troppo lunga ({len(dati) / 1048576:.0f} MB, "
            "il limite è 15). Falla più corta.")
    return _chiedi_al_modello(dati, mime, ISTRUZIONI_AUDIO, chiave, modello)


def trascrivi_scrittura(dati, chiave, modello, mime="image/png"):
    if len(dati) > LIMITE_IMMAGINE:
        raise RuntimeError(
            f"L'immagine è troppo grande ({len(dati) / 1048576:.0f} MB, il "
            "limite è 12). Riducila o fotografa meno pagina per volta.")
    return _chiedi_al_modello(dati, mime, ISTRUZIONI_MANO, chiave, modello)


# ============================================================ la casella ====
def campo(etichetta, chiave, chiave_ai, modello_ai, altezza=150,
          suggerimento="", aiuto=None):
    """
    Una casella di testo con sotto i due modi per riempirla senza tastiera.

    Si usa al posto di `st.text_area` e restituisce la stessa cosa:

        testo = voce.campo("La tua risposta", "scienza_risposta",
                           chiave_ai(), modello_ai())

    La trascrizione viene scritta nella casella e resta modificabile: non
    sostituisce quello che c'è già, lo aggiunge in fondo, così puoi dettare
    un pezzo per volta.
    """
    # quello che è stato trascritto al giro precedente va messo nella casella
    # PRIMA che venga disegnata, altrimenti Streamlit rifiuta di cambiarla
    nuovo = st.session_state.pop(f"__dettato__{chiave}", None)
    if nuovo is not None:
        vecchio = (st.session_state.get(chiave) or "").strip()
        st.session_state[chiave] = (vecchio + "\n\n" + nuovo).strip() \
            if vecchio else nuovo
    if st.session_state.pop(f"__svuota__{chiave}", False):
        st.session_state[chiave] = ""

    testo = st.text_area(etichetta, height=altezza, key=chiave,
                         placeholder=suggerimento, help=aiuto)

    with st.expander("🎙️ Detta  ·  ✍️ Scrivi a mano", expanded=False):
        if not (chiave_ai or "").strip():
            st.info("Serve la chiave di Google AI Studio nei Secrets "
                    "(`google_api_key`) perché la trascrizione funzioni.")
            return testo

        d1, d2 = st.tabs(["🎙️ Detta a voce", "✍️ Scrittura a mano"])

        with d1:
            audio = st.audio_input("Premi e parla", key=f"aud_{chiave}")
            if audio is not None and st.button(
                    "Trascrivi quello che ho detto", key=f"btn_aud_{chiave}",
                    type="primary"):
                try:
                    with st.spinner("Sto ascoltando…"):
                        st.session_state[f"__dettato__{chiave}"] = \
                            trascrivi_audio(audio.getvalue(), chiave_ai,
                                            modello_ai,
                                            getattr(audio, "type", None)
                                            or "audio/wav")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        with d2:
            st.caption("Scrivi col pennino nell'app di note del tablet (o su "
                       "carta), fai uno scatto o una schermata e caricala "
                       "qui. Un foglio per volta viene meglio.")
            img = st.file_uploader("L'immagine della pagina scritta",
                                   type=["png", "jpg", "jpeg", "webp"],
                                   key=f"img_{chiave}")
            if img is not None:
                st.image(img, width=320)
                if st.button("Trascrivi la scrittura", key=f"btn_img_{chiave}",
                             type="primary"):
                    try:
                        with st.spinner("Sto leggendo…"):
                            st.session_state[f"__dettato__{chiave}"] = \
                                trascrivi_scrittura(
                                    img.getvalue(), chiave_ai, modello_ai,
                                    img.type or "image/png")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    return testo


def svuota(chiave):
    """Segna la casella da svuotare al prossimo ricaricamento."""
    st.session_state[f"__svuota__{chiave}"] = True
