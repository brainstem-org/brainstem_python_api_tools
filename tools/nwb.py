from collections import defaultdict
from typing import Dict, Optional

import yaml
from bs4 import BeautifulSoup
from dateutil.parser import parse
from neuroconv.datainterfaces import interfaces_by_category
from neuroconv.utils import FilePathType

from brainstem_api_client import BrainstemClient


def get_project_metadata(client: BrainstemClient, project_id: str, portal: str = "public") -> Dict:
    project = client.load_model(model="project", portal=portal, id=project_id).json()["project"]
    project.pop("subjects")
    project.pop("datasets")
    return project


def get_experiment_data(client: BrainstemClient, experiment_data_id: str, portal: str = "public") -> Dict:
    experiment_data = client.load_model(model="experimentdata", portal=portal, id=experiment_data_id).json()["experiment_data"]
    hardware_device_id = experiment_data["hardware_device"]
    hardware_device = client.load_model(model="hardwaredevice", portal=portal, id=hardware_device_id).json()["hardware_device"]
    supplier = client.load_model(model="supplier", portal=portal, id=hardware_device["supplier"]).json()["supplier"]
    experiment_data["supplier"] = supplier
    hardware_device.pop("supplier")
    experiment_data.update(hardware_device=hardware_device)
    experiment_data.pop("dataset")
    return experiment_data


def get_data_repository(client, data_repository_id: str, portal: str = "public") -> Dict:
    data_repository = client.load_model(model="datarepository", portal=portal, id=data_repository_id).json()["data_repository"]
    return data_repository


def get_action(client, action_id: str, portal: str = "public") -> Dict:
    action = client.load_model(model="action", portal=portal, id=action_id).json()["action"]
    brain_region_id = action["brain_region"]
    brain_region = client.load_model("brainregion", portal=portal, id=brain_region_id).json()["brain_region"]
    action.update(brain_region=brain_region)
    return action


def get_subject(client: BrainstemClient, subject_id: str, portal: str = "public") -> Dict:
    subject = client.load_model(model="subject", portal=portal, id=subject_id).json()["subject"]
    strain_id = subject["strain"]
    strain = client.load_model("strain", portal=portal, id=strain_id).json()["strain"]
    species = client.load_model("species", portal=portal, id=strain["species"]).json()["species"]
    strain.pop("species")
    subject.update(strain=strain)
    subject.update(species=species)
    subject.pop("projects")
    subject.pop("actions")
    return subject


def get_dataset_metadata(client: BrainstemClient, dataset_id: str, portal: str = "public") -> Dict:
    dataset_metadata = client.load_model(model="dataset", portal=portal, id=dataset_id).json()["dataset"]
    # Update metadata with project information
    project_id = dataset_metadata["projects"][0]
    project_metadata = get_project_metadata(client=client, project_id=project_id)
    dataset_metadata.pop("projects")
    dataset_metadata["project"] = project_metadata
    # Update metadata with experiment data information
    experiment_data_id = dataset_metadata["experimentdata"][0]
    experiment_data = get_experiment_data(client=client, experiment_data_id=experiment_data_id)
    dataset_metadata.pop("experimentdata")
    dataset_metadata["experiment_data"] = experiment_data
    # Update metadata with data repository information
    if dataset_metadata["datarepositories"]:
        data_repository = get_data_repository(client=client, data_repository_id=dataset_metadata["datarepositories"][0])
        dataset_metadata.pop("datarepositories")
        dataset_metadata["data_repository"] = data_repository
    # Update metadata with subject and action information
    if experiment_data["actions"]:
        action_id = experiment_data["actions"][0]
        action = get_action(client=client, action_id=action_id)
        dataset_metadata["action"] = action
        subject_id = action["subject"]
        subject = get_subject(client=client, subject_id=subject_id)

        dataset_metadata["subject"] = subject
    return dataset_metadata


def get_ecephys_interface_from_supplier(supplier: str):
    supplier_to_interface = defaultdict()
    supplier_to_interface.update(
        BlackrockMicrosystems="Blackrock",
        CEDCambridgeElectronicdesignlimited="CED",
        IMEC="SpikeGLX",
        IntanTechnologies="Intan",
        JaneliaResearchCampus="SpikeGLX",
        Neuralynx="Neuralynx",
        OpenEphys="OpenEphys",
        PlexonInstruments="Plexon",  # sorting or recording?
        ),
    # note to remove special characters (e.g. re.sub(r'[^A-Za-z0-9\s]+', '', supplier))
    supplier = supplier.replace(" ", "")
    return supplier_to_interface.get(supplier)


def write_conversion_specification_yml(
        yml_file_path: FilePathType,
        dataset_metadata: Dict,
        interface_properties: Optional[Dict] = None,
        conversion_options: Optional[Dict] = None,
):
    """
    Write conversion specification to a yaml file.

    The resulting YAML file will follow the structure outlined below:

   ```
    conversion_options:
        stub_test: true
    data_interfaces:
        recording: OpenEphysRecordingInterface
    experiments:
        ecephys:
            metadata:
                NWBFile:
                    session_description: asd
            sessions:
                - metadata:
                    NWBFile:
                        identifier: 160caf7b-cee7-4034-8529-aee846c4dc71
                        session_id: TestSession1
                        session_start_time: '2023-05-15T14:30:00+00:00'
                    Subject:
                        date_of_birth: '2023-03-01'
                        sex: F
                        species: Mus musculus
                        strain: C57B1/6
                        subject_id: TestS1
                nwbfile_name: TestSession1.nwb
                source_data:
                    recording:
                        folder_path: openephys/OpenEphys_SampleData_1
                        stream_name: Ch
    metadata:
        NWBFile:
            experiment_description: Project description
    ```

    Parameters
    ----------
    yml_file_path : FilePathType
        The destination file path where the .yml specification file will be created.
    dataset_metadata : Dict
        The metadata for BrainSTEM dataset.
        The dataset is required to contain the start time of the recording.
    interface_properties : Dict, optional
        The interface specific properties passed as a dictionary (e.g. dict(stream_name="Signals CH").
    conversion_options: Dict, optional
        The global conversion options passed as a dictionary (e.g. dict(stub_test=True)).
    """
    assert dataset_metadata["date_time"], "The 'date_time' field should contain the start time of the recording."

    conversion_spec = dict(
        metadata=dict(),
        experiments=dict(),
        data_interfaces=dict(),
        conversion_options=dict(),
    )
    # Add global NWBFile metadata (e.g. experiment_description)
    experiment_description_html = dataset_metadata["project"]["description"]
    if experiment_description_html:
        experiment_description = BeautifulSoup(experiment_description_html, "html.parser").get_text()
        conversion_spec["metadata"].update(NWBFile=dict(experiment_description=experiment_description))

    # Add global conversion options (e.g. stub_test)
    if conversion_options:
        conversion_spec.update(dict(conversion_options=conversion_options))

    experiment_data = dataset_metadata["experiment_data"]
    # Add interface specific source data based on experiment_data
    source_data = dict(recording=dict())
    if experiment_data["type"] == "Extracellular":
        supplier_name = experiment_data["supplier"]["name"]
        interface_name = get_ecephys_interface_from_supplier(supplier=supplier_name)
        ecephys_interfaces = interfaces_by_category["ecephys"]
        interface_cls = ecephys_interfaces.get(interface_name)
        assert interface_cls, f"Could not find a matching interface for {supplier_name} supplier."
        conversion_spec["data_interfaces"].update(recording=interface_cls.__name__)

        interface_source_schema = interface_cls.get_source_schema()
        required_properties = interface_source_schema["required"]  # file_path or folder_path
        # limited for now to use only first path
        path = dataset_metadata["data_repository"]["data_protocols_json"][0]["path"]
        source_data["recording"][required_properties[0]] = path

        if interface_properties:
            # e.g. specifying the stream_name
            source_data["recording"].update(interface_properties)

        sessions = []
        ecephys_session_metadata = dict(
            nwbfile_name=f"{dataset_metadata['name']}.nwb",
            source_data=source_data,
            metadata=dict(
                NWBFile=dict(
                    session_id=dataset_metadata["name"],
                    session_start_time=parse(dataset_metadata["date_time"]).isoformat(),
                    identifier=dataset_metadata["id"],
                ),
                Subject=dict(
                    subject_id=dataset_metadata["subject"]["name"],
                    strain=dataset_metadata["subject"]["strain"]["name"],
                    sex=dataset_metadata["subject"]["sex"],
                    species=dataset_metadata["subject"]["species"]["description"].capitalize(),
                    date_of_birth=dataset_metadata["subject"]["birth_date"],
                ),
            ),
        )
        sessions.append(ecephys_session_metadata)

        metadata = dict(NWBFile=dict(session_description=experiment_data["description"]))
        conversion_spec["experiments"].update(ecephys=dict(metadata=metadata, sessions=sessions))

    with open(yml_file_path, 'w') as file:
        yaml.dump(conversion_spec, file, default_flow_style=False)
