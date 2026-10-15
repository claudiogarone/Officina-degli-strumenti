"""
sentinel.py — serve il corso «SENTINEL da zero» un modulo alla volta.

Il problema da risolvere: il file originale è una pagina sola con un indice
laterale fisso e i collegamenti interni («vai al modulo 7»). Dentro un
riquadro incorporato quei collegamenti saltano fuori dal riquadro e la pagina
si scompone — è quello che vedevi cliccando su un modulo.

Come è risolto, e perché così. La prima idea era ritagliare dal file solo la
sezione del modulo scelto. Non va bene: alcune parti (il glossario, i quiz,
le mappe) non sono scritte nell'HTML, le costruisce il JavaScript al
caricamento leggendo delle liste. Ritagliando, quel codice non trova più gli
elementi che cerca e quelle sezioni restano vuote.

Quindi la pagina resta intera — tutto il codice continua a funzionare come
l'hai scritto — e ci si aggiunge in fondo una regola di stile che nasconde
l'indice e tutte le sezioni tranne quella scelta. Il modulo si sceglie con un
menù a tendina di Streamlit, fuori dal riquadro, dove i collegamenti non
possono rompere niente.
"""

import re


def carica(percorso):
    """Legge il file e ricava l'elenco dei moduli. Restituisce (html, moduli)."""
    with open(percorso, encoding="utf-8") as f:
        html = f.read()
    return html, moduli_di(html)


def moduli_di(html):
    moduli = []
    for sez in re.findall(r"<section\b[^>]*>.*?</section>", html, re.S):
        if 'class="modhead"' not in sez:
            continue
        ident = re.search(r'<section\b[^>]*\bid="([^"]+)"', sez)
        num = re.search(r'class="modnum">([^<]*)<', sez)
        tit = re.search(r"<h2>([^<]*)</h2>", sez)
        occhiello = re.search(r'class="eyebrow">([^<]*)<', sez)
        if not ident:
            continue
        moduli.append({
            "id": ident.group(1),
            "numero": (num.group(1).strip() if num else "?"),
            "titolo": (tit.group(1).strip() if tit else "Modulo"),
            "parte": (occhiello.group(1).strip() if occhiello else ""),
        })
    return moduli


def pagina(html, id_modulo):
    """La pagina intera, con tutto nascosto tranne il modulo chiesto."""
    regola = f"""
<style id="qd-solo-un-modulo">
  /* L'indice e la testata della guida li sostituisce il menù di Quadro.
     ATTENZIONE: nasconderlo non basta. La pagina è una griglia a due
     colonne — `.shell {{ grid-template-columns: 280px minmax(0,1fr) }}` — e
     quei 280px restano riservati anche a indice nascosto: il testo finisce
     schiacciato nella colonna di destra. Per questo la griglia va sciolta. */
  .toc, nav.toc, header, .topbar,
  .mobile-toc {{ display: none !important; }}   /* c'è anche l'indice da telefono */
  .shell {{ display: block !important;
            grid-template-columns: none !important; }}

  section {{ display: none !important; }}
  section#{id_modulo} {{ display: block !important; }}

  body {{ margin: 0 !important; max-width: none !important; }}
  main {{ padding: 8px 4px 48px !important; max-width: none !important;
          width: auto !important; }}
  /* la colonna di lettura può respirare: nel riquadro lo spazio è poco */
  .col {{ max-width: 100% !important; margin: 0 !important; }}
  /* Figure e tabelle larghe: gli schemi hanno un `min-width` di 680px, che
     su telefono farebbe scorrere di lato TUTTA la pagina. Confinando lo
     scorrimento dentro il riquadro, scorre solo la figura. */
  .figbox, .tw {{ overflow-x: auto; max-width: 100%; }}
  img, svg, canvas, table {{ max-width: 100%; }}
  .figbox svg {{ max-width: none; }}   /* qui lo scorrimento è voluto */

  /* i collegamenti interni non devono più trascinare la pagina altrove */
  a[href^="#"] {{ pointer-events: none; text-decoration: none; }}
</style>
</body>"""
    if "</body>" in html:
        return html.replace("</body>", regola, 1)
    return html + regola


def etichetta(modulo):
    return f"{modulo['numero']} · {modulo['titolo']}"
