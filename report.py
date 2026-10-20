import base64
from html import escape
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlsplit

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _tabella_lunghezze(lunghezze):
    righe = "".join(
        "<tr>"
        f"<td>{voce['turno']}</td>"
        f"<td>{escape(voce['agente_id'])}</td>"
        f"<td>{voce['parole']}</td>"
        f"<td>{voce['caratteri']}</td>"
        "</tr>"
        for voce in lunghezze
    )
    return (
        "<table><thead><tr><th>Turno</th><th>Macchina</th>"
        "<th>Parole</th><th>Caratteri</th></tr></thead>"
        f"<tbody>{righe}</tbody></table>"
    )


def _tabella_ricorrenze(ricorrenze):
    if not ricorrenze:
        return "<p>Nessuna ricorrenza significativa rilevata.</p>"
    righe = "".join(
        f"<tr><td>{escape(voce['parola'])}</td>"
        f"<td>{voce['occorrenze']}</td></tr>"
        for voce in ricorrenze
    )
    return (
        "<table><thead><tr><th>Parola</th><th>Occorrenze</th></tr></thead>"
        f"<tbody>{righe}</tbody></table>"
    )


def _grafico(accordo_per_turno, cartella_output):
    turni = list(range(1, len(accordo_per_turno) + 1))
    valori = [
        valore if type(valore) is int else float("nan")
        for valore in accordo_per_turno
    ]
    figura, asse = plt.subplots(figsize=(8, 3.5))
    asse.plot(turni, valori, marker="o", color="#167c70", linewidth=2)
    asse.set(title="Andamento dell'accordo", xlabel="Turno", ylabel="Accordo (1-5)")
    asse.set_ylim(0.5, 5.5)
    asse.set_yticks([1, 2, 3, 4, 5])
    asse.set_yticklabels(
        ["1 - Molto basso", "2 - Basso", "3 - Intermedio", "4 - Alto", "5 - Molto alto"]
    )
    asse.set_xticks(turni)
    asse.grid(axis="y", alpha=0.25)
    figura.tight_layout()

    percorso = Path(cartella_output) / "andamento_accordo.png"
    figura.savefig(percorso, dpi=140)
    immagine = BytesIO()
    figura.savefig(immagine, format="png", dpi=140)
    plt.close(figura)
    codifica = base64.b64encode(immagine.getvalue()).decode("ascii")
    return percorso, codifica


def _sezioni_ricerca(cartella, ruoli, config=None):
    cartella_documenti = Path(cartella) / "archivio_documenti"
    cartella_ricerche = cartella_documenti / "ricerche"
    cartella_schede = cartella_documenti / "schede"
    macchine_per_ruolo = {
        agente["ruolo_assegnato"]: agente
        for agente in (config or {}).get("macchine", [])
    }
    gruppi = {
        ruolo: {
            "avvisi": [], "riassunti": [], "pagine": [], "url_visti": set(),
            "modelli": [], "vincoli": [],
        }
        for ruolo in dict.fromkeys(ruoli.values())
    }
    for percorso in sorted(cartella_ricerche.glob("ricerca_*.json")):
        try:
            ricerca = json.loads(percorso.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ruolo = ricerca.get("ruolo")
        if ruoli and ruolo not in gruppi:
            continue
        gruppo = gruppi.setdefault(
            ruolo,
            {
                "avvisi": [], "riassunti": [], "pagine": [], "url_visti": set(),
                "modelli": [], "vincoli": [],
            },
        )

        suffisso = percorso.stem[len("ricerca_") :]
        percorso_scheda = cartella_schede / f"scheda_{suffisso}.json"
        scheda = {}
        try:
            scheda = json.loads(percorso_scheda.read_text(encoding="utf-8"))
            riassunto = scheda.get("riassunto", "").strip()
        except (OSError, json.JSONDecodeError):
            riassunto = ""
        macchina = macchine_per_ruolo.get(ruolo, {})
        modello = macchina.get("nome_modello")
        if modello and modello not in gruppo["modelli"]:
            gruppo["modelli"].append(modello)
        vincoli = macchina.get("vincoli", scheda.get("vincoli", []))
        for vincolo in vincoli:
            if vincolo and vincolo not in gruppo["vincoli"]:
                gruppo["vincoli"].append(vincolo)
        if riassunto and riassunto not in gruppo["riassunti"]:
            gruppo["riassunti"].append(riassunto)
        avviso = ricerca.get("avviso", "").strip()
        if avviso and avviso not in gruppo["avvisi"]:
            gruppo["avvisi"].append(avviso)

        for pagina in ricerca.get("pagine", []):
            url = pagina.get("url", "")
            indirizzo = urlsplit(url)
            if (
                indirizzo.scheme not in {"http", "https"}
                or not indirizzo.netloc
                or url in gruppo["url_visti"]
            ):
                continue
            gruppo["url_visti"].add(url)
            gruppo["pagine"].append(pagina)

    sezioni = []
    for ruolo, gruppo in gruppi.items():
        if not any(
            gruppo[campo]
            for campo in ("riassunti", "pagine", "avvisi", "modelli", "vincoli")
        ):
            continue
        fonti = "".join(
            "<li>"
            f'<a href="{escape(pagina["url"])}" target="_blank" '
            f'rel="noopener noreferrer">{escape(pagina.get("titolo") or pagina["url"])}</a>'
            f" <span>{escape(pagina.get('provenienza', ''))}</span></li>"
            for pagina in gruppo["pagine"]
        )
        elenco_fonti = (
            f"<ul>{fonti}</ul>"
            if fonti
            else "<p>Nessuna fonte web registrata.</p>"
        )
        avvisi = "".join(
            f"<p class=\"avviso-ricerca\">{escape(avviso)}</p>"
            for avviso in gruppo["avvisi"]
        )
        riassunti = "".join(
            f"<p class=\"testo-scheda\">{escape(riassunto)}</p>"
            for riassunto in gruppo["riassunti"]
        ) or '<p class="testo-scheda">Scheda non disponibile.</p>'
        modelli = ", ".join(escape(modello) for modello in gruppo["modelli"])
        vincoli = "".join(
            f"<li>{escape(vincolo)}</li>" for vincolo in gruppo["vincoli"]
        ) or "<li>Nessun vincolo indicato.</li>"
        sezioni.append(
            "<details class=\"scheda-ricerca\">"
            f"<summary>{escape(ruolo or 'Ruolo senza nome')}</summary>"
            f"{avvisi}<h3>Scheda di ricerca</h3>{riassunti}"
            f"<h3>Vincoli inderogabili</h3><ul>{vincoli}</ul>"
            f"<h3>Modello di intelligenza artificiale</h3>"
            f"<p>{modelli or 'Non disponibile'}</p>"
            f"<h3>Fonti utilizzate</h3>{elenco_fonti}</details>"
        )

    return "".join(sezioni) or "<p>Nessuna scheda di ricerca disponibile.</p>"


def _conversazione(interventi, ruoli):
    classi = {
        agente_id: f"messaggio-{indice % 2 + 1}"
        for indice, agente_id in enumerate(
            dict.fromkeys(voce["agente_id"] for voce in interventi)
        )
    }
    messaggi = []
    for voce in interventi:
        agente_id = voce["agente_id"]
        nome = escape(ruoli.get(agente_id, agente_id))
        turno = escape(str(voce["turno"]))
        testo = escape(voce["testo"])
        messaggi.append(
            f'<article class="messaggio {classi[agente_id]}">'
            f"<header><strong>{nome}</strong><span>Turno {turno}</span></header>"
            f"<p>{testo}</p></article>"
        )
    return "".join(messaggi)


def crea_report(
    interventi, metriche, valutazione, cartella_output, ruoli=None, config=None
):
    cartella = Path(cartella_output)
    cartella.mkdir(parents=True, exist_ok=True)
    _, grafico = _grafico(valutazione["accordo_per_turno"], cartella)
    ruoli = ruoli or {}

    coerenza = "".join(
        f"<li>{escape(agente)}: "
        f"{f'{punteggio}/5' if type(punteggio) is int else 'Non determinato/5'}</li>"
        for agente, punteggio in valutazione["coerenza"].items()
    )
    obiettivi_raggiunti = valutazione.get("obiettivi_raggiunti", {})
    motivazioni_obiettivi = valutazione.get("motivazione_obiettivi", {})
    vincoli_rispettati = valutazione.get("vincoli_rispettati", {})
    accordo_raggiunto = valutazione.get("accordo_raggiunto")
    obiettivi = "".join(
        f"<li>{escape(agente)}: "
        f"{'Raggiunto' if esito is True else 'Non raggiunto' if esito is False else 'Non determinato'}"
        f"{f' - {escape(str(motivazioni_obiettivi.get(agente, "")))}' if motivazioni_obiettivi.get(agente) else ''}</li>"
        for agente, esito in obiettivi_raggiunti.items()
    ) or "<li>Non disponibile</li>"
    vincoli = "".join(
        f"<li>{escape(agente)}: vincoli_rispettati="
        f"{'true' if esito is True else 'false' if esito is False else 'non determinato'}</li>"
        for agente, esito in vincoli_rispettati.items()
    ) or "<li>Non disponibile</li>"
    esito_accordo = (
        "true" if accordo_raggiunto is True
        else "false" if accordo_raggiunto is False
        else "non determinato"
    )
    commento = escape(valutazione["commento"])
    ricerca = _sezioni_ricerca(cartella, ruoli, config)
    modello_valutatore = (
        (config or {}).get("valutatore", {}).get("nome_modello")
        or "Non disponibile"
    )
    conversazione = _conversazione(interventi, ruoli)

    pagina = f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Report del dialogo Ollama</title>
  <style>
    :root {{ color-scheme: light; font-family: Segoe UI, sans-serif; color: #202b2a; background: #f4f6f2; }}
    body {{ max-width: 1000px; margin: 0 auto; padding: 32px 20px; line-height: 1.55; }}
    h1, h2 {{ color: #15574f; }}
    section {{ border-top: 1px solid #cbd5ce; padding: 18px 0; }}
    .avviso-simulazione {{ margin: 18px 0; padding: 12px 16px; background: #fff3d8; border-left: 4px solid #c27a16; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    th, td {{ border-bottom: 1px solid #d7dfd9; padding: 8px 10px; text-align: left; }}
    th {{ background: #e6eee8; }}
    .punteggi {{ display: flex; flex-wrap: wrap; gap: 12px 28px; }}
    figure {{ margin: 16px 0; }}
    figure img {{ display: block; max-width: 100%; height: auto; }}
    .scheda-ricerca {{ border-bottom: 1px solid #d7dfd9; padding: 12px 0; }}
    .scheda-ricerca summary {{ color: #15574f; cursor: pointer; font-weight: 650; }}
    .menu-metrica {{ border-bottom: 1px solid #d7dfd9; padding: 12px 0; }}
    .menu-metrica summary {{ color: #15574f; cursor: pointer; font-weight: 650; }}
    .menu-metrica summary h2 {{ display: inline; margin: 0; }}
    .testo-scheda {{ white-space: pre-wrap; }}
    .scheda-ricerca li {{ margin: 8px 0; overflow-wrap: anywhere; }}
    .scheda-ricerca li span {{ color: #586763; font-size: 0.9em; }}
    .avviso-ricerca {{ color: #7b4a0b; }}
    .conversazione {{ display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }}
    .messaggio {{ max-width: 82%; padding: 12px 16px; border-radius: 4px; }}
    .messaggio-1 {{ align-self: flex-start; background: #e5efeb; border-left: 3px solid #167c70; }}
    .messaggio-2 {{ align-self: flex-end; background: #fff; border-right: 3px solid #c27a16; }}
    .messaggio header {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 16px; color: #15574f; }}
    .messaggio header span {{ color: #586763; font-size: 0.9em; }}
    .messaggio p {{ margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    @media (max-width: 600px) {{ body {{ padding: 20px 14px; }} }}
    @media (max-width: 600px) {{ .messaggio {{ max-width: 100%; }} }}
  </style>
</head>
<body>
  <h1>Report del dialogo</h1>
  <aside class="avviso-simulazione" role="note">
    Questo dialogo è una simulazione generata da modelli di intelligenza artificiale.
    Le frasi attribuite alle persone indicate non sono dichiarazioni reali.
  </aside>
  <section>
    <h2>Valutazione</h2>
        <p>Modello di intelligenza artificiale usato dal valutatore: {escape(modello_valutatore)}</p>
    <div class="punteggi">
    <p>Cooperazione: {f"{valutazione['cooperazione']}/10" if type(valutazione['cooperazione']) is int else "Non determinato/10"}</p>
    <p>Conflitto: {f"{valutazione['conflitto']}/10" if type(valutazione['conflitto']) is int else "Non determinato/10"}</p>
    <p>Accordo: {f"{valutazione['accordo']}/5" if type(valutazione['accordo']) is int else "Non determinato/5"}</p>
    </div>
    <p>Coerenza per macchina:</p><ul>{coerenza}</ul>
    <p>Accordo esplicito tra le parti: {esito_accordo}</p>
    <p>Rispetto dei vincoli inderogabili:</p><ul>{vincoli}</ul>
    <p>Raggiungimento degli obiettivi:</p><ul>{obiettivi}</ul>
    <p>{commento}</p>
    <figure><img src="data:image/png;base64,{grafico}" alt="Grafico dell'accordo per turno"></figure>
  </section>
  <section>
        <details class="menu-metrica">
            <summary><h2>Lunghezza degli interventi</h2></summary>
            {_tabella_lunghezze(metriche['lunghezze_interventi'])}
        </details>
  </section>
  <section>
        <details class="menu-metrica">
            <summary><h2>Ricorrenze lessicali</h2></summary>
            {_tabella_ricorrenze(metriche['ricorrenze_lessicali'])}
        </details>
  </section>
  <section>
    <h2>Schede di ricerca e fonti</h2>
    {ricerca}
  </section>
  <section>
    <h2>Dialogo completo</h2>
    <div class="conversazione">{conversazione}</div>
  </section>
</body>
</html>"""

    percorso_report = cartella / "report_dialogo.html"
    percorso_report.write_text(pagina, encoding="utf-8")
    return percorso_report