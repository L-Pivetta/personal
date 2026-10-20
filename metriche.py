import re
from collections import Counter


PAROLE_COMUNI = {
    "anche", "come", "con", "del", "della", "delle", "dello", "dei",
    "di", "e", "gli", "ha", "il", "in", "la", "le", "lo", "ma",
    "non", "o", "per", "piu", "un", "una", "uno", "che", "si", "sono",
    "questa", "questo", "tra", "una", "essere", "puo", "dove", "quando",
}


def calcola_metriche(interventi):
    lunghezze = []
    conteggio = Counter()

    for voce in interventi:
        parole = re.findall(r"\b[\w'-]+\b", voce["testo"].lower())
        lunghezze.append(
            {
                "turno": voce["turno"],
                "agente_id": voce["agente_id"],
                "parole": len(parole),
                "caratteri": len(voce["testo"]),
            }
        )
        conteggio.update(
            parola for parola in parole
            if len(parola) > 2 and parola not in PAROLE_COMUNI
        )

    ricorrenze = [
        {"parola": parola, "occorrenze": numero}
        for parola, numero in conteggio.most_common(20)
        if numero > 1
    ]
    return {"lunghezze_interventi": lunghezze, "ricorrenze_lessicali": ricorrenze}