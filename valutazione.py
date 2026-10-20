import json

import google_api

from negoziazione import errore_vincolo_prezzo


def _punteggio_valido(valore, minimo, massimo):
    if type(valore) is int and minimo <= valore <= massimo:
        return valore
    return None


def _errori_valutazione(dati, id_macchine, numero_turni):
    if not isinstance(dati, dict):
        return ["La risposta JSON deve essere un oggetto."]

    errori = []
    id_macchine_validi = set(id_macchine)
    campi_ammessi = {
        "cooperazione",
        "conflitto",
        "coerenza",
        "obiettivi_raggiunti",
        "motivazione_obiettivi",
        "vincoli_rispettati",
        "accordo_raggiunto",
        "accordo",
        "accordo_per_turno",
        "commento",
    }
    campi_sconosciuti = set(dati) - campi_ammessi
    if campi_sconosciuti:
        errori.append(
            "Nomi o campi non riconosciuti: "
            + ", ".join(sorted(campi_sconosciuti))
            + "."
        )

    macchine = dati.get("macchine")
    if isinstance(macchine, list):
        for indice, macchina in enumerate(macchine):
            if not isinstance(macchina, dict):
                continue
            nome = macchina.get("nome", macchina.get("id"))
            if nome is not None and (
                not isinstance(nome, str) or nome not in id_macchine_validi
            ):
                errori.append(
                    f"macchine[{indice}]: ID macchina non riconosciuto ({nome})."
                )

    for campo, minimo, massimo in (
        ("cooperazione", 0, 10),
        ("conflitto", 0, 10),
        ("accordo", 1, 5),
    ):
        if _punteggio_valido(dati.get(campo), minimo, massimo) is None:
            errori.append(f"{campo}: serve un intero tra {minimo} e {massimo}.")

    for campo in ("coerenza", "obiettivi_raggiunti", "motivazione_obiettivi", "vincoli_rispettati"):
        valori = dati.get(campo)
        if not isinstance(valori, dict):
            errori.append(f"{campo}: serve un oggetto con un valore per ogni macchina.")
            continue
        nomi_sconosciuti = set(valori) - id_macchine_validi
        if nomi_sconosciuti:
            errori.append(
                f"{campo}: ID macchina non riconosciuti: "
                + ", ".join(sorted(nomi_sconosciuti))
                + "."
            )
        for agente_id in id_macchine:
            valore = valori.get(agente_id)
            if campo == "coerenza":
                valido = _punteggio_valido(valore, 1, 5) is not None
            elif campo in ("obiettivi_raggiunti", "vincoli_rispettati"):
                valido = isinstance(valore, bool)
            else:
                valido = isinstance(valore, str) and bool(valore.strip())
            if not valido:
                errori.append(f"{campo}.{agente_id}: valore mancante o non valido.")

    if not isinstance(dati.get("accordo_raggiunto"), bool):
        errori.append("accordo_raggiunto: serve true oppure false.")

    progressione = dati.get("accordo_per_turno")
    if not isinstance(progressione, list) or len(progressione) != numero_turni:
        errori.append(
            f"accordo_per_turno: servono esattamente {numero_turni} punteggi, uno per turno."
        )
    elif any(_punteggio_valido(valore, 1, 5) is None for valore in progressione):
        errori.append("accordo_per_turno: ogni turno deve avere un intero tra 1 e 5.")

    return errori


def valuta_dialogo(config, interventi):
    dialogo = "\n\n".join(
        f"Turno {voce['turno']} - {voce['agente_id']}:\n{voce['testo']}"
        for voce in interventi
    )
    id_macchine = [agente["id"] for agente in config["macchine"]]
    obiettivi_macchine = "\n\n".join(
        f"Macchina {agente['id']}:\n"
        f"Ruolo assegnato: {agente['ruolo_assegnato']}\n"
        f"Obiettivo: {agente['obiettivo']}\n"
        f"Vincoli inderogabili: {'; '.join(agente.get('vincoli', [])) or 'nessuno'}\n"
        f"Istruzioni aggiuntive e vincoli: {agente.get('riassunto', '')}"
        for agente in config["macchine"]
    )
    messaggi = [
            {
                "role": "system",
                "content": (
                    "Valuta il dialogo completo in modo equilibrato. "
                    "Restituisci solo JSON valido con questi campi: "
                    "cooperazione (intero 0-10), conflitto (intero 0-10), "
                    "coerenza (oggetto con un voto 1-5 per ogni macchina), "
                    "obiettivi_raggiunti (oggetto con un booleano per ogni macchina), "
                    "motivazione_obiettivi (oggetto con una breve motivazione per macchina), "
                    "vincoli_rispettati (oggetto con un booleano per ogni macchina), "
                    "accordo_raggiunto (booleano), "
                    "accordo (intero 1-5), "
                    "accordo_per_turno (lista di interi 1-5, uno per turno). "
                    "Per coerenza valuta insieme, per ciascuna macchina, la qualità dei "
                    "nessi logici e la fedeltà al proprio obiettivo: "
                    "1 = nessi logici di qualità molto bassa e fedeltà all'obiettivo molto bassa; "
                    "2 = nessi logici di qualità bassa e fedeltà all'obiettivo bassa; "
                    "3 = nessi logici di qualità mediocre e fedeltà all'obiettivo mediocre; "
                    "4 = nessi logici di qualità buona e fedeltà all'obiettivo buona; "
                    "5 = nessi logici di qualità eccellente e fedeltà all'obiettivo eccellente. "
                    "Valuta il raggiungimento dell'obiettivo separatamente per ogni macchina: "
                    "usa true solo se l'obiettivo risulta raggiunto entro la fine del dialogo; "
                    "usa false se non è raggiunto o è raggiunto solo parzialmente. "
                    "Valuta separatamente vincoli_rispettati: true solo se la macchina "
                    "non ha ritrattato né violato nessuno dei propri vincoli inderogabili "
                    "in alcun momento del dialogo; se ne ritratterà o violerà anche uno, "
                    "usa false. Se non sono indicati vincoli, usa true. "
                    "Valuta accordo_raggiunto come true solo se entrambe le macchine "
                    "accettano esplicitamente gli stessi termini entro la fine del dialogo; "
                    "proposte, disponibilità generiche o accordi solo ipotetici non bastano. "
                    "Considera un obiettivo di compravendita raggiunto quando è stato "
                    "concluso un accordo esplicito e la macchina ha rispettato tutti i "
                    "propri vincoli inderogabili; il prezzo obiettivo è una preferenza, "
                    "non un vincolo, salvo che sia ripetuto tra i vincoli inderogabili. "
                    "Se i vincoli non sono rispettati, l'obiettivo non può essere considerato raggiunto. "
                    "Motiva ogni esito con una breve evidenza tratta dal dialogo. "
                    "Mantieni ogni motivazione entro una frase breve e il commento conciso "
                    "per restituire tutti i campi in un JSON completo. "
                    "Per cooperazione usa la scala operativa indicata alle macchine e "
                    "valuta il comportamento effettivamente mostrato da entrambe nel dialogo: "
                    "disponibilità a rivedere la propria posizione e impegno a cercare "
                    "una soluzione che consideri le esigenze di entrambe. "
                    "0 = mantengono rigidamente la propria posizione e non cercano un compromesso; "
                    "1-2 = sono molto poco disposte a cambiare idea e cedono solo davanti a "
                    "ragioni decisive; "
                    "3-4 = sono poco disposte a cambiare idea, ascoltano ma fanno concessioni "
                    "limitate; "
                    "5-6 = sono abbastanza disposte a rivedere la posizione e a proporre "
                    "compromessi ragionevoli; "
                    "7-8 = sono molto disposte a rivedere la posizione e cercano attivamente "
                    "una soluzione utile a entrambe; "
                    "9-10 = sono pronte a rivedere rapidamente le posizioni negoziabili e "
                    "a privilegiare una soluzione reciprocamente soddisfacente. "
                    "Assegna un solo punteggio complessivo in modo equilibrato, basandoti "
                    "sulle azioni osservate e non soltanto sulle intenzioni dichiarate. "
                    "Per accordo e accordo_per_turno usa sempre questa scala: "
                    "1 = grado di accordo molto basso; "
                    "2 = grado di accordo basso; "
                    "3 = grado di accordo intermedio; "
                    "4 = grado di accordo alto; "
                    "5 = grado di accordo molto alto. "
                    "Confronta le tesi sostenute dalle due macchine in ciascun turno: "
                    "1 = tesi incompatibili e nessuna convergenza; "
                    "2 = prevale la divergenza, con pochi punti condivisi; "
                    "3 = condivisione parziale o primi segnali di convergenza, ma restano differenze; "
                    "4 = tesi in gran parte convergenti, con differenze marginali; "
                    "5 = tesi condivise o accordo esplicito. "
                    "Valuta la posizione espressa, non la cortesia, il tono o la cooperazione. "
                    "Il numero di accordo per turno descrive la vicinanza raggiunta tra le posizioni delle due macchine "
                    "dopo entrambi gli interventi del turno."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Macchine da valutare: {', '.join(id_macchine)}\n"
                    f"Numero di turni: {config['numero_di_turni']}\n\n"
                    f"Obiettivi e istruzioni assegnati:\n{obiettivi_macchine}\n\n"
                    f"Dialogo completo:\n{dialogo}"
                ),
            },
        ]

    tentativi = []
    dati = {}
    errori_finali = []
    for numero_tentativo in range(2):
        try:
            risposta = google_api.chat(
                model=config["valutatore"]["nome_modello"],
                format="json",
                messages=messaggi,
                options={"num_predict": 2048},
            )
            risposta_grezza = risposta.message.content
            try:
                dati = json.loads(risposta_grezza)
                errori_finali = _errori_valutazione(
                    dati, id_macchine, config["numero_di_turni"]
                )
            except json.JSONDecodeError:
                dati = {}
                errori_finali = ["La risposta non contiene JSON valido."]
        except Exception as errore:
            if google_api.is_quota_error(errore):
                raise RuntimeError(
                    "Quota Gemini esaurita durante la valutazione con il "
                    f"modello {config['valutatore']['nome_modello']}. "
                    "Controlla le quote e la fatturazione del progetto Google AI Studio."
                ) from errore
            risposta_grezza = None
            dati = {}
            errori_finali = [f"Chiamata al valutatore non riuscita: {errore}"]

        tentativi.append({"risposta": risposta_grezza, "errori": errori_finali})
        if not errori_finali:
            break
        if numero_tentativo == 0:
            if risposta_grezza is not None:
                messaggi.append({"role": "assistant", "content": risposta_grezza})
            messaggi.append(
                {
                    "role": "user",
                    "content": (
                        "La risposta precedente è incompleta o contiene valori non validi. "
                        "Correggila e restituisci un unico JSON completo, senza omettere "
                        "campi o macchine. Problemi rilevati: "
                        + " ".join(errori_finali)
                    ),
                }
            )

    if errori_finali:
        dati = {}

    if not isinstance(dati, dict):
        dati = {}

    cooperazione = _punteggio_valido(dati.get("cooperazione"), 0, 10)
    coerenza_originale = dati.get("coerenza", {})
    if not isinstance(coerenza_originale, dict):
        coerenza_originale = {}
    coerenza = {
        agente_id: _punteggio_valido(coerenza_originale.get(agente_id), 1, 5)
        for agente_id in id_macchine
    }
    obiettivi_originali = dati.get("obiettivi_raggiunti", {})
    if not isinstance(obiettivi_originali, dict):
        obiettivi_originali = {}
    obiettivi_raggiunti = {
        agente_id: (
            obiettivi_originali.get(agente_id)
            if isinstance(obiettivi_originali.get(agente_id), bool)
            else None
        )
        for agente_id in id_macchine
    }
    accordo_raggiunto = (
        dati.get("accordo_raggiunto")
        if isinstance(dati.get("accordo_raggiunto"), bool)
        else None
    )
    vincoli_configurati = {
        agente["id"]: agente.get("vincoli", []) for agente in config["macchine"]
    }
    vincoli_originali = dati.get("vincoli_rispettati", {})
    if not isinstance(vincoli_originali, dict):
        vincoli_originali = {}
    vincoli_rispettati = {
        agente_id: (
            True
            if not vincoli_configurati.get(agente_id)
            else vincoli_originali.get(agente_id)
            if isinstance(vincoli_originali.get(agente_id), bool)
            else None
        )
        for agente_id in id_macchine
    }
    agenti_configurati = {agente["id"]: agente for agente in config["macchine"]}
    prove_violazione_vincoli = {agente_id: [] for agente_id in id_macchine}
    for voce in interventi:
        agente_id = voce["agente_id"]
        errore = errore_vincolo_prezzo(
            voce["testo"], agenti_configurati[agente_id]
        )
        if errore is not None:
            prove_violazione_vincoli[agente_id].append(errore)
    for agente_id, prove in prove_violazione_vincoli.items():
        if prove:
            vincoli_rispettati[agente_id] = False

    for agente_id, esito in obiettivi_raggiunti.items():
        if accordo_raggiunto is False or vincoli_rispettati[agente_id] is False:
            obiettivi_raggiunti[agente_id] = False
        elif (
            accordo_raggiunto is None
            or vincoli_rispettati[agente_id] is None
        ):
            obiettivi_raggiunti[agente_id] = None
        else:
            obiettivi_raggiunti[agente_id] = True
    motivazioni_originali = dati.get("motivazione_obiettivi", {})
    if not isinstance(motivazioni_originali, dict):
        motivazioni_originali = {}
    motivazione_obiettivi = {
        agente_id: (
            motivazioni_originali.get(agente_id)
            if isinstance(motivazioni_originali.get(agente_id), str)
            and motivazioni_originali.get(agente_id).strip()
            else None
        )
        for agente_id in id_macchine
    }
    for agente_id in id_macchine:
        motivi = []
        if accordo_raggiunto is False:
            motivi.append("non è stato concluso un accordo esplicito tra le parti")
        if vincoli_rispettati[agente_id] is False:
            dettaglio_vincolo = (
                prove_violazione_vincoli[agente_id][0]
                if prove_violazione_vincoli[agente_id]
                else "è stato ritrattato o violato almeno un vincolo inderogabile"
            )
            motivi.append(dettaglio_vincolo)
        if motivi:
            evidenza = motivazione_obiettivi[agente_id]
            dettaglio = "; inoltre, ".join(motivi)
            motivazione_obiettivi[agente_id] = (
                f"{evidenza} Esito: {dettaglio}." if evidenza else f"Esito: {dettaglio}."
            )
    accordo = _punteggio_valido(dati.get("accordo"), 1, 5)
    progressione = dati.get("accordo_per_turno", [])
    if not isinstance(progressione, list):
        progressione = []
    progressione = [
        _punteggio_valido(progressione[indice], 1, 5)
        if indice < len(progressione)
        else None
        for indice in range(config["numero_di_turni"])
    ]

    return {
        "cooperazione": cooperazione,
        "conflitto": 10 - cooperazione if cooperazione is not None else None,
        "coerenza": coerenza,
        "obiettivi_raggiunti": obiettivi_raggiunti,
        "motivazione_obiettivi": motivazione_obiettivi,
        "vincoli_rispettati": vincoli_rispettati,
        "accordo_raggiunto": accordo_raggiunto,
        "accordo": accordo,
        "accordo_per_turno": progressione,
        "commento": dati.get("commento", "")
        if isinstance(dati.get("commento", ""), str)
        else "",
        "risposta_valutatore": tentativi[-1]["risposta"] if tentativi else None,
        "tentativi_valutatore": tentativi,
        "errori_valutazione": errori_finali,
    }