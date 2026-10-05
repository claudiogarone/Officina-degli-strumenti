# -*- coding: utf-8 -*-
"""
Cancelleria — generatore di documenti e materiale di carta intestata.
Modulo della Dashboard Registri Lezioni.

Produce PDF pronti da stampare o inviare: carta intestata, biglietti da visita,
preventivi, ricevute, informativa privacy con contratto, accordo di riservatezza
e attestati di partecipazione.
"""

import io
import json
import os
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Table, TableStyle, KeepTogether)

GRIGIO = colors.HexColor("#6b6a66")
INCHIOSTRO = colors.HexColor("#1a1a19")
RIGA = colors.HexColor("#d9d8d4")

MARGINE = 20 * mm
ALTEZZA_TESTATA = 40 * mm
ALTEZZA_PIEDE = 16 * mm


# ---------------------------------------------------------------------------
# UTILITÀ
# ---------------------------------------------------------------------------

def cartella_loghi():
    """Cartella loghi/ accanto al codice, dove stanno i loghi inclusi nella repo."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "loghi")


def logo_locale(nome_file):
    """Legge un logo dalla cartella loghi/ della repo. None se non c'è."""
    if not nome_file:
        return None
    p = os.path.join(cartella_loghi(), nome_file)
    try:
        with open(p, "rb") as f:
            return f.read()
    except Exception:
        return None


def carica_marchi(percorso="marchi.json"):
    """Legge l'anagrafica dei marchi; se manca, restituisce un minimo utilizzabile."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, percorso), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("mittente_predefinito", {}), d.get("marchi", [])
    except Exception:
        return ({}, [{"nome": "ENESTAR Maker Lab",
                      "sottotitolo": "Innovazione, Tecnologia e Ingegno",
                      "colore": "#1baf7a", "logo": ""}])


def colore(hex_str, fallback="#1baf7a"):
    try:
        return colors.HexColor(hex_str if hex_str else fallback)
    except Exception:
        return colors.HexColor(fallback)


def euro(v):
    """1234.5 -> '1.234,50 €' (formato italiano)."""
    try:
        s = f"{float(v):,.2f}"
    except Exception:
        return str(v)
    return s.replace(",", "§").replace(".", ",").replace("§", ".") + " €"


def data_it(d=None):
    d = d or dt.date.today()
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
            "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"{d.day} {mesi[d.month - 1]} {d.year}"


def _logo_oggetto(logo_bytes):
    """Da bytes a qualcosa che reportlab sa disegnare. Gestisce PNG/JPG e SVG."""
    if not logo_bytes:
        return None
    testa = logo_bytes[:400].lstrip()
    if testa.startswith(b"<?xml") or testa.startswith(b"<svg") or b"<svg" in testa:
        try:
            from svglib.svglib import svg2rlg
            return ("svg", svg2rlg(io.BytesIO(logo_bytes)))
        except Exception:
            return None
    try:
        from reportlab.lib.utils import ImageReader
        return ("img", ImageReader(io.BytesIO(logo_bytes)))
    except Exception:
        return None


def _disegna_logo(c, logo, x, y_top, alt_max):
    """Disegna il logo con l'angolo in alto a sinistra in (x, y_top).
    Restituisce la larghezza occupata."""
    if not logo:
        return 0
    tipo, ogg = logo
    try:
        if tipo == "img":
            iw, ih = ogg.getSize()
            k = alt_max / float(ih)
            w, h = iw * k, alt_max
            c.drawImage(ogg, x, y_top - h, width=w, height=h,
                        mask="auto", preserveAspectRatio=True)
            return w
        else:
            from reportlab.graphics import renderPDF
            k = alt_max / float(ogg.height or 1)
            ogg.scale(k, k)
            ogg.width *= k
            ogg.height *= k
            renderPDF.draw(ogg, c, x, y_top - ogg.height)
            return ogg.width
    except Exception:
        return 0


def _tronca(c, testo, font, size, larghezza):
    """Accorcia con i puntini se non ci sta."""
    if pdfmetrics.stringWidth(testo, font, size) <= larghezza:
        return testo
    while testo and pdfmetrics.stringWidth(testo + "…", font, size) > larghezza:
        testo = testo[:-1]
    return testo + "…"



# ---------------------------------------------------------------------------
# TEMI GRAFICI — lo stile dei documenti, configurabile dal tab Cancelleria
# ---------------------------------------------------------------------------

STILI_PREDEFINITI = {
    "Elegante": {
        "font_titoli": "Times-Bold",
        "font_corpo": "Helvetica",
        "logo_posizione": "sinistra",
        "filetto": "doppio",
        "maiuscoletto": True,
        "spaziatura": "ampia",
        "piede": "completo",
        "banda_laterale": False,
        "corpo_pt": 9.5,
    },
    "Minimale": {
        "font_titoli": "Helvetica-Bold",
        "font_corpo": "Helvetica",
        "logo_posizione": "sinistra",
        "filetto": "sottile",
        "maiuscoletto": False,
        "spaziatura": "ampia",
        "piede": "minimo",
        "banda_laterale": False,
        "corpo_pt": 9.5,
    },
    "Tecnico": {
        "font_titoli": "Helvetica-Bold",
        "font_corpo": "Helvetica",
        "logo_posizione": "sinistra",
        "filetto": "pieno",
        "maiuscoletto": False,
        "spaziatura": "compatta",
        "piede": "completo",
        "banda_laterale": True,
        "corpo_pt": 9,
    },
    "Classico": {
        "font_titoli": "Times-Bold",
        "font_corpo": "Times-Roman",
        "logo_posizione": "centro",
        "filetto": "sottile",
        "maiuscoletto": True,
        "spaziatura": "ampia",
        "piede": "completo",
        "banda_laterale": False,
        "corpo_pt": 10,
    },
}


def stile_di(cfg):
    """Unisce il tema scelto con le eventuali modifiche puntuali."""
    base = dict(STILI_PREDEFINITI.get(cfg.get("tema", "Elegante"),
                                      STILI_PREDEFINITI["Elegante"]))
    base.update({k: v for k, v in (cfg.get("stile") or {}).items() if v is not None})
    return base


def _spazia(st_, base_mm):
    """Scala una distanza secondo la spaziatura del tema."""
    k = 1.25 if st_.get("spaziatura") == "ampia" else (
        0.8 if st_.get("spaziatura") == "compatta" else 1.0)
    return base_mm * k


def _maiuscoletto(testo, attivo):
    """Un maiuscoletto povero ma efficace: tutto maiuscolo e spaziato."""
    if not attivo or not testo:
        return testo
    return " ".join(testo.upper())


# ---------------------------------------------------------------------------
# TESTATA E PIEDE DI PAGINA (comuni a tutti i documenti)
# ---------------------------------------------------------------------------

def disegna_testata(c, cfg, larghezza_pag, altezza_pag):
    st_ = stile_di(cfg)
    col = colore(cfg.get("colore"))
    y_top = altezza_pag - MARGINE
    logo = cfg.get("_logo")
    m = cfg.get("mittente", {})
    centrata = st_.get("logo_posizione") == "centro"

    if st_.get("banda_laterale"):
        c.setFillColor(col)
        c.rect(0, 0, 4 * mm, altezza_pag, fill=1, stroke=0)

    if centrata:
        # logo, nome e sottotitolo centrati; contatti su una riga sotto
        larg_logo = 0
        if logo:
            larg_logo = _disegna_logo(c, logo, larghezza_pag / 2 - 9 * mm,
                                      y_top, 17 * mm)
        c.setFillColor(INCHIOSTRO)
        c.setFont(st_["font_titoli"], 15 if st_.get("maiuscoletto") else 16)
        c.drawCentredString(larghezza_pag / 2, y_top - (22 * mm if logo else 7 * mm),
                            _maiuscoletto(cfg.get("nome", ""),
                                          st_.get("maiuscoletto")))
        if cfg.get("sottotitolo"):
            c.setFillColor(GRIGIO)
            c.setFont(st_["font_corpo"], 8.5)
            c.drawCentredString(larghezza_pag / 2,
                                y_top - (27 * mm if logo else 12 * mm),
                                cfg["sottotitolo"])
        sito = (m.get("sito", "") or "").replace("https://", "").replace("http://", "").rstrip("/")
        pezzi = [p for p in [m.get("cap_citta", ""), m.get("email", ""),
                             m.get("telefono", ""), sito] if p]
        c.setFont(st_["font_corpo"], 7.4)
        c.drawCentredString(larghezza_pag / 2, y_top - (32 * mm if logo else 17 * mm),
                            _tronca(c, "  ·  ".join(pezzi), st_["font_corpo"], 7.4,
                                    larghezza_pag - 2 * MARGINE))
    else:
        x = MARGINE + (4 * mm if st_.get("banda_laterale") else 0)
        occupato = _disegna_logo(c, logo, x, y_top, 16 * mm)
        tx = x + (occupato + 6 * mm if occupato else 0)

        c.setFillColor(INCHIOSTRO)
        c.setFont(st_["font_titoli"], 13 if st_.get("maiuscoletto") else 14)
        c.drawString(tx, y_top - 7 * mm,
                     _maiuscoletto(cfg.get("nome", ""), st_.get("maiuscoletto")))
        if cfg.get("sottotitolo"):
            c.setFillColor(GRIGIO)
            c.setFont(st_["font_corpo"], 8.5)
            c.drawString(tx, y_top - 11.5 * mm, cfg["sottotitolo"])

        sito = (m.get("sito", "") or "").replace("https://", "").replace("http://", "").rstrip("/")
        righe = [r for r in [m.get("ragione_sociale", ""),
                             m.get("cap_citta", "") or m.get("indirizzo", ""),
                             m.get("email", ""), m.get("telefono", ""), sito] if r]
        c.setFont(st_["font_corpo"], 7.6)
        c.setFillColor(GRIGIO)
        yy = y_top - 4 * mm
        for r in righe[:5]:
            c.drawRightString(larghezza_pag - MARGINE, yy,
                              _tronca(c, r, st_["font_corpo"], 7.6, 70 * mm))
            yy -= 3.6 * mm

    # il filetto sotto la testata
    y_riga = altezza_pag - ALTEZZA_TESTATA
    tipo = st_.get("filetto", "sottile")
    sx = MARGINE + (4 * mm if st_.get("banda_laterale") else 0)
    if tipo == "pieno":
        c.setStrokeColor(col)
        c.setLineWidth(1.6)
        c.line(sx, y_riga, larghezza_pag - MARGINE, y_riga)
    elif tipo == "doppio":
        c.setStrokeColor(col)
        c.setLineWidth(1.1)
        c.line(sx, y_riga + 0.8 * mm, larghezza_pag - MARGINE, y_riga + 0.8 * mm)
        c.setStrokeColor(RIGA)
        c.setLineWidth(0.5)
        c.line(sx, y_riga, larghezza_pag - MARGINE, y_riga)
    elif tipo == "sottile":
        c.setStrokeColor(col)
        c.setLineWidth(0.7)
        c.line(sx, y_riga, larghezza_pag - MARGINE, y_riga)
    elif tipo == "corto":
        c.setStrokeColor(col)
        c.setLineWidth(2.2)
        c.line(sx, y_riga, sx + 24 * mm, y_riga)


def disegna_qr(c, testo, x, y, lato):
    """Disegna un codice QR di lato `lato` con angolo in basso a sinistra in (x, y)."""
    if not testo:
        return False
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        widget = qr.QrCodeWidget(testo, barLevel="M")
        b = widget.getBounds()
        w, h = b[2] - b[0], b[3] - b[1]
        d = Drawing(lato, lato, transform=[lato / w, 0, 0, lato / h, 0, 0])
        d.add(widget)
        renderPDF.draw(d, c, x, y)
        return True
    except Exception:
        return False


def disegna_piede(c, cfg, larghezza_pag, numero=True, pagina=1):
    st_ = stile_di(cfg)
    m = cfg.get("mittente", {})
    link = (cfg.get("link") or m.get("link") or "").replace("https://", "").replace("http://", "")
    sx = MARGINE + (4 * mm if st_.get("banda_laterale") else 0)

    if st_.get("piede") == "minimo":
        pezzi = [p for p in [m.get("email", ""), link] if p]
    else:
        pezzi = [p for p in [m.get("ragione_sociale", ""),
                             m.get("piva_cf", "") and f"P.IVA/C.F. {m['piva_cf']}",
                             m.get("email", ""), m.get("telefono", ""), link] if p]

    c.setStrokeColor(RIGA)
    c.setLineWidth(0.6)
    c.line(sx, ALTEZZA_PIEDE + 4 * mm, larghezza_pag - MARGINE, ALTEZZA_PIEDE + 4 * mm)
    c.setFont(st_["font_corpo"], 7)
    c.setFillColor(GRIGIO)
    c.drawString(sx, ALTEZZA_PIEDE,
                 _tronca(c, " · ".join(pezzi), st_["font_corpo"], 7,
                         larghezza_pag - sx - MARGINE - 20 * mm))
    if numero:
        c.drawRightString(larghezza_pag - MARGINE, ALTEZZA_PIEDE, f"pag. {pagina}")


# ---------------------------------------------------------------------------
# STILI DI TESTO
# ---------------------------------------------------------------------------

def stili(cfg):
    st_ = stile_di(cfg)
    col = colore(cfg.get("colore"))
    ft, fc = st_["font_titoli"], st_["font_corpo"]
    fcb = "Times-Bold" if fc.startswith("Times") else "Helvetica-Bold"
    pt = float(st_.get("corpo_pt", 9.5))
    interlinea = pt * (1.6 if st_.get("spaziatura") == "ampia" else 1.4)
    dopo = _spazia(st_, 2.5 * mm)

    return {
        "titolo": ParagraphStyle("t", fontName=ft, fontSize=pt + 5.5,
                                 leading=pt + 9, textColor=col,
                                 spaceAfter=_spazia(st_, 2 * mm)),
        "sottotitolo": ParagraphStyle("st", fontName=fc, fontSize=pt,
                                      leading=pt + 3.5, textColor=GRIGIO,
                                      spaceAfter=_spazia(st_, 5 * mm)),
        "h2": ParagraphStyle("h2", fontName=fcb, fontSize=pt + 1,
                             leading=pt + 4.5, textColor=INCHIOSTRO,
                             spaceBefore=_spazia(st_, 4 * mm),
                             spaceAfter=_spazia(st_, 1.5 * mm)),
        "corpo": ParagraphStyle("c", fontName=fc, fontSize=pt, leading=interlinea,
                                alignment=TA_JUSTIFY, textColor=INCHIOSTRO,
                                spaceAfter=dopo),
        "piccolo": ParagraphStyle("p", fontName=fc, fontSize=pt - 1.5,
                                  leading=pt + 1.5, textColor=GRIGIO),
        "destra": ParagraphStyle("d", fontName=fc, fontSize=pt,
                                 leading=pt + 3.5, alignment=TA_RIGHT),
        "centro": ParagraphStyle("ce", fontName=fc, fontSize=pt + 0.5,
                                 leading=pt + 5.5, alignment=TA_CENTER),
    }


def _documento(cfg, elementi, orizzontale=False):
    """Costruisce un PDF multi-pagina con testata e piede su ogni foglio."""
    buf = io.BytesIO()
    formato = landscape(A4) if orizzontale else A4
    L, H = formato

    doc = BaseDocTemplate(buf, pagesize=formato,
                          leftMargin=MARGINE, rightMargin=MARGINE,
                          topMargin=ALTEZZA_TESTATA + 8 * mm,
                          bottomMargin=ALTEZZA_PIEDE + 10 * mm,
                          title=cfg.get("_titolo_pdf", "Documento"),
                          author=cfg.get("mittente", {}).get("ragione_sociale", ""))

    _st = stile_di(cfg)
    sx = MARGINE + (4 * mm if _st.get("banda_laterale") else 0)
    frame = Frame(sx, ALTEZZA_PIEDE + 10 * mm,
                  L - sx - MARGINE, H - ALTEZZA_TESTATA - ALTEZZA_PIEDE - 18 * mm,
                  id="corpo", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)

    def su_pagina(c, d):
        disegna_testata(c, cfg, L, H)
        disegna_piede(c, cfg, L, numero=True, pagina=c.getPageNumber())

    doc.addPageTemplates([PageTemplate(id="std", frames=[frame], onPage=su_pagina)])
    doc.build(elementi)
    return buf.getvalue()


def _blocco_destinatario(s, dest):
    """Riquadro 'Spett.le' in alto a destra."""
    righe = [r for r in [dest.get("nome", ""), dest.get("indirizzo", ""),
                         dest.get("citta", ""), dest.get("piva", "")] if r]
    if not righe:
        return Spacer(1, 1)
    testo = "<b>Spett.le</b><br/>" + "<br/>".join(righe)
    t = Table([[Paragraph(testo, s["corpo"])]], colWidths=[75 * mm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    cont = Table([["", t]], colWidths=[None, 75 * mm])
    cont.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return cont


def _firme(s, sinistra="Il Fornitore", destra="Il Cliente", luogo_data=True):
    righe = []
    if luogo_data:
        righe.append(Paragraph("Luogo e data _______________________________",
                               s["corpo"]))
        righe.append(Spacer(1, 10 * mm))
    t = Table([[Paragraph(f"{sinistra}<br/><br/>______________________________", s["corpo"]),
                Paragraph(f"{destra}<br/><br/>______________________________", s["corpo"])]],
              colWidths=[80 * mm, 80 * mm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    righe.append(t)
    return righe


# ---------------------------------------------------------------------------
# 1 — CARTA INTESTATA
# ---------------------------------------------------------------------------

def carta_intestata(cfg, oggetto="", corpo="", destinatario=None):
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf="Carta intestata")
    el = []
    if destinatario and any(destinatario.values()):
        el += [_blocco_destinatario(s, destinatario), Spacer(1, 8 * mm)]
    el.append(Paragraph(f"{cfg.get('_luogo', 'Montesano sulla Marcellana')}, "
                        f"{data_it()}", s["destra"]))
    el.append(Spacer(1, 6 * mm))
    if oggetto:
        el.append(Paragraph(f"<b>Oggetto:</b> {oggetto}", s["corpo"]))
        el.append(Spacer(1, 4 * mm))
    for blocco in (corpo or "").split("\n"):
        el.append(Paragraph(blocco.strip() or "&nbsp;", s["corpo"]))
    el.append(Spacer(1, 14 * mm))
    el.append(Paragraph("Cordiali saluti,", s["corpo"]))
    el.append(Spacer(1, 12 * mm))
    el.append(Paragraph(cfg.get("mittente", {}).get("ragione_sociale", ""), s["corpo"]))
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 2 — BIGLIETTI DA VISITA (10 per foglio A4, 85 × 55 mm)
# ---------------------------------------------------------------------------

def biglietti_da_visita(cfg, ruolo="", crocini=True, con_qr=True):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Biglietti da visita")
    L, H = A4
    bw, bh = 85 * mm, 55 * mm
    cols, rows = 2, 5
    mx = (L - cols * bw) / 2
    my = (H - rows * bh) / 2
    col = colore(cfg.get("colore"))
    m = cfg.get("mittente", {})
    logo = cfg.get("_logo")

    for r in range(rows):
        for q in range(cols):
            x = mx + q * bw
            y = H - my - (r + 1) * bh

            if crocini:
                c.setStrokeColor(RIGA)
                c.setLineWidth(0.3)
                for (xa, ya) in [(x, y), (x + bw, y), (x, y + bh), (x + bw, y + bh)]:
                    c.line(xa - 3 * mm, ya, xa + 3 * mm, ya)
                    c.line(xa, ya - 3 * mm, xa, ya + 3 * mm)

            # banda di colore a sinistra
            c.setFillColor(col)
            c.rect(x, y, 3.5 * mm, bh, fill=1, stroke=0)

            px = x + 10 * mm
            ha_logo = bool(logo)
            if ha_logo:
                _disegna_logo(c, logo, px, y + bh - 6 * mm, 10 * mm)

            # titolo del marchio
            y_nome = y + bh - (21 * mm if ha_logo else 13 * mm)
            c.setFillColor(INCHIOSTRO)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(px, y_nome, _tronca(c, cfg.get("nome", ""),
                                             "Helvetica-Bold", 11, bw - 16 * mm))
            if cfg.get("sottotitolo"):
                c.setFillColor(GRIGIO)
                c.setFont("Helvetica", 6.8)
                c.drawString(px, y_nome - 4 * mm,
                             _tronca(c, cfg["sottotitolo"], "Helvetica", 6.8, bw - 16 * mm))

            # filetto di separazione
            c.setStrokeColor(RIGA)
            c.setLineWidth(0.5)
            c.line(px, y + 24 * mm, x + bw - 7 * mm, y + 24 * mm)

            # persona e recapiti
            c.setFillColor(INCHIOSTRO)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(px, y + 18.5 * mm, _tronca(c, m.get("ragione_sociale", ""),
                                                    "Helvetica-Bold", 9, bw - 16 * mm))
            yy = y + 14.5 * mm
            if ruolo:
                c.setFillColor(GRIGIO)
                c.setFont("Helvetica", 7)
                c.drawString(px, yy, _tronca(c, ruolo, "Helvetica", 7, bw - 16 * mm))
                yy -= 4.6 * mm
            else:
                yy -= 1.5 * mm

            link_qr = cfg.get("link") or m.get("link", "")
            if con_qr and link_qr:
                disegna_qr(c, link_qr, x + bw - 20 * mm, y + 6 * mm, 15 * mm)

            sito = (m.get("sito", "") or "").replace("https://", "").replace("http://", "").rstrip("/")
            c.setFillColor(GRIGIO)
            c.setFont("Helvetica", 7)
            larg_txt = bw - 16 * mm - (20 * mm if (con_qr and link_qr) else 0)
            for riga in [m.get("email", ""), m.get("telefono", ""), sito]:
                if riga:
                    c.drawString(px, yy, _tronca(c, riga, "Helvetica", 7, larg_txt))
                    yy -= 3.6 * mm
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3 — PREVENTIVO
# ---------------------------------------------------------------------------

def preventivo(cfg, numero, destinatario, voci, validita_giorni=30,
               note="", aliquota_iva=0.0, condizioni=""):
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf=f"Preventivo {numero}")
    el = [_blocco_destinatario(s, destinatario), Spacer(1, 6 * mm),
          Paragraph(f"Preventivo n. {numero}", s["titolo"]),
          Paragraph(f"Montesano sulla Marcellana, {data_it()} · "
                    f"valido {validita_giorni} giorni", s["sottotitolo"])]

    dati = [["Descrizione", "Q.tà", "Prezzo unit.", "Importo"]]
    imponibile = 0.0
    for v in voci:
        q = float(v.get("quantita") or 0)
        p = float(v.get("prezzo") or 0)
        tot = q * p
        imponibile += tot
        dati.append([Paragraph(v.get("descrizione", ""), s["corpo"]),
                     f"{q:g}", euro(p), euro(tot)])

    t = Table(dati, colWidths=[None, 18 * mm, 28 * mm, 28 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), colore(cfg.get("colore"))),
        ("FONT", (1, 1), (-1, -1), "Helvetica", 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RIGA),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el += [t, Spacer(1, 5 * mm)]

    iva = imponibile * (aliquota_iva / 100.0)
    tot_righe = [["Imponibile", euro(imponibile)]]
    if aliquota_iva:
        tot_righe.append([f"IVA {aliquota_iva:g}%", euro(iva)])
    tot_righe.append(["Totale", euro(imponibile + iva)])

    tt = Table(tot_righe, colWidths=[40 * mm, 34 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -2), "Helvetica", 9.5),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.0, colore(cfg.get("colore"))),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    el += [tt, Spacer(1, 7 * mm)]

    if not aliquota_iva:
        el.append(Paragraph("Operazione non soggetta a IVA. Indicare in fattura il "
                            "regime fiscale applicabile.", s["piccolo"]))
        el.append(Spacer(1, 4 * mm))
    if note:
        el += [Paragraph("Note", s["h2"]), Paragraph(note.replace("\n", "<br/>"), s["corpo"])]
    if condizioni:
        el += [Paragraph("Condizioni", s["h2"]),
               Paragraph(condizioni.replace("\n", "<br/>"), s["corpo"])]
    el.append(Spacer(1, 10 * mm))
    el += _firme(s, "Il Fornitore", "Per accettazione, il Cliente", luogo_data=False)
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 4 — RICEVUTA
# ---------------------------------------------------------------------------

def ricevuta(cfg, numero, destinatario, descrizione, importo,
             modalita="Bonifico bancario", data_pag=None, marca_bollo=True):
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf=f"Ricevuta {numero}")
    el = [_blocco_destinatario(s, destinatario), Spacer(1, 6 * mm),
          Paragraph(f"Ricevuta n. {numero}", s["titolo"]),
          Paragraph(f"Montesano sulla Marcellana, {data_it(data_pag)}", s["sottotitolo"]),
          Paragraph(
              f"Si attesta di aver ricevuto da <b>{destinatario.get('nome', '')}</b> "
              f"la somma di <b>{euro(importo)}</b> a saldo di quanto segue:", s["corpo"]),
          Spacer(1, 3 * mm),
          Paragraph(descrizione.replace("\n", "<br/>"), s["corpo"]),
          Spacer(1, 4 * mm),
          Paragraph(f"Modalità di pagamento: {modalita}.", s["corpo"]),
          Spacer(1, 6 * mm),
          Paragraph("Operazione non soggetta a IVA. Verificare con il proprio "
                    "consulente il regime fiscale e gli obblighi applicabili.",
                    s["piccolo"])]
    if marca_bollo and float(importo or 0) > 77.47:
        el += [Spacer(1, 3 * mm),
               Paragraph("Per importi superiori a 77,47 € è dovuta l'imposta di bollo "
                         "di 2,00 € a carico del committente: applicare la marca "
                         "nello spazio sottostante.", s["piccolo"]),
               Spacer(1, 3 * mm)]
        tb = Table([[""]], colWidths=[40 * mm], rowHeights=[22 * mm])
        tb.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, RIGA)]))
        el.append(tb)
    el.append(Spacer(1, 12 * mm))
    el += _firme(s, "Il Fornitore", "", luogo_data=False)
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 5 — INFORMATIVA PRIVACY (art. 13 GDPR) + CONTRATTO DI FORNITURA
# ---------------------------------------------------------------------------

def informativa_privacy(cfg, cliente, oggetto_fornitura, corrispettivo,
                        acconto="", modalita_pagamento="bonifico bancario",
                        termine_consegna="", con_contratto=True):
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf="Informativa privacy e contratto")
    m = cfg.get("mittente", {})
    titolare = m.get("ragione_sociale", "")
    sede = m.get("cap_citta", "") or m.get("indirizzo", "")

    el = [Paragraph("Informativa sul trattamento dei dati personali", s["titolo"]),
          Paragraph("ai sensi dell'art. 13 del Regolamento UE 2016/679 (GDPR)",
                    s["sottotitolo"]),
          Paragraph(f"<b>Fornitore:</b> {titolare}<br/>"
                    f"<b>Cliente:</b> {cliente.get('nome', '')}"
                    + (f"<br/>{cliente.get('indirizzo', '')}" if cliente.get("indirizzo") else "")
                    + (f"<br/>C.F./P.IVA {cliente.get('piva', '')}" if cliente.get("piva") else ""),
                    s["corpo"]),
          Spacer(1, 3 * mm),
          Paragraph(
              "Ai sensi e per gli effetti dell'art. 13 del Regolamento UE 2016/679, "
              "relativo alla protezione delle persone fisiche con riguardo al "
              "trattamento dei dati personali, La informiamo che i dati da Lei "
              "forniti saranno trattati secondo i principi di liceità, correttezza, "
              "trasparenza e tutela della Sua riservatezza.", s["corpo"]),

          Paragraph("1. Titolare del trattamento", s["h2"]),
          Paragraph(f"Il Titolare del trattamento è {titolare}, con sede in {sede}"
                    + (f", email {m.get('email', '')}" if m.get("email") else "") + ".",
                    s["corpo"]),

          Paragraph("2. Finalità e base giuridica", s["h2"]),
          Paragraph(
              "I dati sono trattati per l'esecuzione del rapporto contrattuale in "
              "essere e degli adempimenti connessi (art. 6, par. 1, lett. b del "
              "Regolamento), nonché per l'assolvimento degli obblighi di legge, "
              "fiscali e contabili (art. 6, par. 1, lett. c).", s["corpo"]),

          Paragraph("3. Natura del conferimento", s["h2"]),
          Paragraph(
              "Il conferimento dei dati è necessario per la conclusione e "
              "l'esecuzione del contratto: l'eventuale rifiuto comporta "
              "l'impossibilità di dare corso al rapporto.", s["corpo"]),

          Paragraph("4. Modalità del trattamento", s["h2"]),
          Paragraph(
              "Il trattamento è effettuato con strumenti cartacei ed elettronici, "
              "con misure tecniche e organizzative adeguate a garantire la sicurezza "
              "dei dati e a prevenirne la perdita, gli usi illeciti o non corretti e "
              "gli accessi non autorizzati.", s["corpo"]),

          Paragraph("5. Comunicazione e diffusione", s["h2"]),
          Paragraph(
              "I dati potranno essere comunicati a consulenti fiscali e contabili, "
              "istituti di credito, soggetti che svolgono attività strumentali per "
              "conto del Titolare e alle autorità competenti nei casi previsti dalla "
              "legge. I dati non sono oggetto di diffusione né trasferiti fuori "
              "dallo Spazio Economico Europeo.", s["corpo"]),

          Paragraph("6. Periodo di conservazione", s["h2"]),
          Paragraph(
              "I dati sono conservati per la durata del rapporto contrattuale e, "
              "successivamente, per il tempo previsto dagli obblighi di legge in "
              "materia fiscale, contabile e civilistica.", s["corpo"]),

          Paragraph("7. Diritti dell'interessato", s["h2"]),
          Paragraph(
              "Lei può esercitare in ogni momento i diritti previsti dagli articoli "
              "da 15 a 22 del Regolamento: accesso, rettifica, cancellazione, "
              "limitazione, portabilità e opposizione al trattamento, scrivendo al "
              "Titolare ai recapiti sopra indicati. Ha inoltre diritto di proporre "
              "reclamo al Garante per la protezione dei dati personali.", s["corpo"]),
          ]

    if con_contratto:
        righe_contratto = [
            Paragraph("Oggetto e condizioni della fornitura", s["titolo"]),
            Paragraph("Le parti concordano quanto segue.", s["corpo"]),
            Paragraph("Oggetto", s["h2"]),
            Paragraph(oggetto_fornitura.replace("\n", "<br/>"), s["corpo"]),
            Paragraph("Corrispettivo e pagamento", s["h2"]),
        ]
        testo_c = f"Il corrispettivo pattuito è pari a <b>{euro(corrispettivo)}</b>"
        if acconto:
            testo_c += f", di cui {euro(acconto)} a titolo di acconto alla " \
                       f"sottoscrizione e il residuo a saldo alla consegna"
        else:
            testo_c += ", da corrispondere a saldo alla consegna"
        testo_c += f", a mezzo {modalita_pagamento}."
        righe_contratto.append(Paragraph(testo_c, s["corpo"]))
        if termine_consegna:
            righe_contratto += [Paragraph("Termine di consegna", s["h2"]),
                                Paragraph(termine_consegna, s["corpo"])]
        righe_contratto += [
            Paragraph("Proprietà intellettuale", s["h2"]),
            Paragraph(
                "Salvo diverso accordo scritto, il Fornitore conserva la titolarità "
                "delle soluzioni, dei metodi e del know-how impiegati e preesistenti; "
                "al Cliente è riconosciuto il diritto d'uso di quanto realizzato per "
                "le finalità indicate nell'oggetto.", s["corpo"]),
            Paragraph("Riservatezza", s["h2"]),
            Paragraph(
                "Ciascuna parte si impegna a non divulgare a terzi le informazioni "
                "tecniche, commerciali e organizzative apprese in esecuzione del "
                "presente accordo.", s["corpo"]),
            Spacer(1, 8 * mm),
        ]
        el += righe_contratto

    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Il Cliente dichiara di aver ricevuto e letto l'informativa che precede e di "
        "accettare le condizioni sopra riportate.", s["corpo"]))
    el.append(Spacer(1, 10 * mm))
    el += _firme(s, "Il Fornitore", "Il Cliente")
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 6 — ACCORDO DI RISERVATEZZA (NDA)
# ---------------------------------------------------------------------------

def accordo_riservatezza(cfg, controparte, oggetto, durata_anni=5,
                         reciproco=True, penale="", foro="Salerno"):
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf="Accordo di riservatezza")
    m = cfg.get("mittente", {})
    titolare = m.get("ragione_sociale", "")
    sede = m.get("cap_citta", "") or m.get("indirizzo", "")
    tipo = "reciproco" if reciproco else "unilaterale"

    if reciproco:
        intro_parti = ("Ciascuna parte potrà rendere note all'altra informazioni "
                       "riservate; gli obblighi del presente accordo si applicano "
                       "pertanto a entrambe, indifferentemente nella veste di parte "
                       "divulgante e di parte ricevente.")
    else:
        intro_parti = (f"{titolare} (la \"Parte Divulgante\") renderà note alla "
                       f"controparte (la \"Parte Ricevente\") informazioni riservate; "
                       f"gli obblighi del presente accordo gravano sulla Parte "
                       f"Ricevente.")

    el = [
        Paragraph(f"Accordo di riservatezza ({tipo})", s["titolo"]),
        Paragraph(f"Montesano sulla Marcellana, {data_it()}", s["sottotitolo"]),

        Paragraph("Tra", s["h2"]),
        Paragraph(f"<b>{titolare}</b>, con sede in {sede}"
                  + (f", C.F./P.IVA {m.get('piva_cf', '')}" if m.get("piva_cf") else "")
                  + " (di seguito anche \"la Parte\");", s["corpo"]),
        Paragraph("e", s["h2"]),
        Paragraph(f"<b>{controparte.get('nome', '')}</b>"
                  + (f", con sede in {controparte.get('indirizzo', '')}"
                     if controparte.get("indirizzo") else "")
                  + (f", C.F./P.IVA {controparte.get('piva', '')}"
                     if controparte.get("piva") else "")
                  + " (di seguito anche \"la Controparte\").", s["corpo"]),

        Paragraph("Premesso che", s["h2"]),
        Paragraph(
            "le parti intendono avviare contatti e valutazioni reciproche in "
            f"relazione a: {oggetto}; che nel corso di tali contatti potranno essere "
            "scambiate informazioni di carattere riservato; e che le parti intendono "
            "disciplinarne l'uso e la protezione, si conviene quanto segue.", s["corpo"]),

        Paragraph("Art. 1 — Informazioni riservate", s["h2"]),
        Paragraph(
            "Per \"informazioni riservate\" si intende ogni informazione, in qualsiasi "
            "forma comunicata, di natura tecnica, progettuale, scientifica, "
            "industriale, commerciale, economica o organizzativa, inclusi disegni, "
            "schemi, firmware, codice sorgente, prototipi, risultati di prove, "
            "descrizioni di invenzioni non ancora pubblicate e domande di brevetto "
            "non accessibili al pubblico. " + intro_parti, s["corpo"]),

        Paragraph("Art. 2 — Obblighi della parte ricevente", s["h2"]),
        Paragraph(
            "La parte ricevente si impegna a: mantenere strettamente riservate le "
            "informazioni ricevute; utilizzarle esclusivamente per le finalità di "
            "valutazione indicate in premessa; non divulgarle a terzi senza previo "
            "consenso scritto; limitarne l'accesso ai soli collaboratori che ne "
            "abbiano effettiva necessità, previo vincolo di riservatezza di contenuto "
            "almeno equivalente; adottare misure di custodia non inferiori a quelle "
            "usate per le proprie informazioni riservate di pari importanza.",
            s["corpo"]),

        Paragraph("Art. 3 — Esclusioni", s["h2"]),
        Paragraph(
            "Gli obblighi non si applicano alle informazioni che: siano di pubblico "
            "dominio al momento della comunicazione o lo diventino successivamente "
            "senza violazione del presente accordo; fossero già legittimamente note "
            "alla parte ricevente, come da documentazione anteriore; siano state "
            "sviluppate autonomamente senza utilizzo delle informazioni riservate; "
            "debbano essere comunicate per obbligo di legge o per ordine "
            "dell'autorità, dandone tempestivo avviso scritto all'altra parte.",
            s["corpo"]),

        Paragraph("Art. 4 — Assenza di licenze e di obbligo a contrarre", s["h2"]),
        Paragraph(
            "La comunicazione delle informazioni riservate non attribuisce alcun "
            "diritto, licenza o opzione su brevetti, domande di brevetto, know-how o "
            "altri diritti di proprietà intellettuale, che restano di titolarità "
            "della parte divulgante. Il presente accordo non obbliga le parti a "
            "concludere alcun ulteriore contratto.", s["corpo"]),

        Paragraph("Art. 5 — Durata", s["h2"]),
        Paragraph(
            f"Gli obblighi di riservatezza decorrono dalla sottoscrizione e "
            f"permangono per {durata_anni} anni dalla cessazione dei contatti fra le "
            "parti, indipendentemente dalla conclusione di accordi successivi.",
            s["corpo"]),

        Paragraph("Art. 6 — Restituzione del materiale", s["h2"]),
        Paragraph(
            "Su richiesta scritta, la parte ricevente restituirà o distruggerà entro "
            "trenta giorni ogni documento e supporto contenente informazioni "
            "riservate, conservandone al più una copia ai soli fini di prova "
            "dell'adempimento.", s["corpo"]),
    ]

    if penale:
        el += [Paragraph("Art. 7 — Inadempimento", s["h2"]),
               Paragraph(
                   f"In caso di violazione degli obblighi di riservatezza la parte "
                   f"inadempiente sarà tenuta al pagamento di una penale pari a "
                   f"{euro(penale)}, salvo il risarcimento del maggior danno.",
                   s["corpo"])]

    el += [
        Paragraph("Legge applicabile e foro competente", s["h2"]),
        Paragraph(
            f"Il presente accordo è regolato dalla legge italiana. Per ogni "
            f"controversia è competente in via esclusiva il Foro di {foro}.",
            s["corpo"]),
        Spacer(1, 10 * mm),
    ]
    el += _firme(s, titolare, controparte.get("nome", "La Controparte"))
    el += [Spacer(1, 6 * mm),
           Paragraph(
               "Ai sensi degli artt. 1341 e 1342 c.c. le parti approvano "
               "specificamente le clausole di cui agli articoli 5 (durata)"
               + (", 7 (penale)" if penale else "")
               + " e foro competente.", s["piccolo"]),
           Spacer(1, 8 * mm)]
    el += _firme(s, titolare, controparte.get("nome", "La Controparte"),
                 luogo_data=False)
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 7 — ATTESTATO DI PARTECIPAZIONE
# ---------------------------------------------------------------------------

def attestato(cfg, allievo, corso, ore, periodo="", argomenti="", luogo="Montesano S/M"):
    buf = io.BytesIO()
    L, H = landscape(A4)
    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))
    c.setTitle(f"Attestato — {allievo}")
    col = colore(cfg.get("colore"))
    m = cfg.get("mittente", {})

    c.setStrokeColor(col)
    c.setLineWidth(2.5)
    c.rect(12 * mm, 12 * mm, L - 24 * mm, H - 24 * mm)
    c.setLineWidth(0.6)
    c.rect(16 * mm, 16 * mm, L - 32 * mm, H - 32 * mm)

    occupato = _disegna_logo(c, cfg.get("_logo"), L / 2 - 9 * mm, H - 26 * mm, 16 * mm)

    c.setFillColor(INCHIOSTRO)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(L / 2, H - 50 * mm, cfg.get("nome", ""))
    if cfg.get("sottotitolo"):
        c.setFillColor(GRIGIO)
        c.setFont("Helvetica", 9)
        c.drawCentredString(L / 2, H - 55 * mm, cfg["sottotitolo"])

    c.setFillColor(col)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(L / 2, H - 75 * mm, "ATTESTATO DI PARTECIPAZIONE")

    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 11)
    c.drawCentredString(L / 2, H - 90 * mm, "Si attesta che")
    c.setFillColor(INCHIOSTRO)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(L / 2, H - 102 * mm, allievo)

    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 11)
    c.drawCentredString(L / 2, H - 114 * mm, "ha partecipato al percorso formativo")
    c.setFillColor(INCHIOSTRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(L / 2, H - 125 * mm, corso)

    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 10.5)
    try:
        ore_txt = f"{float(ore):g}".replace(".", ",")
    except Exception:
        ore_txt = str(ore)
    dettaglio = f"della durata complessiva di {ore_txt} ore"
    if periodo:
        dettaglio += f", svolto nel periodo {periodo}"
    c.drawCentredString(L / 2, H - 135 * mm, dettaglio)

    if argomenti:
        c.setFont("Helvetica", 9)
        testo = _tronca(c, "Argomenti trattati: " + argomenti, "Helvetica", 9, L - 70 * mm)
        c.drawCentredString(L / 2, H - 144 * mm, testo)

    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 9.5)
    c.drawString(30 * mm, 34 * mm, f"{luogo}, {data_it()}")
    c.drawRightString(L - 30 * mm, 46 * mm, m.get("ragione_sociale", ""))
    c.setStrokeColor(RIGA)
    c.line(L - 85 * mm, 42 * mm, L - 30 * mm, 42 * mm)
    c.setFont("Helvetica", 8)
    c.drawRightString(L - 30 * mm, 37 * mm, "Il docente")

    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 8 — SCHEDA PROGETTO (A4, una pagina per presentare un progetto)
# ---------------------------------------------------------------------------

def scheda_progetto(cfg, titolo, descrizione, punti=None, stato="",
                    cerco="", nota_riservatezza=True):
    """Il 'one-pager' di un singolo progetto: da allegare a una mail o stampare."""
    s = stili(cfg)
    cfg = dict(cfg, _titolo_pdf=f"Scheda progetto — {titolo}")
    col = colore(cfg.get("colore"))

    el = [Paragraph(titolo, s["titolo"])]
    if cfg.get("sottotitolo"):
        el.append(Paragraph(cfg["sottotitolo"], s["sottotitolo"]))
    el.append(Paragraph(descrizione.replace("\n", "<br/>"), s["corpo"]))
    el.append(Spacer(1, 3 * mm))

    punti = [p for p in (punti or []) if str(p).strip()]
    if punti:
        el.append(Paragraph("In sintesi", s["h2"]))
        pallino = f'<font color="#{col.hexval()[2:]}">■</font>'
        righe = [[Paragraph(pallino, s["corpo"]),
                  Paragraph(str(p), s["corpo"])] for p in punti]
        t = Table(righe, colWidths=[6 * mm, None])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        el.append(t)

    if stato:
        el += [Paragraph("Stato", s["h2"]), Paragraph(stato, s["corpo"])]
    if cerco:
        el += [Paragraph("Cosa cerco", s["h2"]), Paragraph(cerco, s["corpo"])]

    if nota_riservatezza:
        el += [Spacer(1, 4 * mm),
               Paragraph(
                   "Questo documento descrive il progetto a livello di risultato e "
                   "beneficio. I dettagli tecnici e implementativi sono riservati e "
                   "vengono condivisi solo previa sottoscrizione di un accordo di "
                   "riservatezza.", s["piccolo"])]

    link = cfg.get("link") or cfg.get("mittente", {}).get("link", "")
    if link:
        el += [Spacer(1, 6 * mm),
               Paragraph(f"Per contatti e approfondimenti: <b>{link}</b>", s["corpo"])]
    return _documento(cfg, el)


# ---------------------------------------------------------------------------
# 9 — VOLANTINO A5 (due per foglio A4, con QR)
# ---------------------------------------------------------------------------

def volantino(cfg, titolo, claim, testo, due_per_foglio=True):
    buf = io.BytesIO()
    L, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Volantino — {titolo}")
    col = colore(cfg.get("colore"))
    m = cfg.get("mittente", {})
    link = cfg.get("link") or m.get("link", "")
    logo = cfg.get("_logo")

    def una_facciata(y0, altezza):
        # fascia colorata in alto
        c.setFillColor(col)
        c.rect(0, y0 + altezza - 26 * mm, L, 26 * mm, fill=1, stroke=0)
        if logo:
            _disegna_logo(c, logo, 16 * mm, y0 + altezza - 4 * mm, 17 * mm)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 15)
        c.drawRightString(L - 16 * mm, y0 + altezza - 14 * mm, cfg.get("nome", ""))
        if cfg.get("sottotitolo"):
            c.setFont("Helvetica", 8.5)
            c.drawRightString(L - 16 * mm, y0 + altezza - 20 * mm, cfg["sottotitolo"])

        c.setFillColor(INCHIOSTRO)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(16 * mm, y0 + altezza - 44 * mm,
                     _tronca(c, titolo, "Helvetica-Bold", 20, L - 32 * mm))
        if claim:
            c.setFillColor(col)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(16 * mm, y0 + altezza - 52 * mm,
                         _tronca(c, claim, "Helvetica-Bold", 11, L - 32 * mm))

        # corpo a capo automatico
        c.setFillColor(GRIGIO)
        c.setFont("Helvetica", 9.5)
        yy = y0 + altezza - 64 * mm
        larghezza = L - 32 * mm - (26 * mm if link else 0)
        for paragrafo in (testo or "").split("\n"):
            parole, riga = paragrafo.split(), ""
            if not parole:
                yy -= 4 * mm
                continue
            for p in parole:
                prova = (riga + " " + p).strip()
                if pdfmetrics.stringWidth(prova, "Helvetica", 9.5) > larghezza:
                    c.drawString(16 * mm, yy, riga)
                    yy -= 4.8 * mm
                    riga = p
                else:
                    riga = prova
            if riga:
                c.drawString(16 * mm, yy, riga)
                yy -= 5.6 * mm
            if yy < y0 + 26 * mm:
                break

        # QR e recapiti in basso
        if link:
            disegna_qr(c, link, L - 16 * mm - 24 * mm, y0 + 14 * mm, 24 * mm)
        c.setFillColor(INCHIOSTRO)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(16 * mm, y0 + 24 * mm, m.get("ragione_sociale", ""))
        c.setFillColor(GRIGIO)
        c.setFont("Helvetica", 8)
        yy = y0 + 19.5 * mm
        for r in [m.get("email", ""), m.get("telefono", ""),
                  (link or "").replace("https://", "")]:
            if r:
                c.drawString(16 * mm, yy, _tronca(c, r, "Helvetica", 8, L - 70 * mm))
                yy -= 4 * mm

    if due_per_foglio:
        una_facciata(H / 2, H / 2)
        una_facciata(0, H / 2)
        c.setStrokeColor(RIGA)
        c.setDash(3, 3)
        c.setLineWidth(0.5)
        c.line(0, H / 2, L, H / 2)
        c.setDash()
    else:
        una_facciata(0, H)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 10 — ETICHETTE ADESIVE (24 per foglio A4, 70 × 37 mm)
# ---------------------------------------------------------------------------

def etichette(cfg, riga1="", riga2="", riga3="", con_qr=False, quante=24):
    buf = io.BytesIO()
    L, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Etichette")
    col = colore(cfg.get("colore"))
    link = cfg.get("link") or cfg.get("mittente", {}).get("link", "")
    logo = cfg.get("_logo")

    ew, eh = 70 * mm, 37 * mm
    cols, rows = 3, 8
    mx = (L - cols * ew) / 2
    my = (H - rows * eh) / 2
    fatte = 0
    for r in range(rows):
        for q in range(cols):
            if fatte >= quante:
                break
            x = mx + q * ew
            y = H - my - (r + 1) * eh
            c.setStrokeColor(RIGA)
            c.setLineWidth(0.3)
            c.rect(x, y, ew, eh, fill=0, stroke=1)
            c.setFillColor(col)
            c.rect(x, y, ew, 2.2 * mm, fill=1, stroke=0)

            px = x + 5 * mm
            larg = ew - 10 * mm - (18 * mm if (con_qr and link) else 0)
            if logo:
                _disegna_logo(c, logo, px, y + eh - 4 * mm, 9 * mm)
                ytxt = y + eh - 17 * mm
            else:
                ytxt = y + eh - 9 * mm

            c.setFillColor(INCHIOSTRO)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(px, ytxt, _tronca(c, riga1 or cfg.get("nome", ""),
                                           "Helvetica-Bold", 10, larg))
            if riga2:
                c.setFillColor(GRIGIO)
                c.setFont("Helvetica", 7.6)
                c.drawString(px, ytxt - 4.5 * mm, _tronca(c, riga2, "Helvetica", 7.6, larg))
            if riga3:
                c.setFillColor(GRIGIO)
                c.setFont("Helvetica", 7.6)
                c.drawString(px, ytxt - 9 * mm, _tronca(c, riga3, "Helvetica", 7.6, larg))
            if con_qr and link:
                disegna_qr(c, link, x + ew - 20 * mm, y + 6 * mm, 15 * mm)
            fatte += 1
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 11 — TESSERA CON QR (formato tascabile, fronte e retro)
# ---------------------------------------------------------------------------

def tessera_qr(cfg, invito="Inquadra il codice per tutti i miei progetti"):
    buf = io.BytesIO()
    tw, th = 55 * mm, 85 * mm          # verticale, da tenere nel portafoglio
    c = rl_canvas.Canvas(buf, pagesize=(tw, th))
    c.setTitle("Tessera QR")
    col = colore(cfg.get("colore"))
    m = cfg.get("mittente", {})
    link = cfg.get("link") or m.get("link", "")
    logo = cfg.get("_logo")

    # fronte
    c.setFillColor(col)
    c.rect(0, th - 28 * mm, tw, 28 * mm, fill=1, stroke=0)
    if logo:
        _disegna_logo(c, logo, (tw - 18 * mm) / 2, th - 5 * mm, 18 * mm)
    c.setFillColor(INCHIOSTRO)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(tw / 2, th - 38 * mm,
                        _tronca(c, cfg.get("nome", ""), "Helvetica-Bold", 11, tw - 8 * mm))
    if cfg.get("sottotitolo"):
        c.setFillColor(GRIGIO)
        c.setFont("Helvetica", 6.6)
        c.drawCentredString(tw / 2, th - 42.5 * mm,
                            _tronca(c, cfg["sottotitolo"], "Helvetica", 6.6, tw - 8 * mm))
    # QR al centro della fascia libera: sotto il sottotitolo, sopra la frase
    LATO = 27 * mm
    Y_QR = 11 * mm                      # il QR occupa da 11 a 38 mm
    if link:
        disegna_qr(c, link, (tw - LATO) / 2, Y_QR, LATO)
    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 6.4)
    c.drawCentredString(tw / 2, 5 * mm, _tronca(c, invito, "Helvetica", 6.4, tw - 6 * mm))
    c.showPage()

    # retro — testo centrato nell'altezza, con le righe lunghe mandate a capo
    def a_capo(testo, font, size, larghezza):
        """Spezza una riga troppo lunga in più righe, senza troncarla."""
        parole, righe, corrente = testo.split(), [], ""
        for p in parole:
            prova = (corrente + " " + p).strip()
            if pdfmetrics.stringWidth(prova, font, size) > larghezza and corrente:
                righe.append(corrente)
                corrente = p
            else:
                corrente = prova
        if corrente:
            righe.append(corrente)
        return righe

    larg = tw - 8 * mm
    voci = [v for v in [m.get("email", ""), m.get("telefono", ""),
                        m.get("cap_citta", ""),
                        (m.get("sito", "") or "").replace("https://", "").rstrip("/")] if v]
    righe_testo = []
    for v in voci:
        righe_testo += a_capo(v, "Helvetica", 7, larg)

    # altezza totale del blocco, per centrarlo
    alt_blocco = 6 * mm + len(righe_testo) * 4.4 * mm + 8 * mm
    y_cursore = (th + alt_blocco) / 2

    c.setFillColor(INCHIOSTRO)
    c.setFont("Helvetica-Bold", 9.5)
    for riga in a_capo(m.get("ragione_sociale", ""), "Helvetica-Bold", 9.5, larg):
        c.drawCentredString(tw / 2, y_cursore, riga)
        y_cursore -= 5 * mm
    y_cursore -= 2 * mm

    c.setFillColor(GRIGIO)
    c.setFont("Helvetica", 7)
    for riga in righe_testo:
        c.drawCentredString(tw / 2, y_cursore, riga)
        y_cursore -= 4.4 * mm

    c.setStrokeColor(col)
    c.setLineWidth(2)
    c.line(14 * mm, y_cursore - 2 * mm, tw - 14 * mm, y_cursore - 2 * mm)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 12 — FIRMA EMAIL (HTML da incollare nel client di posta)
# ---------------------------------------------------------------------------

def firma_email(cfg, ruolo="", claim=""):
    """Restituisce (html, testo_semplice). Non è un PDF: si incolla nella posta."""
    m = cfg.get("mittente", {})
    col = cfg.get("colore", "#1baf7a")
    link = cfg.get("link") or m.get("link", "")
    sito = (m.get("sito", "") or "").rstrip("/")

    righe = []
    if m.get("email"):
        righe.append(f'<a href="mailto:{m["email"]}" style="color:#6b6a66;'
                     f'text-decoration:none">{m["email"]}</a>')
    if m.get("telefono"):
        righe.append(m["telefono"])
    if sito:
        righe.append(f'<a href="{sito}" style="color:{col};text-decoration:none">'
                     f'{sito.replace("https://", "")}</a>')
    contatti = " &nbsp;·&nbsp; ".join(righe)

    html = f"""<table cellpadding="0" cellspacing="0" style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#1a1a19;border-collapse:collapse">
  <tr>
    <td style="border-left:3px solid {col};padding:2px 0 2px 12px">
      <div style="font-weight:700;font-size:15px">{m.get('ragione_sociale', '')}</div>
      <div style="color:#6b6a66;font-size:12px;padding-top:1px">{ruolo}</div>
      <div style="font-weight:600;color:{col};font-size:12px;padding-top:6px">{cfg.get('nome', '')}</div>
      <div style="color:#6b6a66;font-size:11px">{cfg.get('sottotitolo', '')}</div>
      <div style="color:#6b6a66;font-size:11px;padding-top:8px">{contatti}</div>
      {f'<div style="padding-top:6px"><a href="{link}" style="color:{col};font-size:11px;text-decoration:none">&#9654; {claim or "Guarda i miei progetti"}</a></div>' if link else ''}
    </td>
  </tr>
</table>"""

    testo = "\n".join([x for x in [
        m.get("ragione_sociale", ""), ruolo,
        f"{cfg.get('nome', '')} — {cfg.get('sottotitolo', '')}".strip(" —"),
        m.get("email", ""), m.get("telefono", ""), sito, link] if x])
    return html, testo
