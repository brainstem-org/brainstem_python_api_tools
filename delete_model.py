import requests
from get_app_from_model import get_app_from_model


def delete_request(settings, portal, app, model, options):
	request_url = settings.address + portal + "/" + app + "/" + model + "/" + options + "/"
	response = requests.delete(request_url, headers={"Authorization": "Token %s" % settings.credentials})

	return response


def delete_model(settings, model, portal="private", app=None, id=None):
	if not app or app == "":
		app = get_app_from_model(model)

	# Check if entry already exists
	if id is not None:
		return delete_request(settings, portal, app, model, options=id)
