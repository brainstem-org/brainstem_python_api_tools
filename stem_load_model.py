import requests
from stem_get_app_from_model import stem_get_app_from_model



def stem_load_model (settings, model, portal="private", app=None, filters={}, sort=[], include=[]):
	if not app or app == "":
		app = stem_get_app_from_model(model)


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
	response = requests.get(request_url, headers={"Authorization": "Basic %s" % settings.credentials})

	return response.json()