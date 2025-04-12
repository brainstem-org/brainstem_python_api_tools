import os

from neuroconv import run_conversion_from_yaml
from pynwb import NWBHDF5IO

from brainstem_api_client import BrainstemClient
from tools.nwb import get_dataset_metadata, write_conversion_specification_yml

# Initialize the BrainstemClient client using a personal access token.
# If the access token is not set in the STEM_TOKEN environment variable,
# the user will be prompted to enter their username and password.
token = os.environ.get("STEM_TOKEN")
client = BrainstemClient(token=token)

dataset_id = "160caf7b-cee7-4034-8529-aee846c4dc71"
dataset_metadata = get_dataset_metadata(client=client, dataset_id=dataset_id)

yml_file_path = "output.yaml"
write_conversion_specification_yml(
    yml_file_path=yml_file_path,
    dataset_metadata=dataset_metadata,
    interface_properties=dict(stream_name="Signals CH"),
    conversion_options=dict(stub_test=True),
)

run_conversion_from_yaml(
    specification_file_path=yml_file_path,
    data_folder_path="/Users/weian/catalystneuro/data/ephy_testing_data/",
    output_folder_path="/Volumes/t7-ssd/nwbfiles",
    overwrite=True,
)

with NWBHDF5IO("/Volumes/t7-ssd/nwbfiles/TestSession1.nwb") as io:
    nwbfile = io.read()
    print(nwbfile.acquisition)
