# BrainSTEM Python API Tools

The `brainstem_python_api_tools` is a Python toolset for interacting with the [BrainSTEM](https://www.brainstem.org/) API, designed for researchers and developers working with neuroscience data.

## Installation
You can install the package using `pip`:
```bash
pip install brainstem_python_api_tools
```

## Getting Started
To get started with the BrainSTEM API tools, please refer to the tutorial script provided:

- **Tutorial:** `brainstem_api_tutorial.py`

The tutorial demonstrates how to:

- **Authenticate:** Load the client and authenticate using your credentials.
- **Loading Data:** Load sessions and filter data using flexible options.
- **Updating Entries:** Modify existing models and update them in the database.
- **Creating Entries:** Submit new data entries with required fields.
- **Loading Public Data:** Access public projects and data using the public portal.

## Example Usage
```python
from brainstem_api_tools import BrainstemClient

client = BrainstemClient()
response = client.load_model('session', sort=['name'])
print(response.json())
```

## Contributing
Contributions are welcome! Feel free to open issues or submit pull requests on [GitHub](https://github.com/brainstem-org/brainstem_python_api_tools).

## License
This project is licensed under the MIT License. See the `LICENSE` file for more details.