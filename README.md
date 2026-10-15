# BrainSTEM Python API Tools

The `brainstem_python_api_tools` is a Python toolset for interacting with the [BrainSTEM](https://www.brainstem.org/) API, designed for researchers and developers working with neuroscience data.

## Installation
You can install the package using `pip`:
```bash
pip install brainstem_python_api_tools
```

## Authentication

Authentication uses a **browser-based device authorization flow** that supports two-factor authentication (2FA). No credentials are entered into the tool itself.

```python
from brainstem_api_tools import BrainstemClient

# First run: opens a browser window for secure login.
# The token is cached at ~/.config/brainstem/token and reused automatically.
client = BrainstemClient()
```

To skip the browser flow, pass a token directly:
```python
client = BrainstemClient(token="YOUR_TOKEN")
```

For headless environments (no browser available):
```python
client = BrainstemClient(headless=True)  # prints a URL + code to enter manually
```

To connect to a different server (e.g. a local development instance):
```python
client = BrainstemClient(url="http://127.0.0.1:8000/")
```

> **Security note:** The cached token file is stored with owner-read-only permissions (`0600`). Treat it like a password and do not commit it to version control.

## Getting Started
To get started with the BrainSTEM API tools, please refer to the tutorial script provided:

- **Tutorial:** `brainstem_api_tutorial.py`

The tutorial demonstrates how to:

- **Authenticate:** Load the client and authenticate via your browser.
- **Load Data:** Load sessions and filter data using flexible options.
- **Paginate:** Retrieve large datasets using `limit` / `offset` or `load_all=True`.
- **Convenience Loaders:** Use `load_session()`, `load_subject()`, etc. for common queries.
- **Update Entries:** Modify existing records and update them in the database.
- **Create Entries:** Submit new data entries with required fields.
- **Delete Entries:** Remove records by ID.
- **Load Public Data:** Access public projects and data using the public portal.

## Example Usage
```python
from brainstem_api_tools import BrainstemClient

client = BrainstemClient()

# Load sessions sorted by name
response = client.load('session', sort=['name'])
print(response.json())

# Filter and include related data
response = client.load(
    'session',
    filters={'name.icontains': 'Rat'},
    sort=['-name'],
    include=['projects'],
)

# Paginate results (manual)
page2 = client.load('session', limit=20, offset=20).json()

# Auto-paginate — fetches every page and returns a merged dict
all_sessions = client.load('session', load_all=True)

# Convenience loaders — sensible defaults with named filter kwargs
# load_session embeds dataacquisition, behaviors, manipulations, epochs
sessions = client.load_session(name='Rat', load_all=True)

# load_subject embeds procedures and subjectlogs
subjects = client.load_subject(sex='M', projects='<project-uuid>', load_all=True)

# load_project embeds sessions, subjects, collections, cohorts
projects = client.load_project(name='MyProject')

# load_behavior / load_dataacquisition / load_manipulation scope by session UUID
behaviors = client.load_behavior(session='<session-uuid>', load_all=True)

# load_procedure scopes by subject UUID
procedures = client.load_procedure(subject='<subject-uuid>', load_all=True)

# Create a record
client.save('session', data={'name': 'New session', 'projects': ['<project-uuid>']})

# Update a record
client.save('session', id='<session-uuid>', data={'description': 'updated'})

# Delete a record
client.delete('session', id='<session-uuid>')
```

## Exporting projects and sessions

`export_project()` returns a whole project as one JSON-serializable dict. It is the same file as the JSON download on the BrainSTEM website (**Project → Download → JSON**). Use it for backups, NWB conversion, external integrations or analysis pipelines. You need read access to the project.

```python
import json

export = client.export_project('<project-uuid>')

print(export['export_info']['format_version'], export['export_info']['counts'])
for record in export['records']['stem.session']:
    print(record['pk'], record['fields']['name'])

with open('project_backup.json', 'w') as f:
    json.dump(export, f)
```

### Session exports

`export_session()` exports one session and everything it touches: the content of one NWB file. You need read access to one of the session's projects.

```python
export = client.export_session('<session-uuid>')
```

The file has the same format as a project export, with `export_info['scope'] == 'session'`. It contains:

- the session with its data acquisitions, manipulations, behaviors and epochs;
- the subjects and specimen sets linked to the session, with their full procedure and log history;
- the session's projects you can read (`export_info['project_ids']`; a session can belong to several);
- the lab resources, catalog entries and users these records reference.

A subject's procedure history is complete, including procedures after the session, so filter by date where that matters.

### Large exports

Large exports can take longer than the server's 30-second request limit. For those, pass `background=True`: the server builds the export as a job, the client waits for it and downloads the result, and you also get an email when it is ready.

```python
export = client.export_project('<project-uuid>', background=True)
export = client.export_session('<session-uuid>', background=True)
```

### Format

Both exports have this structure:

```text
{
  "export_info": {
    "format_version": "2.1",
    "exported_at": "<ISO 8601 UTC timestamp>",
    "scope": "project",              # or "session"
    "project_id": "<project uuid>",  # null for a session export
    "project_ids": ["<project uuid>", ...],
    "session_id": null,              # the session's uuid for a session export
    "lab_resources": "<which lab resources are included>",
    "restricted": {"personal_attributes.datastorage": [{"pk": "<uuid>", "name": "Lab server"}], ...},
    "record_count": 2344,
    "counts": {"stem.project": 1, "stem.subject": 21, ...}
  },
  "records": {
    "stem.project": [{"model": "stem.project", "pk": "<uuid>", "fields": {...}}],
    "stem.subject": [...],
    "stem.session": [...],
    ...
  }
}
```

- `records` is keyed by model label (`app_label.model_name`). Every label is always present, with an empty list when there are no such records.
- Links to other records are primary keys. Many-to-many links are sorted lists of primary keys. Referenced catalog entries (species, brain regions, suppliers, ...) and users (names only) are included in the file.
- Lab resources (setups, data storages, equipment, protocols, ...) are included when you can read them and the exported records use them. Two people exporting the same project can therefore get different lab resources. Referenced lab resources you cannot read are listed by name in `export_info['restricted']`.
- A minor format version (2.1, 2.2, ...) only adds labels and keys, so ignore any you don't recognise.

Problems raise `ExportError` with a readable message, for example when the project or session doesn't exist or you can't read it, a background job fails, or the server doesn't support exports yet.

## Command-line Interface

After installation a `brainstem` command is available in your shell.

### Authentication
```bash
# Authenticate (opens browser) and cache token
brainstem login

# Headless — prints URL + code instead of opening browser
brainstem login --headless

# Connect to a local dev server
brainstem login --url http://127.0.0.1:8000/

# Remove cached token
brainstem logout
```

### Loading data
```bash
# Load all sessions (private portal)
brainstem load session

# Filter, sort and embed related data
brainstem load session --filters name.icontains=Rat --sort -name --include projects

# Load a single record by UUID
brainstem load session --id <uuid>

# Manual pagination
brainstem load session --limit 20 --offset 20

# Public portal
brainstem load project --portal public
```

### Creating and updating records
```bash
# Create a new session
brainstem save session --data '{"name":"New session","projects":["<uuid>"]}'

# Update an existing record
brainstem save session --id <uuid> --data '{"description":"updated"}'
```

### Deleting records
```bash
brainstem delete session --id <uuid>
```

All subcommands accept `--token`, `--headless`, and `--url` to override defaults.

## Contributing
Contributions are welcome! Feel free to open issues or submit pull requests on GitHub.

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.