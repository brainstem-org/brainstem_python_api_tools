import requests
from get_app_from_model import get_app_from_model


def load_model(settings, model, portal="private", app=None, id=None, filters={}, sort=[], include=[]):
	if not app or app == "":
		app = get_app_from_model(model)

	if id:
		query_parameters = id
	else:
		query_parameters = ""

		for key in filters.keys():
			if query_parameters == "":
				prefix = "?"
			else:
				prefix = "&"

			query_parameters += prefix + "filter{" + key + "}=" + filters[key]

		for elem in sort:
			if query_parameters == "":
				prefix = "?"
			else:
				prefix = "&"

			query_parameters += prefix + "sort[]=" + elem

		for elem in include:
			if query_parameters == "":
				prefix = "?"
			else:
				prefix = "&"

			query_parameters += prefix + "include[]=" + elem + ".*"

	request_url = settings.address + portal + "/" + app + "/" + model + "/" + query_parameters
	response = requests.get(request_url, headers={"Authorization": "Token %s" % settings.credentials})

	return response.json()
