import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import ollama
import requests
import trafilatura
from ddgs import DDGS


TIMEOUT_RIASSUNTO_SECONDI = 300
CARATTERI_MASSIMI_PER_FONTE = 7500
PAGINE_OBIETTIVO = 3
ESTENSIONI_ESCLUSE = {".pdf", ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}
DOMINI_ESCLUSI = {
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "reddit.com",
    "pinterest.com",
    "snapchat.com",
    "threads.net",
}


def _nome_file(testo):
    nome = re.sub(r"[^a-z0-9]+", "_", testo.lower()).strip("_")
    return nome or "ruolo"


def _url_non_articolo(url):
    indirizzo = urlparse(url)
    dominio = (indirizzo.hostname or "").lower()
    estensione = Path(unquote(indirizzo.path)).suffix.lower()
    return (
        indirizzo.scheme not in {"http", "https"}
        or estensione in ESTENSIONI_ESCLUSE
        or any(
            dominio == escluso or dominio.endswith(f".{escluso}")
            for escluso in DOMINI_ESCLUSI
        )
    )


def _chiave_url(url):
    indirizzo = urlparse(url)
    return indirizzo._replace(
        scheme=indirizzo.scheme.lower(),
        netloc=indirizzo.netloc.lower(),
        path=indirizzo.path.rstrip("/") or "/",
        fragment="",
    ).geturl()


def _scarica_testo(url):
    if _url_non_articolo(url):
        return None

    risposta = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; DialogoOllama/1.0)"},
    )
    risposta.raise_for_status()
    tipo_contenuto = risposta.headers.get("Content-Type", "").split(";", 1)[0].lower()
    disposizione = risposta.headers.get("Content-Disposition", "").lower()
    if (
        _url_non_articolo(risposta.url)
        or tipo_contenuto == "application/pdf"
        or tipo_contenuto.startswith("video/")
        or ".pdf" in disposizione
    ):
        return None

    testo = trafilatura.extract(
        risposta.text,
        url=risposta.url,
        include_comments=False,
    )
    if not testo:
        return None
    return re.sub(r"[ \t]+", " ", testo).strip()[:CARATTERI_MASSIMI_PER_FONTE]


def _leggi_pagina(url, titolo, provenienza, avvisi):
    try:
        testo = _scarica_testo(url)
    except Exception as errore:
        avviso = f"Impossibile scaricare il sito {url}: {errore}"
        print(f"Avviso: {avviso}")
        avvisi.append(avviso)
        return None

    if not testo:
        avviso = f"Nessun testo estraibile dal sito {url} (formato non supportato?)."
        print(f"Avviso: {avviso}")
        avvisi.append(avviso)
        return None

    pagina = {
        "titolo": titolo,
        "url": url,
        "testo": testo,
        "provenienza": provenienza,
    }
    print(f"\n--- Testo analizzato: {pagina['titolo']} ---")
    print(testo)
    return pagina


def _solo_frasi_complete(testo):
    testo = testo.strip()
    if re.search(r"[.!?…][\"'»”’)]*\s*$", testo):
        return testo

    confini = list(re.finditer(r"[.!?…][\"'»”’)]*(?=\s|$)", testo))
    if not confini:
        return "Riassunto non disponibile in forma completa."
    return testo[:confini[-1].end()].rstrip()


def _sintetizza_fonti(agente, risultati, avviso):
    if not risultati:
        return ""

    try:
        client = ollama.Client(timeout=TIMEOUT_RIASSUNTO_SECONDI)
        riassunti = []
        for pagina in risultati:
            risposta = client.chat(
                model=agente["nome_modello"],
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sei un assistente di ricerca. Riassumi la singola fonte "
                            "per interpretare il ruolo assegnato. Distingui i fatti "
                            "dalle interpretazioni, non inventare informazioni e "
                            "scrivi solo frasi complete."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Ruolo: {agente['ruolo_assegnato']}\n"
                            f"Obiettivo: {agente['obiettivo']}\n"
                            f"Avviso: {avviso or 'nessuno'}\n"
                            f"Fonte: {pagina['titolo']} ({pagina['url']})\n\n"
                            f"Testo della fonte:\n{pagina['testo'][:CARATTERI_MASSIMI_PER_FONTE]}\n\n"
                            "Riassumi le informazioni rilevanti in italiano, "
                            "in frasi complete."
                        ),
                    },
                ],
                options={"num_ctx": 4096, "num_predict": 500},
            )
            riassunti.append(_solo_frasi_complete(risposta.message.content))

        fonti_riassunte = "\n\n".join(
            f"Fonte: {pagina['titolo']} ({pagina['url']})\n"
            f"Riassunto:\n{riassunto}"
            for pagina, riassunto in zip(risultati, riassunti)
        )
        risposta = client.chat(
            model=agente["nome_modello"],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei un assistente di ricerca. Prepara una scheda breve e utile "
                        "per interpretare il ruolo assegnato. Distingui i fatti dalle "
                        "interpretazioni, non inventare informazioni o fonti e scrivi "
                        "solo frasi complete."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Ruolo: {agente['ruolo_assegnato']}\n"
                        f"Obiettivo: {agente['obiettivo']}\n"
                        f"Avviso: {avviso or 'nessuno'}\n\n"
                        f"Riassunti delle fonti:\n{fonti_riassunte}\n\n"
                        "Unisci i riassunti in una scheda in italiano, chiara e "
                        "coerente. Conserva le informazioni rilevanti di tutte le "
                        "fonti, evitando solo le ripetizioni. Usa frasi complete."
                    ),
                },
            ],
            options={"num_ctx": 4096, "num_predict": 500},
        )
    except Exception as errore:
        print(f"Sintesi delle fonti per {agente['id']} non riuscita: {errore}")
        return ""

    return _solo_frasi_complete(risposta.message.content)


def prepara_schede(config, cartella_schede, cartella_ricerche):
    cartella_schede = Path(cartella_schede)
    cartella_ricerche = Path(cartella_ricerche)
    cartella_schede.mkdir(parents=True, exist_ok=True)
    cartella_ricerche.mkdir(parents=True, exist_ok=True)
    data_ora = datetime.now().strftime("%Y%m%d_%H%M%S")
    schede = {}

    for agente in config["macchine"]:
        query = f"{agente['ruolo_assegnato']} {agente['obiettivo']}"
        pagine = []
        avvisi = []
        url_visti = set()

        for url in agente.get("siti_da_indagare", []):
            chiave = _chiave_url(url)
            if chiave in url_visti:
                continue
            url_visti.add(chiave)
            pagina = _leggi_pagina(
                url,
                urlparse(url).hostname or url,
                "indicata dall'operatore",
                avvisi,
            )
            if pagina:
                pagine.append(pagina)

        if agente.get("cerca_sul_web", True) and len(pagine) < PAGINE_OBIETTIVO:
            try:
                risultati = DDGS().text(query, max_results=10)
            except Exception as errore:
                risultati = []
                avvisi.append(f"Ricerca web non riuscita: {errore}")
                print(f"Avviso: ricerca web non riuscita: {errore}")

            for risultato in risultati:
                if len(pagine) >= PAGINE_OBIETTIVO:
                    break
                url = risultato.get("href") or risultato.get("url")
                if not url:
                    continue
                chiave = _chiave_url(url)
                if chiave in url_visti:
                    continue
                url_visti.add(chiave)
                pagina = _leggi_pagina(
                    url,
                    risultato.get("title", "Senza titolo"),
                    "trovata dal motore",
                    avvisi,
                )
                if pagina:
                    pagine.append(pagina)

        avviso = "\n".join(avvisi)

        nome = _nome_file(agente["id"])
        dati_ricerca = {
            "ruolo": agente["ruolo_assegnato"],
            "query": query,
            "avviso": avviso,
            "pagine": pagine,
        }
        suffisso = data_ora
        indice = 2
        percorso_ricerca = cartella_ricerche / f"ricerca_{nome}_{suffisso}.json"
        percorso_scheda = cartella_schede / f"scheda_{nome}_{suffisso}.json"
        while percorso_ricerca.exists() or percorso_scheda.exists():
            suffisso = f"{data_ora}_{indice}"
            percorso_ricerca = cartella_ricerche / f"ricerca_{nome}_{suffisso}.json"
            percorso_scheda = cartella_schede / f"scheda_{nome}_{suffisso}.json"
            indice += 1
        percorso_ricerca.write_text(
            json.dumps(dati_ricerca, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        scheda = {
            "vincoli": agente.get("vincoli", []),
            "riassunto": agente.get("riassunto", "").strip(),
            "sintesi": _sintetizza_fonti(agente, pagine, avviso),
        }
        schede[agente["id"]] = scheda
        percorso_scheda.write_text(
            json.dumps(
                {"ruolo": agente["ruolo_assegnato"], **scheda},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nScheda salvata: {percorso_scheda}")

    return schede