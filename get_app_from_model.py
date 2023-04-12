


def get_app_from_model(modelname):
	app = ""

	if modelname in ['project','subject','dataset','collection']:
		app = 'stem';
	elif modelname in ['action','behavior','experimentdata','manipulation','subjectstatechange', 'actionlog', 'subjectlog']:
		app = 'modules';
	elif modelname in ['behavioralparadigm','datarepository','physicalenvironment']:	
		app = 'personal_attributes';
	elif modelname in ['consumable','hardwaredevice','supplier']:	
		app = 'resources';
	elif modelname in ['brainregion','environmenttype','sensorystimulustype','species','strain', 'strainapproval']:	
		app = 'taxonomies';
	elif modelname in ['journal','laboratory','publication', 'journalapproval']:	
		app = 'attributes';
	elif modelname in ['user']:
		app = 'users';
	elif modelname in ['group']:
		app = 'auth';

	return app