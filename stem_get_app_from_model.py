


def stem_get_app_from_model(modelname):
	app = ""

	if modelname in ['project','subject','dataset','collection']:
		app = 'stem';
	elif modelname in ['action','behavior','experimentdata','manipulation','subjectstatechange']:
		app = 'moodules';
	elif modelname in ['behavioralparadigm','datarepository','physicalenvironment']:	
		app = 'personal_attributes';
	elif modelname in ['consumable','hardwaredevice','supplier']:	
		app = 'resources';
	elif modelname in ['brainregion','environmenttype','sensorystimulustype','species','strain']:	
		app = 'taxonomies';
	elif modelname in ['journal','laboratory','publication']:	
		app = 'attributes';
	elif modelname in ['user']:
		app = 'users';

	return app