"""
radar.py — il radar delle cose che ti interessano.

Raccoglie quello che esce sulle fonti che scegli tu — articoli, progetti
maker, ricerca, podcast, video — lo mette in un elenco solo, toglie i
doppioni e lo ordina mettendo davanti quello che parla delle cose che segui.

COME FUNZIONA, in breve: ogni fonte pubblica un «feed», cioè un elenco
aggiornato in formato standard (RSS o Atom). Questo file li scarica tutti
insieme, li legge e li unisce. Nessun servizio da pagare, nessuna chiave:
sono indirizzi pubblici.

DUE COSE CHE NON PUÒ FARE, e vale la pena saperle subito:

  * Le fonti che non pubblicano un feed restano fuori. È il caso dei siti
    di UNISA e UNIBAS: ho provato gli indirizzi soliti e non ne hanno. Per
    quelli l'unica è andare a guardare la pagina, e infatti in `radar.json`
    stanno in un elenco a parte, come collegamenti da aprire.

  * Il radar non cerca in tutto internet: guarda solo le fonti nella lista.
    Aggiungerne una è una riga in `radar.json`.

Il punteggio di pertinenza è volutamente semplice: conta quante delle tue
parole chiave compaiono nel titolo e nel riassunto, pesando di più il
titolo. Non è intelligenza, è un setaccio — e per un setaccio va benissimo.
"""

import datetime as dt
import html
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

AGENTE = "Mozilla/5.0 (compatible; ENESTAR-Quadro/1.0)"
TIMEOUT = 15


# ------------------------------------------------------------- scaricare ---
def _scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(1_500_000).decode("utf-8", errors="replace")


# --------------------------------------------------------------- leggere ---
def _testo(blocco, *nomi):
    """Prende il contenuto del primo tag trovato fra quelli indicati."""
    for n in nomi:
        m = re.search(rf"<{n}[^>]*>(.*?)</{n}>", blocco, re.S | re.I)
        if m:
            v = m.group(1)
            v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.S)
            v = re.sub(r"<[^>]+>", " ", v)
            return html.unescape(v).strip()
        # Atom mette spesso il link in un attributo invece che nel contenuto
        m = re.search(rf'<{n}[^>]*href="([^"]+)"', blocco, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


MESI = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _data(blocco):
    grezza = _testo(blocco, "pubDate", "published", "updated", "dc:date")
    if not grezza:
        return None
    # RFC 822: «Tue, 20 Oct 2026 08:30:00 +0200»
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", grezza)
    if m:
        giorno, mese, anno = int(m.group(1)), MESI.get(m.group(2).lower()), int(m.group(3))
        if mese:
            try:
                return dt.date(anno, mese, giorno)
            except ValueError:
                return None
    # ISO 8601: «2026-10-20T08:30:00Z»
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", grezza)
    if m:
        try:
            return dt.date(*(int(g) for g in m.groups()))
        except ValueError:
            return None
    return None


def leggi_feed(xml, fonte=""):
    """
    Ricava le voci da un feed.

    Si lavora con le espressioni regolari invece che con un lettore XML
    vero, e non è pigrizia: parecchi feed in giro hanno XML leggermente
    rotto — sezioni CDATA non chiuse, caratteri strani — e un lettore
    rigoroso si ferma e perde tutto. Così invece si recupera quasi sempre.
    """
    blocchi = re.findall(r"<item[\s>].*?</item>", xml, re.S | re.I)
    if not blocchi:
        blocchi = re.findall(r"<entry[\s>].*?</entry>", xml, re.S | re.I)

    voci = []
    for b in blocchi:
        titolo = _testo(b, "title")
        if not titolo:
            continue
        testo = _testo(b, "description", "summary", "content:encoded", "content")
        voci.append({
            "titolo": titolo[:240],
            "link": _testo(b, "link", "guid"),
            "testo": re.sub(r"\s+", " ", testo)[:420],
            "data": _data(b),
            "fonte": fonte,
        })
    return voci


# ------------------------------------------------------------- setacciare --
def _parole(testo):
    return set(re.findall(r"[a-zàèéìòóùü0-9]{3,}", (testo or "").lower()))


def pertinenza(voce, interessi, esclusioni):
    """
    Quanto una voce c'entra con quello che segui.

    Restituisce None se va buttata via, altrimenti un punteggio: le parole
    nel titolo pesano il doppio di quelle nel riassunto.
    """
    t = (voce["titolo"] or "").lower()
    d = (voce["testo"] or "").lower()
    insieme = t + " " + d

    for brutta in esclusioni:
        if brutta.lower() in insieme:
            return None

    punti = 0
    trovate = []
    for chiave in interessi:
        k = chiave.lower()
        if k in t:
            punti += 2
            trovate.append(chiave)
        elif k in d:
            punti += 1
            trovate.append(chiave)
    voce["parole"] = trovate[:4]
    return punti


def raccogli(fonti, interessi, esclusioni, giorni=14, minimo=1):
    """
    Scarica tutte le fonti, unisce, toglie i doppioni e ordina.

    Restituisce (voci, problemi): i problemi sono le fonti che non hanno
    risposto, così si vede subito se una è da togliere dalla lista.
    """
    def una(f):
        try:
            return f["nome"], leggi_feed(_scarica(f["url"]), f["nome"]), None
        except Exception as e:
            return f["nome"], [], f"{type(e).__name__}: {str(e)[:80]}"

    tutte, problemi = [], []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for nome, voci, errore in ex.map(una, fonti):
            if errore:
                problemi.append((nome, errore))
            tutte.extend(voci)

    limite = dt.date.today() - dt.timedelta(days=giorni)
    viste, buone = set(), []
    for v in tutte:
        if v["data"] and v["data"] < limite:
            continue
        impronta = re.sub(r"[^a-z0-9]", "", (v["titolo"] or "").lower())[:70]
        if impronta in viste:
            continue
        viste.add(impronta)
        p = pertinenza(v, interessi, esclusioni)
        if p is None or p < minimo:
            continue
        v["punti"] = p
        buone.append(v)

    buone.sort(key=lambda v: (v["punti"], v["data"] or dt.date(1970, 1, 1)),
               reverse=True)
    return buone, problemi
