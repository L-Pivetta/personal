# Dialogo tra modelli Ollama

Il progetto fa dialogare due modelli locali, consulta il web per preparare le
schede dei ruoli, valuta il confronto con un modello Ollama e crea un report HTML.

## Avvio su Windows

1. Verifica che l'applicazione Ollama sia avviata. Per vedere i modelli installati:
   `ollama list`. Io ho utilizzato `mistral:latest`, `llama3.2:latest`, `llama3.1:8b`.
2. Apri PowerShell e crea l'ambiente virtuale per la cartella del progetto:
   `python -m venv .venv`
3. Installa le librerie del progetto:
   `.venv\Scripts\python -m pip install -r requirements.txt`
4. Modifica solo `config.json`. I nomi dei modelli devono corrispondere a quelli
   mostrati da `ollama list`. Nel campo `riassunto` puoi inserire indicazioni
   sull'identità e sulla posizione che la macchina deve sostenere. La scheda
   `scheda_<macchina>.json` mantiene distinti `vincoli`, `riassunto` e `sintesi`
   delle pagine web; tutti e tre vengono forniti al modello durante il dialogo.
   Se la ricerca o la sintesi non riesce, la scheda segnala la sintesi come
   non disponibile senza sostituirla con il testo manuale. Per ogni
   macchina puoi compilare `siti_da_indagare` con un elenco di URL `http://` o
   `https://` e impostare `cerca_sul_web` a `true` o `false`.
   Per ogni macchina, `vincoli` è un elenco di condizioni inderogabili, per
   esempio `"vincoli": ["Non accettare un prezzo superiore a 1,5 euro/kg"]`.
   Un vincolo è rispettato solo se la macchina non lo ritratterà né lo violerà
   durante il dialogo. La valutazione riporta separatamente
   `vincoli_rispettati` e considera raggiunto un obiettivo solo quando è stato
   concluso un accordo esplicito e i vincoli della macchina sono rispettati;
   il prezzo indicato nell'obiettivo è una preferenza, a meno che non sia
   ripetuto tra i vincoli. Le proposte espresse in euro vengono controllate
   rispetto ai limiti numerici dei vincoli e all'ultima proposta avversaria,
   per evitare che un'offerta peggiori la posizione negoziale della macchina.
   Se `vincoli` è omesso o vuoto, non sono configurati vincoli inderogabili.
5. Avvia il progetto:
   `.venv\Scripts\python main.py`

Per rifare valutazione e report usando un dialogo già salvato, senza avviare
ricerca o generazione, esegui:
`.venv\Scripts\python main.py --da-log "logs\dialogo_<data>_<ora>.json"`
I nuovi log includono una copia della configurazione usata. I log creati con le
versioni precedenti contengono solo gli interventi e vengono elaborati con la
configurazione attuale in `config.json`. L'analisi e il report in `output/`
vengono aggiornati.

La ricerca web richiede una connessione Internet. Sono estratti i testi principali
degli articoli; PDF, video e social vengono esclusi. Le pagine scaricate e le
schede dei ruoli sono salvate in `output/`; il dialogo completo e salvato in `logs/`.
Il report finale si trova in `output/report_dialogo.html`.

I siti in `siti_da_indagare` vengono letti prima e hanno priorità; la ricerca
automatica, se attiva, aggiunge fonti fino a raggiungere tre pagine quando i
siti manuali riusciti sono meno di tre. Tutti i siti manuali vengono comunque
mantenuti. Gli URL duplicati vengono ignorati e ogni pagina in
`ricerca_<macchina>.json` riporta la provenienza. Con `cerca_sul_web: false`
vengono usati solo i siti indicati manualmente. Se un sito non è scaricabile o
non contiene testo estraibile, il programma stampa un avviso.

`numero_di_turni` indica il numero di scambi: in ciascuno parlano entrambe le
macchine. Il grado di cooperazione accetta valori da 0 a 10. Il report include
anche il conflitto, calcolato come `10 - cooperazione`.