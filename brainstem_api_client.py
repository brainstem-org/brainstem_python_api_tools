import os
from getpass import getpass
import requests
from requests.models import Response
import json
from enum import Enum


class ModelType(Enum):
    project = "project"
    subject = "subject"
    session = "session"
    collection = "collection"
    cohort = "cohort"
    procedure = "procedure"
    behavior = "behavior"
    dataacquisition = "dataacquisition"
    manipulation = "manipulation"
    equipment = "equipment"
    consumablestock = "consumablestock"
    procedurelog = "procedurelog"
    subjectlog = "subjectlog"
    behavioralparadigm = "behavioralparadigm"
    datastorage = "datastorage"
    inventory = "inventory"
    setup = "setup"
    consumable = "consumable"
    hardwaredevice = "hardwaredevice"
    supplier = "supplier"
    brainregion = "brainregion"
    setuptype = "setuptype"
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
    super = "super"


class LoginError(Exception):
    def __str__(self):
        return f'User/password combination incorrect or user does not exist'


class BrainstemClient:

    def __init__(self,
                 token: str = None) -> None:

        # Server path
        self._address = 'https://www.brainstem.org/api/'

        if token:
            self._token = token
        else:
            username = input("Please enter your username:")
            password = getpass("Please enter your password:")

            self._token = self.__set_token_authentication(
                url=self._address + "token/",
                username=username,
                password=password,
            )

            print("Your authorization token is:\n", self._token)
            print("\nPlease keep it in a safe place.")

    def __set_token_authentication(self,
                                   url: str,
                                   username: str,
                                   password: str) -> str:

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        params = {
            "username": username,
            "password": password
        }
        resp = requests.post(url, headers=headers, json=params)

        if resp.status_code != 200:
            raise LoginError()

        token = json.loads(resp.text)['token']
        return token

    def __get_app_from_model(self, modelname: str) -> str:
        app = None

        if modelname in ['project', 'subject', 'session', 'collection', 'cohort',
                         'projectmembershipinvitation',
                         'projectgroupmembershipinvitation']:
            app = 'stem'

        elif modelname in ['procedure', 'behavior', 'dataacquisition', 'manipulation', 
                           'equipment', 'consumablestock', 'procedurelog', 'subjectlog']:
            app = 'modules'

        elif modelname in ['behavioralparadigm', 'datastorage', 'inventory',
                           'setup']:
            app = 'personal_attributes'

        elif any([x in modelname for x in
                 ['consumable', 'hardwaredevice', 'supplier']]):
            app = 'resources'

        elif any([x in modelname for x in
                 ['brainregion', 'setuptype',
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
                   portal: PortalType = "private",
                   id: str = None,
                   options: str = None,
                   filters: dict = None,
                   sort: list = None,
                   include: list = None) -> Response:

        app = self.__get_app_from_model(model)
        if app is None:
            resp = Response()
            resp.status_code = 404
            return resp

        if options is None:
            options = ""

        if id:
            query_parameters = id + "/" + options
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

        request_url = (self._address + portal
                       + "/" + app + "/" + model
                       + "/" + query_parameters)

        resp = requests.get(request_url,
                            headers={"Authorization": "Bearer %s"
                                     % self._token})
        return resp

    def save_model(self,
                   model: ModelType,
                   portal: PortalType = "private",
                   id: str = None,
                   data: dict = None,
                   options: str = None) -> Response:

        app = self.__get_app_from_model(model)
        if app is None:
            resp = Response()
            resp.status_code = 404
            return resp

        if data is None:
            data = {}

        if options is None:
            options = ""

        # Check if entry already exists
        if id is not None:
            # This is an update request
            request_url = (self._address + portal + "/" + app + "/" + model
                           + "/" + id + "/" + options)
            resp = requests.patch(request_url, json=data,
                                  headers={"Authorization": "Bearer %s"
                                           % self._token})

        else:
            # This is a create request
            request_url = (self._address + portal + "/" + app + "/"
                           + model + "/" + options)
            resp = requests.post(request_url, json=data,
                                 headers={"Authorization": "Bearer %s"
                                          % self._token})

        return resp

    def delete_model(self,
                     model: ModelType,
                     portal: PortalType = "private",
                     id: str = None):

        app = self.__get_app_from_model(model)
        if app is None:
            resp = Response()
            resp.status_code = 404
            return resp

        # Check if entry already exists
        if id is not None:
            request_url = (self._address + portal + "/" + app + "/" + model
                           + "/" + id + "/")
            resp = requests.delete(request_url,
                                   headers={"Authorization": "Bearer %s"
                                            % self._token})

            return resp
