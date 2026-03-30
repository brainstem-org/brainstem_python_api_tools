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


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

class TestTimeouts:
    def setup_method(self):
        self.client = make_client()

    def test_load_passes_timeout(self):
        self.client._session.get = MagicMock(return_value=mock_response(200, {}))
        self.client.load("session")
        _, kwargs = self.client._session.get.call_args
        assert kwargs.get("timeout") == BrainstemClient.DEFAULT_TIMEOUT

    def test_save_post_passes_timeout(self):
        self.client._session.post = MagicMock(return_value=mock_response(201))
        self.client.save("session", data={"name": "x"})
        _, kwargs = self.client._session.post.call_args
        assert kwargs.get("timeout") == BrainstemClient.DEFAULT_TIMEOUT

    def test_save_patch_passes_timeout(self):
        uid = "00000000-0000-0000-0000-000000000010"
        self.client._session.patch = MagicMock(return_value=mock_response(200))
        self.client.save("session", id=uid, data={"description": "x"})
        _, kwargs = self.client._session.patch.call_args
        assert kwargs.get("timeout") == BrainstemClient.DEFAULT_TIMEOUT

    def test_delete_passes_timeout(self):
        uid = "00000000-0000-0000-0000-000000000011"
        self.client._session.delete = MagicMock(return_value=mock_response(204))
        self.client.delete("session", id=uid)
        _, kwargs = self.client._session.delete.call_args
        assert kwargs.get("timeout") == BrainstemClient.DEFAULT_TIMEOUT

    def test_load_all_passes_timeout(self):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.status_code = 200
        r.json.return_value = {"sessions": [{"id": "1"}], "count": 1}
        self.client._session.get = MagicMock(return_value=r)
        self.client.load("session", load_all=True)
        _, kwargs = self.client._session.get.call_args
        assert kwargs.get("timeout") == BrainstemClient.DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# 401 → AuthenticationError in load_all path
# ---------------------------------------------------------------------------

class TestLoadAll401:
    def test_401_raises_authentication_error(self):
        client = make_client()
        r = MagicMock()
        r.status_code = 401
        r.raise_for_status = MagicMock()
        client._session.get = MagicMock(return_value=r)
        with pytest.raises(AuthenticationError, match="brainstem login"):
            client.load("session", load_all=True)


# ---------------------------------------------------------------------------
# Device auth polling timeout
# ---------------------------------------------------------------------------

class TestDeviceAuthTimeout:
    def test_polling_timeout_raises(self):
        client = make_client()

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

        # max_wait=0 triggers immediate timeout on the first iteration check
        with patch("requests.post", side_effect=[device_resp] + [pending_resp] * 10), \
             patch("webbrowser.open"), \
             patch("time.monotonic", side_effect=[0, 0, 999]):
            with pytest.raises(AuthenticationError, match="timed out"):
                client._device_auth_flow(max_wait=0)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_enter_returns_client(self):
        client = make_client()
        with client as c:
            assert c is client

    def test_exit_closes_session(self):
        client = make_client()
        client._session.close = MagicMock()
        with client:
            pass
        client._session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Unknown kwarg validation in convenience loaders
# ---------------------------------------------------------------------------

class TestUnknownKwarg:
    def test_unknown_kwarg_raises(self):
        client = make_client()
        with pytest.raises(TypeError, match="Unexpected keyword argument"):
            # Call _convenience_load directly with a kwarg not in filter_map
            client._convenience_load(
                "session",
                default_include=[],
                filter_map={"name": "name.icontains"},
                portal="private", id=None, filters=None, sort=None,
                include=None, limit=None, offset=None, load_all=False,
                name="test",
                oops="extra",  # not listed in filter_map
            )


# ---------------------------------------------------------------------------
# New convenience loaders
# ---------------------------------------------------------------------------

class TestNewConvenienceLoaders:
    def setup_method(self):
        self.client = make_client()
        self.client._session.get = MagicMock(return_value=mock_response(200, {}))

    def _get_params(self):
        return self.client._session.get.call_args[1].get("params", {})

    def _get_url(self):
        return self.client._session.get.call_args[0][0]

    def test_load_procedurelog_procedure_filter(self):
        uuid = "11111111-0000-0000-0000-000000000000"
        self.client.load_procedurelog(procedure=uuid)
        assert self._get_params()["filter{procedure.id}"] == uuid
        assert "/modules/procedurelog/" in self._get_url()

    def test_load_subjectlog_subject_filter(self):
        uuid = "22222222-0000-0000-0000-000000000000"
        self.client.load_subjectlog(subject=uuid)
        assert self._get_params()["filter{subject.id}"] == uuid
        assert "/modules/subjectlog/" in self._get_url()

    def test_load_equipment_setup_filter(self):
        uuid = "33333333-0000-0000-0000-000000000000"
        self.client.load_equipment(setup=uuid)
        assert self._get_params()["filter{setup.id}"] == uuid
        assert "/modules/equipment/" in self._get_url()

    def test_load_equipment_name_filter(self):
        self.client.load_equipment(name="headstage")
        assert self._get_params()["filter{name.icontains}"] == "headstage"

    def test_load_consumablestock_url(self):
        self.client.load_consumablestock()
        assert "/modules/consumablestock/" in self._get_url()

    def test_load_behavioralassay_name_filter(self):
        self.client.load_behavioralassay(name="open field")
        assert self._get_params()["filter{name.icontains}"] == "open field"
        assert "/personal_attributes/behavioralassay/" in self._get_url()

    def test_load_datastorage_url(self):
        self.client.load_datastorage()
        assert "/personal_attributes/datastorage/" in self._get_url()

    def test_load_setup_url(self):
        self.client.load_setup()
        assert "/personal_attributes/setup/" in self._get_url()

    def test_load_hardwaredevice_url(self):
        self.client.load_hardwaredevice()
        assert "/resources/hardwaredevice/" in self._get_url()

    def test_load_brainregion_name_filter(self):
        self.client.load_brainregion(name="CA1")
        assert self._get_params()["filter{name.icontains}"] == "CA1"
        assert "/taxonomies/brainregion/" in self._get_url()

    def test_load_species_url(self):
        self.client.load_species()
        assert "/taxonomies/species/" in self._get_url()

    def test_load_strain_species_filter(self):
        uuid = "44444444-0000-0000-0000-000000000000"
        self.client.load_strain(species=uuid)
        assert self._get_params()["filter{species.id}"] == uuid
        assert "/taxonomies/strain/" in self._get_url()

    def test_load_publication_url(self):
        self.client.load_publication()
        assert "/dissemination/publication/" in self._get_url()

    def test_load_laboratory_name_filter(self):
        self.client.load_laboratory(name="Petersen")
        assert self._get_params()["filter{name.icontains}"] == "Petersen"
        assert "/users/laboratory/" in self._get_url()


# ---------------------------------------------------------------------------
# CLI — load / save / delete commands
# ---------------------------------------------------------------------------

class TestCLICommands:
    def _run_cli(self, argv, client_mock):
        import brainstem_api_tools.cli as cli_module
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client_mock), \
             patch("sys.argv", argv):
            cli_module.main()

    def test_cli_load_calls_load(self, capsys):
        resp = mock_response(200, {"sessions": []})
        client = MagicMock()
        client.load.return_value = resp
        self._run_cli(["brainstem", "--token", TOKEN, "load", "session"], client)
        client.load.assert_called_once()

    def test_cli_load_filter_parsed(self, capsys):
        resp = mock_response(200, {})
        client = MagicMock()
        client.load.return_value = resp
        self._run_cli(
            ["brainstem", "--token", TOKEN, "load", "session",
             "--filters", "name.icontains=rat"],
            client,
        )
        _, kwargs = client.load.call_args
        assert kwargs["filters"] == {"name.icontains": "rat"}

    def test_cli_save_post(self, capsys):
        resp = mock_response(201, {"session": {"id": "abc"}})
        client = MagicMock()
        client.save.return_value = resp
        self._run_cli(
            ["brainstem", "--token", TOKEN, "save", "session",
             "--data", '{"name": "x", "projects": []}'],
            client,
        )
        client.save.assert_called_once()
        _, kwargs = client.save.call_args
        assert kwargs["data"] == {"name": "x", "projects": []}

    def test_cli_delete(self, capsys):
        resp = mock_response(204)
        client = MagicMock()
        client.delete.return_value = resp
        self._run_cli(
            ["brainstem", "--token", TOKEN, "delete", "session",
             "--id", "00000000-0000-0000-0000-000000000099"],
            client,
        )
        client.delete.assert_called_once()
        _, kwargs = client.delete.call_args
        assert kwargs["id"] == "00000000-0000-0000-0000-000000000099"

    def test_cli_invalid_filter_exits(self):
        import brainstem_api_tools.cli as cli_module
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=MagicMock()), \
             patch("sys.argv", ["brainstem", "--token", TOKEN, "load", "session",
                                "--filters", "badfilter"]):
            with pytest.raises(SystemExit):
                cli_module.main()

