import json
import redis
import logging

'''
Recieves a tuple of 3-tuples (repo, img_name, img_id) that uniquely identify an image_list
then sorts them based on their repo and returns them in a json dictionary string
Format:
Proj_dict{
	Repo1{
		Img_ID1{
			name
			state
		}
		Img_ID2{
			name
			state
		}
		.
		.
		.
		Img_IDX{
			name
			state
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
				img_dict[image[2]] = img

		repo_dict[repo.tenant] = img_dict
	return json.dumps(repo_dict)


# This function will accept 2 json string dictionaries and find the pending transactions
# from the first and add them to the second and return a jsonified dictstring
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
					# if it was a pending transfer and it is now Present:
					# do nothing
					# OR if it was pending a delete and it still exists: change state to Pending Delete
					if repo_dict[img_key]['state'] == "Pending Delete":
						new_dict[repo_key][img_key]['state'] = "Pending Delete"
				except KeyError as e:
					#Doesn't exist in the new one yet
					# if it was a pending delete and it is now non-existent:
					# do nothing
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
			image_set.add((image_id, image_dict[repo_key][image_id]['name']))
	return image_set

# Accepts a list of images, a project and a repo
# Cross references the image repo in redis against the given image list
# Either returns a list of transactions or posts them to redis to be
# picked up by another thread.
def parse_pending_transactions(project, repo, image_list):
	try:
		r = redis.StrictRedis (host='localhost', port=6379, db=0)
		proj_dict = json.loads(r.get(project))
		repo_dict = proj_dict[repo]
		for image in image_list:
			# If image is not in the image list we need to make a pending transfer
			if not repo_dict.get(image, False):
				#MAKE TRANSFER
				transaction = {
					'action':  'transfer',
					'project': project,
					'repo': repo,
					'image_id': image
				}
				tx = json.dumps(transaction)
				trans_key = project + "_pending_transactions"
				r.rpush(trans_key, json.dumps(transaction))
			#else it is already there and do nothing
			else:
				pass

		# Now we need to check deletes
		for image_key in repo_dict:
			#If the key exists but it isn't in the image list make a pending delete
			if image_key not in image_list:
				# MAKE DELETE
				transaction = {
					'action':  'delete',
					'project': project,
					'repo': repo,
					'image_id': image_key
				}
				tx = json.dumps(transaction)
				trans_key = project + "_pending_transactions"
				r.rpush(trans_key, json.dumps(transaction))

	except KeyError as e:
		logging.error(e)
		logging.error("Couldnt find image list for project %s", project)
		return False

def process_pending_transactions(project, json_img_dict):
	r = redis.StrictRedis (host='localhost', port=6379, db=0)
	trans_key = project + '_pending_transactions'
	img_dict = json.loads(json_img_dict)

	# seems like there is no assignment in while conditionals for python so We will have to be smart and break
	while(True):
		trans = r.lpop(trans_key)
		if trans == None:
			break
		transaction = json.loads(trans)
		# Update global dict and create transfer or delete task
		if transaction['action'] == 'transfer':
			# Make a new img dict
			new_img_dict = {
				'name': __find_image_name(img_dict, transaction['image_id']),
				'state': "Pending Transfer"
			}
			# Add it to redis img dict
			img_dict[transaction['repo']][transaction['image_id']] = new_img_dict

			# queue transfer task
			#celery.transfer_img()

		elif transaction['action'] == 'delete':
			# First check if it exists in the redis dictionary, if it doesn't exist we can't delete it
			if img_dict[transaction['repo']][transaction['image_id']] is not None:
				# Set state and queue delete task
				img_dict[transaction['repo']][transaction['image_id']]['state'] = 'Pending Delete'
				#celery.delete_img()
	return json.dumps(img_dict)



# Returns the name of the img_id that was passed in or False if it doesn't exist
def __find_image_name(img_dict, img_id):
	for repo_key in img_dict:
		for key in img_dict[repo_key]:
			if key == img_id:
				return img_dict[repo_key][key]['name']
	return False