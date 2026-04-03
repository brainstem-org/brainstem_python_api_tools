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