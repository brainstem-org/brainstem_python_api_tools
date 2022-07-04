from common.get_model import get_model

def get_datasets (settings, portal="private"):
	app = "stem"
	model = "dataset"

	return get_model(settings, portal, app, model)



def get_dataset_by_id (settings, id, portal="private", with_projects=False, with_behaviors=False, with_experiment_data=False, with_manipulations=False):
	app = "stem"
	model = "dataset"
	options = id
	n_includes = 0

	if with_projects:
		prefix = "/?" if n_includes == 0 else "&"
		options += prefix+"include[]=projects.*"
		n_includes += 1

	if with_behaviors:
		prefix = "/?" if n_includes == 0 else "&"
		options += prefix+"include[]=behaviors.*"
		n_includes += 1

	if with_experiment_data:
		prefix = "/?" if n_includes == 0 else "&"
		options += prefix+"include[]=experiment_data.*"
		n_includes += 1

	if with_manipulations:
		prefix = "/?" if n_includes == 0 else "&"
		options += prefix+"include[]=manipulations.*"
		n_includes += 1

	return get_model(settings, portal, app, model, options=options)