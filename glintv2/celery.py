from __future__ import absolute_import, unicode_literals
from celery import Celery
from celery.utils.log import get_task_logger
from django.conf import settings
from .utils import  jsonify_image_list, update_pending_transactions, get_images_for_proj, set_images_for_proj, process_pending_transactions, process_state_changes, queue_state_change, find_image_by_name
from glintwebui.glint_api import repo_connector
import glintv2.config as config
 
logger = get_task_logger(__name__)

import os
import time
import redis
 
# Indicate Celery to use the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'glintv2.settings')
 
app = Celery('glintv2', broker=config.celery_url, backend=config.celery_backend)
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
    			
            except Exception as e:
                print(e)
                print("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

        # take the new json and compare it to the previous one
        # and merge the differences, generally the new one will be used but if there are any images awaiting
        # transfer or deletion they must be added to the list
        updated_img_list = update_pending_transactions(get_images_for_proj(project.project_name), jsonify_image_list(image_list=image_list, repo_list=repo_list))
        
        # now we have the most current version of the image matrix for this project
        # The last thing that needs to be done here is to proccess the PROJECTX_pending_transactions
        logger.info("Updating pending Transactions")
        updated_img_list = process_pending_transactions(project=project.project_name, json_img_dict=updated_img_list)
        logger.info("Proccessing state changes")
        updated_img_list = process_state_changes(project=project.project_name, json_img_dict=updated_img_list)
        set_images_for_proj(project=project.project_name, json_img_dict=updated_img_list)


    logger.info("Task finished")


# Accepts Image info, project name, and a repo object
# Must find and download the appropriate image (by name) and then upload it
# to the given image ID
@app.task(bind=True)
def transfer_image(self, image_name, image_id, project, auth_url, project_tenant, username, password):
    logger.info("attempting to transfer %s - %s" % (image_name, image_id))
    # Find image by name in another repo where the state=present
    # returns tuple: (auth_url, tenant, username, password, img_id)
    src_img_info = find_image_by_name(project=project, image_name=image_name)


    # Download said img to a scratch folder /tmp/ for now
    logger.info("Downloading Image from %s" % src_img_info[1])
    src_rcon = repo_connector(auth_url=src_img_info[0], project=src_img_info[1], username=src_img_info[2], password=src_img_info[3])
    src_rcon.download_image(image_name=image_name, image_id=src_img_info[4])

    # Upload said image to the new repo
    logger.info("Uploading Image to %s" % project_tenant)
    dest_rcon = repo_connector(auth_url=auth_url, project=project_tenant, username=username, password=password)
    dest_rcon.upload_image(image_id=image_id, image_name=image_name)
    # clean up scratch folder
    #TODO
    queue_state_change(project=project, repo=project_tenant, img_id=image_id, state='Present')
    logger.info("Task finished")
    return False

# Accepts image id, project name, and repo object to delete image ID from.
@app.task(bind=True)
def delete_image(self, image_id, project, auth_url, project_tenant, username, password):
    logger.info("attempting to delete %s" % image_id)
    rcon = repo_connector(auth_url=auth_url, project=project_tenant, username=username, password=password)
    result = rcon.delete_image(image_id)
    if result:
        queue_state_change(project=project, repo=project_tenant, img_id=image_id, state='deleted')
        logger.info("Task finished")
        return True
    logger.info("Unknown error deleting %s  (result = %s)" % (image_id, result))
    return False

# CELERY workers can get their own ID with self.request.id
# This will be useful during image transfers so there will be no conflicts