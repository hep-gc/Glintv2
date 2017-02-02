from django.http import HttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied

from django.shortcuts import render, get_object_or_404
from .models import Project, User, Glint_User

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
		'projects': Project.objects.all(),
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
	}
	return render(request, 'glintwebui/project_details.html', context)