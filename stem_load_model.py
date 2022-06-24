import requests

def stem_load_model (portal, app, model, settings):
	request_url = settings.address + portal + "/" + app + "/" + model
	response = requests.get(request_url, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()