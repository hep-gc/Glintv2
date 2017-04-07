from django.http import HttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied


from django.shortcuts import render, get_object_or_404
from .models import Project, User_Account, Glint_User
from .forms import addRepoForm
from .glint_api import repo_connector, validate_repo, change_image_name
from glintv2.utils import get_unique_image_list, get_images_for_proj, parse_pending_transactions, build_id_lookup_dict, check_for_duplicate_images

import time
import json
import logging

logger =  logging.getLogger('glintv2')


def getUser(request):
	return request.META.get('REMOTE_USER')



def verifyUser(request):
	cert_user = getUser(request)
	auth_user_list = Glint_User.objects.all()
	for user in auth_user_list:
		if cert_user == user.common_name:
			return True

	return False


def index(request):

	if not verifyUser(request):
		raise PermissionDenied

	# This is a good place to spawn the data-collection worker thread
	# The one drawback is if someone tries to go directly to another page before hitting this one
	# It may be better to put it in the urls.py file then pass in the repo/image info
	# If it cannot be accessed it means its deed and needs to be spawned again.
	active_user = getUser(request)
	user_obj = Glint_User.objects.get(common_name=active_user)
	user_account = User_Account.objects.filter(user=user_obj)
	if user_account is None:
		#User has access to no accounts yet, tell them to contact admin
		#Render index page that has the above info
		pass
	else:
		#Else go to the last account that was active for that user
		active_project = user_obj.active_project
		return project_details(request, active_project)
		

	context = {
		'projects': User_Account.objects.all(),
		'user': getUser(request),
		'all_users': User.objects.all(),
	}
	return render(request, 'glintwebui/index.html', context)




def project_details(request, account_name="null_project"):
	# Since img name, img id is no longer a unique way to identify images across clouds
	# We will instead only use image name, img id will be used as a unique ID inside a given repo
	# this means we now have to create a new unique image set that is just the image names
	if not verifyUser(request):
		raise PermissionDenied
	active_user = getUser(request)
	user_obj = Glint_User.objects.get(common_name=active_user)
	if account_name is None:
		# First time user, lets put them at the first project the have access to
		account_name = User_Account.objects.filter(user=user_obj).first()

	user_obj.active_project = account_name
	user_obj.save()


	repo_list = Project.objects.all()
	proj_alias_dict = {}
	for repo in repo_list:
		proj_alias_dict[repo.tenant] = repo.alias
	try:
		image_set = get_unique_image_list(account_name)
		image_dict = json.loads(get_images_for_proj(account_name))
		# since we are using name as the unique identifer we need to pass in a dictionary
		# that lets us get the image id (uuid) from the repo and image name
		# We will have to implement logic here that spots two images with the same name
		# and forces the user to resolve
		reverse_img_lookup = build_id_lookup_dict(image_dict)

		# Check if there are any duplicate image names in a given repo and
		# if so render a different page that attempts to resolve that
		duplicate_dict = check_for_duplicate_images(image_dict)
		if duplicate_dict is not None:
			# Find the problem repo:
			for image in duplicate_dict:
				problem_repo = duplicate_dict[image]['repo']
			# Render page to resolve name difference
			context = {
				'account_name': account_name,
				'repo': problem_repo,
				'duplicate_dict': duplicate_dict
			}
			return render(request, 'glintwebui/image_conflict.html', context)

	except:
		# No images in database yet, may want some logic here forcing it to wait a little on start up
		image_set = None
		image_dict = None
		reverse_img_lookup = None
		# Should render a page here that says no image info available please refresh in 20 seconds

	# The image_list is a unique list of images stored in tuples (img_id, img_name)
	# Still need to add detection for images that have different names but the same ID
	user_accounts = User_Account.objects.filter(user=user_obj)
	account_list = []
	for acct in user_accounts:
		act_name = acct.account_name
		account_list.append(act_name)
	try:
		account_list.remove(account_name)
	except ValueError as e:
		#list is empty
		pass
	context = {
		'account_name': account_name,
		'account_list': account_list,
		'image_dict': image_dict,
		'image_set': image_set,
		'image_lookup': reverse_img_lookup,
		'proj_alias_dict': proj_alias_dict
	}
	return render(request, 'glintwebui/project_details.html', context)



#displays the form for adding a repo to a project and handles the post request
def add_repo(request, account_name):
	if not verifyUser(request):
		raise PermissionDenied
	if request.method == 'POST':
		form = addRepoForm(request.POST)
		user = getUser(request)

		#Check if the form data is valid
		if form.is_valid():
			logger.info("Attempting to add new repo for User:" + user)
			# all data is exists, check if the repo is valid
			validate_resp = validate_repo(auth_url=form.cleaned_data['auth_url'], tenant_name=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'])
			if (validate_resp[0]):
				#check if repo/auth_url combo already exists
				try:
					if Project.objects.get(account_name=account_name, tenant=form.cleaned_data['tenant'], auth_url=form.cleaned_data['auth_url']) is not None:
						#This combo already exists
						context = {
							'account_name': account_name,
							'error_msg': "Repo already exists"
						}
						return render(request, 'glintwebui/add_repo.html', context, {'form': form})
				except Exception as e:
					# this exception could be tightened around the django "DoesNotExist" exception
					pass

				new_repo = Project(account_name=account_name, auth_url=form.cleaned_data['auth_url'], tenant=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'], alias=form.cleaned_data['alias'])
				new_repo.save()


				#return to project details page after saving the new repo
				repo_list = Project.objects.filter(account_name=account_name)
				image_list = ()
				for repo in repo_list:
					try:
						rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
						image_list = image_list + rcon.image_list
						
					except:
						logger.error("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

					
					logger.info("New repo: " + form.cleaned_data['tenant'] + " added.")
					return manage_repos(request, account_name, feedback_msg="Project: " + form.cleaned_data['tenant'] + " added")
			else:
				#something in the repo information is bad
				form = addRepoForm()
				context = {
					'account_name': account_name,
					'error_msg': validate_resp[1]
				}
				logger.error("Failed to add repo.")
			return render(request, 'glintwebui/add_repo.html', context, {'form': form})

		# Else there has been an error in the entry, display form with error msg
		else:
			form = addRepoForm()
			context = {
				'account_name': account_name,
				'error_msg': "Invalid form enteries."
			}
			return render(request, 'glintwebui/add_repo.html', context, {'form': form})

	#Not a post request, display form
	else:
		form = addRepoForm()
		context = {
			'account_name': account_name,
		}
		return render(request, 'glintwebui/add_repo.html', context, {'form': form})

def save_images(request, account_name):
	if not verifyUser(request):
		raise PermissionDenied
	if request.method == 'POST':
		user = getUser(request)
		#get repos
		repo_list = Project.objects.filter(account_name=account_name)

		# need to iterate thru a for loop of the repos in this project and get the list for each and
		# check if we need to update any states
		# Every image will have to be checked since if they are not present it means they need to be deleted
		for repo in repo_list:
			#try:
			#these check lists will have all of the images that are checked and need to be cross referenced
			#against the images stored in redis to detect changes in state
			check_list = request.POST.getlist(repo.alias)
			#logger.debug(check_list)
			parse_pending_transactions(account_name=account_name, repo_alias=repo.alias, image_list=check_list, user=user)

		#give collection thread a couple seconds to process the request
		#ideally this will be removed in the future
		time.sleep(2)
		return project_details(request, account_name=account_name)
	#Not a post request, display matrix
	else:
		return project_details(request, account_name=account_name)

def resolve_conflict(request, account_name, repo_name):
	if not verifyUser(request):
		raise PermissionDenied
	if request.method == 'POST':
		user = getUser(request)
		repo_obj = Project.objects.get(account_name=account_name, tenant=repo_name)
		image_dict = json.loads(get_images_for_proj(account_name))
		changed_names = 0
		for key, value in request.POST.items():
			if key != 'csrfmiddlewaretoken':
				# check if the name has been changed, if it is different, send update
				if value != image_dict[repo_name][key]['name']:
					change_image_name(repo_obj=repo_obj, img_id=key, old_img_name=image_dict[repo_name][key]['name'], new_img_name=value, user=user)
					changed_names=changed_names+1
		if changed_names == 0:
			# Re render resolve conflict page
			# for now this will do nothing and we trust that the user will change the name.
			context = {
				'projects': User_Account.objects.all(),
				'user': user,
				'all_users': User.objects.all(),
			}
			return render(request, 'glintwebui/index.html', context)

	context = {
		'redirect_url': "/ui/project_details/" + account_name,
	}
	return render(request, 'glintwebui/proccessing_request.html', context)


# This page will render manage_repos.html which will allow users to add, edit, or delete repos
# It would be a good idea to redesign the add repo page to be used to update existing repos
# in addition to adding new ones. However it may be easier to just make a copy of it and modify
# it slightly for use updating existing repos.
def manage_repos(request, account_name, feedback_msg=None, error_msg=None):
	if not verifyUser(request):
		raise PermissionDenied
	active_user = getUser(request)
	repo_list = Project.objects.filter(account_name=account_name)
	context = {
		'account': account_name,
		'repo_list': repo_list,
		'feedback_msg': feedback_msg,
		'error_msg': error_msg,
	}
	return render(request, 'glintwebui/manage_repos.html', context)


def update_repo(request, account_name):
	if not verifyUser(request):
		raise PermissionDenied
	logger.info("Attempting to update repo")
	active_user = getUser(request)
	if request.method == 'POST':
		#handle update
		usr = request.POST.get('username')
		pwd = request.POST.get('password')
		auth_url = request.POST.get('auth_url')
		tenant = request.POST.get('tenant')
		proj_id = request.POST.get('proj_id')

		# probably a more effecient way to do the if below, perhaps to a try/catch without using .get
		if usr is not None and pwd is not None and auth_url is not None and tenant is not None and proj_id is not None:
			#data is there, check if it is valid
			validate_resp = validate_repo(auth_url=auth_url, tenant_name=tenant, username=usr, password=pwd)
			if (validate_resp[0]):
				# new data is good, grab the old repo and update to the new info
				repo_obj = Project.objects.get(proj_id=proj_id)
				repo_obj.username = usr
				repo_obj.auth_url = auth_url
				repo_obj.tenant_name = tenant
				repo_obj.password = pwd
				repo_obj.save()
			else:
				#invalid changes, reload manage_repos page with error msg
				return manage_repos(request=request, account_name=account_name, error_msg=validate_resp[1])

		return manage_repos(request=request, account_name=account_name, feedback_msg="Update Successful")

	else:
		#not a post, shouldnt be coming here, redirect to matrix page
		return project_details(request, account_name)

def delete_repo(request, account_name):
	if not verifyUser(request):
		logger.info("Verifying User")
		raise PermissionDenied
	active_user = getUser(request)
	if request.method == 'POST':
		#handle delete
		repo = request.POST.get('repo')
		repo_id = request.POST.get('repo_id')
		if repo is not None and repo_id is not None:
			logger.info("Attempting to delete repo: %s" % repo)
			Project.objects.filter(tenant=repo, proj_id=repo_id).delete()
			return HttpResponse(True)
		else:
			#invalid post, return false
			return HttpResponse(False)
		#Execution should never reach here, but it it does- return false
		return HttpResponse(False)
	else:
		#not a post, shouldnt be coming here, redirect to matrix page
		return project_details(request, account_name)