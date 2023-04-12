import requests
from get_app_from_model import get_app_from_model


def patch_model (settings, portal, app, model, id, data, options):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + id + "/" + options
	response = requests.patch(request_url, json=data, headers={"Authorization": "Token %s" % settings.credentials})

	return response.json()


def post_model (settings, portal, app, model, data, options):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options
	response = requests.post(request_url, json=data, headers={"Authorization": "Token %s" % settings.credentials})

	return response.json()


def save_model(settings, model, portal="private", app=None, id=None, data={}, options=""):
	if not app or app == "":
		app = get_app_from_model(model)

	# Check if entry already exists
	if id is not None:
		# This is an update request
		return patch_model(settings, portal, app, model, id, data, options)

	else:
		# This is a create request
		return post_model(settings, portal, app, model, data, options)


