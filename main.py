import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import google_api

from crea_archivio_report import archivia_report, archivia_schede_ricerche
from dialogo import avvia_dialogo
from metriche import calcola_metriche
from ricerca import prepara_schede
from report import crea_report
from valutazione import valuta_dialogo


CARTELLA_PROGETTO = Path(__file__).resolve().parent


def verifica_google(config, includi_modelli_dialogo=True):
    modelli_richiesti = (
        {agente["nome_modello"] for agente in config["macchine"]}
        if includi_modelli_dialogo
        else set()
    )
    modelli_richiesti.add(config["valutatore"]["nome_modello"])

    try:
        google_api.verifica_modelli(modelli_richiesti)
    except Exception as errore:
        raise RuntimeError(
            "Verifica Google AI Studio non riuscita. Controlla la chiave "
            "GEMINI_API_KEY e i nomi dei modelli in config.json. "
            f"Dettaglio: {errore}"
        ) from errore


def carica_configurazione():
    percorso = CARTELLA_PROGETTO / "config.json"
    config = json.loads(percorso.read_text(encoding="utf-8"))

    if len(config.get("macchine", [])) != 2:
        raise ValueError("config.json deve contenere esattamente due macchine.")
    if config.get("numero_di_turni", 0) < 1:
        raise ValueError("numero_di_turni deve essere almeno 1.")

    for agente in config["macchine"]:
        if not 0 <= agente["grado_di_cooperazione"] <= 10:
            raise ValueError("Il grado di cooperazione deve essere tra 0 e 10.")

        vincoli = agente.get("vincoli", [])
        if not isinstance(vincoli, list) or any(
            not isinstance(vincolo, str) or not vincolo.strip()
            for vincolo in vincoli
        ):
            raise ValueError("vincoli deve essere un elenco di testi non vuoti.")

        siti = agente.get("siti_da_indagare", [])
        if not isinstance(siti, list):
            raise ValueError("siti_da_indagare deve essere un elenco di URL.")
        for indice, sito in enumerate(siti, start=1):
            if not isinstance(sito, str) or sito != sito.strip():
                raise ValueError(
                    f"L'URL numero {indice} di {agente['id']} non è valido."
                )
            try:
                indirizzo = urlparse(sito)
                indirizzo.port
            except ValueError as errore:
                raise ValueError(
                    f"L'URL numero {indice} di {agente['id']} non è valido: {errore}"
                ) from errore
            if (
                not sito.lower().startswith(("http://", "https://"))
                or indirizzo.scheme not in {"http", "https"}
                or not indirizzo.hostname
            ):
                raise ValueError(
                    f"L'URL numero {indice} di {agente['id']} deve iniziare con "
                    "http:// o https:// e contenere un indirizzo valido."
                )

        if not isinstance(agente.get("cerca_sul_web", True), bool):
            raise ValueError("cerca_sul_web deve essere true oppure false.")

    return config


def carica_log(percorso):
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    if isinstance(dati, list):
        return carica_configurazione(), dati
    if not isinstance(dati, dict):
        raise ValueError("Il log deve contenere un elenco di interventi o un oggetto.")

    config = dati.get("config")
    interventi = dati.get("interventi")
    if not isinstance(config, dict) or not isinstance(interventi, list):
        raise ValueError("Il log non contiene una configurazione e un dialogo validi.")
    return config, interventi


def valuta_e_crea_report(config, interventi, cartella_output, percorso_log=None):
    print("\nCalcolo delle metriche")
    metriche = calcola_metriche(interventi)

    print("Valutazione del dialogo")
    valutazione = valuta_dialogo(config, interventi)
    if percorso_log is not None:
        dati_log = json.loads(percorso_log.read_text(encoding="utf-8"))
        if isinstance(dati_log, list):
            dati_log = {"config": config, "interventi": interventi}
        dati_log["valutazione"] = valutazione
        dati_log["risposta_valutatore"] = valutazione["risposta_valutatore"]
        percorso_log.write_text(
            json.dumps(dati_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    percorso_analisi = cartella_output / "analisi.json"
    percorso_analisi.write_text(
        json.dumps(
            {"metriche": metriche, "valutazione": valutazione},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    archivia_report(
        cartella_output / "report_dialogo.html",
        aggiorna=False,
        config=config,
    )
    print("Creazione del report HTML")
    ruoli = {
        agente["id"]: agente["ruolo_assegnato"] for agente in config["macchine"]
    }
    percorso_report = crea_report(
        interventi, metriche, valutazione, cartella_output, ruoli, config
    )
    archivia_report(percorso_report, config=config)
    print(f"Report creato: {percorso_report}")


def main():
    parser = argparse.ArgumentParser(description="Dialogo tra modelli Gemini")
    parser.add_argument(
        "--da-log",
        metavar="PERCORSO",
        help="ricalcola valutazione e report da un log senza rigenerare il dialogo",
    )
    argomenti = parser.parse_args()

    cartella_output = CARTELLA_PROGETTO / "output"
    cartella_output.mkdir(exist_ok=True)
    if argomenti.da_log:
        percorso_log = Path(argomenti.da_log)
        if not percorso_log.is_absolute():
            percorso_log = CARTELLA_PROGETTO / percorso_log
        config, interventi = carica_log(percorso_log)
        verifica_google(config, includi_modelli_dialogo=False)
        valuta_e_crea_report(config, interventi, cartella_output, percorso_log)
        return

    config = carica_configurazione()
    verifica_google(config)
    cartella_log = CARTELLA_PROGETTO / "logs"
    cartella_output = CARTELLA_PROGETTO / "output"
    cartella_documenti = cartella_output / "archivio_documenti"
    cartella_schede = cartella_documenti / "schede"
    cartella_ricerche = cartella_documenti / "ricerche"
    cartella_log.mkdir(exist_ok=True)
    cartella_output.mkdir(exist_ok=True)
    cartella_schede.mkdir(parents=True, exist_ok=True)
    cartella_ricerche.mkdir(parents=True, exist_ok=True)

    config_log = json.loads(json.dumps(config))

    print("Fase 1/5 - Ricerca web e schede dei ruoli")
    schede = prepara_schede(config, cartella_schede, cartella_ricerche)
    archivia_schede_ricerche(config)

    print("\nFase 2/5 - Dialogo tra le due macchine")
    interventi = avvia_dialogo(config, schede)

    data_ora = datetime.now().strftime("%Y%m%d_%H%M%S")
    percorso_log = cartella_log / f"dialogo_{data_ora}.json"
    percorso_log.write_text(
        json.dumps(
            {"config": config_log, "interventi": interventi},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nLog salvato: {percorso_log}")

    valuta_e_crea_report(config, interventi, cartella_output, percorso_log)


if __name__ == "__main__":
    main()