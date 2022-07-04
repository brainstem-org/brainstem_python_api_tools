import requests

def post_model (settings, portal, app, model, data, options=""):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options
	response = requests.post(request_url, data=data, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()