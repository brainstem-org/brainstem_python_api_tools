import requests

def get_model (settings, portal, app, model, options=""):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options
	response = requests.get(request_url, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()