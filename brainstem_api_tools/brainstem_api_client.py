import gzip
import hashlib
import json
import os
import stat
import time
import warnings
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Union

import requests
from requests.adapters import HTTPAdapter
from requests.models import Response
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Model → app routing table (single source of truth)
# ---------------------------------------------------------------------------

_MODEL_TO_APP: dict = {
    # stem
    "breeding": "stem",
    "cohort": "stem",
    "cohortsubject": "stem",
    "collection": "stem",
    "collectionsession": "stem",
    "epoch": "stem",
    "project": "stem",
    "projectgroupmembershipinvitation": "stem",
    "projectmembershipinvitation": "stem",
    "session": "stem",
    "sessiondatastorage": "stem",
    "specimen": "stem",
    "specimenset": "stem",
    "subject": "stem",
    # modules
    "behavior": "modules",
    "consumablestock": "modules",
    "dataacquisition": "modules",
    "dataacquisitioninterface": "modules",
    "dataacquisitionprocedure": "modules",
    "dataacquisitiontemplate": "modules",
    "episodepersonnel": "modules",
    "equipment": "modules",
    "experimentalinterface": "modules",
    "experimentalinterfacetemplate": "modules",
    "manipulation": "modules",
    "manipulationinterface": "modules",
    "manipulationtemplate": "modules",
    "materialusage": "modules",
    "materialusagetemplate": "modules",
    "procedure": "modules",
    "procedureepisode": "modules",
    "procedureepisodetemplate": "modules",
    "procedurelog": "modules",
    "proceduretemplate": "modules",
    "specimenlog": "modules",
    "specimenprocedure": "modules",
    "specimenproceduretemplate": "modules",
    "subjectlog": "modules",
    # personal_attributes
    "behavioralassay": "personal_attributes",
    "behavioralassaygroupmembershipinvitation": "personal_attributes",
    "behavioralassaymembershipinvitation": "personal_attributes",
    "datastorage": "personal_attributes",
    "datastoragegroupmembershipinvitation": "personal_attributes",
    "datastoragemembershipinvitation": "personal_attributes",
    "inventory": "personal_attributes",
    "inventorygroupmembershipinvitation": "personal_attributes",
    "inventorymembershipinvitation": "personal_attributes",
    "license": "personal_attributes",
    "licensegroupmembershipinvitation": "personal_attributes",
    "licensemembershipinvitation": "personal_attributes",
    "protocol": "personal_attributes",
    "protocolgroupmembershipinvitation": "personal_attributes",
    "protocolmembershipinvitation": "personal_attributes",
    "setup": "personal_attributes",
    "setupgroupmembershipinvitation": "personal_attributes",
    "setupmembershipinvitation": "personal_attributes",
    # resources
    "consumable": "resources",
    "consumableapproval": "resources",
    "hardwaredevice": "resources",
    "hardwaredeviceapproval": "resources",
    "supplier": "resources",
    "supplierapproval": "resources",
    # taxonomies
    "anatomicalreference": "taxonomies",
    "anatomicalregion": "taxonomies",
    "behavioralcategory": "taxonomies",
    "behavioralcategoryapproval": "taxonomies",
    "behavioralparadigm": "taxonomies",
    "behavioralparadigmapproval": "taxonomies",
    "coordinatetransform": "taxonomies",
    "regulatoryauthority": "taxonomies",
    "regulatoryauthorityapproval": "taxonomies",
    "setuptype": "taxonomies",
    "setuptypeapproval": "taxonomies",
    "species": "taxonomies",
    "speciesapproval": "taxonomies",
    "strain": "taxonomies",
    "strainapproval": "taxonomies",
    # dissemination
    "journal": "dissemination",
    "journalapproval": "dissemination",
    "publication": "dissemination",
    "publicationapproval": "dissemination",
    # users
    "admingroup": "users",
    "group": "users",
    "groupmembershipinvitation": "users",
    "groupmembershiprequest": "users",
    "laboratory": "users",
    "pendinginvitation": "users",
    "user": "users",
}

_TOKEN_FILE = Path.home() / ".config" / "brainstem" / "token"

# Deprecated model names, resolved to the server's current name with a warning:
# the underscored names earlier versions of this client used (they never matched
# a server route), and "brainregion", renamed "anatomicalregion".
_MODEL_ALIASES: dict = {
    "brainregion": "anatomicalregion",
    "project_membership_invitation": "projectmembershipinvitation",
    "project_group_membership_invitation": "projectgroupmembershipinvitation",
    "group_membership_invitation": "groupmembershipinvitation",
    "group_membership_request": "groupmembershiprequest",
}

# Derived from _MODEL_TO_APP so there is exactly one source of truth.
ModelType = Enum(  # type: ignore[misc]
    "ModelType", {k: k for k in [*_MODEL_TO_APP, *_MODEL_ALIASES]}
)

_VALID_PORTALS = {"private", "public", "super"}


def _resolve_model(model) -> str:
    """Accept a plain string or a ModelType member and return the server's resource name."""
    if isinstance(model, ModelType):
        model = model.value
    model = str(model)
    if model in _MODEL_ALIASES:
        warnings.warn(
            f"Model name '{model}' is deprecated; use '{_MODEL_ALIASES[model]}'.",
            FutureWarning, stacklevel=3,
        )
        return _MODEL_ALIASES[model]
    if model not in _MODEL_TO_APP:
        raise ValueError(
            f"Unknown model '{model}'. Valid models are: "
            + ", ".join(sorted(_MODEL_TO_APP))
        )
    return model


def _resolve_portal(portal) -> str:
    """Accept a plain string or a PortalType member and return the string value."""
    if isinstance(portal, Enum):
        portal = portal.value
    portal = str(portal)
    if portal not in _VALID_PORTALS:
        raise ValueError(
            f"Unknown portal '{portal}'. Valid portals are: "
            + ", ".join(sorted(_VALID_PORTALS))
        )
    return portal


class PortalType(Enum):
    public = "public"
    private = "private"
    super = "super"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthenticationError(Exception):
    pass


class ExportError(Exception):
    """A project export could not be produced or downloaded."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BrainstemClient:

    BASE_URL = "https://www.brainstem.org/"
    DEFAULT_TIMEOUT: int = 30  # seconds; applied to all HTTP calls
    MAX_PAGE_SIZE: int = 500   # the API returns at most this many records per page

    def __init__(
        self,
        token: str = None,
        headless: bool = False,
        url: str = None,
        anonymous: bool = False,
    ) -> None:
        """Create a client.

        Parameters
        ----------
        token     : API token. Defaults to ``$BRAINSTEM_API_TOKEN``, then the
                    cached token, then the browser device authorization flow.
        headless  : Print the verification URL and code instead of opening a browser.
        url       : Base URL of the server. Defaults to ``$BRAINSTEM_API_URL``,
                    then ``https://www.brainstem.org/``.
        anonymous : Send no token and never start a login. Only the public
                    portal (``portal='public'``) is readable.
        """
        if url is None:
            url = os.environ.get("BRAINSTEM_API_URL")
        if token is None:
            token = os.environ.get("BRAINSTEM_API_TOKEN")

        base = (url.rstrip("/") + "/") if url else self.BASE_URL
        self._base_url = base
        self._address = base + "api/"
        self._session = requests.Session()

        # Automatically retry transient server errors
        _retry = Retry(total=3, backoff_factor=0.5, status_forcelist={502, 503, 504})
        self._session.mount("https://", HTTPAdapter(max_retries=_retry))
        self._session.mount("http://", HTTPAdapter(max_retries=_retry))

        if anonymous:
            self._token = None
            return

        if token:
            self._token = token
        else:
            self._token = self._load_cached_token()
            if not self._token:
                self._token = self._device_auth_flow(headless=headless)
                self._save_token(self._token)

        self._session.headers.update({"Authorization": f"Bearer {self._token}"})

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_cached_token(self) -> str:
        """Return the cached token from disk, or None if not present."""
        if _TOKEN_FILE.exists():
            return _TOKEN_FILE.read_text().strip() or None
        return None

    def _save_token(self, token: str) -> None:
        """Persist the token to disk with owner-read-only permissions."""
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(token)
        _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    def _device_auth_flow(self, headless: bool = False, max_wait: int = 900) -> str:
        """Run the BrainSTEM device authorization flow and return a token.

        The user authenticates in their browser (supports 2FA). No
        credentials are sent by this tool.

        Parameters
        ----------
        headless : If ``True``, print the verification URI and user code
                   instead of opening a browser window.
        max_wait : Maximum seconds to wait for browser approval (default: 900).
        """
        # Step 1 — initiate a device session
        resp = requests.post(
            self._address + "auth/device/",
            json={"client_name": "brainstem-python"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        device_code = data["device_code"]
        interval = int(data.get("interval", 5))

        # Step 2 — open browser or print instructions
        if headless:
            print(f"Open {data['verification_uri']} and enter: {data['user_code']}")
        else:
            webbrowser.open(data["verification_uri_complete"])
            print("Waiting for browser approval...")

        # Step 3 — poll until resolved (timeout after max_wait seconds)
        deadline = time.monotonic() + max_wait
        while True:
            if time.monotonic() > deadline:
                raise AuthenticationError(
                    f"Device authorization timed out after {max_wait} seconds."
                )
            time.sleep(interval)
            poll = requests.post(
                self._address + "auth/device/token/",
                json={"device_code": device_code},
                timeout=10,
            )
            poll.raise_for_status()
            result = poll.json()

            if result.get("status") == "success":
                return result["token"]
            elif result.get("status") == "authorization_pending":
                continue
            else:
                raise AuthenticationError(
                    f"Authorization failed: {result.get('error')}"
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_url(self, portal: str, app: str, model: str,
                   id: str = None, options: str = None) -> str:
        url = f"{self._address}{portal}/{app}/{model}/"
        if id:
            url += f"{id}/"
        if options:
            url += options
        return url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self,
             model,
             portal="private",
             id: str = None,
             options: str = None,
             filters: dict = None,
             sort: list = None,
             include: list = None,
             limit: int = None,
             offset: int = None,
             load_all: bool = False) -> Union[Response, dict]:
        """Load one or more records of *model*.

        Parameters
        ----------
        model    : Model name string or ``ModelType`` member, e.g. ``'session'``.
        portal   : ``'private'`` (default) or ``'public'``, or ``PortalType`` member.
        id       : UUID of a specific record. Returns a single object when set.
        filters  : Dict of field filters, e.g. ``{'name.icontains': 'rat'}``.
                   Supports ``.icontains``, ``.startswith``, ``.endswith``,
                   ``.gt``, ``.gte``, ``.lt``, ``.lte``.
        sort     : List of fields to sort by. Prefix with ``'-'`` for descending.
        include  : Related fields to sideload, e.g. ``['dataacquisition', 'behaviors']``.
                   Their records are returned as extra lists next to the main
                   one, and only records you may read are included. See ``save``
                   before writing back a list field read this way.
        limit    : Records per page, 1 to 500 (default 100). Sent to the API as
                   ``per_page``. With *load_all*, a larger value is reduced to
                   500, which returns the same records in more pages.
        offset   : Number of records to skip. The API pages with ``page`` and
                   ``per_page``, so *offset* must be a multiple of the page size
                   (*limit*, or 100 if *limit* is not set); it is sent as
                   ``page = offset // page_size + 1``.
        load_all : When ``True``, automatically follow pagination and return a
                   combined ``dict`` with all records merged under the model key,
                   starting at the page selected by *offset*.
                   When ``False`` (default), returns the raw ``Response``.
        """
        model = _resolve_model(model)
        portal = _resolve_portal(portal)
        app = _MODEL_TO_APP[model]
        url = self._build_url(portal, app, model, id, options)

        params = {}
        if not id:
            for key, val in (filters or {}).items():
                params[f"filter{{{key}}}"] = val
            for field in (sort or []):
                params.setdefault("sort[]", []).append(field)
            for rel in (include or []):
                params.setdefault("include[]", []).append(f"{rel}.*")

        if load_all and id is not None:
            raise ValueError("load_all=True cannot be used together with id.")

        # The API paginates with page/per_page (limit/offset are ignored by
        # the server), so translate limit/offset into those parameters.
        page_size = 100 if limit is None else limit
        if load_all:
            page_size = min(page_size, self.MAX_PAGE_SIZE)
        if not id and not 1 <= page_size <= self.MAX_PAGE_SIZE:
            raise ValueError(
                f"limit ({limit}) must be between 1 and {self.MAX_PAGE_SIZE}, "
                "the API's maximum page size."
            )
        if not id and offset and offset % page_size:
            raise ValueError(
                f"offset ({offset}) must be a multiple of limit (the page size, "
                f"{page_size}): the API pages with page/per_page."
            )
        start_page = (offset or 0) // page_size + 1

        if load_all:
            return self._load_all_pages(url, params, page_size, start_page=start_page)

        if not id and (limit is not None or offset is not None):
            params["per_page"] = page_size
            params["page"] = start_page
        return self._session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)

    def _get_json(self, url: str, params: dict = None) -> dict:
        """GET *url* and return the decoded JSON, raising on HTTP errors."""
        resp = self._session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
        if resp.status_code == 401:
            raise AuthenticationError(
                "API token is invalid or expired. Run `brainstem login` to re-authenticate."
            )
        resp.raise_for_status()
        return resp.json()

    def _load_all_pages(self, url: str, params: dict,
                        page_size: int = 100, start_page: int = 1) -> dict:
        """Follow pagination and merge every page into a single dict.

        All list-valued keys are concatenated across pages: the primary
        records as well as any sideloaded related records (de-duplicated by
        ``id``). Non-list keys are taken from the first page.
        """
        params = dict(params, per_page=page_size)
        page = start_page
        combined: dict = {}
        seen_ids: dict = {}

        while True:
            data = self._get_json(url, dict(params, page=page))
            lists = {k: v for k, v in data.items() if isinstance(v, list)}

            if not combined:
                if not lists:
                    raise ValueError(
                        "load_all=True requires a paginated list response, but the API "
                        "returned no list-valued key. Use load_all=False for single-object endpoints."
                    )
                combined = {k: v for k, v in data.items() if k not in lists}

            for key, records in lists.items():
                bucket = combined.setdefault(key, [])
                ids = seen_ids.setdefault(key, set())
                for record in records:
                    rid = record.get("id") if isinstance(record, dict) else None
                    if rid is not None:
                        if rid in ids:
                            continue
                        ids.add(rid)
                    bucket.append(record)

            total_pages = (data.get("meta") or {}).get("total_pages")
            if total_pages is None and "count" in data:
                total_pages = -(-data["count"] // page_size)  # ceil division
            if total_pages is None or page >= total_pages or not any(lists.values()):
                break
            page += 1

        return combined

    def save(self,
             model,
             portal="private",
             id: str = None,
             data: dict = None,
             options: str = None) -> Response:
        """Create or update a record.

        When *id* is provided the record is **updated** (PATCH).
        When *id* is omitted a **new record** is created (POST).

        .. warning::
           Sending a list field (``projects``, ``subjects``, ``behaviors``, ...)
           replaces the whole list. A list read with ``include`` (including the
           convenience loaders' default includes) holds only the records you may
           read, so writing it back drops links to records you cannot see. Read
           the record without ``include`` first, e.g.
           ``client.load('session', id=uid).json()``, and change that list.

        Parameters
        ----------
        model   : Model name string or ``ModelType`` member, e.g. ``'session'``.
        portal  : ``'private'`` (default) or ``'public'``, or ``PortalType`` member.
        id      : UUID of the record to update. Omit to create a new record.
        data    : Dict of fields to submit.
        """
        model = _resolve_model(model)
        portal = _resolve_portal(portal)
        app = _MODEL_TO_APP[model]
        if data is None:
            data = {}

        if id is not None:
            url = self._build_url(portal, app, model, id, options)
            return self._session.patch(url, json=data, timeout=self.DEFAULT_TIMEOUT)
        else:
            url = self._build_url(portal, app, model, options=options)
            return self._session.post(url, json=data, timeout=self.DEFAULT_TIMEOUT)

    def delete(self,
               model,
               portal="private",
               id: str = None) -> Response:
        """Delete a record by ID.

        Parameters
        ----------
        model   : Model name string or ``ModelType`` member, e.g. ``'session'``.
        portal  : ``'private'`` (default) or ``'public'``, or ``PortalType`` member.
        id      : UUID of the record to delete (required).
        """
        if id is None:
            raise ValueError("'id' is required to delete a record.")
        model = _resolve_model(model)
        portal = _resolve_portal(portal)
        app = _MODEL_TO_APP[model]
        url = self._build_url(portal, app, model, id)
        return self._session.delete(url, timeout=self.DEFAULT_TIMEOUT)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    EXPORT_TIMEOUT: int = 90  # seconds; the server builds the whole export per request

    def export_project(self, project_id: str, background: bool = False,
                       poll_interval: float = 5.0, timeout: float = 3600) -> dict:
        """Export a project as the server's versioned JSON export.

        Returns the same payload as the JSON download on the BrainSTEM website
        (format documented in the server's ``docs/project-export-format.md``)::

            {
              "export_info": {"format_version", "exported_at", "scope",
                              "project_id", "project_ids", "session_id",
                              "lab_resources", "restricted", "record_count",
                              "counts"},
              "records": {"stem.project": [...], "stem.subject": [...], ...}
            }

        Each record has the shape ``{"model", "pk", "fields"}``. Exporting
        requires read access to the project.

        Parameters
        ----------
        project_id    : UUID of the project to export.
        background    : When ``True``, queue the export as a server-side job,
                        wait for it to finish and download the result. Use this
                        for large projects, which can exceed the server's
                        30-second request limit. The server also emails you
                        when the job finishes.
        poll_interval : Seconds between job status checks (background only).
        timeout       : Maximum seconds to wait for the job (background only).
        """
        return self._export("project", project_id, background, poll_interval, timeout)

    def export_session(self, session_id: str, background: bool = False,
                       poll_interval: float = 5.0, timeout: float = 3600) -> dict:
        """Export one session and everything it touches: the content of one NWB file.

        Returns the same format as ``export_project`` (``export_info.scope`` is
        ``"session"``), holding the session with its data acquisitions,
        manipulations, behaviors and epochs; the subjects and specimen sets
        linked to it with their full procedure and log history; the session's
        projects; and the lab resources, catalog entries and users these
        reference. Only records you can read are included, in any of the
        session's projects.

        A subject's procedure history is complete, including procedures after
        the session, so filter by date where that matters. Exporting requires
        read access to one of the session's projects.

        Parameters are the same as for ``export_project``, with
        ``session_id`` the UUID of the session to export.
        """
        return self._export("session", session_id, background, poll_interval, timeout)

    def _export(self, model: str, record_id: str, background: bool,
                poll_interval: float, timeout: float) -> dict:
        """Run a direct or background export of a project or session record."""
        if not record_id:
            raise ValueError(f"'{model}_id' is required to export a {model}.")
        url = self._build_url("private", "stem", model, record_id, "export/")

        if not background:
            # Bypass the session's automatic retries: a timed-out export would be
            # rebuilt up to three more times, each counting against the export rate limit.
            resp = requests.get(url, headers=self._session.headers, timeout=self.EXPORT_TIMEOUT)
            if resp.status_code in (503, 504):
                raise ExportError(
                    "The export did not finish within the server's request time limit. "
                    f"Use export_{model}(..., background=True) for large exports."
                )
            self._check_export_response(resp, model)
            return resp.json()

        resp = self._session.post(url, timeout=self.DEFAULT_TIMEOUT)
        self._check_export_response(resp, model)
        job = resp.json()["export_job"]
        job_url = self._build_url("private", "stem", model, record_id,
                                  f"export-jobs/{job['id']}/")

        deadline = time.monotonic() + timeout
        while job["status"] in ("pending", "running"):
            if time.monotonic() > deadline:
                raise ExportError(
                    f"Export job {job['id']} did not finish within {timeout} seconds "
                    f"(status: {job['status']}, {job.get('progress_percent', 0)}%)."
                )
            time.sleep(poll_interval)
            job = self._get_json(job_url)["export_job"]

        if job["status"] != "completed":
            raise ExportError(job.get("error_message") or f"Export job ended as '{job['status']}'.")

        resp = self._session.get(self._base_url + job["download_url"].lstrip("/"),
                                 timeout=self.EXPORT_TIMEOUT)
        self._check_export_response(resp, model)
        content = resp.content
        if content[:2] == b"\x1f\x8b":  # gzip magic number
            expected = job.get("file_sha256")
            if expected and hashlib.sha256(content).hexdigest() != expected:
                raise ExportError(f"Export job {job['id']}: downloaded file failed its checksum.")
            content = gzip.decompress(content)
        return json.loads(content)

    def _check_export_response(self, resp: Response, model: str) -> None:
        """Turn export endpoint errors into clear exceptions."""
        if resp.ok:
            return
        if resp.status_code == 401:
            raise AuthenticationError(
                "API token is invalid or expired. Run `brainstem login` to re-authenticate."
            )
        is_json = "json" in resp.headers.get("Content-Type", "")
        if resp.status_code == 404:
            if not is_json:
                raise ExportError(f"This BrainSTEM server does not support {model} export yet.")
            # The API answers 404, not 403, when the record exists but you cannot read it.
            raise ExportError(f"The {model} was not found, or you do not have read access to it.")
        if resp.status_code == 403:
            raise ExportError(f"You do not have permission to export this {model}.")
        if resp.status_code in (400, 409, 410, 429) and is_json:
            raise ExportError(resp.json().get("detail", resp.reason))
        resp.raise_for_status()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    # ------------------------------------------------------------------
    # Convenience loaders  (mirror the MATLAB load_* helpers)
    # ------------------------------------------------------------------

    def _convenience_load(self, model, default_include, filter_map,
                          portal, id, filters, sort, include, limit, offset,
                          load_all, **field_kwargs):
        """Shared implementation for all convenience loaders."""
        unknown = set(field_kwargs) - set(filter_map)
        if unknown:
            raise TypeError(
                f"Unexpected keyword argument(s): {', '.join(sorted(unknown))}"
            )
        merged_filters = dict(filters or {})
        for kwarg, api_field in filter_map.items():
            value = field_kwargs.get(kwarg)
            if value is not None:
                merged_filters[api_field] = value
        return self.load(
            model,
            portal=portal,
            id=id,
            filters=merged_filters or None,
            sort=sort,
            include=include if include is not None else default_include,
            limit=limit,
            offset=offset,
            load_all=load_all,
        )

    def load_project(self, portal="private", id: str = None,
                     name: str = None, sessions: str = None,
                     subjects: str = None, tags: str = None,
                     filters: dict = None, sort: list = None,
                     include: list = None, limit: int = None,
                     offset: int = None, load_all: bool = False):
        """Load project(s). Embeds sessions, subjects, collections and cohorts by default.

        Parameters
        ----------
        name     : Filter by project name (case-insensitive contains).
        sessions : Filter by session UUID.
        subjects : Filter by subject UUID.
        tags     : Filter by numeric tag id (the server does not filter by tag name).
        """
        return self._convenience_load(
            "project",
            default_include=["sessions", "subjects", "collections", "cohorts"],
            filter_map={"name": "name.icontains", "sessions": "sessions",
                        "subjects": "subjects", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, sessions=sessions, subjects=subjects, tags=tags,
        )

    def load_subject(self, portal="private", id: str = None,
                     name: str = None, projects: str = None,
                     strain: str = None, sex: str = None, tags: str = None,
                     filters: dict = None, sort: list = None,
                     include: list = None, limit: int = None,
                     offset: int = None, load_all: bool = False):
        """Load subject(s). Embeds procedures and subjectlogs by default.

        Parameters
        ----------
        name     : Filter by subject name (case-insensitive contains).
        projects : Filter by project UUID.
        strain   : Filter by strain UUID.
        sex      : Filter by sex (``'M'``, ``'F'``, or ``'U'``).
        tags     : Filter by numeric tag id (the server does not filter by tag name).
        """
        return self._convenience_load(
            "subject",
            default_include=["procedures", "subjectlogs"],
            filter_map={"name": "name.icontains", "projects": "projects",
                        "strain": "strain", "sex": "sex", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, projects=projects, strain=strain, sex=sex, tags=tags,
        )

    def load_session(self, portal="private", id: str = None,
                     name: str = None, projects: str = None,
                     datastorage: str = None, tags: str = None,
                     filters: dict = None, sort: list = None,
                     include: list = None, limit: int = None,
                     offset: int = None, load_all: bool = False):
        """Load session(s). Embeds dataacquisition, behaviors, manipulations and epochs by default.

        Parameters
        ----------
        name        : Filter by session name (case-insensitive contains).
        projects    : Filter by project UUID.
        datastorage : Filter by data storage UUID.
        tags        : Filter by numeric tag id (the server does not filter by tag name).
        """
        return self._convenience_load(
            "session",
            default_include=["dataacquisition", "behaviors", "manipulations", "epochs"],
            filter_map={"name": "name.icontains", "projects": "projects",
                        "datastorage": "datastorage", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, projects=projects, datastorage=datastorage, tags=tags,
        )

    def load_collection(self, portal="private", id: str = None,
                        name: str = None, tags: str = None,
                        filters: dict = None, sort: list = None,
                        include: list = None, limit: int = None,
                        offset: int = None, load_all: bool = False):
        """Load collection(s). Embeds sessions by default.

        Parameters
        ----------
        name : Filter by collection name (case-insensitive contains).
        tags : Filter by numeric tag id (the server does not filter by tag name).
        """
        return self._convenience_load(
            "collection",
            default_include=["sessions"],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_cohort(self, portal="private", id: str = None,
                    name: str = None, tags: str = None,
                    filters: dict = None, sort: list = None,
                    include: list = None, limit: int = None,
                    offset: int = None, load_all: bool = False):
        """Load cohort(s). Embeds subjects by default.

        Parameters
        ----------
        name : Filter by cohort name (case-insensitive contains).
        tags : Filter by numeric tag id (the server does not filter by tag name).
        """
        return self._convenience_load(
            "cohort",
            default_include=["subjects"],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_behavior(self, portal="private", id: str = None,
                      session: str = None,
                      filters: dict = None, sort: list = None,
                      include: list = None, limit: int = None,
                      offset: int = None, load_all: bool = False):
        """Load behavior record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        """
        return self._convenience_load(
            "behavior",
            default_include=[],
            filter_map={"session": "session"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session,
        )

    def load_dataacquisition(self, portal="private", id: str = None,
                             session: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load data acquisition record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        """
        return self._convenience_load(
            "dataacquisition",
            default_include=[],
            filter_map={"session": "session"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session,
        )

    def load_manipulation(self, portal="private", id: str = None,
                          session: str = None,
                          filters: dict = None, sort: list = None,
                          include: list = None, limit: int = None,
                          offset: int = None, load_all: bool = False):
        """Load manipulation record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        """
        return self._convenience_load(
            "manipulation",
            default_include=[],
            filter_map={"session": "session"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session,
        )

    def load_procedure(self, portal="private", id: str = None,
                       subject: str = None,
                       filters: dict = None, sort: list = None,
                       include: list = None, limit: int = None,
                       offset: int = None, load_all: bool = False):
        """Load procedure record(s).

        Parameters
        ----------
        subject : Filter by subject UUID.
        """
        return self._convenience_load(
            "procedure",
            default_include=[],
            filter_map={"subject": "subject"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            subject=subject,
        )

    def load_procedurelog(self, portal="private", id: str = None,
                          procedure: str = None,
                          filters: dict = None, sort: list = None,
                          include: list = None, limit: int = None,
                          offset: int = None, load_all: bool = False):
        """Load procedure log record(s).

        Parameters
        ----------
        procedure : Filter by procedure UUID.
        """
        return self._convenience_load(
            "procedurelog",
            default_include=[],
            filter_map={"procedure": "procedure"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            procedure=procedure,
        )

    def load_subjectlog(self, portal="private", id: str = None,
                        subject: str = None,
                        filters: dict = None, sort: list = None,
                        include: list = None, limit: int = None,
                        offset: int = None, load_all: bool = False):
        """Load subject log record(s).

        Parameters
        ----------
        subject : Filter by subject UUID.
        """
        return self._convenience_load(
            "subjectlog",
            default_include=[],
            filter_map={"subject": "subject"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            subject=subject,
        )

    def load_equipment(self, portal="private", id: str = None,
                       name: str = None, setup: str = None,
                       filters: dict = None, sort: list = None,
                       include: list = None, limit: int = None,
                       offset: int = None, load_all: bool = False):
        """Load equipment record(s).

        Parameters
        ----------
        name  : Filter by equipment name (case-insensitive contains).
        setup : Filter by setup UUID.
        """
        return self._convenience_load(
            "equipment",
            default_include=[],
            filter_map={"name": "name.icontains", "setup": "setup"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, setup=setup,
        )

    def load_consumablestock(self, portal="private", id: str = None,
                             inventory: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load consumable stock record(s).

        Parameters
        ----------
        inventory : Filter by inventory UUID.
        """
        return self._convenience_load(
            "consumablestock",
            default_include=[],
            filter_map={"inventory": "inventory"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            inventory=inventory,
        )

    def load_behavioralassay(self, portal="private", id: str = None,
                             name: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load behavioral assay record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "behavioralassay",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )

    def load_datastorage(self, portal="private", id: str = None,
                         name: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Load data storage record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "datastorage",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )

    def load_setup(self, portal="private", id: str = None,
                   name: str = None,
                   filters: dict = None, sort: list = None,
                   include: list = None, limit: int = None,
                   offset: int = None, load_all: bool = False):
        """Load setup record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "setup",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )

    def load_hardwaredevice(self, portal="private", id: str = None,
                            name: str = None,
                            filters: dict = None, sort: list = None,
                            include: list = None, limit: int = None,
                            offset: int = None, load_all: bool = False):
        """Load hardware device record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "hardwaredevice",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )

    def load_brainregion(self, portal="private", id: str = None,
                         name: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Deprecated: use ``load_anatomicalregion``, which this calls.

        Brain regions are ``anatomicalregion`` records; the response holds them
        under ``anatomical_regions``.

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        warnings.warn(
            "load_brainregion() is deprecated; use load_anatomicalregion().",
            FutureWarning, stacklevel=2,
        )
        return self.load_anatomicalregion(
            portal=portal, id=id, name=name, filters=filters, sort=sort,
            include=include, limit=limit, offset=offset, load_all=load_all,
        )

    def load_anatomicalregion(self, portal="private", id: str = None,
                              name: str = None, acronym: str = None,
                              reference: str = None,
                              filters: dict = None, sort: list = None,
                              include: list = None, limit: int = None,
                              offset: int = None, load_all: bool = False):
        """Load anatomical (brain) region record(s).

        Parameters
        ----------
        name      : Filter by name (case-insensitive contains).
        acronym   : Filter by acronym (case-insensitive exact match), e.g. ``'CA1'``.
        reference : Filter by anatomical reference (atlas) UUID.
        """
        return self._convenience_load(
            "anatomicalregion",
            default_include=[],
            filter_map={"name": "name.icontains", "acronym": "acronym.iexact",
                        "reference": "reference"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, acronym=acronym, reference=reference,
        )

    def load_anatomicalregion_descendants(self, id: str, portal="private") -> Response:
        """Load every region below anatomical region *id* in its atlas.

        Returns the raw ``Response``; its JSON is
        ``{"anatomical_regions": [{"id", "name", "acronym", "parent_acronym",
        "is_obsolete", "depth"}, ...]}``, ordered by depth (1 = direct child).
        Atlases without a hierarchy return an empty list.
        """
        if not id:
            raise ValueError("'id' is required to load the descendants of a region.")
        url = self._build_url(_resolve_portal(portal), "taxonomies", "anatomicalregion",
                              id, "descendants/")
        return self._session.get(url, timeout=self.DEFAULT_TIMEOUT)

    def load_species(self, portal="private", id: str = None,
                     name: str = None,
                     filters: dict = None, sort: list = None,
                     include: list = None, limit: int = None,
                     offset: int = None, load_all: bool = False,
                     popular_name: str = None):
        """Load species record(s).

        Parameters
        ----------
        name         : Filter by scientific name (case-insensitive contains).
        popular_name : Filter by common name (case-insensitive contains), e.g.
                       ``'mouse'``. Needs a server with the specimen release.
        """
        return self._convenience_load(
            "species",
            default_include=[],
            filter_map={"name": "name.icontains",
                        "popular_name": "popular_name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, popular_name=popular_name,
        )

    def load_strain(self, portal="private", id: str = None,
                    name: str = None, species: str = None,
                    filters: dict = None, sort: list = None,
                    include: list = None, limit: int = None,
                    offset: int = None, load_all: bool = False,
                    popular_name: str = None):
        """Load strain record(s).

        Parameters
        ----------
        name         : Filter by name (case-insensitive contains).
        species      : Filter by species UUID.
        popular_name : Filter by common name (case-insensitive contains).
                       Needs a server with the specimen release.
        """
        return self._convenience_load(
            "strain",
            default_include=[],
            filter_map={"name": "name.icontains", "species": "species",
                        "popular_name": "popular_name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, species=species, popular_name=popular_name,
        )

    def load_publication(self, portal="private", id: str = None,
                         name: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Load publication record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "publication",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )

    def load_laboratory(self, portal="private", id: str = None,
                        name: str = None,
                        filters: dict = None, sort: list = None,
                        include: list = None, limit: int = None,
                        offset: int = None, load_all: bool = False):
        """Load laboratory record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        """
        return self._convenience_load(
            "laboratory",
            default_include=[],
            filter_map={"name": "name.icontains"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name,
        )
