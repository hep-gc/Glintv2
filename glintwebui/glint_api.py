from keystoneclient.auth.identity import v2
from keystoneauth1 import session
from keystoneauth1 import exceptions
import glanceclient
import glintv2.config as config
import json
import logging
import os


'''
The Glint API file contains any functionality that connects to cloud components
to gather data, upload or download images, or any other need to connect to a cloud.
Most compute or utility functions can be found in utils.py or for asynchronous and
periodic tasks in celery.py
'''

class repo_connector(object):
	def __init__(self, auth_url, project, username, password):
		self.auth_url = auth_url
		self.project = project
		self.username = username
		self.password = password
		self.token = None
		self.keystone = None
		self.cacert = config.cert_auth_bundle_path
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
			img_disk_format = image['disk_format']
			img_containter_format = image['container_format']
			img_visibility = image['visibility']
			image_list += ((self.project, img_name, img_id, img_disk_format, img_containter_format, img_visibility),)

		return image_list



	# Need to collect the image info: disk_format, container_format, name BEFORE calling this function
	def create_placeholder_image(self, image_name, disk_format, container_format):
		glance = glanceclient.Client('2', session=self.sess)
		image = glance.images.create( name=image_name, disk_format=disk_format, container_format=container_format)
		return image.id

	# Upload an image to repo, returns True if successful or False if not
	def upload_image(self, image_id, image_name, scratch_dir):
		glance = glanceclient.Client('2', session=self.sess)
		images = glance.images.list()
		file_path = scratch_dir + image_name
		glance.images.upload(image_id, open(file_path, 'rb'))
		# Delete the file when we are done with it
		logging.info("Upload complete, deleting temp file")
		os.remove(file_path)
		os.rmdir(scratch_dir)
		return True

	# Download an image from the repo, returns True if successful or False if not
	def download_image(self, image_name, image_id, scratch_dir):
		glance = glanceclient.Client('2', session=self.sess)

		#open file then write to it
		file_path = scratch_dir + image_name
		image_file = open(file_path, 'w+')
		for chunk in glance.images.data(image_id):
			image_file.write(chunk)

		return True

	def delete_image(self, image_id):
		try:
			glance = glanceclient.Client('2', session=self.sess)
			glance.images.delete(image_id)
		except Exception as e:
			logging.error("Unknown error, unable to delete image")
			return False
		return True

	def update_image_name(self, image_id, image_name):
		glance = glanceclient.Client('2', session=self.sess)
		glance.images.update(image_id, name=image_name)


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
	except exceptions.connection.SSLError as e:
		print(e)
		return (False, "SSL connection error")
	except Exception as e:
		print("Repo not valid: %s: %s", (tenant_name, auth_url))
		print(e)
		return (False, "unable to validate: please check httpd error log for message")

	return (True, "Ok")


def change_image_name(repo_obj, img_id, old_img_name, new_img_name, user):
	try:
		logging.info("User %s attempting to rename image '%s' to '%s' in repo '%s'" % (user, old_img_name, new_img_name, repo_obj.tenant))
		repo = repo_connector(auth_url=repo_obj.auth_url, project=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password)
		repo.update_image_name(image_id=img_id, image_name=new_img_name)
		logging.info("Image rename complete")
	except Exception as e:
		logging.error('Unknown exception occured when attempting to change image name')
		logging.error(e)
		return None