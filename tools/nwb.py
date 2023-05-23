from typing import Dict

from bs4 import BeautifulSoup
from dateutil.parser import parse

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


def get_nwbfile_metadata(dataset_metadata: Dict) -> Dict:
    assert dataset_metadata["date_time"], "The 'date_time' field should contain the start time of the recording."
    metadata = dict(
        NWBFile=dict(
            session_id=dataset_metadata["name"],
            session_start_time=parse(dataset_metadata["date_time"]),
            identifier=dataset_metadata["id"],
        ),
    )

    if "subject" in dataset_metadata:
        metadata.update(Subject=dict(
            subject_id=dataset_metadata["subject"]["name"],
            strain=dataset_metadata["subject"]["strain"]["name"],
            sex=dataset_metadata["subject"]["sex"],
            species=dataset_metadata["subject"]["species"]["description"],
            date_of_birth=parse(dataset_metadata["subject"]["birth_date"]),
        ),
    )

    experiment_description_html = dataset_metadata["project"]["description"]
    if experiment_description_html:
        experiment_description = BeautifulSoup(experiment_description_html, 'html.parser').get_text()
        metadata["NWBFile"].update(experiment_description=experiment_description)

    return metadata
