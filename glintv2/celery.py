from __future__ import absolute_import, unicode_literals
from celery import Celery
from celery.utils.log import get_task_logger
from django.conf import settings
from .utils import  jsonify_image_list, update_pending_transactions, get_images_for_proj, set_images_for_proj, process_pending_transactions

 
logger = get_task_logger(__name__)

import os
import redis
 
# Indicate Celery to use the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'glintv2.settings')
 
app = Celery('glintv2', broker='redis://localhost:6379/0', backend='redis://localhost:6379/')
app.config_from_object('django.conf:settings')
# This line will tell Celery to autodiscover all your tasks.py that are in your app folders
# However it seems to have issues in an apache/django enviroment
#app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@app.task(bind=True)
def image_collection(self):

    from glintwebui.models import Project, User_Projects
    from glintwebui.glint_api import repo_connector

    logger.info("Start Image collection")
    project_list = User_Projects.objects.all()

    for project in project_list:
        repo_list = Project.objects.filter(project_name=project.project_name)
        image_list = ()
        for repo in repo_list:
            try:
                rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
                image_list= image_list + rcon.image_list
    			
            except:
                print("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

        # take the new json and compare it to the previous one
        # and merge the differences, generally the new one will be used but if there are any images awaiting
        # transfer or deletion they must be added to the list
        updated_img_list = update_pending_transactions(get_images_for_proj(project.project_name), jsonify_image_list(image_list=image_list, repo_list=repo_list))
        
        # now we have the most current version of the image matrix for this project
        # The last thing that needs to be done here is to proccess the PROJECTX_pending_transactions
        updated_img_list = process_pending_transactions(project=project.project_name, json_img_dict=updated_img_list)

        set_images_for_proj(project=project.project_name, json_img_dict=updated_img_list)


    logger.info("Task finished")