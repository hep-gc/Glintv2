import json

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
def find_pending_transactions(old_img_dict, new_img_dict):
	old_dict = json.loads(old_img_dict)
	new_dict = json.loads(new_img_dict)

	for repo_key in old_dict:
		repo_dict = old_dict[repo_key]
		for img_key in repo_dict:
			if repo_dict[img_key]['state'] in {"Pending Transfer", "Pending Delete"}:
				#if a pending one is found, check for it in the new list
				# if it was a pending transfer and it is now Present: do nothing
				# if it was a pending delete and it is now non-existent: do nothing
				# if it was a pending transfer and it still doesnt exist: add it as Pending Xfer
				# OR it was pending a delete and it still exists: change state to Pending Delete

				#TODO
				return

	return


