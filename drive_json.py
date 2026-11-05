"""
drive_json.py — leggere e scrivere piccoli file di testo (JSON) su Drive.

Serve alla segretaria per parlare con i suoi «altri corpi»: il bot Telegram
(che gira su Google Apps Script) e l'app da desktop leggono le tue
impostazioni e il quadro aggiornato da Quadro_Segretaria.json, e scrivono
quello che gli dici da fuori in Quadro_Dalla_Segretaria.json.

PERCHÉ IL FILE VA CARICATO A MANO LA PRIMA VOLTA
Il «service account» di Quadro può MODIFICARE un file che c'è già nella tua
cartella, ma non può CREARNE uno nuovo: Google non gli dà spazio di
archiviazione suo. È lo stesso motivo per cui Quadro_Radar.xlsx e gli altri
li hai caricati tu. Quadro ti fa scaricare il file vuoto da caricare.
"""

import io
import json


def _servizio(info):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credenziali = service_account.Credentials.from_service_account_info(
        dict(info), scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credenziali, cache_discovery=False)


def trova(info, cartelle, nome):
    """L'id del file con quel nome in una delle cartelle (o ovunque sia visibile)."""
    svc = _servizio(info)
    cartelle = [c for c in cartelle if c]
    filtro = f"name = '{nome}' and trashed = false"
    if cartelle:
        filtro += " and (" + " or ".join(f"'{c}' in parents" for c in cartelle) + ")"
    r = svc.files().list(q=filtro, fields="files(id, name, modifiedTime)",
                         supportsAllDrives=True, includeItemsFromAllDrives=True,
                         orderBy="modifiedTime desc", pageSize=5).execute()
    f = r.get("files", [])
    return f[0]["id"] if f else None


def leggi(info, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    svc = _servizio(info)
    buf = io.BytesIO()
    giu = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True))
    fine = False
    while not fine:
        _, fine = giu.next_chunk()
    testo = buf.getvalue().decode("utf-8-sig", errors="replace").strip()
    return json.loads(testo) if testo else {}


def _pulisci(x):
    """NaN e infinito non esistono in JSON: chi legge il file (il bot Telegram,
    l'app desktop) si fermerebbe. Diventano «vuoto»."""
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if isinstance(x, dict):
        return {str(k): _pulisci(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_pulisci(v) for v in x]
    return x


def scrivi(info, file_id, dati):
    from googleapiclient.http import MediaIoBaseUpload
    svc = _servizio(info)
    corpo = json.dumps(_pulisci(dati), ensure_ascii=False, indent=1, default=str,
                       allow_nan=False).encode("utf-8")
    svc.files().update(fileId=file_id, supportsAllDrives=True,
                       media_body=MediaIoBaseUpload(io.BytesIO(corpo), mimetype="application/json",
                                                    resumable=False)).execute()
