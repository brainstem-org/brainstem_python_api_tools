from brainstem_api_client import BrainstemClient
from tools.nwb import get_dataset_metadata, write_conversion_specification_yml

# initialize token
client = BrainstemClient(token="")

dataset_id = "160caf7b-cee7-4034-8529-aee846c4dc71"
dataset_metadata = get_dataset_metadata(client=client, dataset_id=dataset_id)

yml_file_path = "output.yaml"
write_conversion_specification_yml(
    yml_file_path=yml_file_path,
    dataset_metadata=dataset_metadata,
    interface_properties=dict(stream_name="Signals CH"),
    conversion_options=dict(stub_test=True),
)
