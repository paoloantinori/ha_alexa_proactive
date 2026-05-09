"""Alexa interaction model templates."""

SUPPORTED_LOCALES = ["en-US", "it-IT"]

_EN_US_MODEL = {
    "interactionModel": {
        "languageModel": {
            "invocationName": "ping me",
            "intents": [
                {"name": "AMAZON.NavigateHomeIntent", "samples": []},
                {"name": "AMAZON.HelpIntent", "samples": []},
                {"name": "AMAZON.CancelIntent", "samples": []},
                {"name": "AMAZON.StopIntent", "samples": []},
                {
                    "name": "SendNotificationIntent",
                    "slots": [],
                    "samples": [
                        "send a notification",
                        "send me a notification",
                        "send a message",
                        "send me a message",
                        "notify me",
                        "ping me",
                        "alert me",
                        "send an alert",
                    ],
                },
                {
                    "name": "CheckStatusIntent",
                    "slots": [],
                    "samples": [
                        "what is my status",
                        "check my status",
                        "am I subscribed",
                        "status",
                        "am I set up",
                    ],
                },
            ],
            "types": [],
        }
    }
}

_IT_IT_MODEL = {
    "interactionModel": {
        "languageModel": {
            "invocationName": "ping me",
            "intents": [
                {"name": "AMAZON.NavigateHomeIntent", "samples": []},
                {"name": "AMAZON.HelpIntent", "samples": []},
                {"name": "AMAZON.CancelIntent", "samples": []},
                {"name": "AMAZON.StopIntent", "samples": []},
                {
                    "name": "SendNotificationIntent",
                    "slots": [],
                    "samples": [
                        "invia una notifica",
                        "mandami una notifica",
                        "invia un messaggio",
                        "mandami un messaggio",
                        "notificami",
                        "ping me",
                        "avvisami",
                        "invia un avviso",
                    ],
                },
                {
                    "name": "CheckStatusIntent",
                    "slots": [],
                    "samples": [
                        "qual è il mio stato",
                        "controlla il mio stato",
                        "sono iscritto",
                        "stato",
                        "sono configurato",
                    ],
                },
            ],
            "types": [],
        }
    }
}

MODELS = {"en-US": _EN_US_MODEL, "it-IT": _IT_IT_MODEL}


def get_model(locale: str) -> dict:
    return MODELS[locale]
