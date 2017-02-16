from django.http import HttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied

from django.shortcuts import render, get_object_or_404
from .models import Project, User_Projects, User, Glint_User
from .forms import addRepoForm
from .glint_api import repo_connector, validate_repo


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
	repo_list = Project.objects.filter(project_name=project_name)
	image_list = ()
	for repo in repo_list:
		try:
			rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
			image_list= image_list + rcon.image_list
			
		except:
			print("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

	# we can make the image list a set because thorugh the 3-tuple it should be unique across all clouds
	# making it a set eliminates any duplicates if the same repo is added twice
	context = {
		'project': project_name,
		'repo_list': repo_list,
		'image_list': set(image_list)
	}
	return render(request, 'glintwebui/project_details.html', context)

#displays the form for adding a repo to a project and handles the post request
def add_repo(request, project_name):
	if request.method == 'POST':
		form = addRepoForm(request.POST)

		#Check if the form data is valid
		if form.is_valid():
			pass1 = form.cleaned_data['password1']
			pass2 = form.cleaned_data['password2']
			if pass1 == pass2:
				# all data is exists, check if the repo is valid
				validate_resp = validate_repo(auth_url=form.cleaned_data['auth_url'], tenant_name=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
				if (validate_resp[0]):
					new_repo = Project(project_name=form.cleaned_data['project_name'], auth_url=form.cleaned_data['auth_url'], tenant=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
					new_repo.save()


					#return to project details page?
					repo_list = Project.objects.filter(project_name=project_name)
					image_list = []
					for repo in repo_list:
						try:
							rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
							image_list= image_list + rcon.image_list
						except:
							print("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

					context = {
						'project': project_name,
						'repo_list': repo_list,
						'image_list': set(image_list)
					}
					return render(request, 'glintwebui/project_details.html', context)
				else:
					#something in the repo information is bad
					form = addRepoForm()
					context = {
						'project_name': project_name,
						'error_msg': validate_resp[1]
					}
				return render(request, 'glintwebui/add_repo.html', context, {'form': form})
			else:
				# all data is good except the passwords
				form = addRepoForm()
				context = {
					'project_name': project_name,
					'error_msg': "Passwords do not match."
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

