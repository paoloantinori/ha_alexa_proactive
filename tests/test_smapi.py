"""Unit tests for the SMAPI skill client (smapi.py)."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "alexa_proactive"


# ---------------------------------------------------------------------------
# Module loading helpers
# ---------------------------------------------------------------------------


def _register_package(pkg_name: str) -> None:
    """Register a dummy parent package in sys.modules so relative imports resolve."""
    if pkg_name in sys.modules:
        return
    pkg = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location(
            pkg_name, COMPONENT_DIR / "__init__.py", submodule_search_locations=[]
        )
    )
    pkg.__package__ = pkg_name
    pkg.__path__ = [str(COMPONENT_DIR)]
    sys.modules[pkg_name] = pkg


def _load_submodule(module_name: str, filename: str):
    """Load a submodule from COMPONENT_DIR without normal import machinery."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    _register_package("alexa_proactive")
    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT_DIR / filename, submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "alexa_proactive"
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_const():
    return _load_submodule("alexa_proactive.const", "const.py")


def _load_api():
    _load_const()
    return _load_submodule("alexa_proactive.api", "api.py")


def _load_smapi():
    _load_api()
    return _load_submodule("alexa_proactive.smapi", "smapi.py")


# ---------------------------------------------------------------------------
# Mock response / session helpers
# ---------------------------------------------------------------------------


def _make_mock_response(json_data, status=200):
    """Build a mock aiohttp response usable as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=str(json_data))
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_session(mock_response):
    """Build a mock aiohttp ClientSession whose .request() returns an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = MagicMock(return_value=ctx)
    session.closed = False
    return session


def _make_multi_response_session(*mock_responses):
    """Build a mock session that returns a different response for each request call."""
    contexts = []
    for resp in mock_responses:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        contexts.append(ctx)

    session = MagicMock()
    session.request = MagicMock(side_effect=contexts)
    session.closed = False
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def const():
    return _load_const()


@pytest.fixture(scope="module")
def smapi():
    return _load_smapi()


@pytest.fixture
def hass():
    return MagicMock()


@pytest.fixture
def lwa_client():
    client = AsyncMock()
    client.async_get_smapi_token = AsyncMock(return_value="test-token")
    return client


@pytest.fixture
def smtp_client(hass, lwa_client, smapi):
    return smapi.SMTPClient(hass=hass, lwa_client=lwa_client)


# ---------------------------------------------------------------------------
# Test: async_get_vendor_id
# ---------------------------------------------------------------------------


class TestGetVendorId:

    @pytest.mark.asyncio
    async def test_returns_first_vendor_id(self, smtp_client, const):
        mock_session = _make_mock_session(_make_mock_response({"vendors": [{"id": "VENDOR123"}]}))

        with patch.object(smtp_client, "_session", mock_session):
            result = await smtp_client.async_get_vendor_id()

        assert result == "VENDOR123"
        mock_session.request.assert_called_once()
        assert mock_session.request.call_args[0][0] == "GET"
        assert mock_session.request.call_args[0][1] == f"{const.SMAPI_BASE_URL}/v1/vendors"

    @pytest.mark.asyncio
    async def test_raises_when_no_vendors(self, smtp_client, ha_error):
        mock_session = _make_mock_session(_make_mock_response({"vendors": []}))

        with (
            patch.object(smtp_client, "_session", mock_session),
            pytest.raises(ha_error, match="No Amazon vendor account found"),
        ):
            await smtp_client.async_get_vendor_id()


# ---------------------------------------------------------------------------
# Test: async_create_skill
# ---------------------------------------------------------------------------


class TestCreateSkill:

    @pytest.mark.asyncio
    async def test_creates_skill_and_returns_id(self, smtp_client, const):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            result = await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://example.com/webhook",
                skill_name="Home Assistant",
            )

        assert result == "amzn1.ask.skill.123"
        assert session.request.call_args[0][0] == "POST"
        assert session.request.call_args[0][1] == f"{const.SMAPI_BASE_URL}/v1/skills"

    @pytest.mark.asyncio
    async def test_manifest_contains_webhook_url(self, smtp_client):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://example.com/webhook",
                skill_name="Home Assistant",
            )

        body = session.request.call_args[1].get("json") or session.request.call_args.kwargs.get("json")
        assert "https://example.com/webhook" in str(body)

    @pytest.mark.asyncio
    async def test_manifest_contains_notification_permission(self, smtp_client):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://example.com/webhook",
                skill_name="Home Assistant",
            )

        body = session.request.call_args[1].get("json") or session.request.call_args.kwargs.get("json")
        assert "alexa::devices:all:notifications:write" in str(body)

    @pytest.mark.asyncio
    async def test_manifest_contains_proactive_events(self, smtp_client, const):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://example.com/webhook",
                skill_name="Home Assistant",
            )

        body = session.request.call_args[1].get("json") or session.request.call_args.kwargs.get("json")
        body_str = str(body)
        assert const.EVENT_SCHEMA in body_str
        assert "SKILL_PROACTIVE_SUBSCRIPTION_CHANGED" in body_str


# ---------------------------------------------------------------------------
# Test: async_update_manifest
# ---------------------------------------------------------------------------


class TestUpdateManifest:

    @pytest.mark.asyncio
    async def test_updates_manifest_with_put(self, smtp_client, const):
        mock_session = _make_mock_session(_make_mock_response({"status": "SUCCESS"}))
        skill_id = "amzn1.ask.skill.456"

        with (
            patch.object(smtp_client, "_session", mock_session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            await smtp_client.async_update_manifest(
                skill_id=skill_id,
                webhook_url="https://example.com/webhook",
            )

        mock_session.request.assert_called_once()
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "PUT"
        expected_url = (
            f"{const.SMAPI_BASE_URL}/v1/skills/{skill_id}"
            "/stages/development/manifest"
        )
        assert call_args[0][1] == expected_url
        headers = call_args[1].get("headers", {})
        assert headers.get("If-Match") == "*"


# ---------------------------------------------------------------------------
# Test: async_upload_model
# ---------------------------------------------------------------------------


class TestUploadModel:

    @pytest.mark.asyncio
    async def test_uploads_model_to_locale(self, smtp_client, const):
        get_resp = _make_mock_response({"eTag": "etag-123"})
        put_resp = _make_mock_response({"status": "SUCCESS"})
        mock_session = _make_multi_response_session(get_resp, put_resp)
        skill_id = "amzn1.ask.skill.789"
        model = {"interactionModel": {"languageModel": {"intents": []}}}

        with patch.object(smtp_client, "_session", mock_session):
            await smtp_client.async_upload_model(
                skill_id=skill_id, locale="en-US", model=model
            )

        put_call = mock_session.request.call_args_list[-1]
        expected_url = (
            f"{const.SMAPI_BASE_URL}/v1/skills/{skill_id}"
            "/stages/development/interactionModel/locales/en-US"
        )
        assert put_call[0][1] == expected_url
        headers = put_call[1].get("headers", {})
        assert headers.get("If-Match") == "etag-123"

    @pytest.mark.asyncio
    async def test_uploads_without_etag_when_get_fails(self, smtp_client, const):
        get_resp = _make_mock_response({"error": "not found"}, status=404)
        put_resp = _make_mock_response({"status": "SUCCESS"})
        mock_session = _make_multi_response_session(get_resp, put_resp)
        skill_id = "amzn1.ask.skill.789"
        model = {"interactionModel": {"languageModel": {"intents": []}}}

        with patch.object(smtp_client, "_session", mock_session):
            await smtp_client.async_upload_model(
                skill_id=skill_id, locale="it-IT", model=model
            )

        put_call = mock_session.request.call_args_list[-1]
        expected_url = (
            f"{const.SMAPI_BASE_URL}/v1/skills/{skill_id}"
            "/stages/development/interactionModel/locales/it-IT"
        )
        assert put_call[0][1] == expected_url


# ---------------------------------------------------------------------------
# Test: async_enable_skill
# ---------------------------------------------------------------------------


class TestEnableSkill:

    @pytest.mark.asyncio
    async def test_enables_skill_in_development(self, smtp_client, const):
        mock_session = _make_mock_session(_make_mock_response({}))
        skill_id = "amzn1.ask.skill.999"

        with patch.object(smtp_client, "_session", mock_session):
            await smtp_client.async_enable_skill(skill_id=skill_id)

        call_args = mock_session.request.call_args
        assert call_args[0][0] == "PUT"
        expected_url = (
            f"{const.SMAPI_BASE_URL}/v1/skills/{skill_id}"
            "/stages/development/enablement"
        )
        assert call_args[0][1] == expected_url


# ---------------------------------------------------------------------------
# Test: async_setup_skill_complete
# ---------------------------------------------------------------------------


class TestSetupSkillComplete:

    @pytest.mark.asyncio
    async def test_full_setup_orchestrates_all_steps(self, smtp_client):
        webhook_url = "https://example.com/webhook"
        skill_id = "amzn1.ask.skill.111"
        vendor_id = "VENDOR123"
        models = {
            "en-US": {"interactionModel": {"languageModel": {"intents": []}}}
        }

        with (
            patch.object(
                smtp_client, "async_get_vendor_id",
                new_callable=AsyncMock, return_value=vendor_id,
            ) as mock_vendor,
            patch.object(
                smtp_client, "_async_find_existing_skill",
                new_callable=AsyncMock, return_value=None,
            ) as mock_find,
            patch.object(
                smtp_client, "_async_create_skill",
                new_callable=AsyncMock, return_value=skill_id,
            ) as mock_create,
            patch.object(
                smtp_client, "async_upload_model",
                new_callable=AsyncMock,
            ) as mock_upload,
            patch.object(
                smtp_client, "async_enable_skill",
                new_callable=AsyncMock,
            ) as mock_enable,
            patch.object(
                smtp_client, "_detect_ssl_type",
                new=AsyncMock(return_value="Trusted"),
            ),
            patch.object(
                smtp_client, "_async_request",
                new_callable=AsyncMock, return_value=None,
            ),
            patch.object(
                smtp_client, "async_wait_for_model_build",
                new_callable=AsyncMock, return_value=["en-US"],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await smtp_client.async_setup_skill_complete(
                webhook_url=webhook_url, models=models,
            )

        mock_vendor.assert_called_once()
        mock_find.assert_called_once_with(vendor_id, "Home Assistant")
        mock_create.assert_called_once_with(vendor_id, webhook_url, "Home Assistant", ["en-US"])
        mock_upload.assert_called_once()
        mock_enable.assert_called_once_with(skill_id)

        assert result == {
            "skill_id": skill_id,
            "vendor_id": vendor_id,
            "webhook_url": webhook_url,
            "build_succeeded": True,
        }

    @pytest.mark.asyncio
    async def test_setup_survives_build_timeout(self, smtp_client, ha_error):
        """A model-build timeout sets build_succeeded=False but still enables
        the skill (the config flow surfaces the manual-enable warning)."""
        webhook_url = "https://example.com/webhook"
        skill_id = "amzn1.ask.skill.222"
        models = {
            "en-US": {"interactionModel": {"languageModel": {"intents": []}}}
        }

        with (
            patch.object(
                smtp_client, "async_get_vendor_id",
                new_callable=AsyncMock, return_value="VENDOR789",
            ),
            patch.object(
                smtp_client, "_async_find_existing_skill",
                new_callable=AsyncMock, return_value=skill_id,
            ),
            patch.object(
                smtp_client, "async_upload_model",
                new_callable=AsyncMock,
            ),
            patch.object(
                smtp_client, "async_enable_skill",
                new_callable=AsyncMock,
            ) as mock_enable,
            patch.object(
                smtp_client, "_detect_ssl_type",
                new=AsyncMock(return_value="Trusted"),
            ),
            patch.object(
                smtp_client, "_async_request",
                new_callable=AsyncMock, return_value=None,
            ),
            patch.object(
                smtp_client, "async_wait_for_model_build",
                new_callable=AsyncMock,
                side_effect=ha_error("Model build timed out after 180s"),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await smtp_client.async_setup_skill_complete(
                webhook_url=webhook_url, models=models,
            )

        mock_enable.assert_called_once_with(skill_id)
        assert result["skill_id"] == skill_id
        assert result["build_succeeded"] is False

    @pytest.mark.asyncio
    async def test_setup_falls_back_on_conflict(self, smtp_client, ha_error):
        webhook_url = "https://example.com/webhook"
        vendor_id = "VENDOR456"
        models = {
            "en-US": {"interactionModel": {"languageModel": {"intents": []}}}
        }

        conflict_error = ha_error("Conflict (409): skill already exists")

        with (
            patch.object(
                smtp_client, "async_get_vendor_id",
                new_callable=AsyncMock, return_value=vendor_id,
            ),
            patch.object(
                smtp_client, "_async_find_existing_skill",
                new_callable=AsyncMock, return_value=None,
            ),
            patch.object(
                smtp_client, "_async_create_skill",
                new_callable=AsyncMock, side_effect=conflict_error,
            ) as mock_create,
            patch.object(
                smtp_client, "_async_resolve_conflict",
                new_callable=AsyncMock, return_value="amzn1.ask.skill.conflict",
            ) as mock_resolve,
            patch.object(
                smtp_client, "async_upload_model",
                new_callable=AsyncMock,
            ),
            patch.object(
                smtp_client, "async_enable_skill",
                new_callable=AsyncMock,
            ),
            patch.object(
                smtp_client, "_detect_ssl_type",
                new=AsyncMock(return_value="Trusted"),
            ),
            patch.object(
                smtp_client, "_async_request",
                new_callable=AsyncMock, return_value=None,
            ),
            patch.object(
                smtp_client, "async_wait_for_model_build",
                new_callable=AsyncMock, return_value=["en-US"],
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await smtp_client.async_setup_skill_complete(
                webhook_url=webhook_url, models=models,
            )

        mock_create.assert_called_once()
        mock_resolve.assert_called_once_with(vendor_id, webhook_url, "Home Assistant")
        assert result["skill_id"] == "amzn1.ask.skill.conflict"
        assert result["build_succeeded"] is True


# ---------------------------------------------------------------------------
# Test: async_get_skill_status
# ---------------------------------------------------------------------------


class TestGetSkillStatus:

    @pytest.mark.asyncio
    async def test_returns_skill_status_data(self, smtp_client, const):
        status_data = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "SUCCEEDED"}},
                }
            }
        }
        mock_session = _make_mock_session(_make_mock_response(status_data))

        with patch.object(smtp_client, "_session", mock_session):
            result = await smtp_client.async_get_skill_status("amzn1.ask.skill.123")

        assert result == status_data
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "GET"
        assert "/v1/skills/amzn1.ask.skill.123/status" in call_args[0][1]


# ---------------------------------------------------------------------------
# Test: async_wait_for_model_build
# ---------------------------------------------------------------------------


class TestWaitForModelBuild:

    @pytest.mark.asyncio
    async def test_returns_succeeded_locales_immediately(self, smtp_client):
        status = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "SUCCEEDED"}},
                    "it-IT": {"lastUpdateRequest": {"status": "IN_PROGRESS"}},
                }
            }
        }
        with patch.object(
            smtp_client, "async_get_skill_status",
            new_callable=AsyncMock, return_value=status,
        ):
            result = await smtp_client.async_wait_for_model_build(
                "skill1", ["en-US", "it-IT"], timeout=5, poll_interval=0.1,
            )
        assert result == ["en-US"]

    @pytest.mark.asyncio
    async def test_polls_until_success(self, smtp_client):
        in_progress = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "IN_PROGRESS"}},
                }
            }
        }
        succeeded = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "SUCCEEDED"}},
                }
            }
        }
        with patch.object(
            smtp_client, "async_get_skill_status",
            new_callable=AsyncMock, side_effect=[in_progress, succeeded],
        ):
            result = await smtp_client.async_wait_for_model_build(
                "skill1", ["en-US"], timeout=30, poll_interval=0.1,
            )
        assert result == ["en-US"]

    @pytest.mark.asyncio
    async def test_raises_when_all_fail(self, smtp_client, ha_error):
        status = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "FAILED", "errors": [{"message": "bad model"}]}},
                }
            }
        }
        with patch.object(
            smtp_client, "async_get_skill_status",
            new_callable=AsyncMock, return_value=status,
        ):
            with pytest.raises(ha_error, match="no locales reached SUCCEEDED"):
                await smtp_client.async_wait_for_model_build(
                    "skill1", ["en-US"], timeout=5, poll_interval=0.1,
                )

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, smtp_client, ha_error):
        in_progress = {
            "interactionModel": {
                "locales": {
                    "en-US": {"lastUpdateRequest": {"status": "IN_PROGRESS"}},
                }
            }
        }
        with patch.object(
            smtp_client, "async_get_skill_status",
            new_callable=AsyncMock, return_value=in_progress,
        ):
            with pytest.raises(ha_error, match="timed out"):
                await smtp_client.async_wait_for_model_build(
                    "skill1", ["en-US"], timeout=0.3, poll_interval=0.1,
                )


# ---------------------------------------------------------------------------
# Test: error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_unauthorized_raises_error(self, smtp_client, ha_error):
        mock_resp = _make_mock_response({"error": "unauthorized"}, status=401)
        mock_session = _make_mock_session(mock_resp)

        with (
            patch.object(smtp_client, "_session", mock_session),
            pytest.raises(ha_error, match="Invalid LWA credentials"),
        ):
            await smtp_client.async_get_vendor_id()

    @pytest.mark.asyncio
    async def test_network_error_raises_error(self, smtp_client, ha_error):
        import aiohttp

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.request = MagicMock(return_value=ctx)
        session.closed = False

        with (
            patch.object(smtp_client, "_session", session),
            pytest.raises(ha_error, match="SMAPI request failed"),
        ):
            await smtp_client.async_get_vendor_id()


# ---------------------------------------------------------------------------
# Test: _detect_ssl_type
# ---------------------------------------------------------------------------


class TestDetectSslType:

    @pytest.mark.asyncio
    async def test_returns_wildcard_for_wildcard_san(self, smtp_client):
        smtp_client._hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        with patch("ssl.create_default_context") as mock_ctx:
            mock_sock = MagicMock()
            mock_ssock = MagicMock()
            mock_ssock.getpeercert.return_value = {
                "subjectAltName": (("DNS", "*.example.com"), ("DNS", "example.com")),
            }
            mock_ctx.return_value.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssock)
            mock_ctx.return_value.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx.return_value)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("socket.create_connection") as mock_conn:
                mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
                mock_conn.return_value.__exit__ = MagicMock(return_value=False)
                result = await smtp_client._detect_ssl_type("https://test.example.com/api")
        assert result == "Wildcard"

    @pytest.mark.asyncio
    async def test_returns_trusted_for_non_wildcard(self, smtp_client):
        smtp_client._hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        with patch("ssl.create_default_context") as mock_ctx:
            mock_sock = MagicMock()
            mock_ssock = MagicMock()
            mock_ssock.getpeercert.return_value = {
                "subjectAltName": (("DNS", "test.example.com"),),
            }
            mock_ctx.return_value.wrap_socket.return_value.__enter__ = MagicMock(return_value=mock_ssock)
            mock_ctx.return_value.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx.return_value)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("socket.create_connection") as mock_conn:
                mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
                mock_conn.return_value.__exit__ = MagicMock(return_value=False)
                result = await smtp_client._detect_ssl_type("https://test.example.com/api")
        assert result == "Trusted"

    @pytest.mark.asyncio
    async def test_returns_trusted_on_connection_error(self, smtp_client):
        smtp_client._hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        with patch("socket.create_connection", side_effect=OSError("connection refused")):
            result = await smtp_client._detect_ssl_type("https://unreachable.example.com/api")
        assert result == "Trusted"

    @pytest.mark.asyncio
    async def test_returns_trusted_for_no_hostname(self, smtp_client):
        smtp_client._hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        result = await smtp_client._detect_ssl_type("no-host")
        assert result == "Trusted"


# ---------------------------------------------------------------------------
# Test: manifest per-region endpoints
# ---------------------------------------------------------------------------


class TestManifestRegions:

    @pytest.mark.asyncio
    async def test_apis_custom_has_per_region_endpoints(self, smtp_client):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Trusted")),
        ):
            await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://example.com/webhook",
                skill_name="Home Assistant",
            )

        body = session.request.call_args[1].get("json") or session.request.call_args.kwargs.get("json")
        custom = body["manifest"]["apis"]["custom"]
        assert "regions" in custom
        assert "EU" in custom["regions"]
        assert "NA" in custom["regions"]
        assert "FE" in custom["regions"]
        assert custom["regions"]["EU"]["endpoint"]["uri"] == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_manifest_uses_wildcard_ssl_type(self, smtp_client):
        skill_resp = _make_mock_response({"skillId": "amzn1.ask.skill.123"})
        session = _make_mock_session(skill_resp)

        with (
            patch.object(smtp_client, "_session", session),
            patch.object(smtp_client, "_detect_ssl_type", new=AsyncMock(return_value="Wildcard")),
        ):
            await smtp_client._async_create_skill(
                vendor_id="VENDOR123",
                webhook_url="https://wild.example.com/webhook",
                skill_name="Home Assistant",
            )

        body = session.request.call_args[1].get("json") or session.request.call_args.kwargs.get("json")
        custom = body["manifest"]["apis"]["custom"]
        assert custom["endpoint"]["sslCertificateType"] == "Wildcard"
        assert custom["regions"]["EU"]["endpoint"]["sslCertificateType"] == "Wildcard"
        events = body["manifest"]["events"]
        assert events["endpoint"]["sslCertificateType"] == "Wildcard"
        assert events["regions"]["NA"]["endpoint"]["sslCertificateType"] == "Wildcard"


# ---------------------------------------------------------------------------
# Test: async_upload_models (options-flow rename)
# ---------------------------------------------------------------------------


class TestUploadModels:

    @pytest.mark.asyncio
    async def test_uploads_model_for_each_locale(self, smtp_client):
        with (
            patch.object(
                smtp_client, "async_upload_model",
                new_callable=AsyncMock,
            ) as mock_upload,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            uploaded = await smtp_client.async_upload_models(
                "amzn1.ask.skill.123", "notify me", ["en-US", "it-IT"]
            )

        assert uploaded == ["en-US", "it-IT"]
        assert mock_upload.await_count == 2
        locales = [c.kwargs["locale"] for c in mock_upload.await_args_list]
        assert locales == ["en-US", "it-IT"]
        for call in mock_upload.await_args_list:
            assert call.kwargs["model"]["interactionModel"]["languageModel"]["invocationName"] == "notify me"

    @pytest.mark.asyncio
    async def test_retries_then_reports_partial_failure(self, smtp_client, ha_error):
        upload = AsyncMock(
            side_effect=[ha_error("boom"), None, ha_error("boom"), ha_error("boom"), ha_error("boom")]
        )
        with (
            patch.object(smtp_client, "async_upload_model", new=upload),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            uploaded = await smtp_client.async_upload_models(
                "amzn1.ask.skill.123", "notify me", ["en-US", "it-IT"]
            )

        # en-US: fail once then succeed (2 calls); it-IT: exhausts 3 attempts.
        assert uploaded == ["en-US"]
        assert upload.await_count == 5
