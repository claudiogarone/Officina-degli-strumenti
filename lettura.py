"""
lettura.py — 📖 Leggimelo: da una foto, un PDF, un link o un testo incollato
a una lettura ad alta voce, con tutto quello che serve intorno.

    PRENDERE IL TESTO   foto · immagini e PDF · link di un articolo · incolla
    LAVORARCI           riassunto · spiegato semplice · traduzione · punti
                        chiave · modifica a mano · cerca
    ASCOLTARE           lettore nel browser con tutti i comandi, oppure un
                        file audio vero (MP3 o WAV) fatto dalla voce di Gemini
    SCARICARE           TXT · Markdown · Word · PDF · pagina HTML · audio
    CAPIRE              mappa concettuale interattiva · infografica animata ·
                        flashcard con ripasso a intervalli crescenti
    TENERE              la biblioteca delle letture, nel diario

=============================================================================
DUE VOCI DIVERSE, E PERCHÉ
=============================================================================
Il LETTORE usa la voce del browser: è immediata, gratuita, non consuma niente
e si comanda frase per frase. Ma non si può salvare come file: il browser
parla e basta.

Il FILE AUDIO lo fa Gemini (modelli «tts»): voce più naturale, scaricabile,
ascoltabile in macchina. Costa una chiamata all'AI ogni circa 2500 caratteri
e richiede qualche secondo per pezzo. Se il tuo piano di Google AI Studio non
la include, Quadro te lo dice e il lettore resta disponibile.
Attenzione: nel piano gratuito le chiamate di voce al giorno sono poche
(una decina, a fine 2026) e sono le stesse che usa la voce naturale della
segretaria. Il numero vero lo vedi su aistudio.google.com/rate-limit.

I LINK: Quadro scarica la pagina e con la libreria `trafilatura` tiene solo
il testo dell'articolo, togliendo menù, pubblicità e commenti. Non funziona
con gli articoli dietro abbonamento, né con i siti che costruiscono il testo
solo nel browser: in quei casi copia il testo e usa «Incolla».
"""

import base64
import datetime as dt
import html as _html
import io
import json
import re
import time
import wave

import pandas as pd
import streamlit as st


# =============================================================== utilità ===
def _js(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def _errore(e):
    return getattr(e, "messaggio", None) or str(e)


def _json(testo):
    """Il primo oggetto o elenco JSON dentro una risposta dell'AI."""
    if not testo:
        return None
    testo = re.sub(r"^```(?:json)?|```$", "", testo.strip(), flags=re.M)
    # si prova prima la parentesi che compare prima: un elenco di oggetti
    # comincia con «[», e non va scambiato per il suo primo oggetto
    coppie = sorted((("{", "}"), ("[", "]")),
                    key=lambda c: testo.find(c[0]) if testo.find(c[0]) != -1 else 10**9)
    for a, b in coppie:
        i, j = testo.find(a), testo.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(testo[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def pulisci(testo):
    """Via i caratteri di controllo (da OCR o copia-incolla): Word li rifiuta."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", testo or "")


def parole(testo):
    return len(re.findall(r"\w+", testo or ""))


def nome_file(titolo, estensione):
    base = re.sub(r"[^\w\- ]+", "", titolo or "lettura").strip().replace(" ", "_")[:60]
    return f"{base or 'lettura'}.{estensione}"


# ======================================================= prendere il testo ===
ISTRUZIONI_STAMPA = (
    "In questa immagine o documento c'è del testo stampato: una pagina di "
    "libro, un articolo, un documento. Trascrivilo fedelmente, nell'ordine in "
    "cui si legge, nella sua lingua originale. Salta numeri di pagina, "
    "intestazioni e piè di pagina ripetuti. Unisci le parole spezzate "
    "dall'a capo. Separa i paragrafi con una riga vuota. Scrivi solo il "
    "testo, senza commenti.")


def da_link(url):
    """(titolo, autore, data, sito, testo) di un articolo, o un errore chiaro."""
    import requests
    import trafilatura
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    risposta = requests.get(url, timeout=25, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.7"})
    if risposta.status_code >= 400:
        raise RuntimeError(f"la pagina ha risposto con l'errore {risposta.status_code}")
    pagina = risposta.text
    testo = trafilatura.extract(pagina, url=url, output_format="txt",
                                include_comments=False, include_tables=True,
                                favor_recall=True)
    if not testo or len(testo) < 200:
        raise RuntimeError("in questa pagina non trovo un articolo leggibile: forse "
                           "è dietro abbonamento o il testo arriva solo nel "
                           "browser. Copialo e usa «Incolla»")
    meta = trafilatura.extract_metadata(pagina, default_url=url)
    return (getattr(meta, "title", None) or url, getattr(meta, "author", None) or "",
            getattr(meta, "date", None) or "", getattr(meta, "sitename", None) or "", testo)


def da_file(ctx, file_):
    """Testo da foto e PDF, una pagina per volta, con l'AI."""
    pezzi = []
    barra = st.progress(0.0, text="Leggo…")
    for i, (dati, mime) in enumerate(file_):
        pezzi.append(ctx.VOCE._chiedi_al_modello(dati, mime, ISTRUZIONI_STAMPA,
                                                 ctx.chiave_ai, ctx.modello_ai))
        barra.progress((i + 1) / len(file_), text=f"Pagina {i + 1} di {len(file_)}")
    barra.empty()
    return "\n\n".join(p.strip() for p in pezzi if p and p.strip())


# ============================================================ trasformare ===
LINGUE = ["italiano", "inglese", "spagnolo", "francese", "tedesco", "portoghese"]

TRASFORMAZIONI = {
    "riassunto": "Riassumi questo testo in italiano in circa un terzo della "
                 "lunghezza, in frasi complete e scorrevoli da ascoltare, "
                 "senza elenchi puntati.",
    "semplice": "Riscrivi questo testo in italiano semplice, come lo spiegheresti "
                "a voce a una persona intelligente che non conosce l'argomento. "
                "Frasi brevi, esempi concreti quando servono, niente elenchi.",
    "punti": "Estrai i punti chiave di questo testo, in italiano: da 5 a 10 "
             "punti, ognuno una frase completa. Un punto per riga, comincia "
             "ogni riga con «• ».",
}


def trasforma(ctx, testo, tipo, lingua="italiano"):
    if tipo == "traduci":
        istr = (f"Traduci questo testo in {lingua}, fedelmente e in modo "
                "naturale, mantenendo i paragrafi. Solo la traduzione.")
    else:
        istr = TRASFORMAZIONI[tipo]
    return ctx.AI.chiedi(istr + "\n\n---\n" + testo, ctx.chiave_ai, ctx.modello_ai).strip()


# ============================================================ esportare =====
def a_markdown(doc):
    righe = [f"# {doc['titolo']}", ""]
    if doc.get("fonte"):
        righe += [f"*Fonte: {doc['fonte']}*", ""]
    return "\n".join(righe) + doc["testo"] + "\n"


def a_docx(doc):
    from docx import Document
    from docx.shared import Pt
    d = Document()
    stile = d.styles["Normal"]
    stile.font.name = "Calibri"
    stile.font.size = Pt(12)
    d.add_heading(doc["titolo"], level=1)
    if doc.get("fonte"):
        p = d.add_paragraph(f"Fonte: {doc['fonte']}")
        p.runs[0].italic = True
    for par in re.split(r"\n\s*\n", doc["testo"]):
        if par.strip():
            d.add_paragraph(par.strip())
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def a_pdf(doc):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=doc["titolo"])
    st_ = getSampleStyleSheet()
    corpo = ParagraphStyle("corpo", parent=st_["BodyText"], fontSize=11.5, leading=16)
    elementi = [Paragraph(_html.escape(doc["titolo"]), st_["Title"])]
    if doc.get("fonte"):
        elementi.append(Paragraph(f"<i>Fonte: {_html.escape(doc['fonte'])}</i>", st_["Normal"]))
    elementi.append(Spacer(1, 10))
    for par in re.split(r"\n\s*\n", doc["testo"]):
        if par.strip():
            # i caratteri del PDF base sono quelli di Windows (cp1252): ci sono
            # apostrofi curvi, virgolette e l'euro; le emoji no, e si tolgono
            pulito = par.strip().encode("cp1252", "ignore").decode("cp1252")
            elementi.append(Paragraph(_html.escape(pulito).replace("\n", "<br/>"), corpo))
            elementi.append(Spacer(1, 6))
    pdf.build(elementi)
    return buf.getvalue()


def a_html(doc):
    paragrafi = "".join(f"<p>{_html.escape(p.strip())}</p>"
                        for p in re.split(r"\n\s*\n", doc["testo"]) if p.strip())
    fonte = f"<p class='fonte'>Fonte: {_html.escape(doc['fonte'])}</p>" if doc.get("fonte") else ""
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(doc['titolo'])}</title>
<style>body{{max-width:720px;margin:40px auto;padding:0 18px;font:18px/1.65 Georgia,serif;
color:#1d2a26;background:#fbfaf6}}h1{{font:700 30px/1.25 system-ui,sans-serif;color:#0f5d47}}
.fonte{{color:#6b7c76;font-style:italic}}@media(prefers-color-scheme:dark){{body{{background:#14201c;
color:#e7efec}}h1{{color:#7ee0b8}}}}</style></head><body><h1>{_html.escape(doc['titolo'])}</h1>
{fonte}{paragrafi}</body></html>"""


# ============================================================ l'audio vero ===
# Le voci di Gemini. Il carattere tra parentesi è indicativo: il pulsante
# «Prova la voce» è il modo giusto per sceglierle.
VOCI_GEMINI = {
    "Kore": "decisa", "Aoede": "leggera", "Sulafat": "calda", "Achernar": "morbida",
    "Vindemiatrix": "gentile", "Leda": "giovane", "Zephyr": "luminosa",
    "Despina": "fluida", "Callirrhoe": "rilassata", "Autonoe": "chiara",
    "Erinome": "nitida", "Laomedeia": "allegra", "Pulcherrima": "diretta",
    "Gacrux": "matura", "Charon": "informativa", "Puck": "vivace", "Orus": "ferma",
    "Iapetus": "chiara", "Algieba": "liscia", "Rasalgethi": "da documentario",
    "Sadaltager": "esperta", "Achird": "amichevole", "Umbriel": "rilassata",
    "Schedar": "regolare", "Alnilam": "ferma", "Fenrir": "entusiasta",
    "Enceladus": "sussurrata", "Algenib": "roca", "Zubenelgenubi": "informale",
    "Sadachbia": "vivace",
}
STILI_VOCE = {
    "naturale": "",
    "calmo": "Leggi con tono calmo e rilassato, senza fretta: ",
    "da narratore": "Leggi come un narratore di audiolibri, con espressività: ",
    "da lezione": "Leggi in modo chiaro e scandito, come una lezione: ",
    "entusiasta": "Leggi con energia ed entusiasmo: ",
}
MODELLI_TTS = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]


def _pezzi(testo, massimo=2500):
    """Taglia il testo in pezzi di circa `massimo` caratteri, alla fine di una frase."""
    frasi = re.findall(r"[^.!?…\n]+[.!?…]*\s*|\n+", testo)
    pezzi, ora = [], ""
    for f in frasi:
        if len(ora) + len(f) > massimo and ora.strip():
            pezzi.append(ora.strip())
            ora = ""
        ora += f
    if ora.strip():
        pezzi.append(ora.strip())
    return pezzi


def _tts(chiave, testo, voce, modelli=None, attese=(0, 3, 8), timeout=180):
    """
    PCM 16 bit, 24 kHz, mono, per un pezzo di testo.
    `attese`: quanto aspettare prima di ogni tentativo se il servizio è
    occupato. La segretaria passa (0,): una prova sola e, se va male, parla
    con la voce del dispositivo invece di farti aspettare.
    """
    import requests
    ultimo = None
    for modello in modelli or MODELLI_TTS:
        for attesa in attese:
            time.sleep(attesa)
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent",
                params={"key": chiave}, timeout=timeout,
                json={"contents": [{"parts": [{"text": testo}]}],
                      "generationConfig": {
                          "responseModalities": ["AUDIO"],
                          "speechConfig": {"voiceConfig": {
                              "prebuiltVoiceConfig": {"voiceName": voce}}}}})
            if r.status_code == 200:
                try:
                    parte = r.json()["candidates"][0]["content"]["parts"][0]
                    return base64.b64decode((parte.get("inlineData") or parte["inline_data"])["data"])
                except (KeyError, IndexError):
                    ultimo = "il servizio non ha restituito audio"
                    break
            ultimo = f"errore {r.status_code}: {r.text[:200]}"
            if r.status_code not in (429, 500, 503):
                break                       # 404: si prova il modello successivo
    if ultimo and ("429" in ultimo or "403" in ultimo):
        ultimo += (" — la sintesi vocale potrebbe non essere inclusa nel tuo piano "
                   "di Google AI Studio, o hai finito le richieste di oggi")
    raise RuntimeError(ultimo or "sintesi vocale non disponibile")


def _wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue()


def _mp3(pcm):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(24000)
    enc.set_channels(1)
    enc.set_quality(2)
    # lameenc restituisce un «bytearray», che st.audio rifiuta: si converte in bytes
    return bytes(enc.encode(pcm) + enc.flush())


def audio_da_testo(chiave, testo, voce="Kore", stile="naturale", formato="mp3",
                   al_progresso=None):
    """Il file audio di tutto il testo, a pezzi, unito in uno solo."""
    pezzi = _pezzi(testo)
    pcm = b""
    for i, p in enumerate(pezzi):
        if al_progresso:
            al_progresso(i, len(pezzi))
        pcm += _tts(chiave, STILI_VOCE.get(stile, "") + p, voce)
        pcm += b"\x00\x00" * 7200           # 0,3 secondi di silenzio fra i pezzi
    if al_progresso:
        al_progresso(len(pezzi), len(pezzi))
    return _mp3(pcm) if formato == "mp3" else _wav(pcm)


# ================================================================ lettore ====
LETTORE = r"""<!doctype html><meta charset="utf-8">
<style>
  :root { --verde:#1baf7a; --fondo:#0f2a24; --testo:#eef7f3; --tenue:#9cc7b8; --carta:#16352d; }
  body.chiaro { --fondo:#f6f8f5; --testo:#1d2a26; --tenue:#5d7069; --carta:#ffffff; }
  body { margin:0; font-family:system-ui,sans-serif; background:var(--fondo); color:var(--testo); }
  .w { padding:12px 14px; }
  .barra { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:5px 0; }
  button { font-size:14px; padding:7px 11px; border-radius:9px; cursor:pointer;
           border:1px solid var(--verde); background:transparent; color:var(--testo); }
  button.p { background:var(--verde); color:#fff; font-weight:600; }
  button.on { background:rgba(27,175,122,.35); }
  label { font-size:12.5px; color:var(--tenue); display:inline-flex; gap:5px; align-items:center; }
  select, input[type=search] { background:var(--carta); color:var(--testo); border:1px solid #3c5a52;
           border-radius:7px; padding:5px; max-width:100%; }
  #tx { position:relative; margin-top:8px; max-height:340px; overflow-y:auto; line-height:1.6; font-size:18px;
        padding:12px; border-radius:10px; background:var(--carta); }
  #tx p { margin:0 0 .8em; }
  #tx span { cursor:pointer; border-radius:4px; }
  #tx span.ora { background:rgba(27,175,122,.45); }
  #tx span.trov { outline:2px solid #eda100; }
  .prog { height:6px; background:#2b4a42; border-radius:4px; overflow:hidden; margin-top:6px; }
  .prog div { height:100%; width:0; background:var(--verde); transition:width .3s; }
  #info { font-size:12.5px; color:var(--tenue); }
</style>
<div class="w">
  <div class="barra">
    <button class="p" id="play" title="Spazio">▶ Leggi</button>
    <button id="stop" title="Ferma">■</button>
    <button id="pp" title="Paragrafo precedente">⏪</button>
    <button id="fp" title="Frase precedente (←)">⏮</button>
    <button id="fs" title="Frase successiva (→)">⏭</button>
    <button id="ps" title="Paragrafo successivo">⏩</button>
    <button id="ripeti" title="Ripeti la frase in continuazione">🔁</button>
    <button id="meno" title="Testo più piccolo">A−</button>
    <button id="piu" title="Testo più grande">A+</button>
    <button id="tema" title="Chiaro o scuro">◐</button>
    <button id="copia" title="Copia tutto il testo">📋</button>
  </div>
  <div class="barra">
    <label>Voce <select id="voce"></select></label>
    <label><input type="checkbox" id="tutte"> tutte le lingue</label>
  </div>
  <div class="barra">
    <label>Velocità <input type="range" id="vel" min="0.5" max="2.5" step="0.05"> <b id="veln"></b></label>
    <button data-v="0.8">0,8×</button><button data-v="1">1×</button><button data-v="1.25">1,25×</button>
    <button data-v="1.5">1,5×</button><button data-v="2">2×</button>
  </div>
  <div class="barra">
    <label>Tono <input type="range" id="tono" min="0.5" max="1.6" step="0.05"></label>
    <label>Volume <input type="range" id="vol" min="0" max="1" step="0.05"></label>
    <label>Spegni fra <select id="sonno"><option value="0">mai</option><option value="5">5 min</option>
      <option value="10">10 min</option><option value="15">15 min</option><option value="30">30 min</option>
      <option value="60">60 min</option></select></label>
  </div>
  <div class="barra">
    <label><input type="checkbox" id="evid" checked> evidenzia</label>
    <label><input type="checkbox" id="segui" checked> scorri da solo</label>
    <input type="search" id="cerca" placeholder="🔎 cerca nel testo" style="flex:1;min-width:140px">
  </div>
  <div class="prog"><div id="barra"></div></div>
  <div id="info"></div>
  <div id="tx"></div>
</div>
<script>
const TESTO = __TESTO__;
const CHIAVE = 'quadro_lettore';
let pref = { voce:'', vel:1, tono:1, vol:1, tutte:false, dim:18, chiaro:false };
try { Object.assign(pref, JSON.parse(localStorage.getItem(CHIAVE) || '{}')); } catch (e) {}
const $ = id => document.getElementById(id);
function salva() { try { localStorage.setItem(CHIAVE, JSON.stringify(pref)); } catch (e) {} }

// paragrafi: separati da una riga vuota; frasi: dentro ogni paragrafo
const PAR = TESTO.split(/\n\s*\n/).map(p => p.replace(/\s*\n\s*/g, ' ').trim()).filter(Boolean);
const FRASI = [];            // {t: testo, p: indice paragrafo}
const tx = $('tx');
PAR.forEach((p, ip) => {
  const el = document.createElement('p');
  (p.match(/[^.!?…;:]+[.!?…;:]*["»”')\]]*\s*/g) || [p]).forEach(f => {
    if (!f.trim()) return;
    const s = document.createElement('span');
    const k = FRASI.length;
    s.textContent = f; s.id = 'f' + k;
    s.onclick = () => vai(k, true);
    el.appendChild(s);
    FRASI.push({ t: f.trim(), p: ip });
  });
  tx.appendChild(el);
});
const TOT_PAROLE = TESTO.split(/\s+/).filter(Boolean).length;

let i = 0, attivo = false, ripeti = false, spegni = null;

function voci() {
  if (!('speechSynthesis' in window)) return [];
  return speechSynthesis.getVoices().filter(v => $('tutte').checked || (v.lang || '').toLowerCase().startsWith('it'));
}
function riempiVoci() {
  const sel = $('voce'); sel.innerHTML = '';
  const vv = voci();
  vv.forEach(v => { const o = document.createElement('option'); o.value = v.name;
    o.textContent = v.name + ' (' + v.lang + ')'; if (v.name === pref.voce) o.selected = true; sel.appendChild(o); });
  if (!vv.length) { const o = document.createElement('option'); o.textContent = 'nessuna voce italiana: spunta «tutte le lingue»'; sel.appendChild(o); }
}
function aggiorna() {
  FRASI.forEach((_, k) => $('f' + k).classList.toggle('ora', $('evid').checked && k === i));
  const s = $('f' + i);
  if (s && $('segui').checked) centra(s);
  const fatte = FRASI.slice(0, i).reduce((n, f) => n + f.t.split(/\s+/).length, 0);
  $('barra').style.width = (100 * i / Math.max(1, FRASI.length)) + '%';
  const restano = Math.max(0, TOT_PAROLE - fatte) / (160 * Number($('vel').value));
  $('info').textContent = 'frase ' + (i + 1) + ' di ' + FRASI.length + ' · paragrafo ' +
    ((FRASI[i] || {}).p + 1) + ' di ' + PAR.length + ' · ' + TOT_PAROLE + ' parole · restano circa ' +
    Math.ceil(restano) + ' min' + (ripeti ? ' · 🔁 ripeti attivo' : '');
}
// scorre solo il riquadro del testo, non tutta la pagina: i comandi restano in vista
function centra(el) {
  tx.scrollTo({ top: el.offsetTop - tx.clientHeight / 2 + el.offsetHeight / 2, behavior: 'smooth' });
}
function frase(t) {
  const u = new SpeechSynthesisUtterance(t);
  const v = speechSynthesis.getVoices().find(x => x.name === $('voce').value);
  if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = 'it-IT'; }
  u.rate = Number($('vel').value); u.pitch = Number($('tono').value); u.volume = Number($('vol').value);
  return u;
}
function leggi() {
  if (!attivo) return;
  if (i >= FRASI.length) { ferma(); i = 0; aggiorna(); $('info').textContent = 'Finito.'; return; }
  aggiorna();
  const qui = i, u = frase(FRASI[i].t);
  u.onend = () => { if (!attivo) return; if (i === qui && !ripeti) i += 1; leggi(); };
  u.onerror = e => { if (e.error === 'interrupted' || e.error === 'canceled') return; u.onend(); };
  speechSynthesis.speak(u);
}
function avvia() {
  if (!('speechSynthesis' in window)) { $('info').textContent = 'Questo browser non legge ad alta voce.'; return; }
  speechSynthesis.cancel(); attivo = true; $('play').textContent = '⏸ Pausa'; leggi();
  const m = Number($('sonno').value);
  clearTimeout(spegni);
  if (m) spegni = setTimeout(() => { ferma(); $('info').textContent = 'Spento dal timer.'; }, m * 60000);
}
function ferma() { attivo = false; try { speechSynthesis.cancel(); } catch (e) {} $('play').textContent = '▶ Leggi'; }
function vai(k, daClic) {
  i = Math.max(0, Math.min(FRASI.length - 1, k));
  if (attivo) { speechSynthesis.cancel(); setTimeout(() => { if (attivo) leggi(); }, 60); }
  else aggiorna();
}
function paragrafo(d) {
  const p = (FRASI[i] || { p: 0 }).p + d;
  const k = FRASI.findIndex(f => f.p === Math.max(0, Math.min(PAR.length - 1, p)));
  if (k >= 0) vai(k);
}
$('play').onclick = () => attivo ? ferma() : avvia();
$('stop').onclick = () => { ferma(); i = 0; aggiorna(); };
$('fp').onclick = () => vai(i - 1);
$('fs').onclick = () => vai(i + 1);
$('pp').onclick = () => paragrafo(-1);
$('ps').onclick = () => paragrafo(1);
$('ripeti').onclick = () => { ripeti = !ripeti; $('ripeti').classList.toggle('on', ripeti); aggiorna(); };
$('meno').onclick = () => { pref.dim = Math.max(13, pref.dim - 2); tx.style.fontSize = pref.dim + 'px'; salva(); };
$('piu').onclick = () => { pref.dim = Math.min(34, pref.dim + 2); tx.style.fontSize = pref.dim + 'px'; salva(); };
$('tema').onclick = () => { pref.chiaro = !pref.chiaro; document.body.classList.toggle('chiaro', pref.chiaro); salva(); };
$('copia').onclick = async () => {
  try { await navigator.clipboard.writeText(TESTO); $('info').textContent = 'Testo copiato.'; }
  catch (e) { const r = document.createRange(); r.selectNodeContents(tx); const s = getSelection();
    s.removeAllRanges(); s.addRange(r); $('info').textContent = 'Testo selezionato: premi Ctrl+C.'; }
};
document.querySelectorAll('[data-v]').forEach(b => b.onclick = () => {
  $('vel').value = b.dataset.v; pref.vel = Number(b.dataset.v); $('veln').textContent = b.dataset.v + '×'; salva(); aggiorna();
});
$('vel').oninput = () => { pref.vel = Number($('vel').value); $('veln').textContent = pref.vel.toFixed(2) + '×'; salva(); aggiorna(); };
$('tono').oninput = () => { pref.tono = Number($('tono').value); salva(); };
$('vol').oninput = () => { pref.vol = Number($('vol').value); salva(); };
$('voce').onchange = () => { pref.voce = $('voce').value; salva(); };
$('tutte').onchange = () => { pref.tutte = $('tutte').checked; salva(); riempiVoci(); };
$('evid').onchange = aggiorna;
$('cerca').oninput = () => {
  const q = $('cerca').value.trim().toLowerCase();
  let primo = -1;
  FRASI.forEach((f, k) => { const t = q && f.t.toLowerCase().includes(q);
    $('f' + k).classList.toggle('trov', !!t); if (t && primo < 0) primo = k; });
  if (primo >= 0) centra($('f' + primo));
};
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') { e.preventDefault(); attivo ? ferma() : avvia(); }
  if (e.code === 'ArrowRight') vai(i + 1);
  if (e.code === 'ArrowLeft') vai(i - 1);
});
$('vel').value = pref.vel; $('veln').textContent = Number(pref.vel).toFixed(2) + '×';
$('tono').value = pref.tono; $('vol').value = pref.vol; $('tutte').checked = pref.tutte;
tx.style.fontSize = pref.dim + 'px'; document.body.classList.toggle('chiaro', pref.chiaro);
if ('speechSynthesis' in window) { riempiVoci(); speechSynthesis.onvoiceschanged = riempiVoci; }
aggiorna();
</script>"""


def html_lettore(testo):
    return LETTORE.replace("__TESTO__", _js(testo))


# ================================================== mappa concettuale ======
MAPPA = r"""<!doctype html><meta charset="utf-8">
<style>
  body { margin:0; background:__FONDO__; font-family:system-ui,sans-serif; }
  .barra { position:absolute; top:8px; left:8px; z-index:5; display:flex; gap:6px; flex-wrap:wrap; }
  button { font-size:13px; padding:6px 10px; border-radius:8px; border:1px solid #1baf7a;
           background:rgba(255,255,255,.92); color:#0f5d47; cursor:pointer; }
  svg { width:100%; height:__ALTEZZA__px; display:block; }
  .markmap-foreign { font-size:15px; }
</style>
<div class="barra">
  <button id="adatta">⤢ Adatta</button><button id="zp">＋</button><button id="zm">－</button>
  <button id="apri">Espandi tutto</button><button id="chiudi">Comprimi</button>
  <button id="png">⬇️ PNG</button><button id="svgd">⬇️ SVG</button>
</div>
<svg id="m"></svg>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markmap-lib@0.18.12/dist/browser/index.iife.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markmap-view@0.18.12/dist/browser/index.js"></script>
<script>
const MD = __MD__;
const { Transformer, Markmap } = window.markmap;
const { root } = new Transformer().transform(MD);
const mm = Markmap.create('#m', { colorFreezeLevel: 2, duration: 400, maxWidth: 260,
                                  initialExpandLevel: 3, spacingVertical: 8 }, root);
function piega(n, chiuso, livello) {
  n.payload = Object.assign({}, n.payload, { fold: chiuso && livello > 0 ? 1 : 0 });
  (n.children || []).forEach(c => piega(c, chiuso, livello + 1));
}
document.getElementById('adatta').onclick = () => mm.fit();
document.getElementById('zp').onclick = () => mm.rescale(1.25);
document.getElementById('zm').onclick = () => mm.rescale(0.8);
document.getElementById('apri').onclick = () => { piega(root, false, 0); mm.setData(root); mm.fit(); };
document.getElementById('chiudi').onclick = () => { piega(root, true, 0); mm.setData(root); mm.fit(); };
function scarica(nome, url) { const a = document.createElement('a'); a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove(); }
function svgTesto() {
  const s = document.getElementById('m').cloneNode(true);
  s.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  return new XMLSerializer().serializeToString(s);
}
document.getElementById('svgd').onclick = () => scarica('mappa.svg',
  URL.createObjectURL(new Blob([svgTesto()], { type: 'image/svg+xml' })));
document.getElementById('png').onclick = () => {
  const el = document.getElementById('m'), r = el.getBoundingClientRect();
  const img = new Image();
  img.onload = () => { const c = document.createElement('canvas'); c.width = r.width * 2; c.height = r.height * 2;
    const g = c.getContext('2d'); g.fillStyle = '__FONDO__'; g.fillRect(0, 0, c.width, c.height);
    g.drawImage(img, 0, 0, c.width, c.height); scarica('mappa.png', c.toDataURL('image/png')); };
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgTesto());
};
</script>"""


def html_mappa(markdown, altezza=620, fondo="#ffffff"):
    # la mappa la scrive l'AI: via ogni tag HTML e ogni link «javascript:»,
    # perché la pagina gira con accesso a Quadro
    markdown = re.sub(r"<[^>]*>", "", markdown or "")
    markdown = re.sub(r"(?i)javascript:", "", markdown)
    return (MAPPA.replace("__MD__", _js(markdown)).replace("__ALTEZZA__", str(int(altezza)))
            .replace("__FONDO__", fondo))


def mappa_da_testo(ctx, testo, titolo):
    istr = (
        "Costruisci una mappa concettuale di questo testo, in italiano, come "
        "elenco Markdown gerarchico. Prima riga: «# " + titolo.replace("\n", " ")[:80] + "». Poi "
        "da 4 a 7 rami principali («## »), ognuno con 2-5 sotto-rami («- ») e, "
        "dove serve, un terzo livello («  - »). Ogni voce al massimo 8 parole: "
        "concetti, non frasi. Usa **grassetto** per i termini chiave. Rispondi "
        "solo con il Markdown, senza blocchi di codice.")
    md = ctx.AI.chiedi(istr + "\n\n---\n" + testo[:60000], ctx.chiave_ai, ctx.modello_ai)
    return re.sub(r"^```(?:markdown|md)?\s*|```\s*$", "", md.strip(), flags=re.M).strip()


# ========================================================== infografica ====
TEMI_INFO = {
    "Verde ENESTAR": ("#0f5d47", "#1baf7a", "#e9f7f1", "#ffffff"),
    "Blu tecnico": ("#123a6b", "#2a78d6", "#eaf2fc", "#ffffff"),
    "Arancio caldo": ("#7a3410", "#eb6834", "#fdf0e8", "#ffffff"),
    "Notte": ("#0b1220", "#7ee0b8", "#141d2e", "#1b2638"),
}

INFOGRAFICA = r"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITOLO__</title>
<style>
  :root { --scuro:__C1__; --vivo:__C2__; --fondo:__C3__; --carta:__C4__; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,sans-serif; background:var(--fondo); color:#22302b; }
  body.notte { color:#e7efec; }
  .testa { background:linear-gradient(135deg,var(--scuro),var(--vivo)); color:#fff; padding:34px 22px 28px; }
  .testa h1 { margin:0 0 6px; font-size:clamp(24px,5vw,38px); line-height:1.15; }
  .testa p { margin:0; opacity:.9; font-size:17px; }
  .w { max-width:980px; margin:0 auto; padding:18px; }
  .numeri { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-top:-34px; }
  .num { background:var(--carta); border-radius:16px; padding:16px; box-shadow:0 6px 20px rgba(0,0,0,.08);
         border-top:5px solid var(--vivo); }
  .num b { display:block; font-size:30px; color:var(--vivo); }
  .num span { font-size:14px; opacity:.85; }
  h2 { margin:28px 0 12px; font-size:21px; color:var(--scuro); }
  body.notte h2 { color:var(--vivo); }
  .carte { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
  .carta { background:var(--carta); border-radius:14px; padding:16px; cursor:pointer;
           box-shadow:0 3px 12px rgba(0,0,0,.06); transition:transform .2s, box-shadow .2s; }
  .carta:hover { transform:translateY(-3px); box-shadow:0 10px 24px rgba(0,0,0,.12); }
  .carta .ic { font-size:30px; }
  .carta h3 { margin:6px 0; font-size:17px; }
  .carta p { margin:0; font-size:15px; line-height:1.5; max-height:4.5em; overflow:hidden; transition:max-height .35s; }
  .carta.aperta p { max-height:40em; }
  .passi { position:relative; padding-left:28px; }
  .passi:before { content:''; position:absolute; left:11px; top:6px; bottom:6px; width:3px; background:var(--vivo); border-radius:3px; }
  .passo { position:relative; margin-bottom:14px; background:var(--carta); border-radius:12px; padding:12px 14px; }
  .passo:before { content:attr(data-n); position:absolute; left:-28px; top:10px; width:24px; height:24px;
                  border-radius:50%; background:var(--vivo); color:#fff; font:700 13px/24px sans-serif; text-align:center; }
  table { width:100%; border-collapse:collapse; background:var(--carta); border-radius:12px; overflow:hidden; }
  th, td { padding:10px; text-align:left; border-bottom:1px solid rgba(0,0,0,.08); font-size:15px; }
  th { background:var(--scuro); color:#fff; }
  .chiusa { background:var(--scuro); color:#fff; border-radius:16px; padding:18px 20px; margin:26px 0 10px; font-size:17px; line-height:1.5; }
  .graf { background:var(--carta); border-radius:14px; padding:14px; }
  .appare { opacity:0; transform:translateY(16px); transition:opacity .6s, transform .6s; }
  .appare.vista { opacity:1; transform:none; }
  .fonte { font-size:12.5px; opacity:.65; margin-top:16px; }
</style></head><body class="__CLASSE__">
<div class="testa"><div class="w" style="padding:0 4px"><h1>__TITOLO__</h1><p>__SOTTO__</p></div></div>
<div class="w" id="w"></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
const D = __DATI__;
const w = document.getElementById('w');
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let h = '';
if ((D.numeri || []).length) h += '<div class="numeri">' + D.numeri.map(n =>
  `<div class="num appare"><b data-v="${esc(n.valore)}">${esc(n.valore)}</b><span>${esc(n.etichetta)}</span></div>`).join('') + '</div>';
if ((D.sezioni || []).length) h += '<h2 class="appare">I punti</h2><div class="carte">' + D.sezioni.map(s =>
  `<div class="carta appare" onclick="this.classList.toggle('aperta')"><div class="ic">${esc(s.icona || '•')}</div>
   <h3>${esc(s.titolo)}</h3><p>${esc(s.testo)}</p></div>`).join('') + '</div>';
if ((D.passi || []).length) h += '<h2 class="appare">' + esc(D.titolo_passi || 'Passo dopo passo') + '</h2><div class="passi">' +
  D.passi.map((p, k) => `<div class="passo appare" data-n="${k + 1}"><b>${esc(p.titolo)}</b><br>${esc(p.testo)}</div>`).join('') + '</div>';
if (D.grafico && (D.grafico.valori || []).length) h += '<h2 class="appare">' + esc(D.grafico.titolo || 'I numeri') +
  '</h2><div class="graf appare"><canvas id="g" height="140"></canvas></div>';
if (D.confronto && (D.confronto.righe || []).length) h += '<h2 class="appare">' + esc(D.confronto.titolo || 'Confronto') +
  '</h2><table class="appare"><tr>' + ['', ...(D.confronto.colonne || [])].map(c => `<th>${esc(c)}</th>`).join('') + '</tr>' +
  D.confronto.righe.map(r => '<tr>' + r.map(c => `<td>${esc(c)}</td>`).join('') + '</tr>').join('') + '</table>';
if (D.conclusione) h += `<div class="chiusa appare">💡 ${esc(D.conclusione)}</div>`;
if (D.fonte) h += `<div class="fonte">Fonte: ${esc(D.fonte)}</div>`;
w.innerHTML = h;
// i numeri «contano» fino al valore quando compaiono
function conta(el) {
  const v = el.dataset.v, m = v.match(/^([^\d-]*)(-?[\d.,]+)(.*)$/);
  if (!m) return;
  const fin = parseFloat(m[2].replace(/\./g, '').replace(',', '.'));
  if (!isFinite(fin)) return;
  const dec = (m[2].split(',')[1] || '').length, t0 = performance.now();
  (function passo(t) { const k = Math.min(1, (t - t0) / 1200);
    el.textContent = m[1] + (fin * k).toLocaleString('it-IT', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
    if (k < 1) requestAnimationFrame(passo); else el.textContent = v; })(t0);
}
const oss = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) {
  e.target.classList.add('vista'); e.target.querySelectorAll('b[data-v]').forEach(conta); oss.unobserve(e.target); } }), { threshold: .15 });
document.querySelectorAll('.appare').forEach(el => oss.observe(el));
if (D.grafico && (D.grafico.valori || []).length && window.Chart) {
  const css = getComputedStyle(document.documentElement);
  new Chart(document.getElementById('g'), { type: D.grafico.tipo === 'torta' ? 'doughnut' : 'bar',
    data: { labels: D.grafico.etichette, datasets: [{ label: D.grafico.titolo || '', data: D.grafico.valori,
      backgroundColor: [css.getPropertyValue('--vivo'), css.getPropertyValue('--scuro'), '#eda100', '#2a78d6', '#eb6834', '#9cc7b8'],
      borderRadius: 6 }] },
    options: { plugins: { legend: { display: D.grafico.tipo === 'torta' } }, animation: { duration: 1200 } } });
}
</script></body></html>"""


def infografica_da_testo(ctx, testo, titolo):
    istr = (
        "Trasforma questo testo nei dati di un'infografica, in italiano. "
        "Rispondi SOLO con JSON valido con questi campi:\n"
        '{"titolo": "breve", "sottotitolo": "una frase", '
        '"numeri": [{"valore": "42%", "etichetta": "cosa misura"}], '
        '"sezioni": [{"icona": "un emoji", "titolo": "breve", "testo": "2-3 frasi"}], '
        '"titolo_passi": "titolo della sequenza", "passi": [{"titolo": "...", "testo": "..."}], '
        '"grafico": {"tipo": "barre o torta", "titolo": "...", "etichette": ["..."], "valori": [1, 2]}, '
        '"confronto": {"titolo": "...", "colonne": ["A", "B"], "righe": [["criterio", "a", "b"]]}, '
        '"conclusione": "il messaggio da portarsi a casa"}\n'
        "Regole: da 4 a 6 sezioni. «numeri» e «grafico» SOLO con numeri che "
        "compaiono davvero nel testo: se non ce ne sono, lascia gli elenchi "
        "vuoti. «passi» solo se il testo descrive un processo o una sequenza. "
        "«confronto» solo se il testo confronta delle cose. Non inventare dati.")
    d = _json(ctx.AI.chiedi(istr + "\n\n---\n" + testo[:60000], ctx.chiave_ai, ctx.modello_ai))
    if not isinstance(d, dict):
        raise RuntimeError("la risposta non era nel formato atteso: riprova")
    d.setdefault("titolo", titolo)
    return d


def html_infografica(dati, tema="Verde ENESTAR", fonte=""):
    c1, c2, c3, c4 = TEMI_INFO.get(tema, TEMI_INFO["Verde ENESTAR"])
    dati = dict(dati, fonte=fonte)
    return (INFOGRAFICA.replace("__DATI__", _js(dati))
            .replace("__TITOLO__", _html.escape(str(dati.get("titolo", ""))))
            .replace("__SOTTO__", _html.escape(str(dati.get("sottotitolo", ""))))
            .replace("__C1__", c1).replace("__C2__", c2).replace("__C3__", c3).replace("__C4__", c4)
            .replace("__CLASSE__", "notte" if tema == "Notte" else ""))


# ============================================================ flashcard =====
# Il ripasso «a scatole» (metodo Leitner): ogni carta sta in una scatola da
# 1 a 5. Se la sai sale di una e la rivedi più tardi; se non la sai torna
# nella prima e la rivedi domani. Così passi il tempo sulle carte difficili.
INTERVALLI = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}


def flashcard_da_testo(ctx, testo):
    istr = (
        "Crea da 8 a 15 flashcard per studiare questo testo, in italiano. "
        "Ogni flashcard ha una domanda precisa e una risposta breve (al massimo "
        "due frasi). Copri i concetti più importanti, non i dettagli marginali. "
        'Rispondi SOLO con JSON: [{"d": "domanda", "r": "risposta"}]')
    carte = _json(ctx.AI.chiedi(istr + "\n\n---\n" + testo[:60000], ctx.chiave_ai, ctx.modello_ai))
    if not isinstance(carte, list):
        raise RuntimeError("la risposta non era nel formato atteso: riprova")
    return [c for c in carte if isinstance(c, dict) and c.get("d") and c.get("r")]


def carte(dia):
    """Lo stato attuale di ogni carta (vince l'ultima riga)."""
    colonne = ["Mazzo", "Domanda", "Risposta", "Scatola", "Prossima"]
    if dia is None or dia.empty:
        return pd.DataFrame(columns=colonne)
    f = dia[dia["Tipo"] == "flashcard"].sort_values(["Data", "Ora"], kind="stable")
    righe = {}
    for _, r in f.iterrows():
        try:
            d = json.loads(r["Nota"])
        except (json.JSONDecodeError, TypeError):
            continue
        righe[(r["Attivita"], d.get("d"))] = {
            "Mazzo": r["Attivita"], "Domanda": d.get("d"), "Risposta": d.get("r"),
            "Scatola": int(float(r["Strumento"] or 1)),
            "Prossima": pd.to_datetime(d.get("prossima"), errors="coerce")}
    return pd.DataFrame(list(righe.values()), columns=colonne)


def riga_carta(DIARIO, mazzo, d, r, scatola, oggi):
    prossima = oggi + dt.timedelta(days=INTERVALLI.get(scatola, 1))
    return DIARIO.riga("flashcard", mazzo[:80], str(scatola), 0, None,
                       json.dumps({"d": d, "r": r, "prossima": prossima.isoformat()},
                                  ensure_ascii=False))


# ============================================================= la scheda ===
def _doc():
    return st.session_state.get("lt_doc")


def _imposta(titolo, fonte, testo):
    testo = pulisci(testo)
    st.session_state["lt_doc"] = {"titolo": titolo or "Lettura", "fonte": fonte or "",
                                  "originale": testo, "testo": testo}
    for k in ("lt_mappa", "lt_info", "lt_audio", "lt_carte_nuove"):
        st.session_state.pop(k, None)
    st.session_state["__lt_modifica__"] = testo     # va nella casella al prossimo giro


def mostra(ctx):
    """Tutta la parte «Leggimelo», in 📚 Studio. ctx è quello preparato in app.py."""
    S = st.tabs(["📥 Prendi il testo", "🎧 Ascolta e lavora", "🧠 Mappe e infografiche",
                 "🃏 Flashcard", "📚 Biblioteca"], key="lt_sezione")
    with S[0]:
        _prendi(ctx)
    with S[1]:
        _ascolta(ctx)
    with S[2]:
        _capire(ctx)
    with S[3]:
        _flashcard(ctx)
    with S[4]:
        _biblioteca(ctx)


def _serve_ai(ctx):
    if not ctx.chiave_ai:
        st.error("Serve la chiave di Google AI Studio nei Secrets (`google_api_key`).")
        return False
    return True


def _prendi(ctx):
    st.caption("Da dove arriva il testo. Quando è pronto, passa a «Ascolta e lavora».")
    sorgente = st.radio("Da dove", ["📷 Fotografa", "🖼️ Immagini o PDF", "🔗 Link di un articolo",
                                    "✍️ Incolla"], horizontal=True, key="lt_sorgente",
                        label_visibility="collapsed")
    if sorgente.startswith("📷"):
        foto = st.camera_input("Inquadra la pagina, bene illuminata e dritta", key="lt_cam")
        titolo = st.text_input("Titolo (facoltativo)", key="lt_tit_foto")
        if foto is not None and st.button("📖 Trascrivi la foto", type="primary", key="lt_go_foto") \
                and _serve_ai(ctx):
            try:
                testo = da_file(ctx, [(foto.getvalue(), foto.type or "image/jpeg")])
                _imposta(titolo or "Pagina fotografata", "foto", testo)
                ctx.conferma("Testo pronto: vai su «Ascolta e lavora»")
                st.rerun()
            except Exception as e:
                st.error(f"Non sono riuscito a leggerla: {_errore(e)}")
    elif sorgente.startswith("🖼️"):
        caricati = st.file_uploader("Una o più pagine, nell'ordine giusto",
                                    type=["png", "jpg", "jpeg", "webp", "pdf"],
                                    accept_multiple_files=True, key="lt_file")
        titolo = st.text_input("Titolo (facoltativo)", key="lt_tit_file")
        if caricati and st.button(f"📖 Trascrivi {len(caricati)} file", type="primary", key="lt_go_file") \
                and _serve_ai(ctx):
            try:
                testo = da_file(ctx, [(f.getvalue(), f.type or "image/png") for f in caricati])
                _imposta(titolo or caricati[0].name.rsplit(".", 1)[0], "file", testo)
                ctx.conferma("Testo pronto: vai su «Ascolta e lavora»")
                st.rerun()
            except Exception as e:
                st.error(f"Non sono riuscito a leggerli: {_errore(e)}")
    elif sorgente.startswith("🔗"):
        url = st.text_input("L'indirizzo dell'articolo", key="lt_url",
                            placeholder="https://www.ilpost.it/...")
        if url.strip() and st.button("📖 Prendi l'articolo", type="primary", key="lt_go_url"):
            try:
                with st.spinner("Scarico la pagina e tengo solo l'articolo…"):
                    titolo, autore, data, sito, testo = da_link(url)
                fonte = " · ".join(x for x in (sito, autore, data, url.strip()) if x)
                _imposta(titolo, fonte, testo)
                ctx.conferma(f"Articolo pronto: {parole(testo)} parole")
                st.rerun()
            except Exception as e:
                st.error(f"Non riesco a prenderlo: {_errore(e)}")
    else:
        titolo = st.text_input("Titolo", key="lt_tit_inc")
        testo = st.text_area("Il testo", height=220, key="lt_incolla")
        if testo.strip() and st.button("Usa questo testo", type="primary", key="lt_go_inc"):
            _imposta(titolo or "Testo incollato", "", testo.strip())
            st.rerun()

    d = _doc()
    if d:
        st.success(f"Pronto: **{d['titolo']}** · {parole(d['testo'])} parole · circa "
                   f"{max(1, round(parole(d['testo']) / 160))} minuti di ascolto.")


def _ascolta(ctx):
    d = _doc()
    if not d:
        st.info("Prima prendi un testo nella prima linguetta.")
        return
    st.markdown(f"##### {d['titolo']}")
    if d.get("fonte"):
        st.caption(d["fonte"])
    # la casella «Modifica» è più sotto: il suo contenuto va sistemato ora,
    # prima che venga disegnata, altrimenti Streamlit non lo accetta
    if "__lt_modifica__" in st.session_state:
        st.session_state["lt_modifica"] = st.session_state.pop("__lt_modifica__")

    # ---- i comandi sul testo -------------------------------------------
    b = st.columns(4)
    azione = None
    if b[0].button("📝 Riassumi", width='stretch', key="lt_b_ria"):
        azione = ("riassunto", None)
    if b[1].button("🧒 Spiega semplice", width='stretch', key="lt_b_sem"):
        azione = ("semplice", None)
    if b[2].button("🔑 Punti chiave", width='stretch', key="lt_b_pun"):
        azione = ("punti", None)
    if b[3].button("↩️ Originale", width='stretch', key="lt_b_ori",
                   disabled=d["testo"] == d["originale"]):
        d["testo"] = d["originale"]
        st.session_state["__lt_modifica__"] = d["testo"]
        st.rerun()
    t1, t2 = st.columns([2, 1])
    lingua = t1.selectbox("Traduci in", LINGUE, key="lt_lingua", label_visibility="collapsed")
    if t2.button("🌍 Traduci", width='stretch', key="lt_b_tra"):
        azione = ("traduci", lingua)
    if azione and _serve_ai(ctx):
        try:
            with st.spinner("Lavoro sul testo…"):
                d["testo"] = pulisci(trasforma(ctx, d["originale"] if azione[0] != "traduci" else d["testo"],
                                               azione[0], azione[1] or "italiano"))
            st.session_state["__lt_modifica__"] = d["testo"]
            st.rerun()
        except Exception as e:
            st.error(_errore(e))

    # ---- il lettore nel browser ----------------------------------------
    ctx.pagina_html(html_lettore(d["testo"]), 640)
    st.caption("Spazio = leggi/pausa · ← → = frase precedente/successiva · clic su una "
               "frase = leggi da lì. Voce, velocità e dimensione restano ricordate su "
               "questo dispositivo.")

    # ---- modificare e cercare ------------------------------------------
    with st.expander("✏️ Modifica il testo a mano"):
        nuovo = st.text_area("Testo", height=260, key="lt_modifica", label_visibility="collapsed")
        if st.button("💾 Usa questa versione", key="lt_b_mod"):
            d["testo"] = pulisci(nuovo)
            st.rerun()
    with st.expander("📋 Copia il testo"):
        st.code(d["testo"], language=None, wrap_lines=True)

    # ---- il file audio ---------------------------------------------------
    with st.expander("🎧 Crea un file audio da scaricare (voce di Gemini)"):
        a1, a2, a3 = st.columns(3)
        nomi = list(VOCI_GEMINI)
        voce = a1.selectbox("Voce", nomi, key="lt_voce",
                            format_func=lambda v: f"{v} · {VOCI_GEMINI[v]}")
        stile = a2.selectbox("Stile", list(STILI_VOCE), key="lt_stile")
        formato = a3.selectbox("Formato", ["mp3", "wav"], key="lt_formato")
        pezzi = len(_pezzi(d["testo"]))
        st.caption(f"Il testo verrà letto in {pezzi} pezz{'o' if pezzi == 1 else 'i'}: "
                   f"ci vogliono circa {max(1, pezzi * 15 // 60)} minuti. L'MP3 è circa "
                   "dieci volte più leggero del WAV.")
        c1, c2 = st.columns(2)
        if c1.button("🔈 Prova la voce", key="lt_prova") and _serve_ai(ctx):
            try:
                with st.spinner("…"):
                    st.session_state["lt_prova_audio"] = audio_da_testo(
                        ctx.chiave_ai, "Ciao, sono la voce che leggerà i tuoi testi.",
                        voce, stile, "mp3")
            except Exception as e:
                st.error(_errore(e))
        if st.session_state.get("lt_prova_audio"):
            st.audio(st.session_state["lt_prova_audio"], format="audio/mp3")
        if c2.button("🎙️ Crea il file audio", type="primary", key="lt_crea_audio") and _serve_ai(ctx):
            barra = st.progress(0.0, text="Preparo la voce…")
            try:
                dati = audio_da_testo(ctx.chiave_ai, d["testo"], voce, stile, formato,
                                      lambda i, n: barra.progress(i / n, text=f"Pezzo {i} di {n}"))
                st.session_state["lt_audio"] = (dati, formato)
                barra.empty()
            except Exception as e:
                barra.empty()
                st.error(f"Audio non riuscito: {_errore(e)}")
        if st.session_state.get("lt_audio"):
            dati, formato_a = st.session_state["lt_audio"]
            st.audio(dati, format=f"audio/{'mpeg' if formato_a == 'mp3' else 'wav'}")
            st.download_button(f"⬇️ Scarica l'audio ({formato_a.upper()})", dati,
                               nome_file(d["titolo"], formato_a),
                               "audio/mpeg" if formato_a == "mp3" else "audio/wav",
                               key="lt_scarica_audio")

    # ---- scaricare e salvare --------------------------------------------
    st.markdown("##### ⬇️ Scarica il testo")

    def _prova(fn):
        # un file che non si riesce a fare non deve bloccare la pagina
        try:
            return fn(d)
        except Exception:
            return None
    docx_b, pdf_b = _prova(a_docx), _prova(a_pdf)
    s = st.columns(5)
    s[0].download_button("TXT", d["testo"], nome_file(d["titolo"], "txt"), "text/plain",
                         width='stretch', key="lt_txt")
    s[1].download_button("Markdown", a_markdown(d), nome_file(d["titolo"], "md"), "text/markdown",
                         width='stretch', key="lt_md")
    s[2].download_button("Word", docx_b or b"", nome_file(d["titolo"], "docx"),
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                         width='stretch', key="lt_docx", disabled=docx_b is None)
    s[3].download_button("PDF", pdf_b or b"", nome_file(d["titolo"], "pdf"), "application/pdf",
                         width='stretch', key="lt_pdf", disabled=pdf_b is None)
    s[4].download_button("Pagina web", a_html(d), nome_file(d["titolo"], "html"), "text/html",
                         width='stretch', key="lt_html")

    if st.button("💾 Salva nella biblioteca", key="lt_salva", type="primary"):
        ctx.diario_scrivi(ctx.DIARIO.riga("lettura", d["titolo"][:80], d.get("fonte", "")[:200],
                                          parole(d["testo"]), None, d["testo"][:30000]))
        ctx.conferma("Salvata nella biblioteca")
        st.rerun()
    if len(d["testo"]) > 30000:
        st.caption("Nella biblioteca restano i primi 30.000 caratteri: è il limite di una "
                   "cella di Excel. Per tenerlo tutto, scaricalo in Word o PDF.")


def _capire(ctx):
    d = _doc()
    if not d:
        st.info("Prima prendi un testo nella prima linguetta.")
        return
    st.markdown("##### 🗺️ Mappa concettuale")
    st.caption("Interattiva: clic su un nodo per aprirlo o chiuderlo, rotellina o due "
               "dita per lo zoom, trascina per spostarla.")
    if st.button("✨ Crea la mappa", key="lt_b_mappa") and _serve_ai(ctx):
        try:
            with st.spinner("Costruisco la mappa…"):
                st.session_state["lt_mappa"] = mappa_da_testo(ctx, d["testo"], d["titolo"])
        except Exception as e:
            st.error(_errore(e))
    if st.session_state.get("lt_mappa"):
        fondo = st.radio("Sfondo", ["chiaro", "scuro"], horizontal=True, key="lt_mappa_fondo")
        colore = "#ffffff" if fondo == "chiaro" else "#14201c"
        ctx.pagina_html(html_mappa(st.session_state["lt_mappa"], 600, colore), 620)
        with st.expander("✏️ Modifica i rami della mappa"):
            st.caption("È un elenco: «#» il centro, «##» i rami, «-» i sotto-rami.")
            md = st.text_area("Mappa", st.session_state["lt_mappa"], height=260,
                              key=f"lt_mappa_testo_{abs(hash(st.session_state['lt_mappa'])) % 10**8}",
                              label_visibility="collapsed")
            if st.button("Aggiorna la mappa", key="lt_mappa_agg"):
                st.session_state["lt_mappa"] = md
                st.rerun()
        m1, m2 = st.columns(2)
        m1.download_button("⬇️ Mappa interattiva (HTML)", html_mappa(st.session_state["lt_mappa"], 900, colore),
                           nome_file(d["titolo"] + "_mappa", "html"), "text/html", width='stretch',
                           key="lt_mappa_html")
        m2.download_button("⬇️ Mappa come testo (Markdown)", st.session_state["lt_mappa"],
                           nome_file(d["titolo"] + "_mappa", "md"), "text/markdown", width='stretch',
                           key="lt_mappa_md")
        st.caption("PNG e SVG si scaricano dai pulsanti dentro la mappa.")

    st.divider()
    st.markdown("##### 📊 Infografica")
    st.caption("I numeri si animano, le schede si aprono con un clic. L'AI usa solo i "
               "numeri che stanno nel testo: se non ce ne sono, l'infografica non ne mette.")
    tema = st.selectbox("Colori", list(TEMI_INFO), key="lt_tema")
    if st.button("✨ Crea l'infografica", key="lt_b_info") and _serve_ai(ctx):
        try:
            with st.spinner("La preparo…"):
                st.session_state["lt_info"] = infografica_da_testo(ctx, d["testo"], d["titolo"])
        except Exception as e:
            st.error(_errore(e))
    if st.session_state.get("lt_info"):
        pagina = html_infografica(st.session_state["lt_info"], tema, d.get("fonte", ""))
        ctx.pagina_html(pagina, 900)
        st.download_button("⬇️ Scarica l'infografica (pagina HTML)", pagina,
                           nome_file(d["titolo"] + "_infografica", "html"), "text/html",
                           key="lt_info_html")
        st.caption("Aperta nel browser si stampa anche in PDF (Ctrl+P → Salva come PDF).")


def _flashcard(ctx):
    oggi = ctx.DIARIO.oggi()
    tutte = carte(ctx.DIA)
    da_fare = tutte[(tutte["Prossima"].isna()) | (tutte["Prossima"] <= pd.Timestamp(oggi))] \
        if not tutte.empty else tutte
    st.caption("Domande e risposte create dai testi che leggi, da ripassare a "
               "intervalli crescenti: quelle che sai tornano sempre più di rado, "
               "quelle che sbagli tornano domani.")
    k = st.columns(3)
    k[0].metric("Carte in tutto", len(tutte))
    k[1].metric("Da ripassare oggi", len(da_fare))
    k[2].metric("Mazzi", tutte["Mazzo"].nunique() if not tutte.empty else 0)

    d = _doc()
    if d:
        if st.button(f"✨ Crea le flashcard da «{d['titolo'][:40]}»", key="lt_b_fc") and _serve_ai(ctx):
            try:
                with st.spinner("Preparo le domande…"):
                    st.session_state["lt_carte_nuove"] = flashcard_da_testo(ctx, d["testo"])
            except Exception as e:
                st.error(_errore(e))
    nuove = st.session_state.get("lt_carte_nuove")
    if nuove:
        st.markdown(f"**{len(nuove)} carte pronte.** Controllale e salvale:")
        tab = st.data_editor(pd.DataFrame([{"Tieni": True, "Domanda": c["d"], "Risposta": c["r"]}
                                           for c in nuove]), hide_index=True, width='stretch',
                             key="lt_fc_editor", num_rows="dynamic")
        mazzo = st.text_input("Nome del mazzo", (d or {}).get("titolo", "Mazzo")[:80], key="lt_fc_mazzo")
        if st.button("💾 Salva il mazzo", type="primary", key="lt_fc_salva"):
            def t(x):
                return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x).strip()
            righe = [riga_carta(ctx.DIARIO, mazzo, t(r.get("Domanda")), t(r.get("Risposta")), 1,
                                oggi - dt.timedelta(days=1))
                     for r in tab.to_dict("records")
                     if r.get("Tieni") is not False and t(r.get("Domanda")) and t(r.get("Risposta"))]
            if righe:
                ctx.diario_scrivi(righe)
                st.session_state.pop("lt_carte_nuove", None)
                ctx.conferma(f"Salvate {len(righe)} carte nel mazzo «{mazzo}»")
                st.rerun()

    if da_fare.empty:
        if not tutte.empty:
            st.success("Niente da ripassare oggi. 👏")
        return
    st.divider()
    mazzi = ["tutti"] + sorted(da_fare["Mazzo"].unique())
    scelta = st.selectbox("Ripassa", mazzi, key="lt_fc_quale")
    giro = da_fare if scelta == "tutti" else da_fare[da_fare["Mazzo"] == scelta]
    c = giro.iloc[0]
    with st.container(border=True):
        st.caption(f"{c['Mazzo']} · scatola {c['Scatola']} di 5 · ne restano {len(giro)}")
        st.markdown(f"### {c['Domanda']}")
        if st.session_state.get("lt_fc_girata") == c["Domanda"]:
            st.markdown(f"**Risposta:** {c['Risposta']}")
            r1, r2 = st.columns(2)
            if r1.button("✅ La sapevo", type="primary", width='stretch', key="lt_fc_si"):
                ctx.diario_scrivi(riga_carta(ctx.DIARIO, c["Mazzo"], c["Domanda"], c["Risposta"],
                                             min(5, c["Scatola"] + 1), oggi))
                st.session_state.pop("lt_fc_girata", None)
                st.rerun()
            if r2.button("❌ Non la sapevo", width='stretch', key="lt_fc_no"):
                ctx.diario_scrivi(riga_carta(ctx.DIARIO, c["Mazzo"], c["Domanda"], c["Risposta"], 1, oggi))
                st.session_state.pop("lt_fc_girata", None)
                st.rerun()
        elif st.button("🔄 Gira la carta", width='stretch', key="lt_fc_gira"):
            st.session_state["lt_fc_girata"] = c["Domanda"]
            st.rerun()
        ctx.ascolta(c["Domanda"], "🔊 Leggi la domanda")


def _biblioteca(ctx):
    dia = ctx.DIA
    lett = dia[dia["Tipo"] == "lettura"] if not dia.empty else dia
    if lett.empty:
        st.info("La biblioteca è vuota: salva una lettura da «Ascolta e lavora».")
        return
    def quando(r):
        try:
            return pd.Timestamp(r["Data"]) + pd.to_timedelta(str(r["Ora"] or "00:00")[:5] + ":00")
        except (ValueError, TypeError):
            return pd.Timestamp(r["Data"])
    # tolta vale solo se è successo dopo l'ultimo salvataggio: se la risalvi, torna
    tolte = {}
    for _, r in dia[dia["Tipo"] == "lettura_rimossa"].iterrows():
        tolte[r["Attivita"]] = max(tolte.get(r["Attivita"], pd.Timestamp.min), quando(r))
    lett = lett.sort_values(["Data", "Ora"], ascending=False, kind="stable").drop_duplicates("Attivita")
    lett = lett[[r["Attivita"] not in tolte or quando(r) > tolte[r["Attivita"]] for _, r in lett.iterrows()]]
    if lett.empty:
        st.info("La biblioteca è vuota: salva una lettura da «Ascolta e lavora».")
        return
    cerca = st.text_input("🔎 Cerca nella biblioteca", key="lt_bib_cerca")
    if cerca.strip():
        q = cerca.strip().lower()
        lett = lett[lett["Attivita"].str.lower().str.contains(q, regex=False)
                    | lett["Nota"].str.lower().str.contains(q, regex=False)]
    st.caption(f"{len(lett)} letture.")
    for i, (_, r) in enumerate(lett.head(60).iterrows()):
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"**{r['Attivita']}**")
            c1.caption(f"{r['Data']:%d/%m/%Y} · {int(r['Minuti'] or 0)} parole"
                       + (f" · {r['Strumento']}" if r["Strumento"] else ""))
            if c2.button("📖 Apri", key=f"lt_bib_apri_{i}", width='stretch'):
                _imposta(r["Attivita"], r["Strumento"], r["Nota"])
                ctx.conferma("Aperta: la trovi in «Ascolta e lavora»")
                st.rerun()
            if c3.button("🗑️", key=f"lt_bib_via_{i}", width='stretch', help="Togli dalla biblioteca"):
                ctx.diario_scrivi(ctx.DIARIO.riga("lettura_rimossa", r["Attivita"], "", 0, None, ""))
                st.rerun()
