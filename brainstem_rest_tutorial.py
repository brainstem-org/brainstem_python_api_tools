from load_settings import StemSettings
from load_model import load_model
from save_model import save_model


# 0. Setup credentials. User email and password will be requested.
settings = StemSettings()


# 1. Loading datasets.

## load_model can be used to load any model:
## We just need to pass our settings and the name of the model.
output1 = load_model(settings, 'dataset')

### We can fetch a single dataset entry from the loaded models.
dataset = output1["datasets"][0]

## We can also filter the models by providing a dictionary where
## the keys are the fields and the values the possible contents.
## In this example, it will just load datasets whose name is "yeah".
output1 = load_model(settings, 'dataset', filters={'name': 'yeah'})

## Loaded models can be sorted by different criteria applying to
## their fields. In this example, datasets will be sorted in 
## descending ording according to their name.
output1 = load_model(settings, 'dataset', sort=['-name'])

## In some cases models contain relations with other models, and
## they can be also loaded with the models if requested. In this
## example, all the projects, experiment data, behaviors and
## manipulations related to each dataset will be included. 
output1 = load_model(settings, 'dataset', include=['projects', 'experiment_data', 'behaviors', 'manipulations'])

### The list of related experiment data can be retrived from the
### returned dictionary.
experiment_data = output1["experiment_data"]


## All these options can be combined to suit the requirements
## of the users. For example, we can get only the dataset that
## contain the word "Rat" in their name, sorted in descending
## order by their name and including the related projects.
output1 = load_model(settings, 'dataset', filters={'name.icontains': 'Rat'}, sort=["-name"], include=['projects'])



# 2. Updating a dataset

## We can make changes to a model and update it in the database.
## In this case, we changed the description of one of the
## previously loaded datasets.
dataset = output1["datasets"][0]
dataset["description"] = 'new description'
output2 = save_model(settings, "dataset", data=dataset)




# 3. Creating a new dataset

## We can submit a new entry by defining a dictionary with the
## required fields.
dataset = {}
dataset["name"] = 'New dataset88'
dataset["description"] = 'new dataset description'
dataset["projects"] = ['e7475834-7733-48cf-9e3b-f4f2d2d0305a']

## Submitting dataset
output3 = save_model(settings, "dataset", data=dataset)




# 4. Load public projects

## Request the public data by defining the portal to be public
output4 = load_model(settings, "project", portal="public")

