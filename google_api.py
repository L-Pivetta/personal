import os
from types import SimpleNamespace

from google import genai
from google.genai import errors
from google.genai import types


def is_quota_error(error):
    return (
        isinstance(error, errors.APIError)
        and error.code == 429
        and error.status == "RESOURCE_EXHAUSTED"
    )


def retry_delay_seconds(error):
    if not is_quota_error(error):
        return None

    dettagli = getattr(error, "details", {})
    if not isinstance(dettagli, dict):
        return None
    errore = dettagli.get("error", {})
    if not isinstance(errore, dict):
        return None

    for dettaglio in errore.get("details", []):
        if (
            isinstance(dettaglio, dict)
            and dettaglio.get("@type")
            == "type.googleapis.com/google.rpc.RetryInfo"
        ):
            ritardo = dettaglio.get("retryDelay")
            if isinstance(ritardo, str) and ritardo.endswith("s"):
                try:
                    return float(ritardo[:-1])
                except ValueError:
                    return None
    return None


def is_service_unavailable_error(error):
    return (
        isinstance(error, errors.APIError)
        and error.code == 503
        and error.status == "UNAVAILABLE"
    )


def _crea_client(timeout=None):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Chiave API mancante. Imposta la variabile GEMINI_API_KEY "
            "con una chiave creata in Google AI Studio."
        )

    opzioni = {"api_key": api_key}
    if timeout is not None:
        opzioni["http_options"] = types.HttpOptions(timeout=int(timeout * 1000))
    return genai.Client(**opzioni)


def verifica_modelli(modelli):
    client = _crea_client()
    for modello in sorted(set(modelli)):
        client.models.get(model=modello)


def _chat(client, model, messages, format=None, options=None):
    istruzioni_sistema = []
    contenuti = []
    for messaggio in messages:
        ruolo = messaggio["role"]
        testo = messaggio["content"]
        if ruolo == "system":
            istruzioni_sistema.append(testo)
        else:
            contenuti.append(
                {
                    "role": "model" if ruolo == "assistant" else "user",
                    "parts": [{"text": testo}],
                }
            )

    configurazione = {}
    if istruzioni_sistema:
        configurazione["system_instruction"] = "\n\n".join(istruzioni_sistema)
    if options and options.get("num_predict"):
        configurazione["max_output_tokens"] = options["num_predict"]
    if format == "json":
        configurazione["response_mime_type"] = "application/json"

    risposta = client.models.generate_content(
        model=model,
        contents=contenuti,
        config=types.GenerateContentConfig(**configurazione),
    )
    testo = risposta.text or ""
    return SimpleNamespace(message=SimpleNamespace(content=testo))


def chat(model, messages, format=None, options=None):
    return _chat(_crea_client(), model, messages, format=format, options=options)


class Client:
    def __init__(self, timeout=None):
        self._client = _crea_client(timeout=timeout)

    def chat(self, model, messages, format=None, options=None):
        return _chat(
            self._client, model, messages, format=format, options=options
        )