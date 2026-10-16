# Changelog

## 2.1.0 (unreleased)

Server requirements: BrainSTEM with the `specimen-1` data model, the project/session export API
(format 2.1) and the public agent reference (`/reference/`, format 1.x).

### Added
- `export_project()` and `export_session()`: download a project or session export (format 2.1),
  directly or as a background job (`background=True`) that the client polls and downloads.
  Problems raise `ExportError`.
- `agent_reference(page)` and the `brainstem reference <page>` command: read the server's public
  agent reference without a token.
- `BrainstemClient(anonymous=True)`: read public data without logging in.
- Routes for the specimen data model (`specimenset`, `specimen`, `specimenprocedure`,
  `specimenproceduretemplate`, `specimenlog`), interfaces, materials, episodes, coordinates and
  anatomical references; `brainregion` remains as a deprecated alias of `anatomicalregion`.
- `limit`/`offset` and `--per-page`/`--page` paging, `load_all=True` merging of sideloaded lists.

### Changed
- Device-flow errors returned by the server with a non-2xx status (`invalid_device_code`,
  `token_error`) raise `AuthenticationError` instead of `requests.HTTPError`.

## 2.0.0

- Browser-based device authorization with 2FA; token cached at `~/.config/brainstem/token`.
- `brainstem` command-line interface (`login`, `logout`, `load`, `save`, `delete`).
