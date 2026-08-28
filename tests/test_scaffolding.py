"""Tests for the Alexa Proactive Events integration scaffolding."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


def _load_const():
    spec = importlib.util.spec_from_file_location("const", COMPONENT_DIR / "const.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def const():
    return _load_const()


@pytest.fixture(scope="module")
def manifest_data():
    return json.loads((COMPONENT_DIR / "manifest.json").read_text())


@pytest.fixture(scope="module")
def strings_data():
    return json.loads((COMPONENT_DIR / "strings.json").read_text())


class TestManifest:
    """Tests for manifest.json."""

    def test_manifest_is_valid_json(self, manifest_data):
        assert isinstance(manifest_data, dict)

    def test_manifest_has_required_fields(self, manifest_data, const):
        assert manifest_data["domain"] == const.DOMAIN
        assert manifest_data["name"] == "Alexa Proactive Events"
        assert manifest_data["config_flow"] is True
        assert manifest_data["integration_type"] == "service"
        assert manifest_data["iot_class"] == "cloud_push"
        # Drift-proof: validate the format instead of pinning a version that
        # goes stale on every bump.
        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest_data["version"])
        assert "@pantinor" in manifest_data["codeowners"]

    def test_manifest_requirements_is_list(self, manifest_data):
        assert isinstance(manifest_data["requirements"], list)


class TestConstants:
    """Tests for const.py."""

    def test_domain(self, const):
        assert const.DOMAIN == "alexa_proactive"

    def test_lwa_urls(self, const):
        assert "api.amazon.com" in const.LWA_TOKEN_URL

    def test_region_endpoints(self, const):
        assert set(const.PROACTIVE_API_URLS.keys()) == {"na", "eu", "fe"}
        assert "amazonalexa.com" in const.PROACTIVE_API_URLS["eu"]

    def test_scopes(self, const):
        assert "skills:readwrite" in const.SCOPE_SMAPI
        assert "models:readwrite" in const.SCOPE_SMAPI

    def test_config_keys(self, const):
        assert const.CONF_CLIENT_ID == "client_id"
        assert const.CONF_CLIENT_SECRET == "client_secret"
        assert const.CONF_REGION == "region"

    def test_event_schema(self, const):
        assert const.EVENT_SCHEMA == "AMAZON.MessageAlert.Activated"

    def test_defaults(self, const):
        assert const.DEFAULT_REGION == "eu"
        assert const.DEFAULT_SENDER == "Home Assistant"
        assert const.DEFAULT_COUNT == 1


class TestStringsJson:
    """Tests for strings.json."""

    def test_strings_is_valid_json(self, strings_data):
        assert isinstance(strings_data, dict)

    def test_config_flow_steps(self, strings_data):
        steps = strings_data["config"]["step"]
        assert "user" in steps
        assert "setup" in steps
        assert "finish" in steps

    def test_error_messages(self, strings_data):
        errors = strings_data["config"]["error"]
        assert "invalid_auth" in errors
        assert "cannot_connect" in errors
        assert "smapi_error" in errors

    def test_user_step_fields(self, strings_data, const):
        fields = strings_data["config"]["step"]["user"]["data"]
        assert const.CONF_CLIENT_ID in fields
        assert const.CONF_CLIENT_SECRET in fields
        assert const.CONF_REGION in fields


class TestServicesYaml:
    """Tests for services.yaml."""

    def test_services_yaml_exists(self):
        assert (COMPONENT_DIR / "services.yaml").exists()

    def test_services_yaml_has_send(self):
        content = (COMPONENT_DIR / "services.yaml").read_text()
        assert "send:" in content
        assert "sender" in content
        assert "count" in content


class TestInitPy:
    """Tests for __init__.py."""

    def test_init_exists(self):
        assert (COMPONENT_DIR / "__init__.py").exists()

    def test_init_has_required_functions(self):
        content = (COMPONENT_DIR / "__init__.py").read_text()
        assert "async_setup(" in content
        assert "async_setup_entry(" in content
        assert "async_unload_entry(" in content


class TestConfigFlowPy:
    """Tests for config_flow.py."""

    def test_config_flow_exists(self):
        assert (COMPONENT_DIR / "config_flow.py").exists()

    def test_config_flow_class_defined(self):
        content = (COMPONENT_DIR / "config_flow.py").read_text()
        assert "AlexaProactiveConfigFlow" in content
        assert "async_step_user" in content
        assert "ConfigFlow" in content
