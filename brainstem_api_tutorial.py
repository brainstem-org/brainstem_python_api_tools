from brainstem_api_tools import BrainstemClient

# 0. Load the client.
#    On first run a browser window opens for secure login (supports 2FA).
#    The token is cached at ~/.config/brainstem/token and reused automatically.
#    Pass a saved token directly to skip the browser flow:
#      client = BrainstemClient(token="YOUR_TOKEN")
#    To connect to a local development server:
#      client = BrainstemClient(url="http://127.0.0.1:8000/")
client = BrainstemClient()


# Loading sessions.

## load can be used to load any model:
## We just need to pass our settings and the name of the model.
output1 = client.load('session').json()

### We can fetch a single session entry from the loaded models.
session = output1["sessions"][0]

## We can also filter the models by providing a dictionary where
## In this example, it will just load sessions whose name exactly equals "yeah".
output1 = client.load('session', filters={'name': 'yeah'}).json()

## Loaded models can be sorted by different criteria applying to
## their fields. In this example, sessions will be sorted in
## descending order according to their name.
output1 = client.load('session', sort=['-name']).json()

## In some cases models contain relations with other models, and
## they can be also loaded with the models if requested. In this
## example, all the projects, data acquisition, behaviors and
## manipulations related to each session will be included.
output1 = client.load('session', include=['projects', 'dataacquisition', 'behaviors', 'manipulations']).json()

### The list of related experiment data can be retrieved from the
### returned dictionary.
dataacquisition = output1["sessions"][0]["dataacquisition"]


## All these options can be combined to suit the requirements
## of the users. For example, we can get only the sessions that
## contain the word "Rat" in their name, sorted in descending
## order by their name and including the related projects.
output1 = client.load('session', filters={'name.icontains': 'Rat'}, sort=["-name"], include=['projects']).json()

## Pagination: load the second page of results (records 21-40).
output1 = client.load('session', limit=20, offset=20).json()

## load_all=True automatically fetches every page and returns a
## combined dict — useful when the record count exceeds one page.
output1 = client.load('session', load_all=True)
all_sessions = output1["sessions"]


# Convenience loaders

## Each convenience loader sets sensible defaults (related models
## included automatically) and exposes named keyword arguments for
## the most common filter fields.

## load_session includes dataacquisition, behaviors, manipulations
## and epochs by default.  Filter by name substring:
output_sessions = client.load_session(name='Rat', load_all=True)

## load_subject includes procedures and subjectlogs.
## Filter by sex ('M' / 'F') and/or project UUID:
project_uuid = '<YOUR_PROJECT_UUID>'  # replace with a real project UUID
output_subjects = client.load_subject(sex='M', projects=project_uuid, load_all=True)

## load_project includes sessions, subjects, collections and cohorts.
output_projects = client.load_project(name='MyProject')

## load_collection includes sessions by default.
output_collection = client.load_collection(name='MyCollection')

## load_cohort includes subjects by default.
output_cohort = client.load_cohort(name='MyCohort')

## load_behavior / load_dataacquisition / load_manipulation all
## accept session=<uuid> to scope results to a single session.
session_uuid = '<YOUR_SESSION_UUID>'  # replace with a real session UUID
output_behaviors        = client.load_behavior(session=session_uuid, load_all=True)
output_dataacquisition  = client.load_dataacquisition(session=session_uuid, load_all=True)
output_manipulations    = client.load_manipulation(session=session_uuid, load_all=True)

## load_procedure scopes by subject UUID.
subject_uuid = '<YOUR_SUBJECT_UUID>'  # replace with a real subject UUID
output_procedures = client.load_procedure(subject=subject_uuid, load_all=True)

## Any convenience loader also accepts extra filters= and custom
## include= overrides just like load() itself.
output_sessions = client.load_session(
    name='Rat',
    include=['projects'],
    filters={'description.icontains': 'hippocampus'},
    load_all=True,
)


# Updating a session

## We can make changes to a model and update it in the database.
## In this case, we changed the description of one of the
## previously loaded sessions.
session = {}
session["description"] = 'new description'
output2 = client.save("session", id="<YOUR_SESSION_UUID>", data=session).json()


# Creating a new session

## We can submit a new entry by defining a dictionary with the
## required fields.
session = {}
session["name"] = "New session"
session["projects"] = ['<YOUR_PROJECT_UUID>']  # replace with a real project UUID
session["description"] = 'description'

## Submitting session
output3 = client.save("session", data=session).json()


# Deleting a session

## Pass the model name and the UUID of the record to remove.
response = client.delete("session", id="<YOUR_SESSION_UUID>")
if response.status_code == 204:
    print("Session deleted")


# Load public projects

## Request the public data by defining the portal to be public
output4 = client.load("project", portal="public").json()
