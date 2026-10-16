"""Unit tests for BrainstemClient.

All HTTP calls are intercepted with pytest-mock / unittest.mock so no
network access is required.
"""

import gzip
import hashlib
import json

import pytest
import requests
from unittest.mock import MagicMock, patch, PropertyMock

from brainstem_api_tools.brainstem_api_client import (
    BrainstemClient,
    AuthenticationError,
    ModelType,
    ExportError,
    _MODEL_TO_APP,
    _resolve_model,
    _resolve_portal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOKEN = "test-token-abc123"


@pytest.fixture(autouse=True)
def _clear_brainstem_env(monkeypatch):
    """Keep the developer's BRAINSTEM_* environment out of the tests."""
    monkeypatch.delenv("BRAINSTEM_API_TOKEN", raising=False)
    monkeypatch.delenv("BRAINSTEM_API_URL", raising=False)


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

    def test_anonymous_sends_no_token_and_skips_login(self, monkeypatch):
        monkeypatch.setenv("BRAINSTEM_API_TOKEN", "env-token")
        with patch.object(BrainstemClient, "_load_cached_token") as cached, \
                patch.object(BrainstemClient, "_device_auth_flow") as flow:
            client = BrainstemClient(anonymous=True)
        cached.assert_not_called()
        flow.assert_not_called()
        assert client._token is None
        assert "Authorization" not in client._session.headers

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

    def test_token_from_env(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token"
        token_file.write_text("cached-token")
        monkeypatch.setattr(
            "brainstem_api_tools.brainstem_api_client._TOKEN_FILE", token_file
        )
        monkeypatch.setenv("BRAINSTEM_API_TOKEN", "env-token")
        client = BrainstemClient()
        assert client._token == "env-token"
        assert client._session.headers["Authorization"] == "Bearer env-token"

    def test_explicit_token_beats_env(self, monkeypatch):
        monkeypatch.setenv("BRAINSTEM_API_TOKEN", "env-token")
        assert make_client()._token == TOKEN

    def test_url_from_env(self, monkeypatch):
        monkeypatch.setenv("BRAINSTEM_API_URL", "http://127.0.0.1:8000")
        client = make_client()
        assert client._address == "http://127.0.0.1:8000/api/"

    def test_explicit_url_beats_env(self, monkeypatch):
        monkeypatch.setenv("BRAINSTEM_API_URL", "http://127.0.0.1:8000")
        client = BrainstemClient(token=TOKEN, url="https://example.org")
        assert client._address == "https://example.org/api/"

    def test_default_url_without_env(self):
        assert make_client()._address == "https://www.brainstem.org/api/"


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
        self.client.load("session", limit=20, offset=40)
        params = self.client._session.get.call_args[1]["params"]
        assert params["per_page"] == 20
        assert params["page"] == 3
        assert "limit" not in params and "offset" not in params

    def test_load_limit_only_sets_per_page(self):
        self._mock_get()
        self.client.load("session", limit=50)
        params = self.client._session.get.call_args[1]["params"]
        assert params["per_page"] == 50
        assert params["page"] == 1

    def test_load_offset_without_limit_uses_page_size_100(self):
        self._mock_get()
        self.client.load("session", offset=200)
        params = self.client._session.get.call_args[1]["params"]
        assert params["per_page"] == 100
        assert params["page"] == 3

    def test_load_offset_not_multiple_of_page_size_raises(self):
        self._mock_get()
        with pytest.raises(ValueError, match="multiple of limit"):
            self.client.load("session", limit=50, offset=20)
        with pytest.raises(ValueError, match="page size, 100"):
            self.client.load("session", offset=30)
        self.client._session.get.assert_not_called()

    def test_load_without_paging_sends_no_page_params(self):
        self._mock_get()
        self.client.load("session")
        params = self.client._session.get.call_args[1]["params"]
        assert "per_page" not in params and "page" not in params

    def test_load_with_id_ignores_paging(self):
        self._mock_get()
        self.client.load("session", id="00000000-0000-0000-0000-000000000001",
                         limit=10, offset=5)
        assert self.client._session.get.call_args[1]["params"] == {}

    def test_load_public_portal(self):
        self._mock_get()
        self.client.load("project", portal="public")
        url = self.client._session.get.call_args[0][0]
        assert "/public/" in url

    def test_load_invalid_model_raises(self):
        with pytest.raises(ValueError, match="Unknown model"):
            self.client.load("notamodel")

    @pytest.mark.parametrize("model,expected_app", [
        *[(m, "stem") for m in [
            "specimenset", "specimen", "epoch", "sessiondatastorage",
            "collectionsession", "cohortsubject"]],
        *[(m, "modules") for m in [
            "experimentalinterface", "experimentalinterfacetemplate", "materialusage",
            "materialusagetemplate", "specimenprocedure", "specimenproceduretemplate",
            "specimenlog", "dataacquisitioninterface", "manipulationinterface",
            "dataacquisitionprocedure", "proceduretemplate", "dataacquisitiontemplate",
            "manipulationtemplate", "procedureepisode", "procedureepisodetemplate",
            "episodepersonnel"]],
        *[(m, "taxonomies") for m in [
            "anatomicalregion", "anatomicalreference", "coordinatetransform"]],
        ("pendinginvitation", "users"),
    ])
    def test_new_models_routed(self, model, expected_app):
        assert _MODEL_TO_APP[model] == expected_app
        self._mock_get()
        self.client.load(model)
        assert f"/api/private/{expected_app}/{model}/" in self.client._session.get.call_args[0][0]

    def test_load_invalid_portal_raises(self):
        with pytest.raises(ValueError, match="Unknown portal"):
            self.client.load("session", portal="badportal")

    @pytest.mark.parametrize("old,new,app", [
        ("project_membership_invitation", "projectmembershipinvitation", "stem"),
        ("project_group_membership_invitation", "projectgroupmembershipinvitation", "stem"),
        ("group_membership_invitation", "groupmembershipinvitation", "users"),
        ("group_membership_request", "groupmembershiprequest", "users"),
    ])
    def test_old_underscored_names_resolve_with_warning(self, old, new, app):
        self._mock_get()
        with pytest.warns(FutureWarning, match=f"use '{new}'"):
            self.client.load(old)
        assert f"/api/private/{app}/{new}/" in self.client._session.get.call_args[0][0]
        with pytest.warns(FutureWarning):
            self.client.load(ModelType[old])

    @pytest.mark.parametrize("model,app", [
        ("admingroup", "users"),
        ("speciesapproval", "taxonomies"),
        ("supplierapproval", "resources"),
        ("publicationapproval", "dissemination"),
        ("setupmembershipinvitation", "personal_attributes"),
        ("datastoragegroupmembershipinvitation", "personal_attributes"),
    ])
    def test_approval_and_invitation_resources_routed(self, model, app):
        self._mock_get()
        self.client.load(model)
        assert f"/api/private/{app}/{model}/" in self.client._session.get.call_args[0][0]

    def test_brainregion_resolves_to_anatomicalregion(self):
        self._mock_get()
        with pytest.warns(FutureWarning, match="use 'anatomicalregion'"):
            self.client.load("brainregion")
        assert "/taxonomies/anatomicalregion/" in self.client._session.get.call_args[0][0]

    def test_limit_above_page_size_maximum_raises(self):
        self._mock_get()
        with pytest.raises(ValueError, match="between 1 and 500"):
            self.client.load("session", limit=501)
        with pytest.raises(ValueError, match="between 1 and 500"):
            self.client.load("session", limit=0)
        self.client._session.get.assert_not_called()

    def test_limit_at_page_size_maximum(self):
        self._mock_get()
        self.client.load("session", limit=500)
        assert self.client._session.get.call_args[1]["params"]["per_page"] == 500

    def test_model_to_app_routing(self):
        """Spot-check a few app assignments."""
        cases = [
            ("session", "stem"),
            ("breeding", "stem"),
            ("projectmembershipinvitation", "stem"),
            ("procedure", "modules"),
            ("behavioralassay", "personal_attributes"),
            ("license", "personal_attributes"),
            ("setup", "personal_attributes"),
            ("consumable", "resources"),
            ("behavioralparadigm", "taxonomies"),
            ("behavioralcategory", "taxonomies"),
            ("regulatoryauthority", "taxonomies"),
            ("anatomicalregion", "taxonomies"),
            ("specimenset", "stem"),
            ("experimentalinterface", "modules"),
            ("pendinginvitation", "users"),
            ("publication", "dissemination"),
            ("laboratory", "users"),
            ("groupmembershipinvitation", "users"),
            ("groupmembershiprequest", "users"),
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
            r.status_code = 200
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
        result = self.client.load("session", limit=2, load_all=True)
        assert len(result["sessions"]) == 3
        assert [r["id"] for r in result["sessions"]] == ["1", "2", "3"]

    def test_meta_total_pages_drives_paging(self):
        meta = {"per_page": 100, "total_results": 3, "total_pages": 2}
        self._mock_pages([
            {"sessions": [{"id": "1"}, {"id": "2"}], "meta": {**meta, "page": 1}},
            {"sessions": [{"id": "3"}],               "meta": {**meta, "page": 2}},
        ])
        result = self.client.load("session", load_all=True)
        assert [r["id"] for r in result["sessions"]] == ["1", "2", "3"]
        pages = [c[1]["params"]["page"] for c in self.client._session.get.call_args_list]
        assert pages == [1, 2]
        params = self.client._session.get.call_args[1]["params"]
        assert params["per_page"] == 100
        assert "limit" not in params and "offset" not in params

    def test_sideloaded_lists_merged_and_deduplicated(self):
        meta = {"total_pages": 2}
        self._mock_pages([
            {"data_acquisitions": [{"id": "da1"}], "sessions": [{"id": "1"}], "meta": meta},
            {"data_acquisitions": [{"id": "da1"}, {"id": "da2"}], "sessions": [{"id": "2"}], "meta": meta},
        ])
        result = self.client.load("session", include=["dataacquisition"], load_all=True)
        assert [r["id"] for r in result["sessions"]] == ["1", "2"]
        assert [r["id"] for r in result["data_acquisitions"]] == ["da1", "da2"]

    def test_offset_translated_to_page(self):
        self._mock_pages([{"sessions": [{"id": "3"}], "meta": {"total_pages": 2}}])
        self.client.load("session", limit=2, offset=2, load_all=True)
        assert self.client._session.get.call_args[1]["params"]["page"] == 2

    def test_load_all_reduces_page_size_to_maximum(self):
        self._mock_pages([{"sessions": [{"id": "1"}], "meta": {"total_pages": 1}}])
        self.client.load("session", limit=1000, load_all=True)
        assert self.client._session.get.call_args[1]["params"]["per_page"] == 500

    def test_offset_not_multiple_of_limit_raises(self):
        with pytest.raises(ValueError, match="multiple of limit"):
            self.client.load("session", limit=10, offset=5, load_all=True)

    def test_load_all_false_returns_response(self):
        r = MagicMock()
        self.client._session.get = MagicMock(return_value=r)
        result = self.client.load("session", load_all=False)
        assert result is r


# ---------------------------------------------------------------------------
# export_project() / export_session()
# ---------------------------------------------------------------------------

PROJECT_ID = "11111111-0000-0000-0000-000000000000"
JOB_ID = "22222222-0000-0000-0000-000000000000"
EXPORT_URL = f"https://www.brainstem.org/api/private/stem/project/{PROJECT_ID}/export/"
PAYLOAD = {
    "export_info": {"format_version": "2.0", "project_id": PROJECT_ID, "record_count": 1,
                    "counts": {"stem.project": 1}},
    "records": {"stem.project": [{"model": "stem.project", "pk": PROJECT_ID, "fields": {}}]},
}


def export_response(status_code=200, json_body=None, content=None, content_type="application/json"):
    resp = mock_response(status_code, json_body)
    resp.headers = {"Content-Type": content_type}
    resp.reason = "reason"
    if content is not None:
        resp.content = content
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(str(status_code))
    return resp


def job(status, **extra):
    return {"export_job": {"id": JOB_ID, "status": status, "progress_percent": 0, **extra}}


class TestExportProject:
    def setup_method(self):
        self.client = make_client()

    def test_direct_export_returns_payload(self):
        with patch("requests.get", return_value=export_response(200, PAYLOAD)) as get:
            result = self.client.export_project(PROJECT_ID)
        assert result == PAYLOAD
        assert get.call_args[0][0] == EXPORT_URL
        assert get.call_args[1]["headers"]["Authorization"] == f"Bearer {TOKEN}"

    def test_direct_export_bypasses_session_retries(self):
        self.client._session.get = MagicMock()
        with patch("requests.get", return_value=export_response(200, PAYLOAD)):
            self.client.export_project(PROJECT_ID)
        self.client._session.get.assert_not_called()

    def test_direct_timeout_suggests_background(self):
        with patch("requests.get", return_value=export_response(503, content_type="text/html")):
            with pytest.raises(ExportError, match="background=True"):
                self.client.export_project(PROJECT_ID)

    def test_server_without_endpoint(self):
        with patch("requests.get", return_value=export_response(404, content_type="text/html")):
            with pytest.raises(ExportError, match="does not support project export"):
                self.client.export_project(PROJECT_ID)

    def test_unknown_or_unreadable_project(self):
        with patch("requests.get", return_value=export_response(404, {"detail": "Not found."})):
            with pytest.raises(ExportError, match="project was not found, or you do not have read access"):
                self.client.export_project(PROJECT_ID)

    def test_forbidden(self):
        with patch("requests.get", return_value=export_response(403, {"detail": "x"})):
            with pytest.raises(ExportError, match="permission to export this project"):
                self.client.export_project(PROJECT_ID)

    def test_unexpected_status_raises_http_error(self):
        with patch("requests.get", return_value=export_response(500, {"detail": "x"})):
            with pytest.raises(requests.HTTPError):
                self.client.export_project(PROJECT_ID)

    def test_401_raises_authentication_error(self):
        with patch("requests.get", return_value=export_response(401, {"detail": "x"})):
            with pytest.raises(AuthenticationError):
                self.client.export_project(PROJECT_ID)

    def test_throttled_shows_server_detail(self):
        with patch("requests.get", return_value=export_response(429, {"detail": "Request was throttled."})):
            with pytest.raises(ExportError, match="throttled"):
                self.client.export_project(PROJECT_ID)

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="project_id"):
            self.client.export_project(None)

    def _run_background(self, final_job, download):
        self.client._session.post = MagicMock(return_value=export_response(202, job("pending")))
        self.client._session.get = MagicMock(side_effect=[
            export_response(200, job("running")),
            export_response(200, final_job),
            download,
        ])
        with patch("time.sleep"):
            return self.client.export_project(PROJECT_ID, background=True)

    def test_background_export_polls_downloads_and_unpacks(self):
        gz = gzip.compress(json.dumps(PAYLOAD).encode())
        download_path = f"/api/private/stem/project/{PROJECT_ID}/export-jobs/{JOB_ID}/download/"
        result = self._run_background(
            job("completed", download_url=download_path, file_sha256=hashlib.sha256(gz).hexdigest()),
            export_response(200, content=gz, content_type="application/gzip"),
        )
        assert result == PAYLOAD
        assert self.client._session.post.call_args[0][0] == EXPORT_URL
        urls = [c[0][0] for c in self.client._session.get.call_args_list]
        assert urls[0].endswith(f"/project/{PROJECT_ID}/export-jobs/{JOB_ID}/")
        assert urls[2] == "https://www.brainstem.org" + download_path

    def test_background_checksum_mismatch(self):
        gz = gzip.compress(json.dumps(PAYLOAD).encode())
        with pytest.raises(ExportError, match="checksum"):
            self._run_background(
                job("completed", download_url="/x/", file_sha256="0" * 64),
                export_response(200, content=gz, content_type="application/gzip"),
            )

    def test_background_failed_job_raises_server_message(self):
        with pytest.raises(ExportError, match="no longer export"):
            self._run_background(
                job("failed", error_message="The requester can no longer export this project."), None,
            )

    def test_background_timeout(self):
        self.client._session.post = MagicMock(return_value=export_response(202, job("pending")))
        self.client._session.get = MagicMock(return_value=export_response(200, job("running")))
        with patch("time.sleep"), pytest.raises(ExportError, match=JOB_ID):
            self.client.export_project(PROJECT_ID, background=True, timeout=-1)


SESSION_ID = "33333333-0000-0000-0000-000000000000"
SESSION_EXPORT_URL = f"https://www.brainstem.org/api/private/stem/session/{SESSION_ID}/export/"
SESSION_PAYLOAD = {
    "export_info": {"format_version": "2.1", "scope": "session", "session_id": SESSION_ID,
                    "project_id": None, "project_ids": [PROJECT_ID]},
    "records": {"stem.session": [{"model": "stem.session", "pk": SESSION_ID, "fields": {}}]},
}


class TestExportSession:
    def setup_method(self):
        self.client = make_client()

    def test_direct_export_uses_session_endpoint(self):
        with patch("requests.get", return_value=export_response(200, SESSION_PAYLOAD)) as get:
            result = self.client.export_session(SESSION_ID)
        assert result == SESSION_PAYLOAD
        assert get.call_args[0][0] == SESSION_EXPORT_URL

    def test_background_export_polls_under_the_session(self):
        gz = gzip.compress(json.dumps(SESSION_PAYLOAD).encode())
        download_path = f"/api/private/stem/session/{SESSION_ID}/export-jobs/{JOB_ID}/download/"
        self.client._session.post = MagicMock(return_value=export_response(202, job("pending")))
        self.client._session.get = MagicMock(side_effect=[
            export_response(200, job("completed", download_url=download_path,
                                     file_sha256=hashlib.sha256(gz).hexdigest())),
            export_response(200, content=gz, content_type="application/gzip"),
        ])
        with patch("time.sleep"):
            result = self.client.export_session(SESSION_ID, background=True)
        assert result == SESSION_PAYLOAD
        assert self.client._session.post.call_args[0][0] == SESSION_EXPORT_URL
        urls = [c[0][0] for c in self.client._session.get.call_args_list]
        assert urls[0].endswith(f"/session/{SESSION_ID}/export-jobs/{JOB_ID}/")
        assert urls[1] == "https://www.brainstem.org" + download_path

    def test_errors_name_the_session(self):
        with patch("requests.get", return_value=export_response(404, {"detail": "Not found."})):
            with pytest.raises(ExportError, match="session was not found"):
                self.client.export_session(SESSION_ID)
        with patch("requests.get", return_value=export_response(404, content_type="text/html")):
            with pytest.raises(ExportError, match="does not support session export"):
                self.client.export_session(SESSION_ID)
        with patch("requests.get", return_value=export_response(503, content_type="text/html")):
            with pytest.raises(ExportError, match=r"export_session\(\.\.\., background=True\)"):
                self.client.export_session(SESSION_ID)

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="session_id"):
            self.client.export_session("")


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
        assert self._get_params()["filter{strain}"] == uuid

    def test_load_session_default_include(self):
        self.client.load_session()
        params = self._get_params()
        assert set(params["include[]"]) == {
            "dataacquisition.*", "behaviors.*", "manipulations.*", "epochs.*"
        }

    def test_load_session_project_filter(self):
        uuid = "bbbbbbbb-0000-0000-0000-000000000000"
        self.client.load_session(projects=uuid)
        assert self._get_params()["filter{projects}"] == uuid

    def test_load_collection_default_include(self):
        self.client.load_collection()
        assert self._get_params()["include[]"] == ["sessions.*"]

    def test_load_cohort_default_include(self):
        self.client.load_cohort()
        assert self._get_params()["include[]"] == ["subjects.*"]

    def test_load_behavior_session_filter(self):
        uuid = "cccccccc-0000-0000-0000-000000000000"
        self.client.load_behavior(session=uuid)
        assert self._get_params()["filter{session}"] == uuid

    def test_load_dataacquisition_session_filter(self):
        uuid = "dddddddd-0000-0000-0000-000000000000"
        self.client.load_dataacquisition(session=uuid)
        assert self._get_params()["filter{session}"] == uuid

    def test_load_manipulation_session_filter(self):
        uuid = "eeeeeeee-0000-0000-0000-000000000000"
        self.client.load_manipulation(session=uuid)
        assert self._get_params()["filter{session}"] == uuid

    def test_load_procedure_subject_filter(self):
        uuid = "ffffffff-0000-0000-0000-000000000000"
        self.client.load_procedure(subject=uuid)
        assert self._get_params()["filter{subject}"] == uuid

    @pytest.mark.parametrize("loader,kwarg", [
        ("load_procedure", "subject"),
        ("load_behavior", "session"),
        ("load_dataacquisition", "session"),
        ("load_manipulation", "session"),
        ("load_procedurelog", "procedure"),
        ("load_subjectlog", "subject"),
        ("load_equipment", "setup"),
        ("load_strain", "species"),
    ])
    def test_non_nestable_relation_filters_use_bare_field(self, loader, kwarg):
        # The server rejects filter{<field>.id} for plain PK relations.
        uuid = "12345678-0000-0000-0000-000000000000"
        getattr(self.client, loader)(**{kwarg: uuid})
        params = self._get_params()
        assert params[f"filter{{{kwarg}}}"] == uuid
        assert f"filter{{{kwarg}.id}}" not in params

    def test_convenience_loader_paging_translated(self):
        self.client.load_session(limit=25, offset=50)
        params = self._get_params()
        assert params["per_page"] == 25
        assert params["page"] == 3

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
# CLI login
# ---------------------------------------------------------------------------

class TestCLILogin:
    def _run_login(self, argv, token):
        import brainstem_api_tools.cli as cli_module
        client = MagicMock()
        client._token = token
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client) as cls, \
             patch("sys.argv", argv):
            cli_module.main()
        return cls

    def test_login_does_not_print_token(self, capsys):
        import brainstem_api_tools.cli as cli_module
        self._run_login(["brainstem", "login"], "secret-device-token")
        out = capsys.readouterr().out
        assert "secret-device-token" not in out
        assert "Logged in" in out
        assert str(cli_module._TOKEN_FILE) in out

    def test_login_with_explicit_token_does_not_print_it(self, capsys):
        self._run_login(["brainstem", "login", "--token", TOKEN], TOKEN)
        out = capsys.readouterr().out
        assert TOKEN not in out
        assert "Logged in" in out


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
        assert self._get_params()["filter{procedure}"] == uuid
        assert "/modules/procedurelog/" in self._get_url()

    def test_load_subjectlog_subject_filter(self):
        uuid = "22222222-0000-0000-0000-000000000000"
        self.client.load_subjectlog(subject=uuid)
        assert self._get_params()["filter{subject}"] == uuid
        assert "/modules/subjectlog/" in self._get_url()

    def test_load_equipment_setup_filter(self):
        uuid = "33333333-0000-0000-0000-000000000000"
        self.client.load_equipment(setup=uuid)
        assert self._get_params()["filter{setup}"] == uuid
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

    def test_load_brainregion_is_deprecated_alias(self):
        with pytest.warns(FutureWarning, match="load_anatomicalregion"):
            self.client.load_brainregion(name="CA1")
        assert self._get_params()["filter{name.icontains}"] == "CA1"
        assert "/taxonomies/anatomicalregion/" in self._get_url()

    def test_load_species_url(self):
        self.client.load_species()
        assert "/taxonomies/species/" in self._get_url()

    def test_load_strain_species_filter(self):
        uuid = "44444444-0000-0000-0000-000000000000"
        self.client.load_strain(species=uuid)
        assert self._get_params()["filter{species}"] == uuid
        assert "/taxonomies/strain/" in self._get_url()

    def test_load_consumablestock_inventory_filter(self):
        uuid = "77777777-0000-0000-0000-000000000000"
        self.client.load_consumablestock(inventory=uuid)
        assert self._get_params()["filter{inventory}"] == uuid
        assert "/modules/consumablestock/" in self._get_url()

    @pytest.mark.parametrize("loader", [
        "load_behavior", "load_dataacquisition", "load_manipulation", "load_procedure",
        "load_procedurelog", "load_subjectlog", "load_equipment", "load_consumablestock",
        "load_behavioralassay", "load_datastorage", "load_setup", "load_hardwaredevice",
        "load_brainregion", "load_species", "load_strain", "load_publication", "load_laboratory",
    ])
    def test_untagged_models_have_no_tags_filter(self, loader):
        # The server answers 400 "Invalid filter field: tags" for these models.
        with pytest.raises(TypeError):
            getattr(self.client, loader)(tags="x")

    def test_load_species_popular_name_filter(self):
        self.client.load_species(popular_name="mouse")
        assert self._get_params()["filter{popular_name.icontains}"] == "mouse"
        assert "/taxonomies/species/" in self._get_url()

    def test_load_strain_popular_name_filter(self):
        self.client.load_strain(popular_name="black 6")
        assert self._get_params()["filter{popular_name.icontains}"] == "black 6"

    def test_popular_name_not_sent_unless_given(self):
        self.client.load_species(name="Mus")
        assert "filter{popular_name.icontains}" not in self._get_params()

    def test_load_anatomicalregion_filters(self):
        ref = "55555555-0000-0000-0000-000000000000"
        self.client.load_anatomicalregion(acronym="CA1", name="field", reference=ref)
        params = self._get_params()
        assert params["filter{acronym.iexact}"] == "CA1"
        assert params["filter{name.icontains}"] == "field"
        assert params["filter{reference}"] == ref
        assert "/taxonomies/anatomicalregion/" in self._get_url()

    def test_load_anatomicalregion_descendants_url(self):
        uuid = "66666666-0000-0000-0000-000000000000"
        self.client.load_anatomicalregion_descendants(uuid, portal="public")
        assert self._get_url() == (
            f"https://www.brainstem.org/api/public/taxonomies/anatomicalregion/{uuid}/descendants/"
        )

    def test_load_anatomicalregion_descendants_requires_id(self):
        with pytest.raises(ValueError, match="'id' is required"):
            self.client.load_anatomicalregion_descendants(None)

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

    def test_cli_reference_prints_page(self, capsys):
        client = MagicMock()
        client.agent_reference.return_value = "# rules"
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client) as factory, \
             patch("sys.argv", ["brainstem", "reference", "rules.md"]):
            import brainstem_api_tools.cli as cli_module
            cli_module.main()
        assert factory.call_args.kwargs["anonymous"] is True
        client.agent_reference.assert_called_once_with("rules.md")
        assert "# rules" in capsys.readouterr().out

    def test_cli_reference_defaults_to_index(self, capsys):
        client = MagicMock()
        client.agent_reference.return_value = "# index"
        self._run_cli(["brainstem", "--token", TOKEN, "reference"], client)
        client.agent_reference.assert_called_once_with("index.md")

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

    def _load_kwargs(self, argv):
        client = MagicMock()
        client.load.return_value = mock_response(200, {"sessions": []})
        self._run_cli(["brainstem", "load", "session", *argv], client)
        return client.load.call_args[1]

    def test_cli_limit_offset_passed_through(self):
        kwargs = self._load_kwargs(["--limit", "20", "--offset", "40"])
        assert kwargs["limit"] == 20 and kwargs["offset"] == 40

    def test_cli_per_page_and_page(self):
        kwargs = self._load_kwargs(["--per-page", "20", "--page", "3"])
        assert kwargs["limit"] == 20
        assert kwargs["offset"] == 40
        assert "load_all" not in kwargs

    def test_cli_page_without_per_page_uses_100(self):
        kwargs = self._load_kwargs(["--page", "2"])
        assert kwargs["limit"] is None
        assert kwargs["offset"] == 100

    def test_cli_per_page_without_page(self):
        kwargs = self._load_kwargs(["--per-page", "10"])
        assert kwargs["limit"] == 10
        assert kwargs["offset"] is None

    def test_cli_page_and_limit_conflict_exits(self):
        with pytest.raises(SystemExit):
            self._load_kwargs(["--page", "2", "--limit", "10"])

    def test_cli_page_below_one_exits(self):
        with pytest.raises(SystemExit):
            self._load_kwargs(["--page", "0"])

    def test_cli_all_prints_merged_json(self, capsys):
        merged = {"sessions": [{"id": "1"}, {"id": "2"}], "meta": {"total_pages": 2}}
        client = MagicMock()
        client.load.return_value = merged
        self._run_cli(["brainstem", "load", "session", "--all", "--per-page", "50"], client)
        kwargs = client.load.call_args[1]
        assert kwargs["load_all"] is True
        assert kwargs["limit"] == 50
        assert json.loads(capsys.readouterr().out) == merged

    def test_cli_all_error_exits_nonzero(self, capsys):
        client = MagicMock()
        client.load.side_effect = AuthenticationError("API token is invalid or expired.")
        with pytest.raises(SystemExit) as exc:
            self._run_cli(["brainstem", "load", "session", "--all"], client)
        assert exc.value.code == 1
        assert "invalid or expired" in capsys.readouterr().err

    def test_cli_global_flags_before_subcommand_kept(self):
        client = MagicMock()
        client.load.return_value = mock_response(200, {})
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client) as cls, \
             patch("sys.argv", ["brainstem", "--token", TOKEN, "--url", "http://x/",
                                "load", "session"]):
            import brainstem_api_tools.cli as cli_module
            cli_module.main()
        assert cls.call_args[1]["token"] == TOKEN
        assert cls.call_args[1]["url"] == "http://x/"

    def test_cli_url_defaults_to_env(self, monkeypatch):
        monkeypatch.setenv("BRAINSTEM_API_URL", "http://127.0.0.1:8000/")
        monkeypatch.setenv("BRAINSTEM_API_TOKEN", "env-token")
        client = MagicMock()
        client.load.return_value = mock_response(200, {})
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client) as cls, \
             patch("sys.argv", ["brainstem", "load", "session"]):
            import brainstem_api_tools.cli as cli_module
            cli_module.main()
        assert cls.call_args[1]["url"] == "http://127.0.0.1:8000/"
        assert cls.call_args[1]["token"] == "env-token"

    def test_cli_offset_not_multiple_of_page_size_exits(self, capsys):
        import brainstem_api_tools.cli as cli_module
        client = BrainstemClient(token=TOKEN)
        client._session.get = MagicMock()
        with patch("brainstem_api_tools.cli.BrainstemClient", return_value=client), \
             patch("sys.argv", ["brainstem", "load", "session",
                                "--limit", "20", "--offset", "30"]):
            with pytest.raises(SystemExit):
                cli_module.main()
        assert "multiple of limit" in capsys.readouterr().err
        client._session.get.assert_not_called()


# ---------------------------------------------------------------------------
# Agent reference
# ---------------------------------------------------------------------------

class TestAgentReference:
    def test_fetches_page(self):
        client = make_client()
        resp = MagicMock(status_code=200, text="# rules")
        with patch.object(client._session, "get", return_value=resp) as get:
            assert client.agent_reference("rules.md") == "# rules"
        assert get.call_args[0][0] == "https://www.brainstem.org/reference/rules.md"

    def test_default_page_is_index(self):
        client = make_client()
        with patch.object(client._session, "get", return_value=MagicMock(status_code=200, text="x")) as get:
            client.agent_reference()
        assert get.call_args[0][0].endswith("/reference/index.md")

    def test_unknown_page_raises_value_error(self):
        client = make_client()
        with patch.object(client._session, "get", return_value=MagicMock(status_code=404)):
            with pytest.raises(ValueError, match="No agent reference page"):
                client.agent_reference("nope.md")

    def test_anonymous_client_reads_the_public_reference(self):
        client = BrainstemClient(anonymous=True)
        with patch.object(client._session, "get", return_value=MagicMock(status_code=200, text="# index")) as get:
            assert client.agent_reference() == "# index"
        assert "Authorization" not in client._session.headers
        get.assert_called_once()
