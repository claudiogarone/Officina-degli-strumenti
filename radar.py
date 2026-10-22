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
            # l'autore: i feed lo mettono in tag diversi, o non lo mettono
            "autore": _testo(b, "dc:creator", "author", "itunes:author")[:80],
        })
    return voci


# ------------------------------------------------------------- bandi -------
# Le notizie sui bandi si prendono da Google News, che ha un feed pubblico
# per ogni ricerca: si scrive la ricerca («bando Vallo di Diano») e Google
# restituisce le notizie più recenti su quell'argomento. Si aggiorna da solo
# ogni volta che lo chiedi, senza chiavi e senza scraping.
PAROLE_BANDI = ("bando", "bandi", "avviso", "contribut", "finanziament",
                "incentiv", "agevolazion", "voucher", "sovvenzion", "fondo",
                "fondi")


def url_notizie(ricerca):
    from urllib.parse import quote_plus
    return ("https://news.google.com/rss/search?q=" + quote_plus(ricerca)
            + "&hl=it&gl=IT&ceid=IT:it")


def cerca_notizie(ricerche, giorni=30):
    """Notizie su bandi e agevolazioni, senza doppioni, le più recenti prima."""
    def una(q):
        try:
            voci = leggi_feed(_scarica(url_notizie(q)), "Google News")
        except Exception:
            return []
        for v in voci:
            # i titoli di Google News finiscono con «- Testata»
            if " - " in v["titolo"]:
                titolo, _, testata = v["titolo"].rpartition(" - ")
                v["titolo"], v["fonte"] = titolo.strip(), testata.strip()
            v["ricerca"] = q
        return voci

    tutte = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for voci in ex.map(una, ricerche):
            tutte.extend(voci)

    limite = dt.date.today() - dt.timedelta(days=giorni)
    viste, buone = set(), []
    for v in tutte:
        if v["data"] and v["data"] < limite:
            continue
        impronta = re.sub(r"[^a-z0-9]", "", v["titolo"].lower())[:70]
        if impronta in viste:
            continue
        viste.add(impronta)
        testo = (v["titolo"] + " " + v["testo"]).lower()
        if not any(p in testo for p in PAROLE_BANDI):
            continue           # una notizia che non parla di bandi, buttata
        buone.append(v)
    buone.sort(key=lambda v: v["data"] or dt.date(1970, 1, 1), reverse=True)
    return buone


# ------------------------------------------------------- canali YouTube ----
def id_canale_youtube(indirizzo):
    """
    Dal link di un canale ricava l'identificativo UC… che serve al feed.

    Accetta tutte e tre le forme in uso: …/channel/UC…, …/@nome, …/c/nome.
    Per le ultime due va letta la pagina del canale, e lì l'identificativo
    sta nel codice. Se YouTube cambia la pagina, la funzione lo dice.
    """
    indirizzo = indirizzo.strip()
    m = re.search(r"/channel/(UC[\w-]{22})", indirizzo)
    if m:
        return m.group(1)
    if not indirizzo.startswith("http"):
        indirizzo = "https://www.youtube.com/" + indirizzo.lstrip("/")
    pagina = _scarica(indirizzo)
    m = (re.search(r'"channelId":"(UC[\w-]{22})"', pagina)
         or re.search(r'"externalId":"(UC[\w-]{22})"', pagina)
         or re.search(r"channel_id=(UC[\w-]{22})", pagina))
    if not m:
        raise ValueError("non trovo l'identificativo del canale in quella "
                         "pagina: prova con il link «/channel/UC…»")
    return m.group(1)


def canale_youtube(indirizzo):
    """(nome del canale, indirizzo del feed, numero di video letti)."""
    id_c = id_canale_youtube(indirizzo)
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={id_c}"
    xml = _scarica(url)
    m = re.search(r"<author>\s*<name>(.*?)</name>", xml, re.S) \
        or re.search(r"<title>(.*?)</title>", xml, re.S)
    nome = html.unescape(m.group(1)).strip() if m else id_c
    return nome, url, len(leggi_feed(xml, nome))


# --------------------------------------------------------------- lingua ---
# Riconoscere la lingua con una libreria sarebbe più preciso, ma vorrebbe
# dire un pacchetto in più per una cosa che qui si fa benissimo contando le
# parolette: articoli, preposizioni e congiunzioni sono diversissimi fra le
# tre lingue e in un titolo ce n'è sempre qualcuna.
SPIE = {
 "it": {"il","lo","la","gli","le","dei","delle","degli","che","con","per",
        "una","uno","del","della","nel","nella","sono","più","come","anche",
        "non","alla","dai","sul","tra","fra","questo","questa","perché"},
 "es": {"el","los","las","una","uno","del","que","con","por","para","más",
        "como","pero","este","esta","son","desde","sobre","entre","hasta",
        "sus","años","según","también","cómo","qué"},
 "en": {"the","of","and","for","with","from","this","that","are","have",
        "will","about","into","your","their","which","been","more","new",
        "how","what","when"},
}


def lingua(voce):
    """it, es, en oppure «?» quando non c'è abbastanza testo per decidere."""
    parole = _parole(voce.get("titolo", "") + " " + voce.get("testo", ""))
    punti = {k: len(parole & spie) for k, spie in SPIE.items()}
    migliore = max(punti, key=punti.get)
    return migliore if punti[migliore] >= 2 else "?"


# ------------------------------------------------------------ tipologia ---
def tipologia(voce, dichiarata=""):
    """
    Che cosa è: video, podcast, corso o articolo.

    La fonte può dichiararlo in `radar.json`; se non lo fa si guarda
    l'indirizzo, che quasi sempre basta.
    """
    if dichiarata:
        return dichiarata
    link = (voce.get("link") or "").lower()
    if "youtube.com" in link or "youtu.be" in link:
        return "video"
    if any(k in link for k in ("podcast", "/episodi", "/episode", ".mp3")):
        return "podcast"
    if any(k in link for k in ("udemy.com", "coursera", "/corso", "/course")):
        return "corso"
    return "articolo"


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


def raccogli(fonti, interessi, esclusioni, giorni=14, minimo=1,
             bonus_lingua=None):
    """
    Scarica tutte le fonti, unisce, toglie i doppioni e ordina.

    Restituisce (voci, problemi): i problemi sono le fonti che non hanno
    risposto, così si vede subito se una è da togliere dalla lista.
    """
    bonus_lingua = bonus_lingua or {}
    per_nome = {f["nome"]: f for f in fonti}

    def una(f):
        try:
            voci = leggi_feed(_scarica(f["url"]), f["nome"])
            return f["nome"], voci, None
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
        conf = per_nome.get(v["fonte"], {})
        v["ambito"] = conf.get("tipo", "altro")
        v["tipologia"] = tipologia(v, conf.get("contenuto", ""))
        v["lingua"] = conf.get("lingua") or lingua(v)
        # la lingua non cambia la pertinenza, cambia l'ordine: a parità di
        # argomento vedi prima quello che puoi leggere più in fretta
        v["punti"] = p + bonus_lingua.get(v["lingua"], 0)
        v["pertinenza"] = p
        buone.append(v)

    buone.sort(key=lambda v: (v["punti"], v["data"] or dt.date(1970, 1, 1)),
               reverse=True)
    return buone, problemi
