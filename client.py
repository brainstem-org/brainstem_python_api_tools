import os
from getpass import getpass
import requests
import json
from enum import Enum
from typing import List, Dict, Union


class ModelType(Enum):
    project = "project"
    subject = "subject"
    dataset = "dataset"
    collection = "collection"
    action = "action"
    behavior = "behavior"
    experimentdata = "experimentdata"
    manipulation = "manipulation"
    subjectstatechange = "subjectstatechange"
    actionlog = "actionlog"
    subjectlog = "subjectlog"
    behavioralparadigm = "behavioralparadigm"
    datarepository = "datarepository"
    physicalenvironment = "physicalenvironment"
    consumable = "consumable"
    hardwaredevice = "hardwaredevice"
    supplier = "supplier"
    brainregion = "brainregion"
    environmenttype = "environmenttype"
    sensorystimulustype = "sensorystimulustype"
    species = "species"
    strain = "strain"
    strainapproval = "strainapproval"
    journal = "journal"
    laboratory = "laboratory"
    publication = "publication"
    journalapproval = "journalapproval"
    user = "user"
    group = "group"


class PortalType(Enum):
    public = "public"
    private = "private"


class StemClient:

    def __init__(self,
                 username: str = None,
                 password: str = None,
                 load_from_file: bool = False) -> None:

        # Server path
        self.address = 'https://www.brainstem.org/rest/'  # Public server

        if load_from_file:
            path = os.path.dirname(os.path.abspath(__file__))
            with open(path+"/brainstem_credentials_encoded.json") as json_file:
                self._token = json.load(json_file)["credentials"]
        else:
            if not username:
                username = input("Please enter your username:")
            if not password:
                password = getpass("Please enter your password:")

            self._token = self.set_token_authentication(
                url=self.address.replace("rest/", "api-token-auth/"),
                username=username,
                password=password,
                save_to_file=False,
                return_token=True
            )

    def set_token_authentication(self, url: str,
                                 username: str,
                                 password: str,
                                 save_to_file: bool = True,
                                 return_token: bool = False):

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        params = {
            "username": username,
            "password": password
        }
        resp = requests.post(url, headers=headers, json=params)
        token = json.loads(resp.text)['token']

        if resp.status_code != 200:
            print('error: ' + str(resp.status_code))
        else:
            print('Success')

        if save_to_file:
            path = os.path.dirname(os.path.abspath(__file__))
            with open(path+"/brainstem_credentials_encoded.json", 'w') as fp:
                json.dump({'credentials': token}, fp)

        if return_token:
            return token

    def get_app_from_model(modelname):
        app = None

        if modelname in ['project', 'subject', 'dataset', 'collection',
                         'projectmembershipinvitation',
                         'projectgroupmembershipinvitation']:
            app = 'stem'

        elif modelname in ['action', 'behavior', 'experimentdata',
                           'manipulation', 'subjectstatechange', 'actionlog',
                           'subjectlog']:
            app = 'modules'

        elif modelname in ['behavioralparadigm', 'datarepository',
                           'physicalenvironment']:
            app = 'personal_attributes'

        elif any([x in modelname for x in
                 ['consumable', 'hardwaredevice', 'supplier']]):
            app = 'resources'

        elif any([x in modelname for x in
                 ['brainregion', 'environmenttype', 'sensorystimulustype',
                  'species', 'strain']]):
            app = 'taxonomies'

        elif any([x in modelname for x in
                 ['journal', 'laboratory', 'publication']]):
            app = 'attributes'

        elif modelname in ['user', 'group', 'groupmembershipinvitation',
                           'groupmembershiprequest']:
            app = 'users'

        return app

    def load_model(self,
                   model: ModelType,
                   portal: PortalType = "public",
                   id: str = None,
                   filters: dict = None,
                   sort: list = None,
                   include: list = None) -> dict:

        app = self.get_app_from_model(model)

        if id:
            query_parameters = id
        else:
            query_parameters = ""
            if filters:
                for key in filters.keys():
                    if query_parameters == "":
                        prefix = "?"
                    else:
                        prefix = "&"
                    query_parameters += (prefix
                                         + "filter{" + key + "}="
                                         + filters[key])
            if sort:
                for elem in sort:
                    if query_parameters == "":
                        prefix = "?"
                    else:
                        prefix = "&"
                    query_parameters += prefix + "sort[]=" + elem
            if include:
                for elem in include:
                    if query_parameters == "":
                        prefix = "?"
                    else:
                        prefix = "&"
                    query_parameters += prefix + "include[]=" + elem + ".*"

        request_url = (self.address + portal
                       + "/" + app + "/" + model
                       + "/" + query_parameters)

        response = requests.get(request_url,
                                headers={"Authorization": "Token %s"
                                         % self._token})
        return response.json()