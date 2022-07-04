import base64
import os
from scipy.io import savemat

# https://stackoverflow.com/questions/18139093/base64-authentication-python

def set_basic_authorization(username, password):
	usrPass = username+":"+password
	credentials = base64.b64encode(usrPass.encode("ascii"))

	path = os.path.dirname(os.path.abspath(__file__))

	savemat(path+"/../stem_credentials_encoded.mat", {'credentials': credentials})