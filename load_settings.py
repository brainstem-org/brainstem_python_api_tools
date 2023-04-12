import os
from scipy.io import loadmat
from getpass import getpass

from authentication import set_token_authentication

class StemSettings:
	def __init__ (self):
		# Server path
		#self.address = 'https://www.brainstem.org/rest/' # Public server
		self.address = 'http://127.0.0.1:8000/rest/' # Local server

		path = os.path.dirname(os.path.abspath(__file__))
		try:
			self.credentials = loadmat(path+"/brainstem_credentials_encoded.mat")["credentials"][0]
			print(self.credentials)
		except FileNotFoundError:
			username = input("Please enter your username:")
			password = getpass("Please enter your password:")
			set_token_authentication(self.address.replace("rest/", "api-token-auth/"), username, password)

			self.credentials = loadmat(path+"/brainstem_credentials_encoded.mat")["credentials"][0]

