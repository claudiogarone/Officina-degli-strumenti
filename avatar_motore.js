/*
 * avatar_motore.js — la segretaria in 3D. Lo stesso file serve a Quadro
 * (che lo incolla dentro la pagina) e all'app da desktop.
 *
 * DUE MODI DI ESSERE
 *   - stilizzata: costruita qui con forme semplici (sfere, capsule), colori
 *     e acconciatura scelti da te. Non serve nessun file.
 *   - VRM: un personaggio vero creato con VRoid Studio (gratuito), caricato
 *     da un indirizzo. Sbatte le palpebre, muove la bocca, ti guarda.
 *
 * COSA FA DA SOLA: respira, sbatte le palpebre, segue il puntatore con lo
 * sguardo, muove la bocca mentre parla, saluta con la mano.
 *
 * COME SI USA (da un <script type="module">):
 *   import { creaAvatar } from './avatar_motore.js';   // o incollato
 *   const av = await creaAvatar(document.getElementById('scena'), { capelli: '#3b2a20' });
 *   av.parla('Buongiorno!');           // voce del browser + bocca
 *   av.parlaAudio('data:audio/mpeg;base64,…');  // voce di Gemini, bocca sincronizzata
 *   av.stato('pensa');                 // riposo | ascolta | pensa | felice
 *   av.saluta();
 *
 * Ha bisogno di una «importmap» che dica dove stanno three, three/addons/ e
 * @pixiv/three-vrm (le pagine di Quadro e dell'app la mettono già).
 */
import * as THREE from 'three';

export const PREDEFINITE = {
  nome: 'Sofia', pelle: '#f1c7a5', capelli: '#3b2a20', giacca: '#0f5d47', camicia: '#f7f7f2',
  occhi: '#4a3426', labbra: '#c45a5a', acconciatura: 'caschetto', occhiali: false,
  orecchini: true, sfondo: 'trasparente', inquadratura: 'busto', vrm: '',
  voce: '', velocita: 1, tono: 1.05,
};

function materiale(colore, ruvido = 0.6, extra = {}) {
  return new THREE.MeshStandardMaterial(Object.assign({ color: new THREE.Color(colore), roughness: ruvido, metalness: 0 }, extra));
}
function mesh(geo, mat, x = 0, y = 0, z = 0) { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); return m; }
function piuScuro(hex, k) { const c = new THREE.Color(hex); c.multiplyScalar(k); return '#' + c.getHexString(); }

// ---------------------------------------------------------------- stilizzata
function costruisciStilizzata(op) {
  const P = {};
  const corpo = new THREE.Group();
  const pelle = materiale(op.pelle, 0.55);
  const capelli = materiale(op.capelli, 0.75);
  const giacca = materiale(op.giacca, 0.7);

  // busto e braccia
  P.busto = new THREE.Group(); corpo.add(P.busto);
  const torso = mesh(new THREE.CapsuleGeometry(0.95, 0.9, 10, 32), giacca, 0, -2.55, 0);
  torso.scale.set(1.25, 1, 0.68); P.busto.add(torso); P.torso = torso;
  const scollo = new THREE.Shape(); scollo.moveTo(-0.32, 0); scollo.lineTo(0.32, 0); scollo.lineTo(0, -0.78); scollo.closePath();
  P.busto.add(mesh(new THREE.ShapeGeometry(scollo), materiale(op.camicia, 0.8), 0, -1.6, 0.655));
  const bavero = materiale(piuScuro(op.giacca, 0.75), 0.6);
  [-1, 1].forEach(s => {
    // i baveri seguono i lati della «V» della camicia, appena fuori
    const b = mesh(new THREE.BoxGeometry(0.12, 0.92, 0.04), bavero, s * 0.22, -1.98, 0.665);
    b.rotation.z = -s * 0.39; P.busto.add(b);
  });
  P.busto.add(mesh(new THREE.SphereGeometry(0.06, 16, 16), materiale('#1baf7a', 0.3, { metalness: 0.4 }), -0.5, -1.95, 0.6));
  P.braccia = [];
  [-1, 1].forEach(s => {
    const spalla = new THREE.Group(); spalla.position.set(s * 1.12, -1.75, 0);
    const braccio = mesh(new THREE.CapsuleGeometry(0.25, 1.25, 8, 20), giacca, 0, -0.8, 0);
    const mano = mesh(new THREE.SphereGeometry(0.22, 20, 20), pelle, 0, -1.65, 0.05);
    spalla.add(braccio); spalla.add(mano); spalla.rotation.z = s * 0.14;
    P.busto.add(spalla); P.braccia.push(spalla);
  });
  P.busto.add(mesh(new THREE.CylinderGeometry(0.3, 0.36, 0.7, 24), pelle, 0, -1.25, -0.05));

  // testa
  P.testa = new THREE.Group(); P.testa.position.set(0, -0.15, 0); corpo.add(P.testa);
  const cranio = mesh(new THREE.SphereGeometry(1, 48, 48), pelle); cranio.scale.set(0.9, 1.05, 0.92); P.testa.add(cranio);
  [-1, 1].forEach(s => { const o = mesh(new THREE.SphereGeometry(0.17, 16, 16), pelle, s * 0.88, 0, -0.02); o.scale.set(0.5, 1, 0.65); P.testa.add(o); });
  const guance = new THREE.MeshBasicMaterial({ color: '#ff8a80', transparent: true, opacity: 0.22, depthWrite: false });
  [-1, 1].forEach(s => { const g = mesh(new THREE.CircleGeometry(0.15, 24), guance, s * 0.47, -0.28, 0.79); g.rotation.y = s * 0.5; P.testa.add(g); });
  P.testa.add(mesh(new THREE.SphereGeometry(0.075, 16, 16), materiale(piuScuro(op.pelle, 0.93), 0.5), 0, -0.12, 0.91));

  // occhi: un gruppo per occhio, si schiaccia per sbattere le palpebre
  P.occhi = [];
  [-1, 1].forEach(s => {
    const g = new THREE.Group(); g.position.set(s * 0.33, 0.08, 0.78);
    const bianco = mesh(new THREE.SphereGeometry(0.17, 24, 24), materiale('#ffffff', 0.3)); bianco.scale.set(1, 1.15, 0.5);
    const iride = mesh(new THREE.SphereGeometry(0.115, 24, 24), materiale(op.occhi, 0.25), 0, -0.01, 0.055); iride.scale.set(1, 1.1, 0.5);
    const pupilla = mesh(new THREE.SphereGeometry(0.06, 16, 16), materiale('#111111', 0.2), 0, -0.01, 0.1); pupilla.scale.set(1, 1.1, 0.5);
    const luce = mesh(new THREE.SphereGeometry(0.03, 12, 12), new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.045, 0.05, 0.13);
    g.add(bianco, iride, pupilla, luce); P.testa.add(g); P.occhi.push(g);
    g.userData.iride = [iride, pupilla, luce];
  });
  P.sopracciglia = [];
  [-1, 1].forEach(s => {
    const b = mesh(new THREE.CapsuleGeometry(0.028, 0.22, 4, 8), materiale(piuScuro(op.capelli, 0.8)), s * 0.34, 0.37, 0.84);
    b.rotation.z = Math.PI / 2 + s * 0.1; P.testa.add(b); P.sopracciglia.push(b);
  });

  // bocca: un sorriso fisso e un'apertura che si muove quando parla
  P.bocca = new THREE.Group(); P.bocca.position.set(0, -0.42, 0.82); P.testa.add(P.bocca);
  const sorriso = mesh(new THREE.TorusGeometry(0.13, 0.026, 8, 32, Math.PI), materiale(op.labbra, 0.4));
  sorriso.rotation.z = Math.PI; sorriso.scale.set(1, 0.55, 1); P.bocca.add(sorriso); P.sorriso = sorriso;
  P.apertura = mesh(new THREE.SphereGeometry(0.1, 20, 20), materiale('#7a2630', 0.5), 0, -0.035, 0.0);
  P.apertura.scale.set(1.15, 0.01, 0.35); P.bocca.add(P.apertura);

  // capelli
  const calotta = mesh(new THREE.SphereGeometry(1.07, 48, 32, 0, Math.PI * 2, 0, Math.PI * 0.5), capelli, 0, 0.04, -0.02);
  calotta.scale.set(0.93, 1.07, 0.97); calotta.rotation.x = -0.18; P.testa.add(calotta);
  const lunghezza = { corti: 0.5, caschetto: 0.68, lunghi: 0.7, raccolti: 0.55 }[op.acconciatura] || 0.68;
  const dietro = mesh(new THREE.SphereGeometry(1.04, 48, 32, 0, Math.PI * 2, 0, Math.PI * lunghezza), capelli, 0, 0.0, -0.13);
  dietro.scale.set(0.97, 1.05, 0.95); P.testa.add(dietro);
  if (op.acconciatura === 'lunghi') {
    const coda = mesh(new THREE.CapsuleGeometry(0.72, 1.7, 8, 24), capelli, 0, -1.25, -0.42);
    coda.scale.set(1.15, 1, 0.42); corpo.add(coda);
  }
  if (op.acconciatura === 'raccolti') P.testa.add(mesh(new THREE.SphereGeometry(0.4, 24, 24), capelli, 0, 0.8, -0.72));

  if (op.occhiali) {
    const nero = materiale('#222222', 0.3, { metalness: 0.5 });
    [-1, 1].forEach(s => { const l = mesh(new THREE.TorusGeometry(0.21, 0.022, 10, 32), nero, s * 0.33, 0.08, 0.93); P.testa.add(l); });
    const ponte = mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.22, 8), nero, 0, 0.12, 0.95); ponte.rotation.z = Math.PI / 2; P.testa.add(ponte);
  }
  if (op.orecchini) [-1, 1].forEach(s => P.testa.add(mesh(new THREE.SphereGeometry(0.055, 12, 12), materiale('#d9b44a', 0.25, { metalness: 0.8 }), s * 0.9, -0.22, 0.02)));
  return { gruppo: corpo, parti: P, vrm: null };
}

// ------------------------------------------------------------------- VRM
async function caricaVRM(url) {
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { VRMLoaderPlugin, VRMUtils } = await import('@pixiv/three-vrm');
  const loader = new GLTFLoader();
  loader.register(p => new VRMLoaderPlugin(p));
  const gltf = await loader.loadAsync(url);
  const vrm = gltf.userData.vrm;
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  VRMUtils.combineSkeletons ? VRMUtils.combineSkeletons(gltf.scene) : null;
  VRMUtils.rotateVRM0(vrm);
  vrm.scene.traverse(o => { o.frustumCulled = false; });
  // le braccia giù dalla posa a T
  const h = vrm.humanoid;
  const sx = h.getNormalizedBoneNode('leftUpperArm'), dx = h.getNormalizedBoneNode('rightUpperArm');
  if (sx) sx.rotation.z = -1.2;
  if (dx) dx.rotation.z = 1.2;
  return { gruppo: vrm.scene, parti: {}, vrm };
}

// ------------------------------------------------------------- l'avatar
export async function creaAvatar(contenitore, opzioni = {}) {
  const op = Object.assign({}, PREDEFINITE, opzioni);
  const trasparente = op.sfondo === 'trasparente';
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: trasparente, preserveDrawingBuffer: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  if (trasparente) renderer.setClearColor(0x000000, 0); else renderer.setClearColor(new THREE.Color(op.sfondo), 1);
  contenitore.appendChild(renderer.domElement);
  renderer.domElement.style.display = 'block';

  const scena = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.05, 100);
  scena.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.15));
  const chiave = new THREE.DirectionalLight(0xffffff, 1.7); chiave.position.set(2.5, 3, 5); scena.add(chiave);
  const contro = new THREE.DirectionalLight(0x9fe8d0, 0.9); contro.position.set(-3, 2, -4); scena.add(contro);

  let figura;
  try { figura = op.vrm ? await caricaVRM(op.vrm) : costruisciStilizzata(op); }
  catch (e) { console.warn('VRM non caricato, uso la stilizzata:', e); figura = costruisciStilizzata(op); }
  scena.add(figura.gruppo);
  const { parti: P, vrm } = figura;

  // inquadratura
  function inquadra() {
    const w = contenitore.clientWidth || 300, h = contenitore.clientHeight || 400;
    renderer.setSize(w, h, false); renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%';
    camera.aspect = w / h;
    if (vrm) {
      const testa = vrm.humanoid.getNormalizedBoneNode('head');
      const y = testa ? testa.getWorldPosition(new THREE.Vector3()).y : 1.4;
      const viso = op.inquadratura === 'viso';
      const intera = op.inquadratura === 'figura';
      camera.position.set(0, y - (viso ? 0.0 : intera ? 0.6 : 0.05), viso ? 0.8 : intera ? 3.2 : 1.45);
      camera.lookAt(0, y - (viso ? 0.0 : intera ? 0.7 : 0.1), 0);
    } else {
      const viso = op.inquadratura === 'viso', figuraIntera = op.inquadratura === 'figura';
      const d = viso ? 6.3 : figuraIntera ? 12 : 8.6;
      const ty = viso ? -0.1 : figuraIntera ? -1.6 : -0.95;
      camera.position.set(0, ty + 0.15, d / Math.min(1, camera.aspect * 1.4)); camera.lookAt(0, ty, 0);
    }
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(inquadra).observe(contenitore); inquadra();

  // stato e animazione
  let stato = 'riposo', parlando = false, impulso = 0, apertura = 0, livelloAudio = 0;
  let prossimoBattito = 2 + Math.random() * 3, battito = -1, saluto = -1;
  const sguardo = new THREE.Vector2(0, 0), sguardoObiettivo = new THREE.Vector2(0, 0);
  const bersaglio = new THREE.Object3D(); scena.add(bersaglio);
  if (vrm && vrm.lookAt) vrm.lookAt.target = bersaglio;
  window.addEventListener('pointermove', e => {
    sguardoObiettivo.set((e.clientX / window.innerWidth) * 2 - 1, -((e.clientY / window.innerHeight) * 2 - 1));
  });
  renderer.domElement.addEventListener('click', () => { contenitore.dispatchEvent(new CustomEvent('avatar-clic', { bubbles: true })); });

  let analizzatore = null, datiAudio = null, contestoAudio = null, audioCorrente = null;
  const orologio = new THREE.Clock();
  // Leggera sul computer: 30 fotogrammi al secondo bastano, e quando non si vede
  // (scheda chiusa, finestra nascosta, riquadro rimpicciolito) non disegna affatto.
  let ultimoFotogramma = 0;
  function ciclo(adesso = 0) {
    requestAnimationFrame(ciclo);
    if (document.hidden || !contenitore.clientWidth || !contenitore.clientHeight) return;
    if (adesso - ultimoFotogramma < 32) return;
    ultimoFotogramma = adesso;
    const dt = Math.min(orologio.getDelta(), 0.05), t = orologio.elapsedTime;
    sguardo.lerp(sguardoObiettivo, 0.06);
    // la bocca: segue l'audio vero se c'è, altrimenti un movimento «parlato»
    if (analizzatore) {
      analizzatore.getByteTimeDomainData(datiAudio);
      let s = 0; for (const v of datiAudio) { const x = (v - 128) / 128; s += x * x; }
      livelloAudio = Math.min(1, Math.sqrt(s / datiAudio.length) * 5);
    }
    const obiettivo = analizzatore ? livelloAudio : parlando ? (0.25 + 0.6 * Math.abs(Math.sin(t * 13 + Math.sin(t * 3.1) * 2))) * (0.6 + 0.4 * impulso) : 0;
    apertura += (obiettivo - apertura) * 0.35; impulso *= 0.9;
    // battito di palpebre
    if (t > prossimoBattito && battito < 0) battito = 0;
    let occhio = 1;
    if (battito >= 0) { battito += dt; const k = battito / 0.16; occhio = k < 1 ? 1 - Math.sin(k * Math.PI) : 1;
      if (k >= 1) { battito = -1; prossimoBattito = t + 2.2 + Math.random() * 4; } }
    const pensa = stato === 'pensa', ascolta = stato === 'ascolta', felice = stato === 'felice';
    if (vrm) {
      const em = vrm.expressionManager;
      if (em) { em.setValue('blink', 1 - occhio); em.setValue('aa', apertura * 0.8); em.setValue('happy', felice ? 0.6 : 0.15); }
      const h = vrm.humanoid;
      const collo = h.getNormalizedBoneNode('neck'), testa = h.getNormalizedBoneNode('head'), petto = h.getNormalizedBoneNode('chest') || h.getNormalizedBoneNode('spine');
      if (testa) { testa.rotation.y = sguardo.x * 0.35 + Math.sin(t * 0.5) * 0.04; testa.rotation.x = -sguardo.y * 0.15 + (parlando ? Math.sin(t * 6) * 0.03 : 0) + (pensa ? -0.12 : 0); testa.rotation.z = (pensa ? 0.12 : ascolta ? -0.08 : 0) + Math.sin(t * 0.7) * 0.02; }
      if (collo) collo.rotation.y = sguardo.x * 0.1;
      if (petto) petto.rotation.x = Math.sin(t * 1.6) * 0.015;
      const dx = h.getNormalizedBoneNode('rightUpperArm'), avdx = h.getNormalizedBoneNode('rightLowerArm');
      if (dx) {
        if (saluto >= 0) { saluto += dt; const k = Math.min(1, saluto / 0.4); dx.rotation.z = 1.2 - k * 1.55; if (avdx) avdx.rotation.z = (-0.6 + Math.sin(t * 12) * 0.35) * k; if (saluto > 2.2) { saluto = -1; dx.rotation.z = 1.2; if (avdx) avdx.rotation.z = 0; } }
        else dx.rotation.z = 1.2 + Math.sin(t * 1.1) * 0.03;
      }
      bersaglio.position.set(camera.position.x + sguardo.x * 0.6, camera.position.y + sguardo.y * 0.4 + (pensa ? 0.4 : 0), camera.position.z);
      vrm.update(dt);
    } else {
      P.busto.position.y = Math.sin(t * 1.6) * 0.025; P.torso.scale.y = 1 + Math.sin(t * 1.6) * 0.012;
      P.testa.rotation.y = sguardo.x * 0.35 + Math.sin(t * 0.5) * 0.05;
      P.testa.rotation.x = -sguardo.y * 0.2 + Math.sin(t * 0.7) * 0.025 + (parlando ? Math.sin(t * 6) * 0.04 : 0) + (pensa ? -0.12 : 0) + (ascolta ? 0.06 : 0);
      P.testa.rotation.z = (pensa ? 0.12 : ascolta ? -0.08 : 0) + Math.sin(t * 0.6) * 0.02;
      P.testa.position.y = -0.15 + Math.sin(t * 1.6) * 0.02;
      P.occhi.forEach(o => { o.scale.y = Math.max(0.08, occhio); o.userData.iride.forEach(m => { m.position.x = sguardo.x * 0.04 + (m.geometry.parameters.radius < 0.04 ? 0.045 : 0); m.position.y = (sguardo.y * 0.03 + (pensa ? 0.05 : 0)) + (m.geometry.parameters.radius < 0.04 ? 0.05 : -0.01); }); });
      P.sopracciglia.forEach((b, k) => { b.position.y = 0.37 + (ascolta ? 0.05 : 0) + (pensa && k === 1 ? 0.07 : 0) + (felice ? 0.03 : 0); });
      P.apertura.scale.y = 0.01 + apertura * 0.75; P.sorriso.scale.set(felice ? 1.25 : 1, felice ? 0.75 : 0.55, 1);
      P.braccia.forEach((b, k) => { const s = k === 0 ? -1 : 1; b.rotation.x = Math.sin(t * 1.1 + k) * 0.03; if (!(k === 1 && saluto >= 0)) b.rotation.z = s * 0.14 + Math.sin(t * 1.3 + k) * 0.02; });
      if (saluto >= 0) { saluto += dt; const b = P.braccia[1], k = Math.min(1, saluto / 0.35);
        b.rotation.z = 0.14 + k * 2.55 + Math.sin(t * 11) * 0.18 * k; if (saluto > 2.2) saluto = -1; }
    }
    renderer.render(scena, camera);
  }
  requestAnimationFrame(ciclo);

  function vocePreferita() {
    const tutte = ('speechSynthesis' in window) ? speechSynthesis.getVoices() : [];
    return tutte.find(v => v.name === op.voce) || tutte.find(v => (v.lang || '').toLowerCase().startsWith('it') && /female|elsa|isabella|alice|federica|paola|donna|google italiano/i.test(v.name))
      || tutte.find(v => (v.lang || '').toLowerCase().startsWith('it'));
  }

  return {
    opzioni: op,
    stato(s) { stato = s || 'riposo'; },
    saluta() { saluto = 0; },
    /** Parla con la voce del browser. Restituisce una Promise che si chiude alla fine. */
    parla(testo, extra = {}) {
      return new Promise(fine => {
        if (!('speechSynthesis' in window) || !testo) { fine(false); return; }
        speechSynthesis.cancel();
        const pezzi = (testo.match(/[^.!?…]+[.!?…]*\s*/g) || [testo]).map(s => s.trim()).filter(Boolean);
        let i = 0, partito = false;
        const avanti = () => {
          if (i >= pezzi.length) { parlando = false; stato = 'riposo'; fine(true); return; }
          const u = new SpeechSynthesisUtterance(pezzi[i++]);
          const v = vocePreferita(); if (v) { u.voice = v; u.lang = v.lang; } else u.lang = 'it-IT';
          u.rate = Number(extra.velocita || op.velocita || 1); u.pitch = Number(extra.tono || op.tono || 1);
          u.onstart = () => { partito = true; parlando = true; };
          u.onboundary = () => { impulso = 1; };
          u.onend = avanti;
          u.onerror = e => { parlando = false; if (!partito && e.error === 'not-allowed') { contenitore.dispatchEvent(new CustomEvent('avatar-muto', { bubbles: true })); fine(false); } else avanti(); };
          speechSynthesis.speak(u);
        };
        avanti();
      });
    },
    zitta() {
      try { speechSynthesis.cancel(); } catch (e) {}
      try { if (audioCorrente) audioCorrente.pause(); } catch (e) {}
      analizzatore = null; parlando = false;
    },
    /**
     * Parla con un file audio vero (la voce di Gemini): la bocca segue il
     * volume della voce, sillaba per sillaba. `sorgente` è un indirizzo o un
     * «data:audio/...;base64,...». Restituisce una Promise con:
     *   'fatto'   ha parlato fino in fondo
     *   'muto'    il browser non lascia partire l'audio senza un tocco
     *             (manda anche l'evento 'avatar-muto', per mostrare il pulsante)
     *   'errore'  l'audio non si apre: chi chiama può usare la voce del browser
     * Il contesto audio è uno solo e si riusa: i browser ne concedono pochi.
     */
    parlaAudio(sorgente) {
      return new Promise(async fine => {
        try { speechSynthesis.cancel(); } catch (e) {}
        try { if (audioCorrente) audioCorrente.pause(); } catch (e) {}
        const audio = new Audio(); audioCorrente = audio;
        const chiudi = esito => {
          if (audioCorrente === audio) { analizzatore = null; parlando = false; stato = 'riposo'; }
          fine(esito);
        };
        try {
          if (!contestoAudio) contestoAudio = new (window.AudioContext || window.webkitAudioContext)();
          // senza un tocco recente il contesto resta «sospeso»: si aspetta poco
          if (contestoAudio.state !== 'running') {
            await Promise.race([contestoAudio.resume().catch(() => {}), new Promise(r => setTimeout(r, 400))]);
          }
          if (contestoAudio.state !== 'running') {
            contenitore.dispatchEvent(new CustomEvent('avatar-muto', { bubbles: true }));
            chiudi('muto'); return;
          }
          const nodo = contestoAudio.createMediaElementSource(audio);
          const an = contestoAudio.createAnalyser(); an.fftSize = 512;
          nodo.connect(an); an.connect(contestoAudio.destination);
          audio.onended = () => chiudi('fatto');
          audio.onerror = () => chiudi('errore');
          audio.src = sorgente;
          await audio.play();
          analizzatore = an; datiAudio = new Uint8Array(an.fftSize); parlando = true;
        } catch (e) {
          const muto = e && e.name === 'NotAllowedError';
          if (muto) contenitore.dispatchEvent(new CustomEvent('avatar-muto', { bubbles: true }));
          chiudi(muto ? 'muto' : 'errore');
        }
      });
    },
    get parlando() { return parlando; },
  };
}
