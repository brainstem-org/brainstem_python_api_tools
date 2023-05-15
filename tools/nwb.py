from typing import Dict

from client import StemClient


def load_subject_metadata(client: StemClient, action_id: str) -> Dict:
    subjects = client.load_subjects(filters=dict(actions=action_id))
    subject = subjects[0]

    strain_id = subject["strain"]
    strain = client.load_model("strain", id=strain_id)["strain"]
    species = client.load_model("species", id=strain["species"])["species"]

    strain.pop("species")
    subject.update(strain=strain)
    subject.update(species=species)

    return subject


def load_action_metadata(client: StemClient, action_id: str) -> Dict:
    action = client.load_actions(id=action_id)
    action.pop("subject")
    brain_region_id = action["brain_region"]
    brain_region = client.load_model("brainregion", id=brain_region_id)["brain_region"]
    action.update(brain_region=brain_region)

    return action


def get_dataset_metadata(client: StemClient, dataset_id: str) -> Dict:
    dataset_metadata = client.load_datasets(id=dataset_id)
    # Update metadata with project information
    project_id = dataset_metadata["projects"][0]
    project = client.load_projects(id=project_id)
    project.pop("subjects")
    project.pop("datasets")
    dataset_metadata.pop("projects")
    dataset_metadata["project"] = project
    # Update metadata with experiment data information
    experiment_data_id = dataset_metadata["experimentdata"][0]
    experiment_data = client.load_experiment_data(id=experiment_data_id)
    experiment_data.pop("dataset")
    dataset_metadata.pop("experimentdata")
    dataset_metadata["experiment_data"] = experiment_data
    # Update metadata with data repository information
    if dataset_metadata["datarepositories"]:
        data_repository = client.load_data_repository(id=dataset_metadata["datarepositories"][0])
        dataset_metadata.pop("datarepositories")
        dataset_metadata["data_repository"] = data_repository
    # Update metadata with subject and action information
    if experiment_data["actions"]:
        action_id = experiment_data["actions"][0]
        action = load_action_metadata(client=client, action_id=action_id)
        dataset_metadata["action"] = action
        subject = load_subject_metadata(client=client, action_id=action_id)
        subject.pop("projects")
        subject.pop("actions")
        dataset_metadata["subject"] = subject
    return dataset_metadata
