/**
 * segretaria_telegram.gs — la segretaria di Quadro su Telegram.
 *
 * Gira su Google Apps Script (script.google.com), gratis, con il tuo account
 * Google. Ogni minuto:
 *   1. legge i messaggi che le hai scritto (anche vocali) e risponde;
 *   2. controlla se è l'ora di una notifica e la manda.
 *
 * Le impostazioni NON stanno qui: le prende da Quadro_Segretaria.json su
 * Drive, che Quadro aggiorna. Quello che le dici con i comandi lo scrive in
 * Quadro_Dalla_Segretaria.json, e Quadro lo importa nel diario.
 *
 * PRIMA DI TUTTO (lo spiega anche Quadro, scheda Segretaria):
 *   Impostazioni progetto → Fuso orario: Roma
 *   Proprietà script: TELEGRAM_TOKEN, GEMINI_KEY
 *   Esegui una volta la funzione «configura», poi scrivi /start al bot.
 */

const FILE_SEGRETARIA = 'Quadro_Segretaria.json';
const FILE_POSTA = 'Quadro_Dalla_Segretaria.json';
const FUSO = 'Europe/Rome';
const GIORNI = { lun: 1, mar: 2, mer: 3, gio: 4, ven: 5, sab: 6, dom: 7 };
const NOMI_GIORNI = ['', 'lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica'];

// ------------------------------------------------------------- piccoli aiuti
function prop(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function setProp(k, v) { PropertiesService.getScriptProperties().setProperty(k, String(v)); }
function delProp(k) { PropertiesService.getScriptProperties().deleteProperty(k); }
function propJSON(k, def) { try { return JSON.parse(prop(k) || '') ; } catch (e) { return def; } }
function ora(formato) { return Utilities.formatDate(new Date(), FUSO, formato); }

// ------------------------------------------------------------------- avvio
/** Da eseguire UNA volta dall'editor: crea il controllo ogni minuto. */
function configura() {
  if (!prop('TELEGRAM_TOKEN') || !prop('GEMINI_KEY')) {
    throw new Error('Mancano TELEGRAM_TOKEN o GEMINI_KEY nelle Proprietà script.');
  }
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('ciclo').timeBased().everyMinutes(1).create();
  telegram('deleteWebhook', {});          // leggiamo noi i messaggi, niente webhook
  const io = telegram('getMe', {});
  const cfg = leggiConfig(true);
  Logger.log('Bot pronto: @' + (io.result ? io.result.username : '?') +
             (cfg ? ' — impostazioni di Quadro trovate.' : ' — ATTENZIONE: non trovo ' + FILE_SEGRETARIA + ' su Drive.') +
             ' Ora scrivi /start al bot.');
}

/** Il giro di ogni minuto. */
function ciclo() {
  const lucchetto = LockService.getScriptLock();
  if (!lucchetto.tryLock(5000)) return;      // il giro precedente non ha finito
  try {
    leggiMessaggi();
    controllaNotifiche();
  } finally {
    lucchetto.releaseLock();
  }
}

// ---------------------------------------------------------------- telegram
function telegram(metodo, dati) {
  const r = UrlFetchApp.fetch('https://api.telegram.org/bot' + prop('TELEGRAM_TOKEN') + '/' + metodo, {
    method: 'post', contentType: 'application/json', payload: JSON.stringify(dati), muteHttpExceptions: true });
  try { return JSON.parse(r.getContentText()); } catch (e) { return {}; }
}

function invia(testo, chat) {
  chat = chat || prop('CHAT_ID');
  if (!chat || !testo) return;
  const pezzi = String(testo).match(/[\s\S]{1,3900}/g) || [];
  pezzi.forEach(function (p) { telegram('sendMessage', { chat_id: chat, text: p, disable_web_page_preview: true }); });
}

// -------------------------------------------------------- le impostazioni
function leggiConfig(senzaCache) {
  const cache = CacheService.getScriptCache();
  if (!senzaCache) {
    const c = cache.get('cfg');
    if (c) { try { return JSON.parse(c); } catch (e) {} }
  }
  const f = DriveApp.getFilesByName(FILE_SEGRETARIA);
  if (!f.hasNext()) return null;
  const file = f.next();
  let cfg = null;
  try { cfg = JSON.parse(file.getBlob().getDataAsString('UTF-8') || '{}'); } catch (e) { return null; }
  try { cache.put('cfg', JSON.stringify(cfg), 120); } catch (e) {}     // due minuti
  return cfg;
}

function seg(cfg) {
  const s = (cfg && cfg.segretaria) || {};
  return { nome: s.nome || 'Sofia', chiamami: s.chiamami || 'Claudio', carattere: s.carattere || 'cordiale e diretta',
           extra: s.carattere_extra || '' };
}

/** Avviso se i dati di Quadro sono vecchi: meglio dirlo che fingere. */
function vecchiezza(cfg) {
  if (!cfg || !cfg.aggiornato) return '';
  const giorni = (new Date() - new Date(cfg.aggiornato)) / 86400000;
  return giorni > 1 ? '\n\n(i dati di Quadro sono del ' + cfg.aggiornato.slice(8, 10) + '/' + cfg.aggiornato.slice(5, 7) +
    ': apri Quadro per aggiornarli)' : '';
}

// --------------------------------------------------------- la posta in uscita
/** Scrive una voce in Quadro_Dalla_Segretaria.json (lo crea se non c'è). */
function posta(tipo, testo, extra) {
  let file;
  const f = DriveApp.getFilesByName(FILE_POSTA);
  if (f.hasNext()) file = f.next();
  else {
    const cf = DriveApp.getFilesByName(FILE_SEGRETARIA);
    const cartella = cf.hasNext() ? cf.next().getParents().next() : DriveApp.getRootFolder();
    file = cartella.createFile(FILE_POSTA, JSON.stringify({ voci: [] }), 'application/json');
  }
  let dati;
  try { dati = JSON.parse(file.getBlob().getDataAsString('UTF-8') || '{}'); } catch (e) { dati = {}; }
  dati.voci = (dati.voci || []).concat([Object.assign({
    id: Utilities.getUuid().slice(0, 8), quando: ora("yyyy-MM-dd'T'HH:mm"), tipo: tipo, testo: testo, da: 'Telegram'
  }, extra || {})]).slice(-500);
  file.setContent(JSON.stringify(dati));
}

// ------------------------------------------------------------------ gemini
function gemini(testo, parti) {
  const cfg = leggiConfig();
  const modelli = [(cfg && cfg.modello_ai) || 'gemini-flash-latest', 'gemini-flash-latest'];
  for (let i = 0; i < modelli.length; i++) {
    const r = UrlFetchApp.fetch('https://generativelanguage.googleapis.com/v1beta/models/' + modelli[i] +
      ':generateContent?key=' + prop('GEMINI_KEY'), {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      payload: JSON.stringify({ contents: [{ parts: [{ text: testo }].concat(parti || []) }] }) });
    if (r.getResponseCode() === 200) {
      try { return JSON.parse(r.getContentText()).candidates[0].content.parts[0].text.trim(); } catch (e) { return null; }
    }
    if (r.getResponseCode() === 503 || r.getResponseCode() === 429) Utilities.sleep(3000);
  }
  return null;
}

function jsonDa(testo) {
  if (!testo) return null;
  const i = testo.indexOf('{'), j = testo.lastIndexOf('}');
  if (i < 0 || j < i) return null;
  try { return JSON.parse(testo.slice(i, j + 1)); } catch (e) { return null; }
}

function trascrivi(voce) {
  const info = telegram('getFile', { file_id: voce.file_id });
  if (!info.result) return '';
  const audio = UrlFetchApp.fetch('https://api.telegram.org/file/bot' + prop('TELEGRAM_TOKEN') + '/' + info.result.file_path).getBlob();
  return gemini('Trascrivi fedelmente in italiano quello che senti. Scrivi solo la trascrizione.',
    [{ inline_data: { mime_type: voce.mime_type || 'audio/ogg', data: Utilities.base64Encode(audio.getBytes()) } }]) || '';
}

// ------------------------------------------------------------- i messaggi
function leggiMessaggi() {
  const offset = Number(prop('OFFSET') || 0);
  const r = telegram('getUpdates', { offset: offset, timeout: 0, allowed_updates: ['message'] });
  (r.result || []).forEach(function (u) {
    setProp('OFFSET', u.update_id + 1);     // subito: un errore dopo non lo fa ripetere
    const m = u.message;
    if (!m) return;
    const chat = String(m.chat.id), padrone = prop('CHAT_ID');
    let testo = m.text || m.caption || '';
    if (!padrone) {
      if (/^\/start/.test(testo)) {
        setProp('CHAT_ID', chat);
        const s = seg(leggiConfig());
        invia('Ciao ' + s.chiamami + ', sono ' + s.nome + '. Da adesso parlo solo con te. 🙂\n\n' + AIUTO, chat);
      }
      return;
    }
    if (chat !== padrone) { invia('Questo è un assistente privato.', chat); return; }
    try {
      if (m.voice || m.audio) {
        testo = trascrivi(m.voice || m.audio);
        if (!testo) { invia('Non sono riuscita a capire il vocale, me lo riscrivi?'); return; }
        invia('🎙️ «' + testo + '»');
      }
      if (testo) gestisci(testo.trim());
    } catch (e) {
      invia('Qualcosa è andato storto: ' + String(e).slice(0, 200));
    }
  });
}

const AIUTO = 'Puoi scrivermi o mandarmi un vocale come a una persona. E poi:\n' +
  '/oggi — la tua giornata\n/aforisma — uno nuovo (es. /aforisma coraggio)\n/respira — un minuto di pausa\n' +
  '/nota testo · /idea testo · /ricorda testo\n/priorita testo — tra le tre cose\n/fatto testo — segna come fatta\n' +
  '/scadenza 2026-11-20 testo\n/silenzio 2 — niente notifiche per 2 ore · /riprendi\n/aiuto';

function gestisci(testo) {
  const cfg = leggiConfig();
  const comando = (testo.match(/^\/(\w+)/) || [])[1];
  const resto = testo.replace(/^\/\w+(@\w+)?\s*/, '').trim();

  // una conferma a una proposta in sospeso
  const attesa = propJSON('IN_ATTESA', null);
  if (attesa && !comando) {
    delProp('IN_ATTESA');
    // niente «\b» qui: per JavaScript la «ì» non è una lettera, e «sì» non verrebbe riconosciuto
    if (/^(s[iì]|ok|okay|certo|va bene|fallo|vai|d'accordo)(?=$|[\s!.,])/i.test(testo)) {
      posta(attesa.tipo, attesa.testo, attesa.data ? { data: attesa.data } : null);
      invia('Fatto ✅ Lo trovi in Quadro, nella scheda Segretaria.');
      return;
    }
  }

  switch (comando) {
    case 'start': case 'aiuto': case 'help': invia(AIUTO); return;
    case 'oggi': invia(componi('buongiorno', '', cfg)); return;
    case 'aforisma': invia(componi('aforisma', resto, cfg)); return;
    case 'respira': invia(componi('respiro', '', cfg)); return;
    case 'nota': case 'idea': case 'ricorda': case 'priorita': case 'fatto':
      if (!resto) { invia('Scrivi il testo dopo il comando, es. /' + comando + ' chiamare il frantoio'); return; }
      posta(comando === 'ricorda' ? 'ricordo' : comando, resto);
      invia({ nota: '📝 Nota salvata.', idea: '💡 Idea salvata.', ricorda: '🧠 Me lo ricorderò.',
              priorita: '🎯 Aggiunta alle tre cose.', fatto: '✅ Segnata come fatta.' }[comando] +
            ' La trovi in Quadro.');
      return;
    case 'scadenza': {
      const m = resto.match(/^(\d{4}-\d{2}-\d{2})\s+(.+)$/);
      if (!m) { invia('Scrivila così: /scadenza 2026-11-20 dichiarazione IVA'); return; }
      posta('scadenza', m[2], { data: m[1] }); invia('⏰ Scadenza del ' + m[1].slice(8) + '/' + m[1].slice(5, 7) + ' segnata.');
      return;
    }
    case 'silenzio': {
      const ore = Number(resto) || 2;
      setProp('SILENZIO_FINO', Date.now() + ore * 3600000);
      invia('🤫 Niente notifiche per ' + ore + (ore === 1 ? ' ora.' : ' ore.') + ' /riprendi per riattivarle.');
      return;
    }
    case 'riprendi': delProp('SILENZIO_FINO'); invia('🔔 Notifiche riattivate.'); return;
  }
  chiacchiera(testo, cfg);
}

/** La conversazione libera, con il profilo, i ricordi e la situazione di Quadro. */
// Ogni chiacchierata va nella posta come «scambio»: Quadro la mette nel registro
// della segretaria (📈 Come lavora), con il tempo di risposta e l'azione proposta.
function registraScambio(domanda, risposta, secondi, azione, errore) {
  try {
    posta('scambio', String(domanda).slice(0, 400), {
      risposta: String(risposta || '').slice(0, 800), secondi: secondi, azione: azione || '', errore: errore || '' });
  } catch (e) { console.warn('Registro non scritto: ' + e); }
}

function chiacchiera(testo, cfg) {
  const s = seg(cfg);
  const storia = propJSON('STORIA', []);
  const p = 'Sei ' + s.nome + ', la segretaria personale di ' + s.chiamami + '. Carattere: ' + s.carattere + '. ' + s.extra +
    '\nParli italiano, dai del tu, frasi brevi (al massimo 5) perché le legge sul telefono. Usa SOLO le informazioni qui ' +
    'sotto, non inventare impegni o numeri. Non sei un medico: su salute e farmaci rimanda al medico.\n' +
    'Adesso: ' + NOMI_GIORNI[Number(ora('u'))] + ' ' + ora('dd/MM/yyyy HH:mm') + '.\n' +
    'Chi è, nelle sue parole: ' + ((cfg && cfg.profilo) || '(non scritto)') + '\n' +
    'Cose da ricordare: ' + JSON.stringify((cfg && cfg.ricordi) || []) + '\n' +
    'Situazione in Quadro (aggiornata il ' + ((cfg && cfg.aggiornato) || '?') + '): ' + JSON.stringify((cfg && cfg.contesto) || {}) + '\n' +
    'Conversazione:\n' + storia.map(function (x) { return (x.r === 'io' ? 'Lui: ' : 'Tu: ') + x.t; }).join('\n') +
    '\nLui: ' + testo + '\n\nRispondi SOLO con JSON: {"risposta": "...", "azione": null oppure ' +
    '{"tipo": "nota|idea|ricordo|priorita|scadenza", "testo": "...", "data": "AAAA-MM-GG o vuoto"}}. ' +
    'Proponi un\'azione solo se te la chiede o è chiaramente utile: la confermerà lui.';
  const t0 = Date.now();
  const r = gemini(p);
  const secondi = Math.round((Date.now() - t0) / 100) / 10;
  if (!r) {
    invia('Non riesco a pensare in questo momento (il servizio AI non risponde). Riprova fra poco.');
    registraScambio(testo, '', secondi, '', 'il servizio AI non risponde');
    return;
  }
  const d = jsonDa(r) || { risposta: r };
  let risposta = d.risposta || r;
  if (d.azione && d.azione.tipo && d.azione.testo) {
    setProp('IN_ATTESA', JSON.stringify(d.azione));
    risposta += '\n\n👉 Vuoi che segni «' + d.azione.testo + '»' + (d.azione.data ? ' per il ' + d.azione.data : '') + '? Rispondi sì.';
  }
  invia(risposta);
  registraScambio(testo, String(d.risposta || r), secondi, d.azione && d.azione.tipo ? d.azione.tipo : '', '');
  storia.push({ r: 'io', t: testo.slice(0, 400) }, { r: 'lei', t: String(d.risposta || r).slice(0, 400) });
  setProp('STORIA', JSON.stringify(storia.slice(-10)));
}

// ------------------------------------------------------------- le notifiche
function minutiDa(hhmm) { const p = String(hhmm).split(':'); return Number(p[0]) * 60 + Number(p[1]); }

function giornoGiusto(giorni, oggiISO, dow) {
  giorni = String(giorni || 'tutti').toLowerCase().trim();
  if (giorni === 'tutti' || giorni === '') return true;
  if (giorni === 'feriali') return dow <= 5;
  if (giorni === 'weekend') return dow >= 6;
  if (/^\d{4}-\d{2}-\d{2}$/.test(giorni)) return giorni === oggiISO;
  return giorni.split(/[,\s]+/).some(function (g) { return GIORNI[g.slice(0, 3)] === dow; });
}

function controllaNotifiche() {
  if (!prop('CHAT_ID')) return;
  if (Number(prop('SILENZIO_FINO') || 0) > Date.now()) return;
  const cfg = leggiConfig();
  if (!cfg || !cfg.notifiche || cfg.notifiche.attive === false) return;
  const oggiISO = ora('yyyy-MM-dd'), adesso = minutiDa(ora('HH:mm')), dow = Number(ora('u'));
  const inviate = propJSON('INVIATE', {});
  (cfg.notifiche.regole || []).forEach(function (r) {
    if (!r.attiva || !r.ora) return;
    const chiave = r.id + '|' + oggiISO;
    const quando = minutiDa(r.ora);
    // dentro una finestra di 30 minuti: se un giro salta, la notifica arriva lo stesso,
    // ma accendendo lo script alle 15 non arrivano tutte quelle del mattino
    if (inviate[chiave] || adesso < quando || adesso - quando > 30) return;
    if (!giornoGiusto(r.giorni, oggiISO, dow)) return;
    inviate[chiave] = true;
    const testo = componi(r.tipo, r.dettagli || '', cfg);
    if (testo) invia(testo);
  });
  // tengo solo gli ultimi tre giorni
  const limite = Utilities.formatDate(new Date(Date.now() - 3 * 86400000), FUSO, 'yyyy-MM-dd');
  Object.keys(inviate).forEach(function (k) { if (k.split('|')[1] < limite) delete inviate[k]; });
  setProp('INVIATE', JSON.stringify(inviate));
}

// --------------------------------------------------------- cosa scrive
function aforisma(dettagli, cfg) {
  const pref = (cfg && cfg.aforismi && cfg.aforismi.preferenze) || {};
  const gusti = (cfg && cfg.aforismi && cfg.aforismi.gusti) || {};
  const gia = propJSON('AFORISMI', []);
  const temi = dettagli || [].concat(pref.temi || [], String(pref.altri || '').split(',')).filter(String).join(', ');
  const p = 'Proponi UN aforisma o una citazione breve in italiano. Temi: ' + (temi || 'la vita quotidiana') + '. ' +
    (pref.tradizioni && pref.tradizioni.length ? 'Da: ' + pref.tradizioni.join(', ') + '. ' : '') +
    (pref.tono && pref.tono !== 'qualsiasi' ? 'Tono: ' + pref.tono + '. ' : '') +
    (pref.epoca && pref.epoca !== 'qualsiasi' ? 'Epoca: ' + pref.epoca + '. ' : '') +
    (pref.autori ? 'Autori preferiti: ' + pref.autori + '. ' : '') + (pref.evita ? 'Da evitare: ' + pref.evita + '. ' : '') +
    ((gusti.piace || []).length ? 'Gli piacciono: ' + gusti.piace.join(', ') + '. ' : '') +
    ((gusti.non_piace || []).length ? 'Non gli piacciono: ' + gusti.non_piace.join(', ') + '. ' : '') +
    'Se attribuisci la frase a un autore deve essere una citazione vera e nota di cui sei sicuro; altrimenti scrivi ' +
    'una riflessione tua con autore «riflessione». Non ripetere: ' + gia.join(' | ') +
    '\nRispondi SOLO con JSON: {"testo": "...", "autore": "...", "fonte": "..."}';
  let a = jsonDa(gemini(p));
  if (!a || !a.testo) {
    const scorta = ((cfg && cfg.aforismi && cfg.aforismi.scorta) || []).filter(function (x) { return gia.indexOf(x.testo) < 0; });
    a = scorta.length ? scorta[Math.floor(Math.random() * scorta.length)] : { testo: 'Respira.', autore: '' };
  }
  gia.push(a.testo); setProp('AFORISMI', JSON.stringify(gia.slice(-30)));
  return '«' + a.testo + '»' + (a.autore ? '\n— ' + a.autore + (a.fonte ? ', ' + a.fonte : '') : '');
}

function elenco(titolo, righe) { return righe.length ? '\n\n' + titolo + '\n' + righe.map(function (r) { return '• ' + r; }).join('\n') : ''; }

function componi(tipo, dettagli, cfg) {
  const s = seg(cfg), c = (cfg && cfg.contesto) || {};
  const tre = (c.tre_cose || []).map(function (x) { return x.cosa + (x.rinvii >= 2 ? ' (rinviata ' + x.rinvii + ' volte)' : ''); });
  const oggiISO = ora('yyyy-MM-dd'), fra3 = Utilities.formatDate(new Date(Date.now() + 3 * 86400000), FUSO, 'yyyy-MM-dd');
  const scad = (c.scadenze || []).filter(function (x) { return x.quando <= fra3; })
    .map(function (x) { return x.cosa + ' — ' + x.quando.slice(8) + '/' + x.quando.slice(5, 7) + (x.quando < oggiISO ? ' (in ritardo)' : ''); });
  const rich = (c.da_richiamare || []).map(function (x) { return x.cliente + (x.passo ? ': ' + x.passo : ''); });
  switch (tipo) {
    case 'buongiorno': {
      let t = 'Buongiorno ' + s.chiamami + '! ☀️ È ' + NOMI_GIORNI[Number(ora('u'))] + '.';
      t += tre.length ? elenco('🎯 Le tre cose:', tre) : '\n\nNon hai ancora scelto le tre cose di oggi: quali sono?';
      t += elenco('⏰ Scadenze vicine:', scad) + elenco('📞 Da richiamare:', rich);
      if (c.focus_settimana) t += '\n\n🔁 Il focus della settimana: ' + c.focus_settimana;
      if (c.flashcard_da_ripassare) t += '\n\n🃏 ' + c.flashcard_da_ripassare + ' flashcard da ripassare.';
      return t + '\n\n' + aforisma('', cfg) + vecchiezza(cfg);
    }
    case 'aforisma': return aforisma(dettagli, cfg);
    case 'consiglio': {
      const r = gemini('Sei ' + s.nome + ', segretaria di ' + s.chiamami + '. In base a questa situazione dai UN consiglio pratico ' +
        'per oggi, in due o tre frasi, in italiano, senza frasi fatte. Situazione: ' + JSON.stringify(c));
      return r ? '💡 ' + r + vecchiezza(cfg) : '';
    }
    case 'scadenze': return scad.length ? '⏰ Scadenze dei prossimi giorni:\n' + scad.map(function (x) { return '• ' + x; }).join('\n') + vecchiezza(cfg) : '';
    case 'respiro': return '🌬️ Un minuto per te.\nSpalle giù. Inspira contando fino a cinque, espira contando fino a cinque. ' +
      'Sei volte. Poi scegli la prossima cosa da fare, una sola.';
    case 'sera': {
      let t = '🌙 Com\'è andata oggi, ' + s.chiamami + '?';
      if (tre.length) t += elenco('Restano aperte:', tre) + '\nDomani le ritrovi in cima.';
      return t + '\n\nSe ti va, fai il check-in in Quadro → Equilibrio, o scrivimi una /nota sulla giornata.';
    }
    case 'ripasso': return c.flashcard_da_ripassare ? '🃏 Hai ' + c.flashcard_da_ripassare +
      ' flashcard da ripassare oggi: bastano cinque minuti, in Quadro → Studio → Leggimelo.' : '';
    case 'promemoria': return dettagli ? '⏰ Promemoria: ' + dettagli : '';
  }
  return '';
}
