import json
import redis
import logging
from glintwebui.glint_api import repo_connector


'''
Recieves a tuple of 3-tuples (repo, img_name, img_id) that uniquely identify an image_list
then sorts them based on their repo and returns them in a json dictionary string
Format:
Proj_dict{
	Repo1{
		Img_ID1{
			name
			state
			disk_format
			container_format
		}
		Img_ID2{
			name
			state
			disk_format
			container_format
		}
		.
		.
		.
		Img_IDX{
			name
			state
			disk_format
			container_format
		}
	}
	Repo2{
	...
	}
	.
	.
	.
	RepoX{
	...
	}
}
'''
def jsonify_image_list(image_list, repo_list):
	#take img list and sort it into repos
	repo_dict = {}
	# Build repo_dict
	for repo in repo_list:
		img_dict = {}
		for image in image_list:
			if image[0] == repo.tenant:
				img = {}
				img['name'] = image[1]
				img['state'] = 'Present'
				img['disk_format'] = image[3]
				img['container_format'] = image[4]
				img_dict[image[2]] = img

		repo_dict[repo.tenant] = img_dict
	return json.dumps(repo_dict)


# This function will accept 2 json string dictionaries and find the pending transactions
# from the first and add them to the second then check the queue for any state changes
# apply those final updates and finally return a jsonified dictstring
#
# This function changed significantly when we started using the image name as the unique identifier
# which changed the way the state changes are handled, We can no longer change intuitively change
# the states here based on the information of the two dictionaries. State changes are now handled
# in a seperate function that reads from a queue ()
#
def update_pending_transactions(old_img_dict, new_img_dict):
	#on startup there wont be an old dict
	try:
		old_dict = json.loads(old_img_dict)
	except TypeError as e:
		logging.info("No old image dictionary, either bad redis entry or first call since startup")
		return new_img_dict
	new_dict = json.loads(new_img_dict)

	for repo_key in old_dict:
		repo_dict = old_dict[repo_key]
		for img_key in repo_dict:
			#if a pending one is found, check for it in the new list
			if repo_dict[img_key]['state'] in {"Pending Transfer", "Pending Delete"}:
				try:
					new_img = new_dict[repo_key][img_key]
					# if it was a pending transfer change the state to pending:
					if repo_dict[img_key]['state'] == "Pending Transfer":
						new_dict[repo_key][img_key]['state'] = "Pending Transfer"
					# OR if it was pending a delete and it still exists: change state to Pending Delete
					if repo_dict[img_key]['state'] == "Pending Delete":
						new_dict[repo_key][img_key]['state'] = "Pending Delete"
				except KeyError as e:
					#Doesn't exist in the new one yet
					# if it was a pending delete 
					if repo_dict[img_key]['state'] == "Pending Delete":
						new_dict[repo_key][img_key] = repo_dict[img_key]
					# if it was a pending transfer and it still doesnt exist: add it as Pending Xfer
					if repo_dict[img_key]['state'] == "Pending Transfer":
						new_dict[repo_key][img_key] = repo_dict[img_key]
				
	return json.dumps(new_dict)

# returns a jsonified python dictionary containing the image list for a given project
# If the image list doesn't exist in redis it returns False
# Redis info should be moved to a config file
def get_images_for_proj(project):
	try:
		r = redis.StrictRedis (host='localhost', port=6379, db=0)
		return r.get(project)
	except KeyError as e:
		logging.error("Couldnt find image list for project %s", project)
		return False

# accepts a project as key string and a jsonified dictionary of the images and stores them in redis
# Redis info should be moved to a config file 
def set_images_for_proj(project, json_img_dict):
	try:
		r = redis.StrictRedis (host='localhost', port=6379, db=0)
		r.set(project, json_img_dict)

	except Exception as e:
		logging.error ("Unknown exception while trying to set images for: %s", project)


'''
THIS FUNCTION IS NOT USED, SHOULD BE REMOVED LATER
'''
# Accepts a project as redis key and builds the image matrix in a dictionary
# that will be parsed to display on the project details web page
# The only problem with this is we discard the state and image name with this method
def build_image_matrix(project):
	image_dict=json.loads(get_images_for_proj(project))
	img_matrix = {}
	key_set = set()
	# make a dictionary of all the images in the format key:value = image_id:list_of_repos
	# start by making a list of the keys, using a set will keep them unique
	for repo_key in image_dict:
		for image_id in image_dict[repo_key]:
			key_set.add(image_id)

	# now with a unique set of keys fill out the dictionary
	for key in key_set:
		for repo_key in image_dict:
			#try to get the image dict from the repo key, if there is a no key error it exists in that repo
			try:
				image_dict[repo_key][key]
				img_matrix[key] = [repo_key]

			#otherwise the image doesn't exist in that repo
			except KeyError as e:
				pass

	return img_matrix


# Returns a unique list of (image, name) tuples
# May be a problem if two sites have the same image (id) but with different names
# as the tuple will no longer be unique
def get_unique_image_list(project):
	image_dict=json.loads(get_images_for_proj(project))
	image_set = set()
	# make a dictionary of all the images in the format key:value = image_id:list_of_repos
	# start by making a list of the keys, using a set will keep them unique
	for repo_key in image_dict:
		for image_id in image_dict[repo_key]:
			image_set.add(image_dict[repo_key][image_id]['name'])
	return image_set


# accepts image dictionary and returns a dictionary that inverses the format to
# repo1{
#	img_name: img_key
#   ...
#}
# repo2{
#	img_name: img_key
#   ...
#}
def build_id_lookup_dict(image_dict):
	reverse_dict = {}
	for repo in image_dict:
		reversed_repo = {}
		for image in image_dict[repo]:
			reversed_repo[image_dict[repo][image]['name']] = image
		reverse_dict[repo] = reversed_repo
	return reverse_dict


# Accepts the image dictionary and checks if there are any repos that
# have multiple images with the same name, if none are found return true
# otherwise return a dictionary that contains the images with conflicting names
def check_for_duplicate_images(image_dict):
	for repo in image_dict:
		image_set = set()
		for image in image_dict[repo]:
			if image_dict[repo][image]['name'] in image_set:
				# Mayday we have a duplicate
				duplicate_dict = {}
				duplicate_img = {
					'name': image_dict[repo][image]['name'],
					'repo': repo,
					'disk_format': image_dict[repo][image]['disk_format'],
					'container_format': image_dict[repo][image]['container_format']
				}
				duplicate_dict[image] = duplicate_img
				# we need to go find the other one
				for second_image in image_dict[repo]:
					if (image_dict[repo][second_image]['name'] == image_dict[repo][image]['name'] and image != second_image):
						# We found it, return the duplicate dictionary
						duplicate_img = {
							'name': image_dict[repo][second_image]['name'],
							'repo': repo,
							'disk_format': image_dict[repo][second_image]['disk_format'],
							'container_format': image_dict[repo][second_image]['container_format']
						}
						duplicate_dict[second_image] = duplicate_img
						return duplicate_dict
				# We should never get here
				logging.error("An error occured, couldn't find duplicate image")

			else:
				image_set.add(image_dict[repo][image]['name'])

	return None


# Accepts a list of images (names), a project and a repo
# Cross references the image repo in redis against the given image list
# Either returns a list of transactions or posts them to redis to be
# picked up by another thread.
def parse_pending_transactions(project, repo, image_list):
	try:
		r = redis.StrictRedis (host='localhost', port=6379, db=0)
		proj_dict = json.loads(r.get(project))
		repo_dict = proj_dict[repo]

		# This function takes a repo dictionary and returns a dictionary that has the format:
		# image_name: image_id
		# This is neccesary since we are now using image name as the unique identifier not the img id
		img_translation = __get_image_ids(repo_dict)

		for image in image_list:
			# If image is not in the image list we need to make a pending transfer
			if not img_translation.get(image, False):
				#MAKE TRANSFER
				#We need to get disk_format and container_format from another repo that has this image
				img_details = __get_image_details(project=project, image=image)
				disk_format = img_details[0]
				container_format = img_details[1]
				transaction = {
					'action':  'transfer',
					'project': project,
					'repo': repo,
					'image_name': image,
					'disk_format': disk_format,
					'container_format': container_format
				}
				trans_key = project + "_pending_transactions"
				r.rpush(trans_key, json.dumps(transaction))
			#else it is already there and do nothing
			else:
				pass

		# Now we need to check deletes
		for image_key in repo_dict:
			#If the key exists but it isn't in the image list make a pending delete
			if repo_dict[image_key]['name'] not in image_list:
				# if its pending already we don't need to touch it
				if repo_dict[image_key].get('state') not in {'Pending Delete', 'Pending Transfer'}:
					# MAKE DELETE
					transaction = {
						'action':  'delete',
						'project': project,
						'repo': repo,
						'image_id': image_key,
						'image_name': repo_dict[image_key].get('name')
					}
					trans_key = project + "_pending_transactions"
					r.rpush(trans_key, json.dumps(transaction))

	except KeyError as e:
		logging.error(e)
		logging.error("Couldnt find image list for project %s", project)
		return False


# This function reads pending transactions from a redis queue and spawns celery
# tasks to perform the file transfers. Since our repo dictionaries are using the
# uuid as the image key we need to connect to the repo and create a placeholder
# image and retrieve the img id (uuid) to use as the repo image key
# Then finally we can call the asynch celery tasks
def process_pending_transactions(project, json_img_dict):
	from glintwebui.models import Project
	from .celery import transfer_image, delete_image

	r = redis.StrictRedis (host='localhost', port=6379, db=0)
	trans_key = project + '_pending_transactions'
	img_dict = json.loads(json_img_dict)

	# seems like there is no assignment in while conditionals for python so We will have to be smart and use break
	while(True):
		trans = r.lpop(trans_key)
		if trans == None:
			break
		transaction = json.loads(trans)
		# Update global dict and create transfer or delete task
		if transaction['action'] == 'transfer':
			
			# First we need to create a placeholder img and get the new image_id
			# This may cause an error if the same repo is added twice, perhaps we can screen for this when repos are added
			repo_obj = Project.objects.get(project_name=transaction['project'], tenant=transaction['repo'])

			rcon = repo_connector(auth_url=repo_obj.auth_url, project=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password)
			new_img_id = rcon.create_placeholder_image(transaction['image_name'], transaction['disk_format'], transaction['container_format'])
			# Make a new img dict
			new_img_dict = {
				'name': transaction['image_name'],
				'state': 'Pending Transfer',
				'disk_format': transaction['disk_format'],
				'container_format': transaction['container_format']
			}
			img_dict[transaction['repo']][new_img_id] = new_img_dict

			# queue transfer task
			transfer_image.delay(image_name=transaction['image_name'], image_id=new_img_id, project=project, auth_url=repo_obj.auth_url, project_tenant=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password)

		elif transaction['action'] == 'delete':
			# First check if it exists in the redis dictionary, if it doesn't exist we can't delete it
			if img_dict[transaction['repo']].get(transaction['image_id']) is not None:
				# Set state and queue delete task
				repo_obj = Project.objects.get(project_name=transaction['project'], tenant=transaction['repo'])
				img_dict[transaction['repo']][transaction['image_id']]['state'] = 'Pending Delete'
				delete_image.delay(image_id=transaction['image_id'], project=project, auth_url=repo_obj.auth_url, project_tenant=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password)
	return json.dumps(img_dict)


# Queues a state change in redis for the periodic task to perform
# Key will take the form of project_pending_state_changes
# and thus there will be a seperate queue for each project
def queue_state_change(project, repo, img_id, state):
	r = redis.StrictRedis (host='localhost', port=6379, db=0)
	state_key = project + '_pending_state_changes'
	state_change = {
		'state': state,
		'image_id': img_id,
		'repo':repo
	}
	r.rpush(state_key, json.dumps(state_change))
	return True



def process_state_changes(project, json_img_dict):
	r = redis.StrictRedis (host='localhost', port=6379, db=0)
	state_key = project + '_pending_state_changes'
	img_dict = json.loads(json_img_dict)
	while(True):
		raw_state_change = r.lpop(state_key)
		if raw_state_change == None:
			break
		state_change = json.loads(raw_state_change)
		if state_change['state'] == "deleted":
			# Remove the key
			img_dict[state_change['repo']].pop(state_change['image_id'], None)
		else:
			# Update the state
			img_dict[state_change['repo']][state_change['image_id']]['state'] = state_change['state']

	return json.dumps(img_dict)

# This function accepts a project and an image name and looks through the image
# dictionary until it finds a match where state='present' and returns a tuple of
# (auth_url, tenant, username, password, img_id)
def find_image_by_name(project, image_name):
	from glintwebui.models import Project
	
	image_dict=json.loads(get_images_for_proj(project))
	for repo in image_dict:
		for image in image_dict[repo]:
			if image_dict[repo][image]['name'] == image_name:
				if image_dict[repo][image]['state'] == 'Present':
					repo_obj = Project.objects.get(project_name=project, tenant=repo)
					return (repo_obj.auth_url, repo, repo_obj.username, repo_obj.password, image)
	return False
'''
added image_name to transaction
this function should no longer be needed
'''
# Returns the name of the img_id that was passed in or False if it doesn't exist
def __find_image_name(img_dict, img_id):
	for repo_key in img_dict:
		for key in img_dict[repo_key]:
			if key == img_id:
				return img_dict[repo_key][key]['name']
	return False


def __get_image_ids(repo_dict):
	img_trans_dict = {}
	for image in repo_dict:
		img_trans_dict[repo_dict[image]['name']] = image

	return img_trans_dict

#Searches through the image dict until it finds this image and returns the disk/container formats
def __get_image_details(project, image):

	r = redis.StrictRedis (host='localhost', port=6379, db=0)
	proj_dict = json.loads(r.get(project))
	for repo in proj_dict:
		for img in proj_dict[repo]:
			if proj_dict[repo][img]['name'] == image:
				return (proj_dict[repo][img]['disk_format'], proj_dict[repo][img]['container_format'])
	