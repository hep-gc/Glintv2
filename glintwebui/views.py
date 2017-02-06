from django.http import HttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied

from django.shortcuts import render, get_object_or_404
from .models import Project, User_Projects, User, Glint_User
from .forms import addRepoForm

#import os


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
	#template = loader.get_template('glintwebui/project_details.html')
	context = {
		'project': project_name,
		'repo_list': Project.objects.filter(project_name=project_name)
	}
	return render(request, 'glintwebui/project_details.html', context)

#displays the form for adding a repo to a project
def add_repo(request, project_name):
	if request.method == 'POST':
		form = addRepoForm(request.POST)

		#Check if the form data is valid
		if form.is_valid():
			pass1 = form.cleaned_data['password1']
			pass2 = form.cleaned_data['password2']
			if pass1 == pass2:
				# all data is valid: save the info
				new_repo = Project(project_name=form.cleaned_data['project_name'], auth_url=form.cleaned_data['auth_url'], tenant=form.cleaned_data['tenant'], tenant_id=form.cleaned_data['tenant_id'], username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
				new_repo.save()


				#return to project details page?
				context = {
					'project': project_name,
					'repo_list': Project.objects.filter(project_name=project_name)
				}
				return render(request, 'glintwebui/project_details.html', context)
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



#this is the post view that actually saves the repo
def save_repo(request):
	return
