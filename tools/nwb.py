from collections import defaultdict
from typing import Dict, Optional

import yaml
from bs4 import BeautifulSoup
from dateutil.parser import parse
from neuroconv.datainterfaces import interfaces_by_category

from brainstem_api_client import BrainstemClient

ecephys_interfaces = interfaces_by_category["ecephys"]
supplier_to_ecephys_interface = defaultdict(None)
supplier_to_ecephys_interface.update(
        BlackrockMicrosystems=ecephys_interfaces.get("Blackrock").__name__,
        CEDCambridgeElectronicdesignlimited=ecephys_interfaces.get("CED").__name__,
        IMEC=ecephys_interfaces.get("SpikeGLX").__name__,
        IntanTechnologies=ecephys_interfaces.get("Intan").__name__,
        JaneliaResearchCampus=ecephys_interfaces.get("SpikeGLX").__name__,
        Neuralynx=ecephys_interfaces.get("Neuralynx").__name__,
        OpenEphys=ecephys_interfaces.get("OpenEphys").__name__,
        PlexonInstruments=ecephys_interfaces.get("Plexon").__name__,  # sorting or recording?
    )


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


def write_conversion_specification_yml(
        yml_file_path: str,
        dataset_metadata: Dict,
        interface_kwargs: Optional[Dict] = None,
        conversion_options: Optional[Dict] = None,
):
    assert dataset_metadata["date_time"], "The 'date_time' field should contain the start time of the recording."

    conversion_spec = dict(metadata=dict(NWBFile=dict()))
    experiment_description_html = dataset_metadata["project"]["description"]
    if experiment_description_html:
        experiment_description = BeautifulSoup(experiment_description_html, "html.parser").get_text()
        conversion_spec["metadata"]["NWBFile"].update(experiment_description=experiment_description)

    if conversion_options:
        conversion_spec.update(dict(conversion_options=conversion_options))

    experiment_data = dataset_metadata["experiment_data"]
    source_data = dict(recording=dict())

    if experiment_data["type"] == "Extracellular":
        # note to remove special characters (e.g. re.sub(r'[^A-Za-z0-9\s]+', '', supplier))
        supplier = experiment_data["supplier"]["name"].replace(" ", "")
        interface_name = supplier_to_ecephys_interface.get(supplier)
        if interface_name is not None:
            conversion_spec.update(dict(data_interfaces=dict(recording=interface_name)))

            if interface_kwargs:
                # e.g. specifying the stream_name
                source_data.update(recording=interface_kwargs)

        conversion_spec.update(experiments=dict(ecephys=dict()))
        session_metadata = dict(NWBFile=dict(session_description=experiment_data["description"]))

        # limited for now to use only first path
        path = dataset_metadata["data_repository"]["data_protocols_json"][0]["path"]
        # TODO: interface specific folder path or file path
        source_data["recording"].update(folder_path=path)  # relative folder path

        sessions = [
            dict(
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
                )
            )
        ]

        conversion_spec["experiments"]["ecephys"].update(
            metadata=session_metadata,
            sessions=sessions,
        )

    with open(yml_file_path, 'w') as file:
        yaml.dump(conversion_spec, file, default_flow_style=False)
