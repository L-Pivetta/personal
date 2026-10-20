import html
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


CARTELLA_PROGETTO = Path(__file__).resolve().parent
CARTELLA_OUTPUT = CARTELLA_PROGETTO / "output"
CARTELLA_DOCUMENTI_ARCHIVIATI = CARTELLA_OUTPUT / "archivio_documenti"
CARTELLA_REPORT = CARTELLA_DOCUMENTI_ARCHIVIATI / "Tutti_i_report"
PERCORSO_ARCHIVIO = CARTELLA_OUTPUT / "archivio_completo.html"


def leggi_json(percorso):
    return json.loads(percorso.read_text(encoding="utf-8"))


def crea_menu_scheda(percorso, titolo, etichetta):
    scheda = leggi_json(percorso)
    ruolo = html.escape(str(scheda.get("ruolo", etichetta)))
    riassunto = html.escape(str(scheda.get("riassunto", "")))
    return (
        '<details class="voce macchina">'
        f"<summary>{html.escape(titolo)}</summary>"
        '<dl class="scheda-dati"><dt>Ruolo</dt>'
        f"<dd>{ruolo}</dd><dt>Riassunto</dt><dd>{riassunto}</dd></dl>"
        "</details>"
    )


def crea_menu_ricerca(percorso, titolo, etichetta):
    ricerca = leggi_json(percorso)
    ruolo = html.escape(str(ricerca.get("ruolo", etichetta)))
    query = html.escape(str(ricerca.get("query", "")))
    avviso = str(ricerca.get("avviso", "")).strip()
    avviso_html = (
        f'<p class="avviso">{html.escape(avviso)}</p>' if avviso else ""
    )
    fonti = []
    for indice, pagina in enumerate(ricerca.get("pagine", []), start=1):
        titolo_pagina = str(
            pagina.get("titolo") or pagina.get("url") or f"Fonte {indice}"
        )
        url = str(pagina.get("url", ""))
        titolo_html = html.escape(titolo_pagina)
        if url.startswith(("https://", "http://")):
            titolo_html = (
                f'<a href="{html.escape(url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{titolo_html}</a>'
            )
        provenienza = html.escape(str(pagina.get("provenienza", "")))
        testo = html.escape(str(pagina.get("testo", "")))
        fonti.append(
            '<details class="fonte"><summary>'
            f"Fonte {indice}: {titolo_html}</summary>"
            f'<p class="provenienza">{provenienza}</p>'
            f'<p class="testo-fonte">{testo}</p></details>'
        )
    fonti_html = "".join(fonti) or "<p>Nessuna fonte registrata.</p>"
    return (
        '<details class="voce macchina">'
        f"<summary>{html.escape(titolo)}</summary>"
        f'<p><strong>Query:</strong> {query}</p>{avviso_html}{fonti_html}'
        "</details>"
    )


def _copia_datata(percorso, cartella_destinazione, nome_base=None):
    cartella_destinazione.mkdir(parents=True, exist_ok=True)
    nome_base = nome_base or percorso.stem
    data_ora = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _copia_progressiva(
        percorso,
        cartella_destinazione,
        f"{nome_base}_{data_ora}",
    )


def _copia_progressiva(percorso, cartella_destinazione, nome_base):
    destinazione = cartella_destinazione / f"{nome_base}{percorso.suffix}"
    indice = 2
    while destinazione.exists():
        destinazione = cartella_destinazione / (
            f"{nome_base}_{indice}{percorso.suffix}"
        )
        indice += 1
    shutil.copy2(percorso, destinazione)
    return destinazione


def archivia_report(percorso_report, aggiorna=True, config=None):
    percorso_report = Path(percorso_report)
    if percorso_report.is_file():
        impronta = hashlib.sha256(percorso_report.read_bytes()).digest()
        CARTELLA_REPORT.mkdir(parents=True, exist_ok=True)
        gia_archiviato = any(
            hashlib.sha256(percorso.read_bytes()).digest() == impronta
            for percorso in CARTELLA_REPORT.glob("*.html")
        )
        if not gia_archiviato:
            macchine = (config or {}).get("macchine", [])
            if len(macchine) == 2:
                id_macchine = "_".join(str(macchina["id"]) for macchina in macchine)
                nome_base = f"Report del dialogo Ollama_{id_macchine}"
                _copia_progressiva(percorso_report, CARTELLA_REPORT, nome_base)
            else:
                _copia_datata(
                    percorso_report,
                    CARTELLA_REPORT,
                    "Report del dialogo Ollama",
                )
    if aggiorna:
        crea_archivio()


def archivia_schede_ricerche(config=None):
    archivia_report(
        CARTELLA_OUTPUT / "report_dialogo.html",
        aggiorna=False,
        config=config,
    )
    crea_archivio()


def _titolo_documento(percorso, tipo, prefisso):
    nome_file = percorso.stem[len(tipo) + 1 :]
    nome_file = re.sub(r"_(\d{8}_\d{6}(?:_\d+)?)$", "", nome_file)

    dati = leggi_json(percorso)
    ruolo = dati.get("ruolo")
    etichetta = (
        ruolo.strip()
        if isinstance(ruolo, str) and ruolo.strip()
        else nome_file.replace("_", " ").title()
    )
    titolo = f"{prefisso} {nome_file}"
    return titolo, etichetta


def crea_archivio():
    CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)
    report = sorted(CARTELLA_REPORT.glob("*.html"))
    menu_report = []
    for percorso in report:
        contenuto = html.escape(percorso.read_text(encoding="utf-8"), quote=True)
        titolo = html.escape(percorso.stem)
        menu_report.append(
            '<details class="voce report">'
            f"<summary>{titolo}</summary>"
            f'<iframe title="{titolo}" srcdoc="{contenuto}" '
            'loading="lazy"></iframe></details>'
        )

    menu_schede = []
    menu_ricerche = []
    for tipo, cartella, menu, prefisso in (
        (
            "scheda",
            CARTELLA_DOCUMENTI_ARCHIVIATI / "schede",
            menu_schede,
            "Scheda",
        ),
        (
            "ricerca",
            CARTELLA_DOCUMENTI_ARCHIVIATI / "ricerche",
            menu_ricerche,
            "Ricerca",
        ),
    ):
        for documento in sorted(cartella.glob(f"{tipo}_*.json")):
            titolo, etichetta = _titolo_documento(documento, tipo, prefisso)
            if tipo == "scheda":
                menu.append(crea_menu_scheda(documento, titolo, etichetta))
            else:
                menu.append(crea_menu_ricerca(documento, titolo, etichetta))
    pagina = f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Archivio report e ricerche</title>
  <style>
    :root {{ color-scheme: light; font-family: Segoe UI, sans-serif; color: #202b2a; background: #f4f6f2; }}
    body {{ max-width: 1100px; margin: 0 auto; padding: 30px 20px 60px; line-height: 1.55; }}
    h1 {{ color: #15574f; margin-bottom: 8px; }}
    .introduzione {{ color: #586763; margin: 0 0 26px; }}
    .sezione {{ border-top: 1px solid #cbd5ce; padding: 18px 0; }}
    .sezione > summary {{ color: #15574f; cursor: pointer; font-size: 1.25rem; font-weight: 700; }}
    .contenuto-sezione {{ padding-top: 10px; }}
    .voce {{ border-bottom: 1px solid #d7dfd9; padding: 11px 0; }}
    .voce > summary, .fonte > summary {{ cursor: pointer; color: #15574f; font-weight: 600; }}
    .report iframe {{ display: block; box-sizing: border-box; width: 100%; height: min(78vh, 900px); min-height: 560px; margin-top: 14px; border: 1px solid #cbd5ce; background: white; }}
    .scheda-dati {{ display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px 16px; }}
    .scheda-dati dt {{ font-weight: 650; }}
    .scheda-dati dd {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .macchina > p {{ overflow-wrap: anywhere; }}
    .fonte {{ margin: 12px 0; padding-left: 14px; border-left: 2px solid #cbd5ce; }}
    .fonte a {{ color: #15574f; }}
    .provenienza {{ color: #586763; font-size: .9rem; }}
    .testo-fonte {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    .avviso {{ color: #7b4a0b; }}
    @media (max-width: 600px) {{ body {{ padding: 22px 14px 40px; }} .scheda-dati {{ grid-template-columns: 1fr; gap: 2px; }} .scheda-dati dd {{ margin-bottom: 10px; }} .report iframe {{ min-height: 440px; }} }}
  </style>
</head>
<body>
  <h1>Archivio report e ricerche</h1>
    <p class="introduzione">{len(report)} report passati, {len(menu_schede)} schede e {len(menu_ricerche)} ricerche.</p>
  <details class="sezione">
    <summary>1. Report passati</summary>
    <div class="contenuto-sezione">{"".join(menu_report)}</div>
  </details>
  <details class="sezione">
    <summary>2. Tutte le schede</summary>
    <div class="contenuto-sezione">{"".join(menu_schede)}</div>
  </details>
  <details class="sezione">
    <summary>3. Tutte le ricerche</summary>
    <div class="contenuto-sezione">{"".join(menu_ricerche)}</div>
  </details>
</body>
</html>
"""
    PERCORSO_ARCHIVIO.write_text(pagina, encoding="utf-8")
    return len(report)


if __name__ == "__main__":
    quantita_report = crea_archivio()
    print(f"Creato {PERCORSO_ARCHIVIO} con {quantita_report} report passati.")