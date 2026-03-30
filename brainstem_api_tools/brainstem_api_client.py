import os
import stat
import time
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
    "project": "stem",
    "subject": "stem",
    "session": "stem",
    "collection": "stem",
    "cohort": "stem",
    "breeding": "stem",
    "project_membership_invitation": "stem",
    "project_group_membership_invitation": "stem",
    # modules
    "procedure": "modules",
    "behavior": "modules",
    "dataacquisition": "modules",
    "manipulation": "modules",
    "equipment": "modules",
    "consumablestock": "modules",
    "procedurelog": "modules",
    "subjectlog": "modules",
    # personal_attributes
    "behavioralassay": "personal_attributes",
    "datastorage": "personal_attributes",
    "inventory": "personal_attributes",
    "license": "personal_attributes",
    "protocol": "personal_attributes",
    "setup": "personal_attributes",
    # resources
    "consumable": "resources",
    "hardwaredevice": "resources",
    "supplier": "resources",
    # taxonomies
    "behavioralcategory": "taxonomies",
    "behavioralparadigm": "taxonomies",
    "brainregion": "taxonomies",
    "regulatoryauthority": "taxonomies",
    "setuptype": "taxonomies",
    "species": "taxonomies",
    "strain": "taxonomies",
    "strainapproval": "taxonomies",
    # dissemination
    "journal": "dissemination",
    "journalapproval": "dissemination",
    "publication": "dissemination",
    # users
    "group": "users",
    "group_membership_invitation": "users",
    "group_membership_request": "users",
    "laboratory": "users",
    "user": "users",
}

_TOKEN_FILE = Path.home() / ".config" / "brainstem" / "token"

# Derived from _MODEL_TO_APP so there is exactly one source of truth.
ModelType = Enum("ModelType", {k: k for k in _MODEL_TO_APP})  # type: ignore[misc]

_VALID_PORTALS = {"private", "public", "super"}


def _resolve_model(model) -> str:
    """Accept a plain string or a ModelType member and return the string value."""
    if isinstance(model, ModelType):
        return model.value
    model = str(model)
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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BrainstemClient:

    BASE_URL = "https://www.brainstem.org/"
    DEFAULT_TIMEOUT: int = 30  # seconds; applied to all HTTP calls

    def __init__(
        self,
        token: str = None,
        headless: bool = False,
        url: str = None,
    ) -> None:
        base = (url.rstrip("/") + "/") if url else self.BASE_URL
        self._address = base + "api/"
        self._session = requests.Session()

        # Automatically retry transient server errors
        _retry = Retry(total=3, backoff_factor=0.5, status_forcelist={502, 503, 504})
        self._session.mount("https://", HTTPAdapter(max_retries=_retry))
        self._session.mount("http://", HTTPAdapter(max_retries=_retry))

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
        include  : Related models to embed, e.g. ``['dataacquisition', 'behaviors']``.
        limit    : Max records per page (API maximum: 100).
        offset   : Number of records to skip (for pagination).
        load_all : When ``True``, automatically follow pagination and return a
                   combined ``dict`` with all records merged under the model key.
                   When ``False`` (default), returns the raw ``Response``.
        """
        model = _resolve_model(model)
        portal = _resolve_portal(portal)
        app = _MODEL_TO_APP[model]
        url = self._build_url(portal, app, model, id, options if id else None)

        params = {}
        if not id:
            for key, val in (filters or {}).items():
                params[f"filter{{{key}}}"] = val
            for field in (sort or []):
                params.setdefault("sort[]", []).append(field)
            for rel in (include or []):
                params.setdefault("include[]", []).append(f"{rel}.*")
            if limit is not None:
                params["limit"] = limit
            if offset is not None:
                params["offset"] = offset

        if not load_all:
            return self._session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)

        # --- auto-paginate and merge all pages ---
        page_size = limit or 100
        params["limit"] = page_size
        params.setdefault("offset", offset or 0)

        combined: dict = {}
        records_key: str = None

        while True:
            resp = self._session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
            if resp.status_code == 401:
                raise AuthenticationError(
                    "API token is invalid or expired. Run `brainstem login` to re-authenticate."
                )
            resp.raise_for_status()
            data = resp.json()

            if records_key is None:
                # Detect the list key (e.g. 'sessions', 'projects')
                records_key = next(
                    (k for k, v in data.items() if isinstance(v, list)), None
                )
                combined = {k: v for k, v in data.items() if k != records_key}
                combined[records_key] = []

            combined[records_key].extend(data.get(records_key, []))
            total = data.get("count", len(combined[records_key]))

            if len(combined[records_key]) >= total:
                break

            params["offset"] = params.get("offset", 0) + page_size

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
            if value:
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
        tags     : Filter by tag.
        """
        return self._convenience_load(
            "project",
            default_include=["sessions", "subjects", "collections", "cohorts"],
            filter_map={"name": "name.icontains", "sessions": "sessions.id",
                        "subjects": "subjects.id", "tags": "tags"},
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
        tags     : Filter by tag.
        """
        return self._convenience_load(
            "subject",
            default_include=["procedures", "subjectlogs"],
            filter_map={"name": "name.icontains", "projects": "projects.id",
                        "strain": "strain.id", "sex": "sex", "tags": "tags"},
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
        tags        : Filter by tag.
        """
        return self._convenience_load(
            "session",
            default_include=["dataacquisition", "behaviors", "manipulations", "epochs"],
            filter_map={"name": "name.icontains", "projects": "projects.id",
                        "datastorage": "datastorage.id", "tags": "tags"},
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
        tags : Filter by tag.
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
        tags : Filter by tag.
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
                      session: str = None, tags: str = None,
                      filters: dict = None, sort: list = None,
                      include: list = None, limit: int = None,
                      offset: int = None, load_all: bool = False):
        """Load behavior record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "behavior",
            default_include=[],
            filter_map={"session": "session.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session, tags=tags,
        )

    def load_dataacquisition(self, portal="private", id: str = None,
                             session: str = None, tags: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load data acquisition record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "dataacquisition",
            default_include=[],
            filter_map={"session": "session.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session, tags=tags,
        )

    def load_manipulation(self, portal="private", id: str = None,
                          session: str = None, tags: str = None,
                          filters: dict = None, sort: list = None,
                          include: list = None, limit: int = None,
                          offset: int = None, load_all: bool = False):
        """Load manipulation record(s).

        Parameters
        ----------
        session : Filter by session UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "manipulation",
            default_include=[],
            filter_map={"session": "session.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            session=session, tags=tags,
        )

    def load_procedure(self, portal="private", id: str = None,
                       subject: str = None, tags: str = None,
                       filters: dict = None, sort: list = None,
                       include: list = None, limit: int = None,
                       offset: int = None, load_all: bool = False):
        """Load procedure record(s).

        Parameters
        ----------
        subject : Filter by subject UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "procedure",
            default_include=[],
            filter_map={"subject": "subject.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            subject=subject, tags=tags,
        )

    def load_procedurelog(self, portal="private", id: str = None,
                          procedure: str = None, tags: str = None,
                          filters: dict = None, sort: list = None,
                          include: list = None, limit: int = None,
                          offset: int = None, load_all: bool = False):
        """Load procedure log record(s).

        Parameters
        ----------
        procedure : Filter by procedure UUID.
        tags      : Filter by tag.
        """
        return self._convenience_load(
            "procedurelog",
            default_include=[],
            filter_map={"procedure": "procedure.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            procedure=procedure, tags=tags,
        )

    def load_subjectlog(self, portal="private", id: str = None,
                        subject: str = None, tags: str = None,
                        filters: dict = None, sort: list = None,
                        include: list = None, limit: int = None,
                        offset: int = None, load_all: bool = False):
        """Load subject log record(s).

        Parameters
        ----------
        subject : Filter by subject UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "subjectlog",
            default_include=[],
            filter_map={"subject": "subject.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            subject=subject, tags=tags,
        )

    def load_equipment(self, portal="private", id: str = None,
                       name: str = None, setup: str = None, tags: str = None,
                       filters: dict = None, sort: list = None,
                       include: list = None, limit: int = None,
                       offset: int = None, load_all: bool = False):
        """Load equipment record(s).

        Parameters
        ----------
        name  : Filter by equipment name (case-insensitive contains).
        setup : Filter by setup UUID.
        tags  : Filter by tag.
        """
        return self._convenience_load(
            "equipment",
            default_include=[],
            filter_map={"name": "name.icontains", "setup": "setup.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, setup=setup, tags=tags,
        )

    def load_consumablestock(self, portal="private", id: str = None,
                             tags: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load consumable stock record(s).

        Parameters
        ----------
        tags : Filter by tag.
        """
        return self._convenience_load(
            "consumablestock",
            default_include=[],
            filter_map={"tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            tags=tags,
        )

    def load_behavioralassay(self, portal="private", id: str = None,
                             name: str = None, tags: str = None,
                             filters: dict = None, sort: list = None,
                             include: list = None, limit: int = None,
                             offset: int = None, load_all: bool = False):
        """Load behavioral assay record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "behavioralassay",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_datastorage(self, portal="private", id: str = None,
                         name: str = None, tags: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Load data storage record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "datastorage",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_setup(self, portal="private", id: str = None,
                   name: str = None, tags: str = None,
                   filters: dict = None, sort: list = None,
                   include: list = None, limit: int = None,
                   offset: int = None, load_all: bool = False):
        """Load setup record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "setup",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_hardwaredevice(self, portal="private", id: str = None,
                            name: str = None, tags: str = None,
                            filters: dict = None, sort: list = None,
                            include: list = None, limit: int = None,
                            offset: int = None, load_all: bool = False):
        """Load hardware device record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "hardwaredevice",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_brainregion(self, portal="private", id: str = None,
                         name: str = None, tags: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Load brain region record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "brainregion",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_species(self, portal="private", id: str = None,
                     name: str = None, tags: str = None,
                     filters: dict = None, sort: list = None,
                     include: list = None, limit: int = None,
                     offset: int = None, load_all: bool = False):
        """Load species record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "species",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_strain(self, portal="private", id: str = None,
                    name: str = None, species: str = None, tags: str = None,
                    filters: dict = None, sort: list = None,
                    include: list = None, limit: int = None,
                    offset: int = None, load_all: bool = False):
        """Load strain record(s).

        Parameters
        ----------
        name    : Filter by name (case-insensitive contains).
        species : Filter by species UUID.
        tags    : Filter by tag.
        """
        return self._convenience_load(
            "strain",
            default_include=[],
            filter_map={"name": "name.icontains", "species": "species.id", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, species=species, tags=tags,
        )

    def load_publication(self, portal="private", id: str = None,
                         name: str = None, tags: str = None,
                         filters: dict = None, sort: list = None,
                         include: list = None, limit: int = None,
                         offset: int = None, load_all: bool = False):
        """Load publication record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "publication",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )

    def load_laboratory(self, portal="private", id: str = None,
                        name: str = None, tags: str = None,
                        filters: dict = None, sort: list = None,
                        include: list = None, limit: int = None,
                        offset: int = None, load_all: bool = False):
        """Load laboratory record(s).

        Parameters
        ----------
        name : Filter by name (case-insensitive contains).
        tags : Filter by tag.
        """
        return self._convenience_load(
            "laboratory",
            default_include=[],
            filter_map={"name": "name.icontains", "tags": "tags"},
            portal=portal, id=id, filters=filters, sort=sort, include=include,
            limit=limit, offset=offset, load_all=load_all,
            name=name, tags=tags,
        )
