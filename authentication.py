import base64
import os
import requests
from scipy.io import savemat
import json

# https://stackoverflow.com/questions/18139093/base64-authentication-python

def set_basic_authentication(username, password):
	usrPass = username+":"+password
	credentials = base64.b64encode(usrPass.encode("ascii"))

	path = os.path.dirname(os.path.abspath(__file__))

	savemat(path+"/brainstem_credentials_encoded.mat", {'credentials': credentials})


def set_token_authentication(url, username, password):
	path = os.path.dirname(os.path.abspath(__file__))

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

	savemat(path+"/brainstem_credentials_encoded.mat", {'credentials': token})