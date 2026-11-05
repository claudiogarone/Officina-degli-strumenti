"""
equilibrio.py — la scheda 🌿 Equilibrio di Quadro.

Quattro parti:
    🌬️ Respira       respirazione guidata e conteggio dei respiri al minuto
    🧘 Presenza      timer di meditazione con campana e pratiche guidate a voce
    🌙 Stile di vita check-in serale, dati dello smartwatch da una foto, lettura AI
    🌱 Crescita      obiettivi del trimestre e revisione settimanale

Prima c'erano anche «Leggimelo» e gli aforismi: Leggimelo ora sta in
📚 Studio (lettura.py), gli aforismi nella 👩‍💼 Segretaria (aforismi.py) e
quello del momento in cima alla Scrivania. Le funzioni sugli aforismi qui
sotto restano solo come scorciatoie, perché app.py le usa ancora.

=============================================================================
COME È FATTO, per chi vuole metterci le mani
=============================================================================
Tutto quello che si muove nel browser — il cerchio del respiro, il timer, la
voce — è una piccola pagina HTML con dentro JavaScript: le funzioni `html_…`
qui sotto la costruiscono come testo e Quadro la mostra in un riquadro. Il
motivo è che Streamlit ricarica la pagina a ogni clic: un cerchio che si
gonfia per cinque secondi, fatto in Python, verrebbe interrotto di continuo.
Nel browser invece gira liscio, anche dal telefono.

Il rovescio della medaglia: quello che succede dentro il riquadro Python non
lo vede. Per questo, finita una pratica, c'è un pulsante «Registra» a parte.

La voce è quella del browser (gratuita, nessuna chiave). Le voci disponibili
dipendono dal dispositivo: su Android quelle di Google, su Windows con Edge
le voci «Natural» di Microsoft, che sono le migliori.

DOVE FINISCONO I DATI
    Pratiche, respiri e check-in → nell'archivio PRIVATO, Quadro_Taratura.xlsx,
                                   lo stesso della Taratura (stessa password).
    Obiettivi, revisioni, aforismi salvati, impostazioni → nel diario normale.

Tutto quello che Quadro deve sapere dall'esterno arriva in `ctx`, un
contenitore preparato in app.py: così questo file non dipende dal resto e si
può provare da solo.
"""

import datetime as dt
import json
import re

import pandas as pd
import streamlit as st


# =========================================================== utilità ======
def _js(valore):
    """Un valore Python dentro JavaScript, senza rompere la pagina."""
    return json.dumps(valore, ensure_ascii=False).replace("</", "<\\/")


def _messaggio_errore(e):
    return getattr(e, "messaggio", None) or str(e)


def _json_da_testo(testo):
    """Il primo oggetto JSON dentro una risposta dell'AI, o None."""
    m = re.search(r"\{.*\}", testo or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def impostazione(df, nome, predefinita):
    """L'ultima impostazione salvata con quel nome nel diario, o quella data."""
    if df is None or df.empty:
        return dict(predefinita)
    righe = df[(df["Tipo"] == "impostazione") & (df["Attivita"] == nome)]
    if righe.empty:
        return dict(predefinita)
    try:
        # Data e Ora, con ordinamento stabile: due salvataggi nello stesso giorno
        # devono restare nell'ordine in cui li hai fatti
        salvata = json.loads(righe.sort_values(["Data", "Ora"], kind="stable").iloc[-1]["Nota"])
    except (json.JSONDecodeError, TypeError):
        return dict(predefinita)
    return {**predefinita, **salvata}


# ============================================== la voce, in comune =========
# Il pezzo di JavaScript che sceglie la voce, la velocità e il tono. Lo usano
# sia le pratiche guidate sia il lettore di «Leggimelo». Le scelte restano nel browser
# (localStorage), quindi ogni dispositivo ricorda le sue: le voci cambiano da
# un dispositivo all'altro, ha senso così.
_STILE = """
<style>
  :root { --verde:#1baf7a; --fondo:#0f2a24; --testo:#eef7f3; --tenue:#9cc7b8; }
  body { margin:0; font-family: system-ui, sans-serif; background:var(--fondo);
         color:var(--testo); }
  .riquadro { padding:14px 16px; }
  button { font-size:15px; padding:8px 14px; border-radius:10px; cursor:pointer;
           border:1px solid var(--verde); background:var(--verde); color:#fff; }
  button.secondario { background:transparent; color:var(--testo); }
  button:disabled { opacity:.45; cursor:default; }
  select, input[type=range] { max-width:100%; }
  label { font-size:13px; color:var(--tenue); }
  .riga { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0; }
</style>
"""

_VOCE_JS = """
<div class="riga">
  <label>Voce <select id="qv_voce"></select></label>
  <label><input type="checkbox" id="qv_tutte"> tutte le lingue</label>
</div>
<div class="riga">
  <label>Velocità <input type="range" id="qv_vel" min="0.5" max="2" step="0.05"></label>
  <span id="qv_vel_n"></span>
  <label>Tono <input type="range" id="qv_tono" min="0.5" max="1.6" step="0.05"></label>
</div>
<script>
const QV = (() => {
  const CHIAVE = 'quadro_voce';
  let pref = { voce: '', vel: VEL_INIZIALE, tono: 1, tutte: false };
  try { Object.assign(pref, JSON.parse(localStorage.getItem(CHIAVE) || '{}')); } catch (e) {}
  const sel = document.getElementById('qv_voce');
  const vel = document.getElementById('qv_vel');
  const velN = document.getElementById('qv_vel_n');
  const tono = document.getElementById('qv_tono');
  const tutte = document.getElementById('qv_tutte');
  vel.value = pref.vel; tono.value = pref.tono; tutte.checked = pref.tutte;
  velN.textContent = Number(pref.vel).toFixed(2) + '×';
  function salva() {
    pref = { voce: sel.value, vel: Number(vel.value), tono: Number(tono.value),
             tutte: tutte.checked };
    velN.textContent = pref.vel.toFixed(2) + '×';
    try { localStorage.setItem(CHIAVE, JSON.stringify(pref)); } catch (e) {}
  }
  function riempi() {
    if (!('speechSynthesis' in window)) return;
    const voci = speechSynthesis.getVoices().filter(
      v => tutte.checked || (v.lang || '').toLowerCase().startsWith('it'));
    sel.innerHTML = '';
    voci.forEach(v => {
      const o = document.createElement('option');
      o.value = v.name; o.textContent = v.name + ' (' + v.lang + ')';
      if (v.name === pref.voce) o.selected = true;
      sel.appendChild(o);
    });
    if (!voci.length) {
      const o = document.createElement('option');
      o.textContent = 'nessuna voce italiana: spunta «tutte le lingue»';
      sel.appendChild(o);
    }
  }
  [sel, vel, tono].forEach(x => x.addEventListener('input', salva));
  tutte.addEventListener('change', () => { salva(); riempi(); });
  if ('speechSynthesis' in window) {
    riempi();
    speechSynthesis.onvoiceschanged = riempi;   // su Chrome arrivano dopo
  }
  return {
    frase(testo) {
      const u = new SpeechSynthesisUtterance(testo);
      const v = speechSynthesis.getVoices().find(x => x.name === sel.value);
      if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = 'it-IT'; }
      u.rate = Number(vel.value); u.pitch = Number(tono.value);
      return u;
    }
  };
})();
</script>
"""


def _voce(velocita=1.0):
    return _VOCE_JS.replace("VEL_INIZIALE", str(float(velocita)))


# ============================================================ respiro =====
def cicli(ritmo, minuti):
    """Quanti cicli interi stanno nei minuti scelti, con il limite del ritmo."""
    durata = sum(s for _, s in ritmo["fasi"]) or 1
    n = max(1, round(minuti * 60 / durata))
    if ritmo.get("cicli_massimi"):
        n = min(n, int(ritmo["cicli_massimi"]))
    return n


def html_respiro(ritmo, minuti, guida="voce"):
    """Il cerchio che si gonfia e si sgonfia. guida: voce, bip o silenzio."""
    n = cicli(ritmo, minuti)
    return _STILE + f"""
<div class="riquadro" style="text-align:center">
  <div style="height:220px;display:flex;align-items:center;justify-content:center">
    <div id="c" style="width:190px;height:190px;border-radius:50%;
         background:radial-gradient(circle at 35% 35%,#7ee0b8,#1baf7a 60%,#11735a);
         box-shadow:0 0 40px rgba(27,175,122,.45);transform:scale(.55)"></div>
  </div>
  <div id="f" style="font-size:24px;font-weight:600;min-height:32px">Pronto</div>
  <div id="t" style="color:var(--tenue);margin:4px 0 10px">{n} cicli</div>
  <button id="b">▶ Comincia</button>
</div>
<script>
const FASI = {_js(ritmo["fasi"])};
const CICLI = {n};
const GUIDA = {_js(guida)};
const c = document.getElementById('c'), f = document.getElementById('f'),
      t = document.getElementById('t'), b = document.getElementById('b');
let attivo = false, timer = null, passo = 0, audio = null, blocco = null;
const DURATA = FASI.reduce((s, x) => s + x[1], 0) * CICLI;
let trascorsi = 0;

function bip(freq) {{
  if (GUIDA !== 'bip') return;
  try {{
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = freq; o.connect(g); g.connect(audio.destination);
    const ora = audio.currentTime;
    g.gain.setValueAtTime(0.0001, ora);
    g.gain.exponentialRampToValueAtTime(0.25, ora + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ora + 0.4);
    o.start(ora); o.stop(ora + 0.45);
  }} catch (e) {{}}
}}
function di(testo) {{
  if (GUIDA !== 'voce' || !('speechSynthesis' in window)) return;
  try {{
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(testo);
    u.lang = 'it-IT'; u.rate = 0.9;
    const v = speechSynthesis.getVoices().filter(
      x => (x.lang || '').toLowerCase().startsWith('it'));
    if (v.length) u.voice = v[0];
    speechSynthesis.speak(u);
  }} catch (e) {{}}
}}
function scala(nome) {{
  const n = nome.toLowerCase();
  if (n.startsWith('ancora')) return 1.12;
  if (n.startsWith('inspira')) return 1.0;
  if (n.startsWith('espira')) return 0.5;
  return null;                         // trattieni: il cerchio resta com'è
}}
function orologio() {{
  const r = Math.max(0, DURATA - trascorsi);
  t.textContent = 'ciclo ' + Math.min(CICLI, Math.floor(passo / FASI.length) + 1)
    + ' di ' + CICLI + ' · ' + Math.floor(r / 60) + ':' + String(r % 60).padStart(2, '0');
}}
function fase() {{
  if (!attivo) return;
  if (passo >= CICLI * FASI.length) {{ fine(true); return; }}
  const [nome, sec] = FASI[passo % FASI.length];
  const s = scala(nome);
  c.style.transition = 'transform ' + sec + 's ease-in-out';
  if (s !== null) c.style.transform = 'scale(' + s + ')';
  f.textContent = nome;
  di(nome);
  const n = nome.toLowerCase();
  bip(n.startsWith('espira') ? 330 : (n.startsWith('trattieni') ? 440 : 523));
  orologio();
  passo += 1;
  timer = setTimeout(() => {{ trascorsi += sec; fase(); }}, sec * 1000);
}}
async function tieniAcceso() {{
  try {{ blocco = await navigator.wakeLock.request('screen'); }} catch (e) {{}}
}}
function comincia() {{
  attivo = true; passo = 0; trascorsi = 0;
  b.textContent = '■ Ferma'; b.className = 'secondario';
  tieniAcceso(); fase();
}}
function fine(completa) {{
  attivo = false; clearTimeout(timer);
  c.style.transition = 'transform 1.5s'; c.style.transform = 'scale(.55)';
  f.textContent = completa ? 'Fatto. Resta un momento così.' : 'Fermato';
  b.textContent = '▶ Ricomincia'; b.className = '';
  if (completa) {{ di('Fatto'); bip(392); }}
  try {{ if (blocco) blocco.release(); }} catch (e) {{}}
}}
b.onclick = () => attivo ? fine(false) : comincia();
</script>"""


def html_conta_respiri():
    """Un minuto: premi a ogni espirazione, alla fine dice quanti."""
    return _STILE + """
<div class="riquadro" style="text-align:center">
  <div id="istr" style="color:var(--tenue)">Respira normalmente, senza cambiare niente.
    Premi il pulsante grande <b>a ogni espirazione</b>, per un minuto.</div>
  <div id="n" style="font-size:44px;font-weight:700;margin:8px 0">0</div>
  <div id="t" style="color:var(--tenue);margin-bottom:8px">60 secondi</div>
  <button id="via">▶ Comincia il minuto</button>
  <button id="tap" disabled style="display:block;margin:12px auto 0;width:80%;
          height:84px;font-size:20px">Respiro</button>
</div>
<script>
let n = 0, resta = 60, giro = null;
const N = document.getElementById('n'), T = document.getElementById('t'),
      via = document.getElementById('via'), tap = document.getElementById('tap');
via.onclick = () => {
  n = 0; resta = 60; N.textContent = '0'; tap.disabled = false; via.disabled = true;
  giro = setInterval(() => {
    resta -= 1; T.textContent = resta + ' secondi';
    if (resta <= 0) {
      clearInterval(giro); tap.disabled = true; via.disabled = false;
      via.textContent = '↺ Rifai';
      T.innerHTML = '<b>' + n + ' respiri al minuto</b>. Scrivilo qui sotto per salvarlo.';
    }
  }, 1000);
};
tap.onclick = () => { n += 1; N.textContent = n; };
</script>"""


# ============================================================ presenza ====
def html_timer(minuti, campana_ogni=0):
    """Timer di meditazione con campana all'inizio, a intervalli e alla fine."""
    return _STILE + f"""
<div class="riquadro" style="text-align:center">
  <div id="t" style="font-size:52px;font-weight:700;letter-spacing:1px">{minuti:02d}:00</div>
  <div id="s" style="color:var(--tenue);margin-bottom:10px">
    {"campana ogni " + str(campana_ogni) + " minuti" if campana_ogni else "campana all'inizio e alla fine"}</div>
  <button id="b">▶ Comincia</button>
  <button id="p" class="secondario" disabled>⏸ Pausa</button>
</div>
<script>
const TOT = {int(minuti) * 60}, OGNI = {int(campana_ogni) * 60};
let resta = TOT, giro = null, audio = null, attivo = false, blocco = null;
const T = document.getElementById('t'), S = document.getElementById('s'),
      B = document.getElementById('b'), P = document.getElementById('p');
function campana(colpi) {{
  try {{
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    for (let k = 0; k < (colpi || 1); k++) {{
      const via = audio.currentTime + k * 1.6;
      [[523.25, .30], [1046.5, .14], [1568, .07], [2093, .04]].forEach(([fr, vol]) => {{
        const o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = fr; o.connect(g); g.connect(audio.destination);
        g.gain.setValueAtTime(0.0001, via);
        g.gain.exponentialRampToValueAtTime(vol, via + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, via + 5);
        o.start(via); o.stop(via + 5.1);
      }});
    }}
  }} catch (e) {{}}
}}
function mostra() {{
  T.textContent = String(Math.floor(resta / 60)).padStart(2, '0') + ':' + String(resta % 60).padStart(2, '0');
}}
function passo() {{
  resta -= 1; mostra();
  if (resta <= 0) {{ ferma(true); return; }}
  if (OGNI && (TOT - resta) % OGNI === 0) campana(1);
}}
async function tieniAcceso() {{ try {{ blocco = await navigator.wakeLock.request('screen'); }} catch (e) {{}} }}
function via() {{
  attivo = true; campana(1); tieniAcceso();
  giro = setInterval(passo, 1000);
  B.textContent = '■ Ferma'; P.disabled = false; P.textContent = '⏸ Pausa';
}}
function ferma(finito) {{
  clearInterval(giro); attivo = false; P.disabled = true;
  B.textContent = '▶ Ricomincia';
  if (finito) {{ campana(3); S.textContent = 'Fatto.'; }}
  resta = TOT; if (!finito) mostra();
  try {{ if (blocco) blocco.release(); }} catch (e) {{}}
}}
B.onclick = () => attivo ? ferma(false) : via();
P.onclick = () => {{
  if (giro) {{ clearInterval(giro); giro = null; P.textContent = '▶ Riprendi'; }}
  else {{ giro = setInterval(passo, 1000); P.textContent = '⏸ Pausa'; }}
}};
</script>"""


def html_guidata(pratica, velocita=0.95):
    """Una pratica guidata: legge ogni passo a voce e poi aspetta la sua pausa."""
    totale = sum(p for _, p in pratica["passi"])
    return _STILE + f"""
<div class="riquadro">
  {_voce(velocita)}
  <div id="testo" style="font-size:19px;line-height:1.45;min-height:84px;margin:12px 0">
    Premi «Comincia» e lasciati guidare. Circa {max(1, round(totale / 60))} minuti.</div>
  <div id="stato" style="color:var(--tenue);margin-bottom:8px"></div>
  <button id="b">▶ Comincia</button>
</div>
<script>
const PASSI = {_js(pratica["passi"])};
let i = 0, attivo = false, attesa = null;
const testo = document.getElementById('testo'), stato = document.getElementById('stato'),
      b = document.getElementById('b');
function prossimo() {{
  if (!attivo) return;
  if (i >= PASSI.length) {{ fine('Fatto. Torna con calma.'); return; }}
  const [frase, pausa] = PASSI[i];
  testo.textContent = frase;
  stato.textContent = 'passo ' + (i + 1) + ' di ' + PASSI.length;
  const u = QV.frase(frase);
  u.onend = () => {{ attesa = setTimeout(() => {{ i += 1; prossimo(); }}, pausa * 1000); }};
  u.onerror = u.onend;
  speechSynthesis.speak(u);
}}
function fine(msg) {{
  attivo = false; clearTimeout(attesa);
  try {{ speechSynthesis.cancel(); }} catch (e) {{}}
  testo.textContent = msg; b.textContent = '▶ Ricomincia'; b.className = '';
}}
b.onclick = () => {{
  if (!('speechSynthesis' in window)) {{ testo.textContent = 'Questo browser non legge ad alta voce.'; return; }}
  if (attivo) {{ fine('Fermato.'); return; }}
  attivo = true; i = 0; b.textContent = '■ Ferma'; b.className = 'secondario';
  speechSynthesis.cancel(); prossimo();
}};
</script>"""


# ============================================================ aforismi ====
# Gli aforismi stanno in aforismi.py. Qui restano i nomi che usa app.py, così
# la Scrivania continua a chiamare EQ.riquadro_aforisma come prima.
import aforismi as AF

PREDEFINITE_AFORISMI = AF.PREDEFINITE


def aforisma_corrente(ctx, forza=False):
    return AF.corrente(ctx, forza)


def riquadro_aforisma(ctx, chiave="eq", compatto=False):
    AF.riquadro(ctx, chiave, compatto)


# ======================================================= stile di vita =====
CAMPI_FOTO = (
    "Questa è una schermata di un'app per la salute o di uno smartwatch (per "
    "esempio Honor Health). Estrai solo i valori che vedi chiaramente. "
    "Rispondi SOLO con un JSON con queste chiavi, e null per quelle che non "
    "vedi: {\"data\": \"AAAA-MM-GG oppure null\", \"sonno_ore\": numero, "
    "\"sonno_punteggio\": numero, \"passi\": intero, \"movimento_minuti\": intero, "
    "\"battito_riposo\": intero, \"stress_punteggio\": numero}. Le ore di sonno "
    "in decimali (7 ore e 30 minuti = 7.5). Non inventare niente.")


def checkin_tabella(privato):
    """I check-in come tabella, uno per giorno (vince l'ultimo)."""
    if privato is None or privato.empty:
        return pd.DataFrame()
    c = privato[privato["Tipo"] == "checkin"].sort_values(["Data", "Ora"], kind="stable")
    righe = []
    for _, r in c.iterrows():
        try:
            d = json.loads(r["Nota"])
        except (json.JSONDecodeError, TypeError):
            continue
        d["Giorno"] = pd.to_datetime(r["Attivita"], errors="coerce")
        righe.append(d)
    if not righe:
        return pd.DataFrame()
    t = pd.DataFrame(righe).dropna(subset=["Giorno"])
    return t.drop_duplicates("Giorno", keep="last").sort_values("Giorno")


def lavoro_per_giorno(dia, dal):
    """Minuti di sessione, voto medio e interruzioni per giorno, dal diario."""
    if dia is None or dia.empty:
        return pd.DataFrame()
    d = dia[dia["Data"] >= pd.Timestamp(dal)]
    ses = d[d["Tipo"] == "sessione"]
    if ses.empty:
        return pd.DataFrame()
    g = ses.groupby(ses["Data"].dt.normalize()).agg(
        minuti=("Minuti", "sum"), voto=("Valore", "mean"), sessioni=("Tipo", "size"))
    inter = d[d["Tipo"] == "interruzioni"]
    if not inter.empty:
        g["interruzioni"] = inter.groupby(inter["Data"].dt.normalize())["Valore"].sum()
    return g.fillna(0)


# ============================================================ la scheda ====
SEZIONI = ["🌬️ Respira", "🧘 Presenza", "🌙 Stile di vita", "🌱 Crescita"]


def mostra(ctx):
    st.markdown("#### 🌿 Equilibrio")
    st.caption("Respiro, presenza, stile di vita e crescita. Le pratiche sono "
               "aperte; i tuoi dati personali stanno sotto la password della "
               "Taratura.")

    T = st.tabs(SEZIONI, key="eq_sezione")
    with T[0]:
        _respira(ctx)
    with T[1]:
        _presenza(ctx)
    with T[2]:
        _stile_di_vita(ctx)
    with T[3]:
        _crescita(ctx)


def _registra_pratica(ctx, chiave, tipo, minuti):
    """Il pulsante per mettere la pratica appena fatta nell'archivio privato."""
    with st.form(f"{chiave}_registra", clear_on_submit=True):
        st.markdown("##### ✅ Registra la pratica")
        r1, r2, r3 = st.columns([2, 1, 2])
        tipi = list(ctx.pratiche)
        tipo_r = r1.selectbox("Cosa", tipi, index=tipi.index(tipo) if tipo in tipi else 0)
        min_r = r2.number_input("Minuti", 1, 180, int(minuti))
        qual_r = r3.select_slider("Com'è andata", [1, 2, 3, 4, 5], value=3)
        if st.form_submit_button("💾 Registra", type="primary"):
            ctx.privato_scrivi(ctx.DIARIO.riga("pratica", tipo_r, "Equilibrio",
                                               int(min_r), qual_r, ""))
            ctx.conferma(f"Registrata: {tipo_r}, {int(min_r)} minuti")
            st.rerun()


# -------------------------------------------------------------- respira ---
def _respira(ctx):
    ritmi = ctx.cfg.get("ritmi", [])
    if not ritmi:
        st.error("Nessun ritmo in `equilibrio.json`.")
        return
    c1, c2, c3 = st.columns([2, 1, 1])
    nomi = [r["nome"] for r in ritmi]
    scelta = c1.selectbox("Ritmo", nomi, key="eq_ritmo")
    ritmo = ritmi[nomi.index(scelta)]
    minuti = c2.select_slider("Minuti", [1, 2, 3, 5, 10], value=3, key="eq_resp_min")
    guida = c3.selectbox("Guida", ["voce", "bip", "silenzio"], key="eq_resp_guida")
    st.caption(ritmo.get("nota", "") + "  \n⚠️ " + ctx.cfg.get("avvertenza_respiro", ""))
    ctx.pagina_html(html_respiro(ritmo, minuti, guida), 380)
    n = cicli(ritmo, minuti)
    durata = round(n * sum(s for _, s in ritmo["fasi"]) / 60) or 1
    _registra_pratica(ctx, "eq_resp", "Respirazione", durata)

    with st.expander("📏 Conta i respiri al minuto"):
        st.caption("È la misura più semplice dello stato del momento: a riposo "
                   "un adulto sta di solito fra 12 e 20. Misurala prima e dopo "
                   "una pratica e guarda se scende.")
        ctx.pagina_html(html_conta_respiri(), 300)
        with st.form("eq_respiri", clear_on_submit=True):
            k1, k2 = st.columns(2)
            n_r = k1.number_input("Respiri al minuto", 3, 60, 14)
            quando_r = k2.selectbox("Quando", ["a riposo", "prima della pratica",
                                                "dopo la pratica"])
            if st.form_submit_button("💾 Salva la misura"):
                ctx.privato_scrivi(ctx.DIARIO.riga("respiri", quando_r, "Equilibrio",
                                                   0, int(n_r), ""))
                ctx.conferma(f"Salvato: {int(n_r)} respiri al minuto")
                st.rerun()
        if ctx.aperto():
            p = ctx.privato_leggi()
            r = p[p["Tipo"] == "respiri"].sort_values("Data") if not p.empty else p
            if len(r) >= 2:
                st.line_chart(r.set_index("Data")["Valore"], height=180)


# ------------------------------------------------------------- presenza ---
def _presenza(ctx):
    st.markdown("##### ⏳ Timer di meditazione")
    c1, c2 = st.columns(2)
    minuti = c1.select_slider("Minuti", [3, 5, 10, 15, 20, 30, 45], value=10, key="eq_med_min")
    ogni = c2.selectbox("Campana in mezzo", [0, 1, 2, 5, 10],
                        format_func=lambda m: "nessuna" if m == 0 else f"ogni {m} minuti",
                        key="eq_med_ogni")
    ctx.pagina_html(html_timer(int(minuti), int(ogni)), 200)

    st.markdown("##### 🎧 Pratiche guidate")
    guidate = ctx.cfg.get("guidate", [])
    if guidate:
        nomi = [g["nome"] for g in guidate]
        scelta = st.selectbox("Quale", nomi, key="eq_guidata")
        ctx.pagina_html(html_guidata(guidate[nomi.index(scelta)]), 330)
        st.caption("La voce e la velocità si scelgono nel riquadro, e il "
                   "dispositivo se le ricorda.")
    _registra_pratica(ctx, "eq_med", "Meditazione", int(minuti))


# -------------------------------------------------------- stile di vita ---
def _stile_di_vita(ctx):
    if not ctx.aperto():
        st.info("🔒 Questa parte è riservata, con la stessa password della "
                "Taratura. Si richiude da sola dopo qualche minuto.")
        with st.form("eq_ingresso"):
            pw = st.text_input("Password", type="password", label_visibility="collapsed",
                               placeholder="Password")
            if st.form_submit_button("Apri", type="primary"):
                if ctx.sblocca(pw):
                    st.rerun()
                else:
                    st.error("Password errata.")
        return

    # i valori letti da una foto vanno messi nelle caselle PRIMA di disegnarle
    for k, v in (st.session_state.pop("__eq_ci_prefill__", None) or {}).items():
        st.session_state[f"eq_ci_{k}"] = v

    st.markdown("##### 🌙 Il check-in di oggi")
    st.caption("Trenta secondi la sera. Dopo un paio di settimane si vede cosa "
               "ti dà energia e cosa te la toglie.")

    with st.expander("⌚ Leggi i dati dallo smartwatch, da una foto"):
        st.caption("Fai uno screenshot di Honor Health (sonno, passi, battito, "
                   "stress) e caricalo qui: l'AI legge i numeri e riempie le "
                   "caselle. Controllali prima di salvare.")
        foto = st.file_uploader("Gli screenshot", type=["png", "jpg", "jpeg", "webp"],
                                accept_multiple_files=True, key="eq_ci_foto")
        if foto and st.button("Leggi i numeri", key="eq_ci_leggi", type="primary"):
            if not ctx.chiave_ai:
                st.error("Serve la chiave di Google AI Studio nei Secrets.")
            else:
                trovati = {}
                try:
                    with st.spinner("Leggo…"):
                        for f in foto:
                            d = _json_da_testo(ctx.VOCE._chiedi_al_modello(
                                f.getvalue(), f.type or "image/png", CAMPI_FOTO,
                                ctx.chiave_ai, ctx.modello_ai)) or {}
                            trovati.update({k: v for k, v in d.items() if v not in (None, "")})
                except Exception as e:
                    st.error(f"Non sono riuscito a leggerla: {_messaggio_errore(e)}")
                mappa = {"sonno_ore": "sonno", "passi": "passi",
                         "movimento_minuti": "movimento", "battito_riposo": "battito",
                         "stress_punteggio": "stress_watch", "sonno_punteggio": "sonno_punti"}
                pre = {}
                for k, campo in mappa.items():
                    if k in trovati:
                        try:
                            pre[campo] = float(trovati[k])
                        except (TypeError, ValueError):
                            pass
                if trovati.get("data"):
                    try:
                        pre["giorno"] = dt.date.fromisoformat(str(trovati["data"])[:10])
                    except ValueError:
                        pass
                if pre:
                    st.session_state["__eq_ci_prefill__"] = pre
                    st.rerun()
                elif trovati is not None:
                    st.warning("Non ho trovato numeri leggibili in queste immagini.")

    # I valori di partenza stanno nello stato della sessione, non nelle
    # caselle: così la foto dello smartwatch può sovrascriverli senza che
    # Streamlit protesti per due valori iniziali diversi.
    for k, v in {"giorno": ctx.DIARIO.oggi(), "sonno": 7.0, "qsonno": 3,
                 "movimento": 0.0, "passi": 0.0, "schermo": 2.0, "stress": 3,
                 "energia": 3, "battito": 0.0, "stress_watch": 0.0,
                 "sonno_punti": 0.0}.items():
        st.session_state.setdefault(f"eq_ci_{k}", v)

    g1, g2, g3 = st.columns(3)
    giorno = g1.date_input("Giorno", format="DD/MM/YYYY", key="eq_ci_giorno")
    sonno = g2.number_input("Ore di sonno", min_value=0.0, max_value=14.0, step=0.25,
                            key="eq_ci_sonno")
    q_sonno = g3.select_slider("Com'è stato il sonno", [1, 2, 3, 4, 5], key="eq_ci_qsonno")
    m1, m2, m3 = st.columns(3)
    movimento = m1.number_input("Minuti di movimento", min_value=0.0, max_value=600.0,
                                step=5.0, key="eq_ci_movimento")
    passi = m2.number_input("Passi", min_value=0.0, max_value=100000.0, step=500.0,
                            key="eq_ci_passi")
    schermo = m3.number_input("Ore di schermo fuori dal lavoro", min_value=0.0,
                              max_value=16.0, step=0.5, key="eq_ci_schermo")
    s1, s2 = st.columns(2)
    stress = s1.select_slider("Stress", [1, 2, 3, 4, 5], key="eq_ci_stress",
                              format_func=lambda v: {1: "1 · sereno", 3: "3", 5: "5 · al limite"}.get(v, str(v)))
    energia = s2.select_slider("Energia", [1, 2, 3, 4, 5], key="eq_ci_energia",
                               format_func=lambda v: {1: "1 · a terra", 3: "3", 5: "5 · carico"}.get(v, str(v)))
    w1, w2, w3 = st.columns(3)
    battito = w1.number_input("Battito a riposo (dal watch)", min_value=0.0, max_value=200.0,
                              step=1.0, key="eq_ci_battito", help="0 = non registrato")
    stress_w = w2.number_input("Stress dal watch (0-100)", min_value=0.0, max_value=100.0,
                               step=1.0, key="eq_ci_stress_watch", help="0 = non registrato")
    sonno_p = w3.number_input("Punteggio sonno dal watch", min_value=0.0, max_value=100.0,
                              step=1.0, key="eq_ci_sonno_punti", help="0 = non registrato")
    nota = ctx.VOCE.campo("Una riga sulla giornata", "eq_ci_nota", ctx.chiave_ai,
                          ctx.modello_ai, altezza=80)
    if st.button("💾 Salva il check-in", type="primary", key="eq_ci_salva"):
        valori = {"sonno": sonno, "qualita_sonno": q_sonno, "movimento": movimento,
                  "passi": passi, "schermo": schermo, "stress": stress, "energia": energia,
                  "battito": battito or None, "stress_watch": stress_w or None,
                  "sonno_punti": sonno_p or None, "nota": (nota or "").strip()}
        ctx.privato_scrivi(ctx.DIARIO.riga(
            "checkin", giorno.isoformat(), "Equilibrio", 0, stress,
            json.dumps(valori, ensure_ascii=False),
            # l'ora vera del salvataggio: se lo correggi, vince la versione nuova
            quando=dt.datetime.combine(giorno, ctx.DIARIO.adesso().time().replace(second=0, microsecond=0))))
        ctx.VOCE.svuota("eq_ci_nota")
        for k in ("battito", "stress_watch", "sonno_punti", "passi", "movimento"):
            st.session_state.pop(f"eq_ci_{k}", None)
        ctx.conferma(f"Check-in del {giorno:%d/%m} salvato")
        st.rerun()

    _andamento_stile(ctx)


def _andamento_stile(ctx):
    privato = ctx.privato_leggi()
    ci = checkin_tabella(privato)
    if ci.empty:
        st.caption("Ancora nessun check-in salvato.")
        return
    st.divider()
    st.markdown("##### 📈 Come stai andando")
    giorni = st.select_slider("Periodo", [14, 30, 90, 365], value=30, key="eq_ci_periodo",
                              format_func=lambda g: f"ultimi {g} giorni")
    dal = pd.Timestamp(ctx.DIARIO.oggi()) - pd.Timedelta(days=giorni)
    v = ci[ci["Giorno"] >= dal].set_index("Giorno")
    if v.empty:
        st.caption("Nessun check-in in questo periodo.")
        return
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Sonno medio", f"{v['sonno'].mean():.1f} h")
    a2.metric("Stress medio", f"{v['stress'].mean():.1f} / 5")
    a3.metric("Energia media", f"{v['energia'].mean():.1f} / 5")
    a4.metric("Check-in", len(v))
    st.line_chart(v[["stress", "energia", "qualita_sonno"]].rename(
        columns={"qualita_sonno": "sonno (qualità)"}), height=220)
    st.bar_chart(v[["sonno", "schermo"]], height=200)

    # un primo confronto senza AI: l'energia nei giorni dopo poco sonno
    poco, bene = v[v["sonno"] < 6], v[v["sonno"] >= 7]
    if len(poco) >= 3 and len(bene) >= 3:
        st.info(f"Con meno di 6 ore di sonno la tua energia media è "
                f"**{poco['energia'].mean():.1f}**, con 7 o più è "
                f"**{bene['energia'].mean():.1f}** ({len(poco)} e {len(bene)} giorni).")

    if st.button("✨ Cosa vedi nelle ultime settimane?", key="eq_ci_ai"):
        if not ctx.chiave_ai:
            st.error("Serve la chiave di Google AI Studio nei Secrets.")
            return
        lav = lavoro_per_giorno(ctx.DIA, dal)
        prat = privato[(privato["Tipo"] == "pratica") & (privato["Data"] >= dal)] \
            if not privato.empty else privato
        tab_ci = v.drop(columns=[c for c in ("nota",) if c in v.columns]).round(1).to_csv()
        prompt = (
            "Sei un assistente che aiuta una persona a osservare il proprio stile "
            "di vita. NON sei un medico né uno psicologo: non fare diagnosi, non "
            "parlare di farmaci, non dare indicazioni mediche. Se i dati "
            "suggeriscono un malessere che dura, consiglia con delicatezza di "
            "parlarne con il proprio medico.\n\n"
            f"Check-in serali (stress ed energia da 1 a 5):\n{tab_ci}\n\n"
            f"Lavoro per giorno (minuti di sessione, voto medio, interruzioni):\n"
            f"{lav.round(1).to_csv() if not lav.empty else 'nessun dato'}\n\n"
            f"Pratiche (respiro, meditazione…): {len(prat)} in questo periodo, "
            f"{int(prat['Minuti'].sum()) if not prat.empty else 0} minuti in tutto.\n\n"
            "Scrivi in italiano, frasi brevi: tre osservazioni concrete basate "
            "solo su questi numeri (collegamenti fra sonno, schermo, movimento, "
            "stress, energia e lavoro), dicendo quando i dati sono pochi per "
            "esserne sicuri. Poi UN piccolo esperimento da provare la prossima "
            "settimana. Niente frasi motivazionali generiche.")
        try:
            with st.spinner("Guardo i tuoi dati…"):
                st.session_state["eq_ci_lettura"] = ctx.AI.chiedi(
                    prompt, ctx.chiave_ai, ctx.modello_ai)
        except Exception as e:
            st.error(_messaggio_errore(e))
    if st.session_state.get("eq_ci_lettura"):
        with st.container(border=True):
            st.markdown(st.session_state["eq_ci_lettura"])
            ctx.ascolta(re.sub(r"[*#_`]", "", st.session_state["eq_ci_lettura"]),
                        "🔊 Ascolta")


# -------------------------------------------------------------- crescita ---
STATI_OBIETTIVO = ["in corso", "raggiunto", "lasciato"]


def trimestre(giorno):
    return f"T{(giorno.month - 1) // 3 + 1} {giorno.year}"


def obiettivi(dia):
    """Un obiettivo per riga, con l'ultimo stato registrato."""
    if dia is None or dia.empty:
        return pd.DataFrame(columns=["Obiettivo", "Stato", "Prossimo passo",
                                     "Perché", "Trimestre", "Aggiornato"])
    o = dia[dia["Tipo"] == "obiettivo_trim"].sort_values(["Data", "Ora"], kind="stable")
    righe = []
    for _, r in o.groupby("Attivita", sort=False).tail(1).iterrows():
        try:
            d = json.loads(r["Nota"])
        except (json.JSONDecodeError, TypeError):
            d = {"passo": r["Nota"]}
        righe.append({"Obiettivo": r["Attivita"], "Stato": r["Strumento"],
                      "Prossimo passo": d.get("passo", ""), "Perché": d.get("perche", ""),
                      "Trimestre": d.get("trimestre", ""), "Aggiornato": r["Data"]})
    return pd.DataFrame(righe, columns=["Obiettivo", "Stato", "Prossimo passo",
                                        "Perché", "Trimestre", "Aggiornato"])


def _crescita(ctx):
    oggi = ctx.DIARIO.oggi()
    st.markdown(f"##### 🎯 Gli obiettivi del trimestre · {trimestre(oggi)}")
    st.caption("Al massimo tre. Ognuno con il prossimo passo concreto: se non "
               "sai qual è, l'obiettivo è ancora troppo vago.")
    ob = obiettivi(ctx.DIA)
    in_corso = ob[ob["Stato"] == "in corso"] if not ob.empty else ob
    if len(in_corso) > 3:
        st.warning(f"Ne hai {len(in_corso)} in corso. Tre bastano: sceglierne "
                   "meno è già metà del lavoro.")
    for _, r in in_corso.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['Obiettivo']}**")
            if r["Trimestre"]:
                st.caption(r["Trimestre"])
            st.markdown(f"➡️ {r['Prossimo passo'] or '*nessun passo scritto*'}")
            if r["Perché"]:
                st.caption(f"Perché conta: {r['Perché']}")
    chiusi = ob[ob["Stato"] != "in corso"] if not ob.empty else ob
    if not chiusi.empty:
        with st.expander(f"Quelli chiusi ({len(chiusi)})"):
            for _, r in chiusi.iterrows():
                st.markdown(f"{'✅' if r['Stato'] == 'raggiunto' else '⏹️'} "
                            f"**{r['Obiettivo']}** — {r['Stato']}")

    with st.form("eq_obiettivo", clear_on_submit=True):
        st.markdown("Aggiungi un obiettivo, o aggiornane uno scrivendo lo stesso nome")
        o1, o2 = st.columns([3, 1])
        titolo = o1.text_input("Obiettivo", placeholder="es. finire il prontuario SQL")
        stato = o2.selectbox("Stato", STATI_OBIETTIVO)
        passo = st.text_input("Il prossimo passo", placeholder="la prossima azione, piccola e concreta")
        perche = st.text_input("Perché conta (facoltativo)")
        if st.form_submit_button("💾 Salva", type="primary"):
            if titolo.strip():
                ctx.diario_scrivi(ctx.DIARIO.riga(
                    "obiettivo_trim", titolo.strip()[:80], stato, 0, None,
                    json.dumps({"passo": passo.strip(), "perche": perche.strip(),
                                "trimestre": trimestre(oggi)}, ensure_ascii=False)))
                ctx.conferma(f"Obiettivo salvato: {titolo.strip()[:40]}")
                st.rerun()
            else:
                st.warning("Serve il nome dell'obiettivo.")

    st.divider()
    _revisione(ctx, ob)


def _revisione(ctx, ob):
    oggi = ctx.DIARIO.oggi()
    anno, sett, _ = oggi.isocalendar()
    etichetta = f"Settimana {sett}/{anno}"
    st.markdown(f"##### 🔁 La revisione della settimana · {etichetta}")
    st.caption("Dieci minuti, una volta a settimana: cosa è andato, cosa "
               "cambi, un solo focus per la prossima. L'AI può prepararti una "
               "bozza leggendo il diario: tu la correggi.")

    for k, v in (st.session_state.pop("__eq_rev_prefill__", None) or {}).items():
        st.session_state[f"eq_rev_{k}"] = v

    if st.button("✨ Prepara una bozza dal diario", key="eq_rev_ai"):
        if not ctx.chiave_ai:
            st.error("Serve la chiave di Google AI Studio nei Secrets.")
        else:
            dal = pd.Timestamp(oggi) - pd.Timedelta(days=7)
            d = ctx.DIA[ctx.DIA["Data"] >= dal] if not ctx.DIA.empty else ctx.DIA
            lav = lavoro_per_giorno(ctx.DIA, dal)
            pr = d[d["Tipo"] == "priorita"]
            fatte = pr[pr["Attivita"] == "fatta"]["Nota"].tolist()
            rinviate = pr[pr["Attivita"] == "rinviata"]["Nota"].tolist()
            ses = d[d["Tipo"] == "sessione"]
            per_att = ses.groupby("Attivita")["Minuti"].sum().sort_values(ascending=False) \
                if not ses.empty else pd.Series(dtype=float)
            prompt = (
                "Aiuta una persona a fare la revisione della sua settimana. Usa "
                "SOLO questi dati del suo diario, senza inventare.\n"
                f"Minuti per attività: {per_att.to_dict()}\n"
                f"Per giorno (minuti, voto 1-5, interruzioni): "
                f"{lav.round(1).to_dict('index') if not lav.empty else 'nessun dato'}\n"
                f"Cose fatte: {fatte}\nCose rinviate: {rinviate}\n"
                f"Obiettivi del trimestre in corso: "
                f"{ob[ob['Stato'] == 'in corso'][['Obiettivo', 'Prossimo passo']].to_dict('records') if not ob.empty else []}\n\n"
                "Rispondi SOLO con JSON con tre campi in italiano, frasi brevi in "
                'prima persona: {"bene": "cosa è andato bene", "cambio": "cosa '
                'cambio la prossima settimana", "focus": "il solo focus della '
                'prossima settimana, collegato a un obiettivo se possibile"}')
            try:
                with st.spinner("Leggo la settimana…"):
                    bozza = _json_da_testo(ctx.AI.chiedi(prompt, ctx.chiave_ai, ctx.modello_ai))
                if bozza:
                    st.session_state["__eq_rev_prefill__"] = {
                        k: str(bozza.get(k, "")) for k in ("bene", "cambio", "focus")}
                    st.rerun()
                else:
                    st.warning("La risposta non era nel formato atteso: riprova.")
            except Exception as e:
                st.error(_messaggio_errore(e))

    bene = ctx.VOCE.campo("Cosa è andato bene", "eq_rev_bene", ctx.chiave_ai, ctx.modello_ai, altezza=90)
    cambio = ctx.VOCE.campo("Cosa cambio", "eq_rev_cambio", ctx.chiave_ai, ctx.modello_ai, altezza=90)
    focus = ctx.VOCE.campo("Il focus della prossima settimana", "eq_rev_focus",
                           ctx.chiave_ai, ctx.modello_ai, altezza=70)
    if st.button("💾 Salva la revisione", type="primary", key="eq_rev_salva"):
        if (bene or cambio or focus or "").strip():
            ctx.diario_scrivi(ctx.DIARIO.riga(
                "revisione", etichetta, "Equilibrio", 0, None,
                json.dumps({"bene": bene, "cambio": cambio, "focus": focus},
                           ensure_ascii=False)))
            for k in ("eq_rev_bene", "eq_rev_cambio", "eq_rev_focus"):
                ctx.VOCE.svuota(k)
            ctx.conferma(f"Revisione della {etichetta.lower()} salvata")
            st.rerun()
        else:
            st.warning("Scrivi almeno una delle tre.")

    rev = ctx.DIA[ctx.DIA["Tipo"] == "revisione"] if not ctx.DIA.empty else ctx.DIA
    if not rev.empty:
        st.markdown("##### Le revisioni passate")
        for _, r in rev.sort_values("Data", ascending=False).head(12).iterrows():
            try:
                d = json.loads(r["Nota"])
            except (json.JSONDecodeError, TypeError):
                d = {"bene": r["Nota"]}
            with st.expander(f"{r['Attivita']} · {r['Data']:%d/%m/%Y}"):
                st.markdown(f"**Bene:** {d.get('bene', '')}\n\n**Cambio:** "
                            f"{d.get('cambio', '')}\n\n**Focus:** {d.get('focus', '')}")
