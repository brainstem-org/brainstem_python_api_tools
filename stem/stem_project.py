from common.get_model import get_model

def get_projects (settings, portal="private"):
	app = "stem"
	model = "project"

	return get_model(settings, portal, app, model)



def get_project_by_id (settings, id, portal="private", with_datasets=False):
	app = "stem"
	model = "project"
	options = id

	if with_datasets:
		options += "/?include[]=datasets.*"

	return get_model(settings, portal, app, model, options=options)