"""Unit tests for BrainstemClient.

All HTTP calls are intercepted with pytest-mock / unittest.mock so no
network access is required.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from brainstem_api_tools.brainstem_api_client import (
    BrainstemClient,
    AuthenticationError,
    _MODEL_TO_APP,
    _resolve_model,
    _resolve_portal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOKEN = "test-token-abc123"


def make_client(token=TOKEN):
    """Return a BrainstemClient with a pre-set token (no auth flow)."""
    return BrainstemClient(token=token)


def mock_response(status_code=200, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_body or {}
    return resp


# ---------------------------------------------------------------------------
# _resolve_model / _resolve_portal
# ---------------------------------------------------------------------------

class TestResolvers:
    def test_resolve_model_string(self):
        assert _resolve_model("session") == "session"

    def test_resolve_model_invalid(self):
        with pytest.raises(ValueError, match="Unknown model 'foobar'"):
            _resolve_model("foobar")

    def test_resolve_portal_string(self):
        assert _resolve_portal("public") == "public"

    def test_resolve_portal_invalid(self):
        with pytest.raises(ValueError, match="Unknown portal 'nope'"):
            _resolve_portal("nope")


# ---------------------------------------------------------------------------
# BrainstemClient construction
# ---------------------------------------------------------------------------

class TestClientInit:
    def test_token_set_directly(self):
        client = make_client()
        assert client._token == TOKEN

    def test_auth_header_on_session(self):
        client = make_client()
        assert client._session.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_cached_token_used_on_init(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token"
        token_file.write_text("cached-token")
        monkeypatch.setattr(
            "brainstem_api_tools.brainstem_api_client._TOKEN_FILE", token_file
        )
        client = BrainstemClient()
        assert client._token == "cached-token"

    def test_device_flow_triggered_when_no_cache(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token"  # does not exist
        monkeypatch.setattr(
            "brainstem_api_tools.brainstem_api_client._TOKEN_FILE", token_file
        )
        with patch.object(BrainstemClient, "_device_auth_flow", return_value="new-token") as mock_flow, \
             patch.object(BrainstemClient, "_save_token") as mock_save:
            client = BrainstemClient()
            mock_flow.assert_called_once()
            mock_save.assert_called_once_with("new-token")
            assert client._token == "new-token"


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------

class TestLoad:
    def setup_method(self):
        self.client = make_client()

    def _mock_get(self, json_body=None, status=200):
        resp = mock_response(status, json_body)
        self.client._session.get = MagicMock(return_value=resp)
        return resp

    def test_load_all_sessions(self):
        self._mock_get({"sessions": []})
        self.client.load("session")
        self.client._session.get.assert_called_once()
        url = self.client._session.get.call_args[0][0]
        assert "stem/session/" in url

    def test_load_with_id(self):
        uid = "00000000-0000-0000-0000-000000000001"
        self._mock_get({"session": {}})
        self.client.load("session", id=uid)
        url = self.client._session.get.call_args[0][0]
        assert uid in url

    def test_load_filters_built_correctly(self):
        self._mock_get()
        self.client.load("session", filters={"name.icontains": "rat"})
        params = self.client._session.get.call_args[1]["params"]
        assert params["filter{name.icontains}"] == "rat"

    def test_load_sort_built_correctly(self):
        self._mock_get()
        self.client.load("session", sort=["-name", "date"])
        params = self.client._session.get.call_args[1]["params"]
        assert params["sort[]"] == ["-name", "date"]

    def test_load_include_appends_wildcard(self):
        self._mock_get()
        self.client.load("session", include=["behaviors"])
        params = self.client._session.get.call_args[1]["params"]
        assert params["include[]"] == ["behaviors.*"]

    def test_load_pagination_params(self):
        self._mock_get()
        self.client.load("session", limit=50, offset=20)
        params = self.client._session.get.call_args[1]["params"]
        assert params["limit"] == 50
        assert params["offset"] == 20

    def test_load_public_portal(self):
        self._mock_get()
        self.client.load("project", portal="public")
        url = self.client._session.get.call_args[0][0]
        assert "/public/" in url

    def test_load_invalid_model_raises(self):
        with pytest.raises(ValueError, match="Unknown model"):
            self.client.load("notamodel")

    def test_load_invalid_portal_raises(self):
        with pytest.raises(ValueError, match="Unknown portal"):
            self.client.load("session", portal="badportal")

    def test_model_to_app_routing(self):
        """Spot-check a few app assignments."""
        cases = [
            ("session", "stem"),
            ("breeding", "stem"),
            ("project_membership_invitation", "stem"),
            ("procedure", "modules"),
            ("behavioralassay", "personal_attributes"),
            ("license", "personal_attributes"),
            ("setup", "personal_attributes"),
            ("consumable", "resources"),
            ("behavioralparadigm", "taxonomies"),
            ("behavioralcategory", "taxonomies"),
            ("regulatoryauthority", "taxonomies"),
            ("brainregion", "taxonomies"),
            ("publication", "dissemination"),
            ("laboratory", "users"),
            ("group_membership_invitation", "users"),
            ("group_membership_request", "users"),
        ]
        for model, expected_app in cases:
            self._mock_get()
            self.client.load(model)
            url = self.client._session.get.call_args[0][0]
            assert f"/{expected_app}/{model}/" in url, (
                f"Expected app '{expected_app}' for model '{model}', got URL: {url}"
            )


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

class TestSave:
    def setup_method(self):
        self.client = make_client()

    def test_create_uses_post(self):
        self.client._session.post = MagicMock(return_value=mock_response(201))
        self.client.save("session", data={"name": "x", "projects": ["uuid"]})
        self.client._session.post.assert_called_once()

    def test_update_uses_patch(self):
        uid = "00000000-0000-0000-0000-000000000002"
        self.client._session.patch = MagicMock(return_value=mock_response(200))
        self.client.save("session", id=uid, data={"description": "updated"})
        self.client._session.patch.assert_called_once()
        url = self.client._session.patch.call_args[0][0]
        assert uid in url

    def test_save_invalid_model_raises(self):
        with pytest.raises(ValueError):
            self.client.save("ghost")


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def setup_method(self):
        self.client = make_client()

    def test_delete_sends_correct_url(self):
        uid = "00000000-0000-0000-0000-000000000003"
        self.client._session.delete = MagicMock(return_value=mock_response(204))
        self.client.delete("session", id=uid)
        url = self.client._session.delete.call_args[0][0]
        assert uid in url
        assert "stem/session/" in url

    def test_delete_without_id_raises(self):
        with pytest.raises(ValueError, match="'id' is required"):
            self.client.delete("session")

    def test_delete_invalid_model_raises(self):
        with pytest.raises(ValueError):
            self.client.delete("ghost", id="some-uuid")


# ---------------------------------------------------------------------------
# Device auth flow
# ---------------------------------------------------------------------------

class TestDeviceAuthFlow:
    def test_success_flow(self):
        client = make_client()  # skip auth

        device_resp = MagicMock()
        device_resp.raise_for_status = MagicMock()
        device_resp.json.return_value = {
            "device_code": "dev123",
            "user_code": "ABC-DEF",
            "verification_uri": "https://brainstem.org/activate",
            "verification_uri_complete": "https://brainstem.org/activate?code=ABC-DEF",
            "interval": 0,
        }

        pending_resp = MagicMock()
        pending_resp.raise_for_status = MagicMock()
        pending_resp.json.return_value = {"status": "authorization_pending"}

        success_resp = MagicMock()
        success_resp.raise_for_status = MagicMock()
        success_resp.json.return_value = {"status": "success", "token": "new-jwt"}

        with patch("requests.post", side_effect=[device_resp, pending_resp, success_resp]), \
             patch("webbrowser.open"):
            token = client._device_auth_flow()

        assert token == "new-jwt"

    def test_access_denied_raises(self):
        client = make_client()

        device_resp = MagicMock()
        device_resp.raise_for_status = MagicMock()
        device_resp.json.return_value = {
            "device_code": "dev123",
            "user_code": "XYZ",
            "verification_uri": "https://brainstem.org/activate",
            "verification_uri_complete": "https://brainstem.org/activate?code=XYZ",
            "interval": 0,
        }
        denied_resp = MagicMock()
        denied_resp.raise_for_status = MagicMock()
        denied_resp.json.return_value = {"error": "access_denied"}

        with patch("requests.post", side_effect=[device_resp, denied_resp]), \
             patch("webbrowser.open"):
            with pytest.raises(AuthenticationError, match="Authorization failed"):
                client._device_auth_flow()


# ---------------------------------------------------------------------------
# load_all auto-pagination
# ---------------------------------------------------------------------------

class TestLoadAll:
    def setup_method(self):
        self.client = make_client()

    def _mock_pages(self, pages):
        responses = []
        for page in pages:
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.json.return_value = page
            responses.append(r)
        self.client._session.get = MagicMock(side_effect=responses)

    def test_single_page(self):
        self._mock_pages([
            {"sessions": [{"id": "1"}, {"id": "2"}], "count": 2},
        ])
        result = self.client.load("session", load_all=True)
        assert isinstance(result, dict)
        assert len(result["sessions"]) == 2

    def test_two_pages_merged(self):
        self._mock_pages([
            {"sessions": [{"id": "1"}, {"id": "2"}], "count": 3},
            {"sessions": [{"id": "3"}],               "count": 3},
        ])
        result = self.client.load("session", load_all=True)
        assert len(result["sessions"]) == 3
        assert [r["id"] for r in result["sessions"]] == ["1", "2", "3"]

    def test_load_all_false_returns_response(self):
        r = MagicMock()
        self.client._session.get = MagicMock(return_value=r)
        result = self.client.load("session", load_all=False)
        assert result is r


# ---------------------------------------------------------------------------
# Convenience loaders
# ---------------------------------------------------------------------------

class TestConvenienceLoaders:
    def setup_method(self):
        self.client = make_client()
        self.client._session.get = MagicMock(return_value=mock_response(200, {}))

    def _get_params(self):
        return self.client._session.get.call_args[1].get("params", {})

    def test_load_project_default_include(self):
        self.client.load_project()
        params = self._get_params()
        assert set(params["include[]"]) == {
            "sessions.*", "subjects.*", "collections.*", "cohorts.*"
        }

    def test_load_project_name_filter(self):
        self.client.load_project(name="Allen")
        params = self._get_params()
        assert params["filter{name.icontains}"] == "Allen"

    def test_load_subject_default_include(self):
        self.client.load_subject()
        params = self._get_params()
        assert set(params["include[]"]) == {"procedures.*", "subjectlogs.*"}

    def test_load_subject_sex_filter(self):
        self.client.load_subject(sex="M")
        assert self._get_params()["filter{sex}"] == "M"

    def test_load_subject_strain_filter(self):
        uuid = "aaaaaaaa-0000-0000-0000-000000000000"
        self.client.load_subject(strain=uuid)
        assert self._get_params()["filter{strain.id}"] == uuid

    def test_load_session_default_include(self):
        self.client.load_session()
        params = self._get_params()
        assert set(params["include[]"]) == {
            "dataacquisition.*", "behaviors.*", "manipulations.*", "epochs.*"
        }

    def test_load_session_project_filter(self):
        uuid = "bbbbbbbb-0000-0000-0000-000000000000"
        self.client.load_session(projects=uuid)
        assert self._get_params()["filter{projects.id}"] == uuid

    def test_load_collection_default_include(self):
        self.client.load_collection()
        assert self._get_params()["include[]"] == ["sessions.*"]

    def test_load_cohort_default_include(self):
        self.client.load_cohort()
        assert self._get_params()["include[]"] == ["subjects.*"]

    def test_load_behavior_session_filter(self):
        uuid = "cccccccc-0000-0000-0000-000000000000"
        self.client.load_behavior(session=uuid)
        assert self._get_params()["filter{session.id}"] == uuid

    def test_load_dataacquisition_session_filter(self):
        uuid = "dddddddd-0000-0000-0000-000000000000"
        self.client.load_dataacquisition(session=uuid)
        assert self._get_params()["filter{session.id}"] == uuid

    def test_load_manipulation_session_filter(self):
        uuid = "eeeeeeee-0000-0000-0000-000000000000"
        self.client.load_manipulation(session=uuid)
        assert self._get_params()["filter{session.id}"] == uuid

    def test_load_procedure_subject_filter(self):
        uuid = "ffffffff-0000-0000-0000-000000000000"
        self.client.load_procedure(subject=uuid)
        assert self._get_params()["filter{subject.id}"] == uuid

    def test_custom_include_overrides_default(self):
        self.client.load_session(include=["behaviors"])
        assert self._get_params()["include[]"] == ["behaviors.*"]

    def test_extra_filters_merged_with_field_kwargs(self):
        self.client.load_session(
            name="Rat",
            filters={"description.icontains": "hippocampus"},
        )
        params = self._get_params()
        assert params["filter{name.icontains}"] == "Rat"
        assert params["filter{description.icontains}"] == "hippocampus"


# ---------------------------------------------------------------------------
# CLI logout
# ---------------------------------------------------------------------------

class TestCLILogout:
    def test_logout_removes_token_file(self, tmp_path, capsys):
        import brainstem_api_tools.cli as cli_module
        token_file = tmp_path / "token"
        token_file.write_text("mytoken")

        with patch.object(cli_module, "_TOKEN_FILE", token_file), \
             patch("sys.argv", ["brainstem", "logout"]):
            cli_module.main()

        assert not token_file.exists()
        assert "Logged out" in capsys.readouterr().out

    def test_logout_no_token_file(self, tmp_path, capsys):
        import brainstem_api_tools.cli as cli_module
        token_file = tmp_path / "token"  # does not exist

        with patch.object(cli_module, "_TOKEN_FILE", token_file), \
             patch("sys.argv", ["brainstem", "logout"]):
            cli_module.main()

        assert "No cached token found" in capsys.readouterr().out
