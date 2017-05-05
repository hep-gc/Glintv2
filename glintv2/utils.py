import json
import redis
import logging
from glintwebui.glint_api import repo_connector
import config

logger =  logging.getLogger('glintv2')

'''
Recieves a tuple of 3-tuples (repo, img_name, img_id) that uniquely identify an image_list
then sorts them based on their repo and returns them in a json dictionary string
Format:
Proj_dict{
	Repo1Alias{
		Img_ID1{
			name
			state
			disk_format
			container_format
			visibility
			checksum
		}
		Img_ID2{
			name
			state
			disk_format
			container_format
			visibility
			checksum
		}
		.
		.
		.
		Img_IDX{
			name
			state
			disk_format
			container_format
			visibility
			checksum
		}
	}
	Repo2Alias{
	...
	}
	.
	.
	.
	RepoXAlias{
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
				img['visibility'] = image[5]
				img['checksum'] = image[6]
				img_dict[image[2]] = img

		repo_dict[repo.alias] = img_dict
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
		logger.info("No old image dictionary, either bad redis entry or first call since startup")
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
def get_images_for_proj(account_name):
	try:
		r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
		return r.get(account_name)
	except KeyError as e:
		logger.error("Couldnt find image list for account %s", account_name)
		return False

# accepts a project as key string and a jsonified dictionary of the images and stores them in redis
# Redis info should be moved to a config file 
def set_images_for_proj(account_name, json_img_dict):
	try:
		r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
		r.set(account_name, json_img_dict)

	except Exception as e:
		logger.error ("Unknown exception while trying to set images for: %s", account_name)


# returns dictionary containing any conflicts for a given account name
def get_conflicts_for_acc(account_name):
	try:
		r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
		conflict_key = account_name + "_conflicts"
		json_conflict_dict = r.get(conflict_key)
		if json_conflict_dict is not None:
			return json.loads(json_conflict_dict)
		else:
			return None
	except KeyError as e:
		logger.info("Couldnt find conflict list for account %s", account_name)
		return None

def set_conflicts_for_acc(account_name, conflict_dict):
	try:
		json_conflict_dict = json.dumps(conflict_dict)
		conflict_key = account_name + "_conflicts"
		r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
		r.set(conflict_key, json_conflict_dict)

	except Exception as e:
		logger.error ("Unknown exception while trying to set conflicts for: %s", account_name)


# Returns a unique list of (image, name) tuples
# May be a problem if two sites have the same image (id) but with different names
# as the tuple will no longer be unique
def get_unique_image_list(account_name):
	image_dict=json.loads(get_images_for_proj(account_name))
	image_set = set()
	# make a dictionary of all the images in the format key:value = image_id:list_of_repos
	# start by making a list of the keys, using a set will keep them unique
	for repo_key in image_dict:
		for image_id in image_dict[repo_key]:
			image_set.add(image_dict[repo_key][image_id]['name'])
	return sorted(image_set, key=lambda s: s.lower())


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


# Accepts the image dictionary and checks if there are any repos that contain conflicts
#
#   Type 1 - Image1 and Image2 have the same name but are different images.
#   Type 2 - Image1 and Image2 have the same name and are the same image.
#   Type 3 - Image1 and image 2 have different names but are the same image.

def check_for_image_conflicts(json_img_dict):
	image_dict=json.loads(json_img_dict)
	conflicts_dict = {}
	for repo in image_dict:
		conflicts = list()
		for image in image_dict[repo]:
			if image_dict[repo][image]['checksum'] == "No Checksum":
				continue
			for image2 in image_dict[repo]:
				if image_dict[repo][image2]['checksum'] == "No Checksum":
					continue
				if image is not image2:
					try:
						#Check for name conflicts (type 1/type 2)
						if image_dict[repo][image]['name'] == image_dict[repo][image2]['name']:
							# Mayday we have a duplicate
							# check if it is type 1 or type 2 conflint

							if image_dict[repo][image]['checksum'] == image_dict[repo][image2]['checksum']:
								logging.error("Type 2 image conflict detected.")
								# Type 2
								conflict = {
									'type': 2,
									'image_one': image,
									'image_one_name': image_dict[repo][image]['name'],
									'image_two': image2,
									'image_two_name': image_dict[repo][image2]['name']
								}
								duplicate_entry = False
								for entry in conflicts:
									if(entry['image_one'] == conflict['image_two'] and entry['image_two'] == conflict['image_one']):
										duplicate_entry = True
										break
								if not duplicate_entry:
									conflicts.append(conflict)

							else:
								logging.error("Type 1 image conflict detected.")
								# Type 1
								conflict = {
									'type': 1,
									'image_one': image,
									'image_one_name': image_dict[repo][image]['name'],
									'image_two': image2,
									'image_two_name': image_dict[repo][image2]['name']
								}
								duplicate_entry = False
								for entry in conflicts:
									if(entry['image_one'] == conflict['image_two'] and entry['image_two'] == conflict['image_one']):
										duplicate_entry = True
										break
								if not duplicate_entry:
									conflicts.append(conflict)

						#Check for checksum conflicts (type 3, since type 2 will be caught by the first check)
						if image_dict[repo][image]['checksum'] == image_dict[repo][image2]['checksum']:
							logging.error("Type 3 image conflict detected.")
							# Type 3
							conflict = {
								'type': 3,
								'image_one': image,
								'image_two': image2,
								'image_one_name': image_dict[repo][image]['name'],
								'image_two': image2,
								'image_two_name': image_dict[repo][image2]['name']
							}
							duplicate_entry = False
							for entry in conflicts:
								if(entry['image_one'] == conflict['image_two'] and entry['image_two'] == conflict['image_one']):
									duplicate_entry = True
									break
							if not duplicate_entry:
								conflicts.append(conflict)
					except Exception as e:
						logger.error("Error when checking for conflicts on images: %s and %s" % (image, image2))
						logger.error(e)
						logger.error(image_dict)
		if conflicts:
			conflicts_dict[repo] = conflicts



	return conflicts_dict


# Accepts a list of images (names), a project and a repo
# Cross references the image repo in redis against the given image list
# Either returns a list of transactions or posts them to redis to be
# picked up by another thread.
def parse_pending_transactions(account_name, repo_alias, image_list, user):
	try:
		r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
		proj_dict = json.loads(r.get(account_name))
		repo_dict = proj_dict[repo_alias]

		# This function takes a repo dictionary and returns a dictionary that has the format:
		# image_name: image_id
		# This is neccesary since we are now using image name as the unique identifier not the img id
		img_translation = __get_image_ids(repo_dict)

		for image in image_list:
			# If image is not in the image list we need to make a pending transfer
			if not img_translation.get(image, False):
				#MAKE TRANSFER
				#We need to get disk_format and container_format from another repo that has this image
				img_details = __get_image_details(account_name=account_name, image=image)
				disk_format = img_details[0]
				container_format = img_details[1]
				transaction = {
				    'user': user,
					'action':  'transfer',
					'account_name': account_name,
					'repo': repo_alias,
					'image_name': image,
					'disk_format': disk_format,
					'container_format': container_format
				}
				trans_key = account_name + "_pending_transactions"
				r.rpush(trans_key, json.dumps(transaction))
				increment_transactions()
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
					    'user': user,
						'action':  'delete',
						'account_name': account_name,
						'repo': repo_alias,
						'image_id': image_key,
						'image_name': repo_dict[image_key].get('name')
					}
					trans_key = account_name + "_pending_transactions"
					r.rpush(trans_key, json.dumps(transaction))
					increment_transactions()

	except KeyError as e:
		logger.error(e)
		logger.error("Couldnt find image list for account %s", account_name)
		return False


# This function reads pending transactions from a redis queue and spawns celery
# tasks to perform the file transfers. Since our repo dictionaries are using the
# uuid as the image key we need to connect to the repo and create a placeholder
# image and retrieve the img id (uuid) to use as the repo image key
# Then finally we can call the asynch celery tasks
def process_pending_transactions(account_name, json_img_dict):
	from glintwebui.models import Project
	from .celery_app import transfer_image, delete_image

	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	trans_key = account_name + '_pending_transactions'
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
			repo_obj = Project.objects.get(account_name=transaction['account_name'], alias=transaction['repo'])

			rcon = repo_connector(auth_url=repo_obj.auth_url, project=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password)
			new_img_id = rcon.create_placeholder_image(transaction['image_name'], transaction['disk_format'], transaction['container_format'])
			# Make a new img dict
			new_img_dict = {
				'name': transaction['image_name'],
				'state': 'Pending Transfer',
				'disk_format': transaction['disk_format'],
				'container_format': transaction['container_format'],
				'checksum': "No Checksum"
			}
			img_dict[transaction['repo']][new_img_id] = new_img_dict

			# queue transfer task
			transfer_image.delay(image_name=transaction['image_name'], image_id=new_img_id, account_name=account_name, auth_url=repo_obj.auth_url, project_tenant=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password, requesting_user=transaction['user'], project_alias=repo_obj.alias)

		elif transaction['action'] == 'delete':
			# First check if it exists in the redis dictionary, if it doesn't exist we can't delete it
			if img_dict[transaction['repo']].get(transaction['image_id']) is not None:
				# Set state and queue delete task
				repo_obj = Project.objects.get(account_name=transaction['account_name'], alias=transaction['repo'])
				img_dict[transaction['repo']][transaction['image_id']]['state'] = 'Pending Delete'
				delete_image.delay(image_id=transaction['image_id'], image_name=transaction['image_name'], account_name=account_name, auth_url=repo_obj.auth_url, project_tenant=repo_obj.tenant, username=repo_obj.username, password=repo_obj.password, requesting_user=transaction['user'], project_alias=repo_obj.alias)
	return json.dumps(img_dict)


# Queues a state change in redis for the periodic task to perform
# Key will take the form of project_pending_state_changes
# and thus there will be a seperate queue for each project
def queue_state_change(account_name, repo, img_id, state):
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	state_key = account_name + '_pending_state_changes'
	state_change = {
		'state': state,
		'image_id': img_id,
		'repo':repo
	}
	r.rpush(state_key, json.dumps(state_change))
	return True



def process_state_changes(account_name, json_img_dict):
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	state_key = account_name + '_pending_state_changes'
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
def find_image_by_name(account_name, image_name):
	from glintwebui.models import Project

	image_dict=json.loads(get_images_for_proj(account_name))
	for repo in image_dict:
		for image in image_dict[repo]:
			if image_dict[repo][image]['name'] == image_name:
				if image_dict[repo][image]['state'] == 'Present':
					repo_obj = Project.objects.get(account_name=account_name, alias=repo)
					return (repo_obj.auth_url, repo_obj.tenant, repo_obj.username, repo_obj.password, image)
	return False

# Applys the delete rules and returns True if its ok to delete, False otherwise
# Rule 1: Can't delete a shared image
# Rule 2: Can't delete the last copy of an image.
def check_delete_restrictions(image_id, account_name, project_alias):
	json_dict = get_images_for_proj(account_name)
	image_dict = json.loads(json_dict)

	# Rule 1: check if image is shared
	if image_dict[project_alias][image_id]['visibility'] is "public":
		return False

	# Rule 2: check if its the last copy of the image
	for repo in image_dict:
		if repo is not project_alias:
			for image in image_dict[repo]:
				if image_dict[repo][image]['name'] is image_dict[project_alias][image_id]['name']:
					#found one, its ok to delete
					return True

	return False


'''
This function checks if image collection has started so we don't accidentally queue
multiple image collection jobs
'''

def check_collection_task():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	state = r.get("collection_started")
	if state is None:
		return False
	if "True" in state:
		return True
	if "False" in state:
		return False

def set_collection_task(state):
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.set("collection_started", state)


'''
THESE FUNCTIONS ARE UNUSED BUT MAY BE USEFULL TO PROVIDE REAL TIME FEEDBACK ABOUT TRANSFERS

def post_transfer_progress(key, progress):
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.set(key, progress)

def get_transfer_progress(key):
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	progress = r.get(key)
	return progress
'''

def increment_transactions():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.incr("num_transactions", 1)
	return True

def decrement_transactions():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.decr("num_transactions", 1)
	return True

def get_num_transactions():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	num_tx = r.get("num_transactions")
	if(num_tx < 0 or num_tx is None):
		num_tx = 0
		r.set("num_transactions", num_tx)
	return int(num_tx)

def repo_modified():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.incr("repos_modified")
	return True

def check_for_repo_changes():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	result = r.get("repos_modified")
	if result is None:
		return False
	elif(int(result)>0):
		return True
	else:
		return False

def repo_proccesed():
	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	r.set("repos_modified", 0)



def __get_image_ids(repo_dict):
	img_trans_dict = {}
	for image in repo_dict:
		img_trans_dict[repo_dict[image]['name']] = image

	return img_trans_dict

#Searches through the image dict until it finds this image and returns the disk/container formats
def __get_image_details(account_name, image):

	r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
	proj_dict = json.loads(r.get(account_name))
	for repo in proj_dict:
		for img in proj_dict[repo]:
			if proj_dict[repo][img]['name'] == image:
				return (proj_dict[repo][img]['disk_format'], proj_dict[repo][img]['container_format'])
	
