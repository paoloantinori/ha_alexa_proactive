"""Alexa interaction model templates."""

import copy

from .const import LOCALE_LABELS

SUPPORTED_LOCALES = list(LOCALE_LABELS)

_STANDARD_INTENTS = [
    {"name": "AMAZON.NavigateHomeIntent", "samples": []},
    {"name": "AMAZON.HelpIntent", "samples": []},
    {"name": "AMAZON.CancelIntent", "samples": []},
    {"name": "AMAZON.StopIntent", "samples": []},
]


def _build_model(invocation_name: str, send_samples: list[str], check_samples: list[str]) -> dict:
    return {
        "interactionModel": {
            "languageModel": {
                "invocationName": invocation_name,
                "intents": [
                    *_STANDARD_INTENTS,
                    {
                        "name": "SendNotificationIntent",
                        "slots": [],
                        "samples": send_samples,
                    },
                    {
                        "name": "CheckStatusIntent",
                        "slots": [],
                        "samples": check_samples,
                    },
                ],
                "types": [],
            }
        }
    }


# -- Shared utterance sets for locale families with identical/similar samples --

_EN_SEND = [
    "send a notification",
    "send me a notification",
    "send a message",
    "send me a message",
    "notify me",
    "ping me",
    "alert me",
    "send an alert",
]
_EN_CHECK = [
    "what is my status",
    "check my status",
    "am I subscribed",
    "status",
    "am I set up",
]

_ES_SEND = [
    "envía una notificación",
    "envíame una notificación",
    "envía un mensaje",
    "envíame un mensaje",
    "notifícame",
    "ping me",
    "envía una alerta",
    "avísame",
]
_ES_CHECK_COMMON = [
    "cuál es mi estado",
    "estoy suscrito",
    "estado",
    "estoy configurado",
]

_FR_SEND = [
    "envoie une notification",
    "envoie-moi une notification",
    "envoie un message",
    "envoie-moi un message",
    "notifie-moi",
    "ping me",
    "envoie une alerte",
]

# -- Per-locale utterances --

_LOCALE_UTTERANCES: dict[str, dict[str, list[str]]] = {
    "ar-SA": {
        "send": [
            "أرسل إشعار",
            "أرسل لي إشعار",
            "أرسل رسالة",
            "أرسل لي رسالة",
            "نبّهني",
            "أرسل تنبيه",
        ],
        "check": [
            "ما هي حالتي",
            "تحقق من حالتي",
            "هل أنا مشترك",
            "حالة",
            "هل أنا جاهز",
        ],
    },
    "de-DE": {
        "send": [
            "sende eine benachrichtigung",
            "sende mir eine benachrichtigung",
            "sende eine nachricht",
            "sende mir eine nachricht",
            "benachrichtige mich",
            "ping me",
            "sende einen alarm",
        ],
        "check": [
            "was ist mein status",
            "prüfe meinen status",
            "bin ich angemeldet",
            "status",
            "bin ich eingerichtet",
        ],
    },
    "en-AU": {"send": _EN_SEND, "check": _EN_CHECK},
    "en-CA": {"send": _EN_SEND, "check": _EN_CHECK},
    "en-GB": {"send": _EN_SEND, "check": _EN_CHECK},
    "en-IN": {"send": _EN_SEND, "check": _EN_CHECK},
    "en-US": {"send": _EN_SEND, "check": _EN_CHECK},
    "es-ES": {
        "send": _ES_SEND,
        "check": ["comprueba mi estado", *_ES_CHECK_COMMON],
    },
    "es-MX": {
        "send": _ES_SEND,
        "check": ["revisa mi estado", *_ES_CHECK_COMMON],
    },
    "es-US": {
        "send": _ES_SEND,
        "check": ["verifica mi estado", *_ES_CHECK_COMMON],
    },
    "fr-CA": {
        "send": _FR_SEND,
        "check": [
            "quel est mon état",
            "vérifie mon état",
            "suis-je abonné",
            "état",
            "suis-je configuré",
        ],
    },
    "fr-FR": {
        "send": _FR_SEND,
        "check": [
            "quel est mon statut",
            "vérifie mon statut",
            "suis-je abonné",
            "statut",
            "suis-je configuré",
        ],
    },
    "hi-IN": {
        "send": [
            "सूचना भेजो",
            "मुझे सूचना भेजो",
            "संदेश भेजो",
            "मुझे संदेश भेजो",
            "मुझे सूचित करो",
            "ping me",
            "अलर्ट भेजो",
        ],
        "check": [
            "मेरी स्थिति क्या है",
            "मेरी स्थिति जांचो",
            "क्या मैं सब्सक्राइब्ड हूं",
            "स्थिति",
            "क्या मैं सेटअप हूं",
        ],
    },
    "it-IT": {
        "send": [
            "invia una notifica",
            "mandami una notifica",
            "invia un messaggio",
            "mandami un messaggio",
            "notificami",
            "ping me",
            "avvisami",
            "invia un avviso",
        ],
        "check": [
            "qual è il mio stato",
            "controlla il mio stato",
            "sono iscritto",
            "stato",
            "sono configurato",
        ],
    },
    "ja-JP": {
        "send": [
            "通知を送って",
            "通知をして",
            "メッセージを送って",
            "メッセージをして",
            "知らせて",
            "ping me",
            "アラートを送って",
        ],
        "check": [
            "ステータスは",
            "ステータスを確認して",
            "登録されている",
            "状態",
            "設定されている",
        ],
    },
    "nl-NL": {
        "send": [
            "stuur een melding",
            "stuur me een melding",
            "stuur een bericht",
            "stuur me een bericht",
            "breng me op de hoogte",
            "ping me",
            "stuur een alarm",
        ],
        "check": [
            "wat is mijn status",
            "controleer mijn status",
            "ben ik ingeschreven",
            "status",
            "ben ik ingesteld",
        ],
    },
    "pt-BR": {
        "send": [
            "envie uma notificação",
            "me envie uma notificação",
            "envie uma mensagem",
            "me envie uma mensagem",
            "me notifique",
            "ping me",
            "envie um alerta",
        ],
        "check": [
            "qual é o meu status",
            "verifique meu status",
            "estou inscrito",
            "status",
            "estou configurado",
        ],
    },
}

MODELS = {
    locale: _build_model("ping me", u["send"], u["check"])
    for locale, u in _LOCALE_UTTERANCES.items()
}

_DEFAULT_INVOCATION = "ping me"


def get_model(locale: str, invocation_name: str = _DEFAULT_INVOCATION) -> dict:
    if invocation_name == _DEFAULT_INVOCATION:
        return MODELS[locale]
    model = copy.deepcopy(MODELS[locale])
    model["interactionModel"]["languageModel"]["invocationName"] = invocation_name
    return model
