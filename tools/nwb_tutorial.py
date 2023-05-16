from brainstem_api_client import BrainstemClient
from tools.nwb import get_dataset_metadata, get_nwbfile_metadata

# initialize token
client = BrainstemClient(token="")

dataset_id = "160caf7b-cee7-4034-8529-aee846c4dc71"
dataset_metadata = get_dataset_metadata(client=client, dataset_id=dataset_id)
nwbfile_metadata = get_nwbfile_metadata(dataset_metadata=dataset_metadata)
