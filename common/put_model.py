import requests

def put_model (settings, portal, app, model, data, options=""):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options
	response = requests.put(request_url, data=data, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()