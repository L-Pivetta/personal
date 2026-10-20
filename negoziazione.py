import re


_NUMERO_IMPORTO = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
_IMPORTO_RE = re.compile(rf"({_NUMERO_IMPORTO})\s*(?:euro|€)", re.IGNORECASE)
_INTENZIONE_OFFERTA_RE = re.compile(
    r"\b(?:propongo|proporre|proposta|considerare|consideriamo|suggerire|"
    r"suggerisco|offrire|offro|pagare|accettare|accetto)\b",
    re.IGNORECASE,
)
_RIFERIMENTO_OFFERTA_RE = re.compile(
    r"\b(?:tuo suggerimento|tua proposta|che hai proposto|mi hai proposto|"
    r"mio suggerimento|mia proposta precedente)\b",
    re.IGNORECASE,
)
_RIFIUTO_RE = re.compile(
    r"\b(?:non posso accettare|non accetto|devo rifiutare|rifiuto)\b",
    re.IGNORECASE,
)


def prezzi_dichiarati(testo):
    prezzi = []
    for corrispondenza in _IMPORTO_RE.finditer(testo):
        inizio_contesto = max(0, corrispondenza.start() - 65)
        contesto = testo[inizio_contesto:corrispondenza.start()]
        confini = [contesto.rfind(segno) for segno in ".!?\n"]
        contesto = contesto[max(confini) + 1:]
        if (
            not _INTENZIONE_OFFERTA_RE.search(contesto)
            or _RIFERIMENTO_OFFERTA_RE.search(contesto)
            or _RIFIUTO_RE.search(contesto)
        ):
            continue
        importo = corrispondenza.group(1)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", importo):
            importo = importo.replace(".", "")
        prezzi.append(float(importo.replace(",", ".")))
    return prezzi


def prezzo_dichiarato(testo):
    prezzi = prezzi_dichiarati(testo)
    return prezzi[-1] if prezzi else None


def errore_vincolo_prezzo(testo, agente):
    prezzi = prezzi_dichiarati(testo)
    if not prezzi:
        return None

    for vincolo in agente.get("vincoli", []):
        importi = re.findall(
            r"(inferiore|minore|sotto|meno di|superiore|maggiore|oltre|più di)"
            rf"\s+(?:a\s+)?({_NUMERO_IMPORTO})\s*(?:euro|€)",
            vincolo,
            re.IGNORECASE,
        )
        for direzione, importo in importi:
            if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", importo):
                importo = importo.replace(".", "")
            soglia = float(importo.replace(",", "."))
            for prezzo in prezzi:
                if direzione.lower() in {"inferiore", "minore", "sotto", "meno di"} and prezzo < soglia:
                    return (
                        f"L'offerta di {prezzo:g} euro viola il vincolo inderogabile: "
                        f"{vincolo}"
                    )
                if direzione.lower() in {"superiore", "maggiore", "oltre", "più di"} and prezzo > soglia:
                    return (
                        f"L'offerta di {prezzo:g} euro viola il vincolo inderogabile: "
                        f"{vincolo}"
                    )
    return None


def errore_offerta(testo, agente, interventi, macchine):
    prezzo = prezzo_dichiarato(testo)
    if prezzo is None:
        return None

    errore_vincolo = errore_vincolo_prezzo(testo, agente)
    if errore_vincolo is not None:
        return errore_vincolo

    altro = next((macchina for macchina in macchine if macchina["id"] != agente["id"]), None)
    if altro is None:
        return None
    ultime_proposte = [
        voce
        for voce in interventi
        if voce["agente_id"] == altro["id"] and prezzo_dichiarato(voce["testo"]) is not None
    ]
    if not ultime_proposte:
        return None

    prezzo_avversario = prezzo_dichiarato(ultime_proposte[-1]["testo"])
    descrizione_ruolo = " ".join(
        str(agente.get(campo, ""))
        for campo in ("id", "ruolo_assegnato", "obiettivo", "riassunto")
    ).lower().replace("_", " ")
    ruolo_venditore = any(
        parola in descrizione_ruolo
        for parola in ("contadin", "venditor", "vendere", "vendita", "seller")
    )
    ruolo_acquirente = any(
        parola in descrizione_ruolo
        for parola in ("mercant", "acquirent", "compr", "buyer")
    )
    if ruolo_venditore and prezzo < prezzo_avversario:
        return (
            f"La tua offerta di {prezzo:g} euro è meno vantaggiosa per il venditore "
            f"dell'ultima proposta dell'acquirente ({prezzo_avversario:g} euro)."
        )
    if ruolo_acquirente and prezzo > prezzo_avversario:
        return (
            f"La tua offerta di {prezzo:g} euro è meno vantaggiosa per l'acquirente "
            f"dell'ultima proposta del venditore ({prezzo_avversario:g} euro)."
        )
    return None