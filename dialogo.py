import re

import ollama
from wordfreq import tokenize, zipf_frequency

from negoziazione import errore_offerta


def _frase_finale_completa(testo):
    return bool(re.search(r"[.!?…][\"'»”’)\]]*\s*$", testo))


def _rimuovi_frase_incompleta(testo):
    confini = list(re.finditer(r"[.!?…][\"'»”’)\]]*(?=\s|$)", testo))
    if not confini:
        return "Non ho altri elementi da aggiungere su questo punto."
    return testo[:confini[-1].end()].rstrip()


def _parla_per_altra_macchina(testo, agente, macchine):
    etichette = sorted(
        {
            etichetta
            for altra in macchine
            if altra["id"] != agente["id"]
            for etichetta in (altra["id"], altra.get("ruolo_assegnato", ""))
            if etichetta
        },
        key=len,
        reverse=True,
    )
    if not etichette:
        return False
    markup = r"(?:\*{1,3}|_{1,3}|~{1,2}|`{1,3})?"
    pattern = (
        rf"(?im)^[ \t]*{markup}[ \t]*"
        rf"(?:{'|'.join(re.escape(etichetta) for etichetta in etichette)})"
        rf"{markup}[ \t]*:{markup}[ \t]*"
    )
    return re.search(pattern, testo) is not None


def _istruzioni(agente, scheda):
    vincoli = "\n".join(f"- {vincolo}" for vincolo in scheda.get("vincoli", []))
    return (
        "Interpreta il ruolo assegnato in modo coerente e realistico. "
        "Considera tutte le sezioni della scheda, senza inventare fatti. "
        "Rispondi in italiano con un solo intervento conciso (massimo 120 parole). "
        "Esponilo come un unico testo coeso, senza dividerlo in più battute o turni. "
        "Non riportare il dialogo precedente e non parlare a nome dell'altra macchina. "
        "Concludi sempre con una frase completa e con la punteggiatura finale. "
        "Prima di rispondere, controlla soprattutto che l'ultima frase sia completa. "
        "Il grado di cooperazione indica insieme la disponibilità a rivedere "
        "la tua posizione e l'impegno a cercare una soluzione che consideri "
        "le esigenze di entrambe le macchine. Usalo come orientamento del tuo "
        "comportamento, non come esito già deciso: "
        "0 = mantieni rigidamente la tua posizione e non cerchi un compromesso; "
        "1-2 = sei molto poco disposto a cambiare idea e cedi solo davanti a "
        "ragioni decisive; "
        "3-4 = sei poco disposto a cambiare idea, ascolti ma fai concessioni "
        "limitate; "
        "5-6 = sei abbastanza disposto a rivedere la posizione e a proporre "
        "compromessi ragionevoli; "
        "7-8 = sei molto disposto a rivedere la posizione e cerchi attivamente "
        "una soluzione utile a entrambi; "
        "9-10 = sei pronto a rivedere rapidamente le posizioni negoziabili e "
        "a privilegiare una soluzione reciprocamente soddisfacente. "
        "Distingui gli obiettivi dai vincoli non negoziabili: puoi adattare "
        "le proposte, ma non ignorare né inventare vincoli. Applica il grado "
        "solo al tuo comportamento, senza presumere che l'altra macchina sia "
        "altrettanto cooperativa. In una trattativa sul prezzo, il venditore "
        "chiede un prezzo più alto: non ridurre la propria richiesta sotto "
        "l'ultima offerta dell'acquirente. L'acquirente chiede un prezzo più "
        "basso: non rilanciare sopra l'ultima richiesta del venditore. Un "
        "prezzo più basso proposto dal venditore è più vantaggioso per "
        "l'acquirente; riconoscilo, accettalo se rispetta i tuoi vincoli o "
        "controproponi un importo ancora più basso. Puoi accettare esplicitamente "
        "l'offerta dell'altra macchina solo se rispetta tutti i tuoi vincoli. "
        f"Grado di cooperazione assegnato: {agente['grado_di_cooperazione']}/10.\n\n"
        f"Ruolo: {agente['ruolo_assegnato']}\n"
        f"Obiettivo: {agente['obiettivo']}\n"
        f"Vincoli inderogabili:\n{vincoli or 'Nessuno.'}\n\n"
        "Indicazioni manuali dell'operatore:\n"
        f"{scheda.get('riassunto', '').strip() or 'Nessuna.'}\n\n"
        "Sintesi delle pagine web:\n"
        f"{scheda.get('sintesi', '').strip() or 'Non disponibile.'}"
    )


def _richiesta_turno(tema, interventi):
    if interventi:
        contesto = "\n".join(
            f"{voce['agente_id']}: {voce['testo']}" for voce in interventi
        )
        return (
            f"Tema iniziale: {tema}\n\n"
            f"Dialogo finora:\n{contesto}\n\n"
            "Rispondi all'ultimo intervento e fai avanzare il confronto. "
            "Scrivi un solo intervento in un unico testo coeso, senza dividerlo "
            "in più battute o turni e senza ripetere quelli precedenti. "
            "Termina con una frase completa."
        )
    return (
        f"Avvia il dialogo sul tema: {tema}. Scrivi un solo intervento "
        "in un unico testo coeso, senza dividerlo in più battute o turni."
    )


def _parole_italiane(testo):
    for parola in tokenize(testo, "it"):
        yield from (parte for parte in re.split(r"['’]", parola) if parte)


def _lessico_ammesso(config, schede):
    testi = []
    for agente in config["macchine"]:
        testi.extend(
            [
                agente["id"],
                agente["ruolo_assegnato"],
                agente["obiettivo"],
                agente["tema_iniziale"],
                agente.get("riassunto", ""),
                *agente.get("vincoli", []),
            ]
        )
        scheda = schede.get(agente["id"], {})
        testi.extend(
            scheda.get(campo, "")
            for campo in ("riassunto", "sintesi")
        )
        testi.extend(scheda.get("vincoli", []))

    return {parola for testo in testi for parola in _parole_italiane(testo)}


def _interventi_con_parole_sconosciute(interventi, lessico_ammesso):
    risultati = {}
    for indice, voce in enumerate(interventi):
        if voce["testo"] == "[creazione turno fallita]":
            continue
        parole = set(_parole_italiane(voce["testo"]))
        sconosciute = {
            parola
            for parola in parole - lessico_ammesso
            if not re.fullmatch(r"\d+(?:[.,]\d+)?", parola)
            if zipf_frequency(parola, "it") == 0
        }
        if sconosciute:
            risultati[indice] = sorted(sconosciute)
    return risultati


def _rigenera_se_include_altra_macchina(testo, richiesta, agente, schede, macchine):
    for _ in range(2):
        if not _parla_per_altra_macchina(testo, agente, macchine):
            return testo
        print(
            f"\nRisposta non valida di {agente['id']}: "
            "attribuisce battute all'altra macchina; provo a rigenerarla."
        )
        risposta = ollama.chat(
            model=agente["nome_modello"],
            messages=[
                {
                    "role": "system",
                    "content": _istruzioni(agente, schede.get(agente["id"], "")),
                },
                {
                    "role": "user",
                    "content": (
                        f"{richiesta}\n\n"
                        "La risposta precedente non è valida perché include battute "
                        "attribuite all'altra macchina. Riscrivi da zero un solo "
                        f"intervento coeso come {agente['ruolo_assegnato']} "
                        f"(ID {agente['id']}). Non inserire etichette di parlante, "
                        "non scrivere battute o pensieri dell'altra macchina e "
                        "concludi con una frase completa e la punteggiatura finale."
                    ),
                },
            ],
            options={"num_predict": 400},
        )
        testo = risposta.message.content.strip()

    if _parla_per_altra_macchina(testo, agente, macchine):
        raise ValueError(
            f"Il modello {agente['nome_modello']} continua a parlare "
            f"per l'altra macchina nell'intervento di {agente['id']}."
        )
    return testo


def _completa_intervento(testo, agente, schede):
    if _frase_finale_completa(testo):
        return testo

    print(f"\nRisposta incompleta di {agente['id']}: provo a completarla.")
    recupero = ollama.chat(
        model=agente["nome_modello"],
        messages=[
            {
                "role": "system",
                "content": _istruzioni(agente, schede.get(agente["id"], "")),
            },
            {
                "role": "user",
                "content": (
                    "Riscrivi questo intervento in forma concisa, "
                    "mantenendo il suo significato. Restituisci un solo "
                    "intervento e assicurati che l'ultima frase sia "
                    "completa e termini con la punteggiatura.\n\n"
                    f"Intervento da completare:\n{testo}"
                ),
            },
        ],
        options={"num_predict": 400},
    )
    testo_recuperato = recupero.message.content.strip()
    if testo_recuperato:
        testo = testo_recuperato
    if not _frase_finale_completa(testo):
        testo = _rimuovi_frase_incompleta(testo)
    return testo


def _verifica_e_rigenera_dialogo(
    interventi, config, schede, lessico_ammesso, tema
):
    macchine = {agente["id"]: agente for agente in config["macchine"]}
    tentativi = {}

    while True:
        errori = _interventi_con_parole_sconosciute(interventi, lessico_ammesso)
        if not errori:
            return

        indice = min(errori)
        if tentativi.get(indice, 0) >= 2:
            termini = ", ".join(errori[indice])
            print(
                f"Intervento di {interventi[indice]['agente_id']} non recuperabile "
                f"dopo due tentativi ({termini}); proseguo il dialogo."
            )
            interventi[indice]["testo"] = "[creazione turno fallita]"
            continue

        voce = interventi[indice]
        agente = macchine[voce["agente_id"]]
        richiesta = _richiesta_turno(tema, interventi[:indice])
        termini = ", ".join(errori[indice])
        print(
            f"\nIntervento non valido di {agente['id']}: il correttore italiano "
            f"non riconosce {termini}; provo a rigenerarlo."
        )
        tentativi[indice] = tentativi.get(indice, 0) + 1
        try:
            risposta = ollama.chat(
                model=agente["nome_modello"],
                messages=[
                    {
                        "role": "system",
                        "content": _istruzioni(agente, schede.get(agente["id"], "")),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"{richiesta}\n\n"
                            "Il correttore italiano non riconosce questi termini: "
                            f"{termini}. Riscrivi da zero l'intervento senza usarli "
                            "e senza introdurre parole inventate. Mantieni la libertà "
                            "di formulazione e usa normalmente il lessico italiano."
                        ),
                    },
                ],
                options={"num_predict": 700},
            )
            testo = risposta.message.content.strip()
            testo = _rigenera_se_include_altra_macchina(
                testo, richiesta, agente, schede, config["macchine"]
            )
            testo = _completa_intervento(testo, agente, schede)
            testo = _rigenera_se_include_altra_macchina(
                testo, richiesta, agente, schede, config["macchine"]
            )
            voce["testo"] = testo
            print(f"Intervento rigenerato di {agente['id']}:\n{testo}")
        except Exception as errore:
            print(
                f"Rigenerazione dell'intervento di {agente['id']} fallita: "
                f"{errore}"
            )


def _genera_intervento(richiesta, agente, schede, macchine, interventi):
    for tentativo in range(2):
        try:
            risposta = ollama.chat(
                model=agente["nome_modello"],
                messages=[
                    {
                        "role": "system",
                        "content": _istruzioni(
                            agente, schede.get(agente["id"], "")
                        ),
                    },
                    {"role": "user", "content": richiesta},
                ],
                options={"num_predict": 700},
            )
            testo = risposta.message.content.strip()
            testo = _rigenera_se_include_altra_macchina(
                testo, richiesta, agente, schede, macchine
            )
            testo = _completa_intervento(testo, agente, schede)
            testo = _rigenera_se_include_altra_macchina(
                testo, richiesta, agente, schede, macchine
            )

            for _ in range(2):
                errore = errore_offerta(testo, agente, interventi, macchine)
                if errore is None:
                    return testo
                print(
                    f"\nOfferta non coerente di {agente['id']}: "
                    f"{errore} Provo a rigenerarla."
                )
                risposta = ollama.chat(
                    model=agente["nome_modello"],
                    messages=[
                        {
                            "role": "system",
                            "content": _istruzioni(
                                agente, schede.get(agente["id"], "")
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{richiesta}\n\n"
                                f"La risposta precedente non è valida: {errore} "
                                "Riscrivi l'intervento senza violare i vincoli. "
                                "Se sei il venditore, chiedi un prezzo più alto "
                                "dell'ultima offerta dell'acquirente; se sei "
                                "l'acquirente, chiedi un prezzo più basso "
                                "dell'ultima richiesta del venditore. Non dichiarare "
                                "accordi che l'altra macchina non ha accettato."
                            ),
                        },
                    ],
                    options={"num_predict": 700},
                )
                testo = risposta.message.content.strip()
                testo = _rigenera_se_include_altra_macchina(
                    testo, richiesta, agente, schede, macchine
                )
                testo = _completa_intervento(testo, agente, schede)
                testo = _rigenera_se_include_altra_macchina(
                    testo, richiesta, agente, schede, macchine
                )

            errore = errore_offerta(testo, agente, interventi, macchine)
            if errore is None:
                return testo
            raise ValueError(
                f"Offerta incoerente per {agente['id']}: {errore}"
            )
        except Exception as errore:
            print(
                f"Creazione dell'intervento di {agente['id']} non riuscita "
                f"(tentativo {tentativo + 1}/2): {errore}"
            )

    print(f"Intervento di {agente['id']} non prodotto: proseguo il dialogo.")
    return "[creazione turno fallita]"


def avvia_dialogo(config, schede):
    macchine = config["macchine"]
    tema = macchine[0]["tema_iniziale"]
    interventi = []
    lessico_ammesso = _lessico_ammesso(config, schede)

    for numero_turno in range(1, config["numero_di_turni"] + 1):
        for agente in macchine:
            richiesta = _richiesta_turno(tema, interventi)
            testo = _genera_intervento(
                richiesta, agente, schede, macchine, interventi
            )

            voce = {
                "turno": numero_turno,
                "agente_id": agente["id"],
                "nome_modello": agente["nome_modello"],
                "testo": testo,
            }
            interventi.append(voce)
            print(f"\n{agente['id']} (turno {numero_turno}):\n{testo}")
            _verifica_e_rigenera_dialogo(
                interventi, config, schede, lessico_ammesso, tema
            )

    return interventi