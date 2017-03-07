from django.http import HttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied


from django.shortcuts import render, get_object_or_404
from .models import Project, User_Projects, User, Glint_User
from .forms import addRepoForm
from .glint_api import repo_connector, validate_repo, change_image_name
from glintv2.utils import get_unique_image_list, get_images_for_proj, parse_pending_transactions, build_id_lookup_dict, check_for_duplicate_images

import json


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

	context = {
		'projects': User_Projects.objects.all(),
		'user': getUser(request),
		'all_users': User.objects.all(),
	}
	return render(request, 'glintwebui/index.html', context)



def users(request, users="N/A"):
    response = "The following are registered users: %s."
    return HttpResponse(response % users)



# Once the users are authenticated with a cert this page will no longer be needed 
# because everyone will see a unique landing page.
def user_projects(request, user_id="N/A"):
    return HttpResponse("Your projects: %s" % user_id)



def project_details(request, project_name="null_project"):
	# Since img name, img id is no longer a unique way to identify images across clouds
	# We will instead only use image name, img id will be used as a unique ID inside a given repo
	# this means we now have to create a new unique image set that is just the image names

	repo_list = Project.objects.filter(project_name=project_name)
	try:
		image_set = get_unique_image_list(project_name)
		image_dict = json.loads(get_images_for_proj(project_name))
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
				'project': project_name,
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
	context = {
		'project': project_name,
		'image_dict': image_dict,
		'image_set': image_set,
		'image_lookup': reverse_img_lookup
	}
	return render(request, 'glintwebui/project_details.html', context)



#displays the form for adding a repo to a project and handles the post request
def add_repo(request, project_name):
	if request.method == 'POST':
		form = addRepoForm(request.POST)

		#Check if the form data is valid
		if form.is_valid():
			# all data is exists, check if the repo is valid
			validate_resp = validate_repo(auth_url=form.cleaned_data['auth_url'], tenant_name=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'])
			if (validate_resp[0]):
				#check if repo/auth_url combo already exists
				try:
					if Project.objects.get(project_name=project_name, tenant=form.cleaned_data['tenant'], auth_url=form.cleaned_data['auth_url']) is not None:
						#This combo already exists
						context = {
							'project_name': project_name,
							'error_msg': "Repo already exists"
						}
						return render(request, 'glintwebui/add_repo.html', context, {'form': form})
				except Exception as e:
					# this exception could be tightened around the django "DoesNotExist" exception
					pass

				new_repo = Project(project_name=form.cleaned_data['project_name'], auth_url=form.cleaned_data['auth_url'], tenant=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'])
				new_repo.save()


				#return to project details page after saving the new repo
				repo_list = Project.objects.filter(project_name=project_name)
				image_list = ()
				for repo in repo_list:
					try:
						rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
						image_list= image_list + rcon.image_list
						
					except:
						print("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

					context = {
						'redirect_url': '/ui/project_details/' + project_name,
					}
					return render(request, 'glintwebui/proccessing_request.html', context)
			else:
				#something in the repo information is bad
				form = addRepoForm()
				context = {
					'project_name': project_name,
					'error_msg': validate_resp[1]
				}
			return render(request, 'glintwebui/add_repo.html', context, {'form': form})

		# Else there has been an error in the entry, display form with error msg
		else:
			form = addRepoForm()
			context = {
				'project_name': project_name,
				'error_msg': "Invalid form enteries."
			}
			return render(request, 'glintwebui/add_repo.html', context, {'form': form})

	#Not a post request, display form
	else:
		form = addRepoForm()
		context = {
			'project_name': project_name,
		}
		return render(request, 'glintwebui/add_repo.html', context, {'form': form})

def save_images(request, project_name):
	if request.method == 'POST':
		#get repos
		repo_list = Project.objects.filter(project_name=project_name)

		# need to iterate thru a for loop of the repos in this project and get the list for each and
		# check if we need to update any states
		# Every image will have to be checked since if they are not present it means they need to be deleted
		for repo in repo_list:
			#try:
			#these check lists will have all of the images that are checked and need to be cross referenced
			#against the images stored in redis to detect changes in state
			check_list = request.POST.getlist(repo.tenant)
			parse_pending_transactions(project=project_name, repo=repo.tenant, image_list=check_list)

			
		context = {
			'redirect_url': "/ui/project_details/" + project_name,
		}
		return render(request, 'glintwebui/proccessing_request.html', context)
	#Not a post request, display matrix
	else:
		return project_details(request, project_name=project_name)

def resolve_conflict(request, project_name, repo_name):
	if request.method == 'POST':
		repo_obj = Project.objects.get(project_name=project_name, tenant=repo_name)
		image_dict = json.loads(get_images_for_proj(project_name))
		changed_names = 0
		for key, value in request.POST.items():
			if key != 'csrfmiddlewaretoken':
				# check if the name has been changed, if it is different, send update
				if value != image_dict[repo_name][key]['name']:
					change_image_name(repo_obj, key, value)
					changed_names=changed_names+1
		if changed_names == 0:
			# Re render resolve conflict page
			# for now this will do nothing and we trust that the user will change the name.
			context = {
				'projects': User_Projects.objects.all(),
				'user': getUser(request),
				'all_users': User.objects.all(),
			}
			return render(request, 'glintwebui/index.html', context)

	context = {
		'redirect_url': "/ui/project_details/" + project_name,
	}
	return render(request, 'glintwebui/proccessing_request.html', context)

# may not need this def, could just render this page from the post views
def processing_request(request, project_name):

	context = {
		'redirect_url': None,
	}
	return render(request, 'glintwebui/proccessing_request.html', context)