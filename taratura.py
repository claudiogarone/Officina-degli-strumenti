"""
taratura.py — la sezione riservata.

Il nome è volutamente anonimo: in una dashboard da maker «Taratura» non fa
alzare un sopracciglio a nessuno. Dentro c'è il tuo diario personale: come
stai, cosa ti pesa, cosa è andato bene, e un interlocutore con cui ragionarci
sopra senza doverti spiegare ogni volta da capo.

=============================================================================
LA PASSWORD
=============================================================================
Si cambia in due posti, e il primo vince sul secondo:

  1. nei Secrets dell'app, con la riga        taratura_password = "..."
  2. qui sotto, nella costante PASSWORD_DI_SCORTA

**Usa i Secrets.** Il repository su GitHub è pubblico: una password scritta
qui sotto è leggibile da chiunque apra il file su GitHub, e quindi non
protegge niente. Nei Secrets no: quelli stanno solo su Streamlit e non
finiscono mai nel codice.

La costante qui sotto esiste solo perché tu possa entrare comunque se un
giorno ti dimentichi cosa hai messo nei Secrets. Cambiala pure.
"""

import datetime as dt
import hashlib

PASSWORD_DI_SCORTA = "taratura2026"

# dopo quanti minuti senza toccare niente la sezione si richiude da sola
MINUTI_DI_APERTURA = 10


def password_giusta(digitata, dai_secrets=None):
    """
    Confronto a tempo costante: non cambia durata a seconda di quante
    lettere sono giuste, così non si può indovinare a tentativi cronometrati.
    """
    attesa = (dai_secrets or "").strip() or PASSWORD_DI_SCORTA
    a = hashlib.sha256((digitata or "").encode()).hexdigest()
    b = hashlib.sha256(attesa.encode()).hexdigest()
    uguali = 0
    for x, y in zip(a, b):
        uguali |= ord(x) ^ ord(y)
    return uguali == 0 and len(a) == len(b)


def scaduta(aperta_alle):
    if not aperta_alle:
        return True
    return (dt.datetime.now() - aperta_alle).total_seconds() > MINUTI_DI_APERTURA * 60


# ============================================================ l'interlocutore
# Questo testo decide come risponde. Due cose sono volute e non vanno tolte:
# non si spaccia per uno psicologo, e se legge qualcosa che somiglia a una
# crisi smette di fare il coach e ti dice di parlare con una persona vera.
ISTRUZIONI = """Sei un interlocutore attento e concreto. La persona che ti
scrive tiene un diario personale e ti sta raccontando come sta.

Come rispondere:
- Parla italiano semplice, in seconda persona, senza gergo.
- Prima riconosci quello che ha scritto, con parole tue e senza ripeterlo a
  pappagallo. Poi, solo se serve, aggiungi una cosa su cui ragionare.
- Fai al massimo una domanda, e solo se apre davvero qualcosa.
- Non dire mai «capisco perfettamente» o «è normale sentirsi così»: sono
  frasi che chiudono invece di aprire.
- Se chiede un consiglio pratico, daglielo, piccolo e fattibile oggi.
- Niente elenchi puntati, niente titoli: scrivi tre o quattro frasi, come
  una persona che risponde a una persona.
- Non sei uno psicologo e non fai diagnosi. Se ti chiede cosa ha, dillo con
  calma e resta sul concreto.

Se in quello che scrive compare l'idea di farsi del male, di farla finita, o
una disperazione che non si muove da giorni: lascia perdere tutto il resto.
Dì con poche parole che non vuoi che resti solo con questa cosa, e che
parlarne con una persona vera — il medico di base, qualcuno di cui si fida,
o il Telefono Amico al 02 2327 2327 — è la cosa che conta adesso. Niente
consigli pratici, niente domande, niente analisi.

SUI FARMACI, una regola che non ha eccezioni. Se nomina un medicinale, una
dose, un effetto che attribuisce a una terapia, o ti chiede se continuare,
sospendere o cambiare qualcosa: non entrare nel merito. Nemmeno per
rassicurare, nemmeno per dire che è normale. Rispondi a come sta — quello sì
— e di' in una riga che su quel punto la persona da sentire è chi gliel'ha
prescritto, e che quello che ha annotato qui serve proprio a farglielo
vedere. Non commentare mai dosi, tempi, effetti o interazioni."""


def prompt(testo_oggi, umore, storico_righe, contesto=""):
    """Costruisce la richiesta, con un po' di memoria dei giorni scorsi."""
    passato = ""
    if storico_righe:
        passato = "\n\nCosa aveva scritto nei giorni scorsi, dal più recente:\n"
        for d, u, t in storico_righe[:5]:
            passato += f"- {d:%d/%m}: (umore {u}/10) {t[:260]}\n"

    extra = f"\n\nAltro che può servirti:\n{contesto}" if contesto else ""
    return (f"{ISTRUZIONI}\n\nOggi ha messo l'umore a {umore} su 10 e ha "
            f"scritto:\n\n{testo_oggi}{passato}{extra}"
            f"\n\nRispondi a lui, adesso.")


# le pratiche che si possono registrare nella scheda Benessere
PRATICHE = ["Yoga", "Meditazione", "Respirazione", "Camminata", "Altro"]


def riassunto_periodo(righe):
    """Due numeri onesti sull'andamento, senza interpretazioni."""
    if not righe:
        return None
    umori = [u for _, u, _ in righe if u is not None]
    if not umori:
        return None
    recenti = umori[:7]
    prima = umori[7:21] or recenti
    return {
        "voci": len(righe),
        "media_recente": sum(recenti) / len(recenti),
        "media_prima": sum(prima) / len(prima),
        "minimo": min(umori),
        "massimo": max(umori),
    }
