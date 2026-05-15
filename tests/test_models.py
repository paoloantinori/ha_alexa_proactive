"""Unit tests for the interaction model templates (models.py)."""

import importlib.util
import sys
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


def _load_models():
    pkg_name = "alexa_proactive"
    if pkg_name not in sys.modules:
        pkg = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location(
                pkg_name, COMPONENT_DIR / "__init__.py", submodule_search_locations=[]
            )
        )
        pkg.__package__ = pkg_name
        pkg.__path__ = [str(COMPONENT_DIR)]
        sys.modules[pkg_name] = pkg

    module_name = "alexa_proactive.models"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT_DIR / "models.py", submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _intent_names(model):
    return [i["name"] for i in model["interactionModel"]["languageModel"]["intents"]]


@pytest.fixture(scope="module")
def models():
    return _load_models()


@pytest.fixture(scope="module")
def en_us(models):
    return models.MODELS["en-US"]


@pytest.fixture(scope="module")
def it_it(models):
    return models.MODELS["it-IT"]


# ---------------------------------------------------------------------------
# Test: SUPPORTED_LOCALES
# ---------------------------------------------------------------------------


class TestSupportedLocales:

    def test_contains_en_us(self, models):
        assert "en-US" in models.SUPPORTED_LOCALES

    def test_contains_it_it(self, models):
        assert "it-IT" in models.SUPPORTED_LOCALES

    def test_has_17_locales(self, models):
        assert len(models.SUPPORTED_LOCALES) == 17


# ---------------------------------------------------------------------------
# Test: MODELS dict
# ---------------------------------------------------------------------------


class TestModelsDict:

    def test_has_all_supported_locales(self, models):
        assert set(models.MODELS.keys()) == set(models.SUPPORTED_LOCALES)

    def test_values_are_dicts(self, models):
        for locale_model in models.MODELS.values():
            assert isinstance(locale_model, dict)
            assert "interactionModel" in locale_model

    def test_all_locales_have_send_and_check_intents(self, models):
        for locale, model in models.MODELS.items():
            names = _intent_names(model)
            assert "SendNotificationIntent" in names, f"{locale} missing SendNotificationIntent"
            assert "CheckStatusIntent" in names, f"{locale} missing CheckStatusIntent"
            send = next(i for i in model["interactionModel"]["languageModel"]["intents"] if i["name"] == "SendNotificationIntent")
            check = next(i for i in model["interactionModel"]["languageModel"]["intents"] if i["name"] == "CheckStatusIntent")
            assert len(send["samples"]) > 0, f"{locale} has empty send samples"
            assert len(check["samples"]) > 0, f"{locale} has empty check samples"


# ---------------------------------------------------------------------------
# Test: en-US model
# ---------------------------------------------------------------------------


class TestEnUSModel:

    def test_invocation_name(self, en_us):
        assert en_us["interactionModel"]["languageModel"]["invocationName"] == "ping me"

    def test_has_send_notification_intent(self, en_us):
        names = _intent_names(en_us)
        assert "SendNotificationIntent" in names
        intent = next(i for i in en_us["interactionModel"]["languageModel"]["intents"] if i["name"] == "SendNotificationIntent")
        assert len(intent["samples"]) > 0

    def test_has_check_status_intent(self, en_us):
        names = _intent_names(en_us)
        assert "CheckStatusIntent" in names
        intent = next(i for i in en_us["interactionModel"]["languageModel"]["intents"] if i["name"] == "CheckStatusIntent")
        assert len(intent["samples"]) > 0

    def test_has_builtin_intents(self, en_us):
        names = _intent_names(en_us)
        for builtin in ["AMAZON.NavigateHomeIntent", "AMAZON.HelpIntent", "AMAZON.CancelIntent", "AMAZON.StopIntent"]:
            assert builtin in names

    def test_intent_names_are_unique(self, en_us):
        names = _intent_names(en_us)
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Test: it-IT model
# ---------------------------------------------------------------------------


class TestItITModel:

    def test_invocation_name(self, it_it):
        assert it_it["interactionModel"]["languageModel"]["invocationName"] == "manda avviso"

    def test_has_send_notification_intent_with_italian_samples(self, it_it):
        names = _intent_names(it_it)
        assert "SendNotificationIntent" in names
        intent = next(i for i in it_it["interactionModel"]["languageModel"]["intents"] if i["name"] == "SendNotificationIntent")
        assert "invia una notifica" in intent["samples"]

    def test_has_check_status_intent_with_italian_samples(self, it_it):
        names = _intent_names(it_it)
        assert "CheckStatusIntent" in names
        intent = next(i for i in it_it["interactionModel"]["languageModel"]["intents"] if i["name"] == "CheckStatusIntent")
        assert "controlla il mio stato" in intent["samples"]

    def test_has_builtin_intents(self, it_it):
        names = _intent_names(it_it)
        for builtin in ["AMAZON.NavigateHomeIntent", "AMAZON.HelpIntent", "AMAZON.CancelIntent", "AMAZON.StopIntent"]:
            assert builtin in names

    def test_intent_names_are_unique(self, it_it):
        names = _intent_names(it_it)
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Test: get_model()
# ---------------------------------------------------------------------------


class TestGetModel:

    def test_returns_en_us_with_default_invocation(self, models, en_us):
        result = models.get_model("en-US")
        assert result["interactionModel"]["languageModel"]["invocationName"] == "ping me"

    def test_returns_it_it_with_default_invocation(self, models, it_it):
        result = models.get_model("it-IT")
        assert result["interactionModel"]["languageModel"]["invocationName"] == "manda avviso"

    def test_custom_invocation_name_en_us(self, models):
        result = models.get_model("en-US", invocation_name="notify me")
        assert result["interactionModel"]["languageModel"]["invocationName"] == "notify me"

    def test_custom_invocation_name_it_it(self, models):
        result = models.get_model("it-IT", invocation_name="notificami")
        assert result["interactionModel"]["languageModel"]["invocationName"] == "notificami"

    def test_does_not_mutate_template(self, models):
        original = models.MODELS["en-US"]["interactionModel"]["languageModel"]["invocationName"]
        models.get_model("en-US", invocation_name="custom name")
        assert models.MODELS["en-US"]["interactionModel"]["languageModel"]["invocationName"] == original

    def test_raises_on_unknown_locale(self, models):
        with pytest.raises(KeyError):
            models.get_model("xx-XX")
