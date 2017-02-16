from keystoneclient.auth.identity import v2
from keystoneauth1 import session
from keystoneauth1 import exceptions
from keystoneclient.v2_0 import client as ksclient
import glanceclient
import json

class repo_connector(object):
	def __init__(self, auth_url, project, username, password):
		self.auth_url = auth_url
		self.project = project
		self.username = username
		self.password = password
		self.token = None
		self.keystone = None
		self.cacert = "/etc/glintv2/GridCanadaCertificateAuthority"
		self.sess = self._get_keystone_session()
		self.image_list = self._get_images()

	# Borrowed from cloud schedular and modified to match this enviroment
	# This was a nightmare to get working behind apache but it turns out 
	# all that was needed was to upgrade the python cryptography library
	def _get_keystone_session(self):
		try:
			auth = v2.Password(auth_url=self.auth_url, username=self.username, password=self.password, tenant_name=self.project)
			sess = session.Session(auth=auth, verify=self.cacert)
		except Exception as e:
			print("Problem importing keystone modules, and getting session: %s" % e)
		return sess

	def _get_images(self):
		glance = glanceclient.Client('2', session=self.sess)
		images = glance.images.list()
		image_list = ()

		# Do things with images
		for image in glance.images.list():
			img_id = image['id']
			img_name = image['name']
			image_list += ((self.project, img_name, img_id),)
		

		return image_list

def validate_repo(auth_url, username, password, tenant_name):
	try:
		repo = repo_connector(auth_url=auth_url, project=tenant_name, username=username, password=password)

	except exceptions.connection.ConnectFailure as e:
		print("Repo not valid: %s: %s", (tenant_name, auth_url))
		print(e)
		return (False, "Unable to validate: Bad Auth URL")
	except exceptions.http.HTTPClientError as e:
		print(e)
		return (False, "Unable to connect: Bad username, password, or tenant")
	#except Exception as e:
		#need to break these exceptions apart to provide user feedback about what information is messed up
		print("Repo not valid: %s: %s", (tenant_name, auth_url))
		print(e)
		return (False, "unable to validate: unknown error")

	return (True, "Ok")
