import requests
from stem_get_app_from_model import stem_get_app_from_model


def put_model (settings, portal, app, model, data, options=""):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options + "/"
	response = requests.put(request_url, json=data, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()


def post_model (settings, portal, app, model, data, options=""):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options
	response = requests.post(request_url, json=data, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()


def stem_save_model(settings, model, portal="private", app=None, data={}):
	if not app or app == "":
		app = stem_get_app_from_model(model)


	id = data.get("id", None)

	# Check if entry already exists
	if id is not None:
		# This is an update request
		return put_model(settings, portal, app, model, data, options=id)

	else:
		# This is a create request
		return post_model(settings, portal, app, model, data)


