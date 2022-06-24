import os
from scipy.io import loadmat
from getpass import getpass

from stem_set_basic_authorization import stem_set_basic_authorization

class StemSettings:
	def __init__ (self):
		# Server path
		#self.address = 'https://www.brainstem.org/rest/' # Public server
		self.address = 'http://127.0.0.1:8000/rest/' # Local server

		path = os.path.dirname(os.path.abspath(__file__))
		try:
			self.credentials = loadmat(path+"/stem_credentials_encoded.mat")["credentials"]
		except FileNotFoundError:
			username = input("Please enter your username:")
			password = getpass("Please enter your password:")
			stem_set_basic_authorization(username, password)

			self.credentials = loadmat(path+"/stem_credentials_encoded.mat")["credentials"]

