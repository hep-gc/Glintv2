from __future__ import absolute_import, unicode_literals
from celery import Celery
from celery.utils.log import get_task_logger
from django.conf import settings
from .utils import  jsonify_image_list, update_pending_transactions, get_images_for_proj, set_images_for_proj, process_pending_transactions, process_state_changes, queue_state_change, find_image_by_name, check_delete_restrictions, decrement_transactions, get_num_transactions, repo_proccesed, check_for_repo_changes, set_collection_task, check_for_image_conflicts, set_conflicts_for_acc
from glintwebui.glint_api import repo_connector
import glintv2.config as config
 
logger = get_task_logger(__name__)

import os
import time
import redis
import subprocess

 


# Indicate Celery to use the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'glintv2.settings')
import django
django.setup()
 
app = Celery('glintv2', broker=config.celery_url, backend=config.celery_backend)
app.config_from_object('django.conf:settings')



# This line will tell Celery to autodiscover all your tasks.py that are in your app folders
# However it seems to have issues in an apache/django enviroment
#app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@app.task(bind=True)
def debug_task(self):
    logger.debug('Request: {0!r}'.format(self.request))


@app.task(bind=True)
def image_collection(self):

    from glintwebui.models import Project, User_Account, Account
    from glintwebui.glint_api import repo_connector

    wait_period = 0
    term_signal = False
    num_tx = get_num_transactions()

    #perminant for loop to monitor image states and to queue up tasks
    while(True):
        # First check for term signal
        logger.debug("Term signal: %s" % term_signal)
        if term_signal is True:
            #term signal detected, break while loop
            logger.info("Term signal detected, shutting down")
            set_collection_task(False)
            return
        logger.info("Start Image collection")
        account_list = Account.objects.all()

        for account in account_list:
            repo_list = Project.objects.filter(account_name=account.account_name)
            image_list = ()
            for repo in repo_list:
                try:
                    rcon = repo_connector(auth_url=repo.auth_url, project=repo.tenant, username=repo.username, password=repo.password)
                    image_list= image_list + rcon.image_list

                except Exception as e:
                    logger.error(e)
                    logger.error("Could not connet to repo: %s at %s", (repo.tenant, repo.auth_url))

            # take the new json and compare it to the previous one
            # and merge the differences, generally the new one will be used but if there are any images awaiting
            # transfer or deletion they must be added to the list
            updated_img_list = update_pending_transactions(get_images_for_proj(account.account_name), jsonify_image_list(image_list=image_list, repo_list=repo_list))
            
        
            # now we have the most current version of the image matrix for this account
            # The last thing that needs to be done here is to proccess the PROJECTX_pending_transactions
            logger.info("Processing pending Transactions for account: %s" % account.account_name)
            updated_img_list = process_pending_transactions(account_name=account.account_name, json_img_dict=updated_img_list)
            logger.info("Proccessing state changes for account: %s" % account.account_name)
            updated_img_list = process_state_changes(account_name=account.account_name, json_img_dict=updated_img_list)
            set_images_for_proj(account_name=account.account_name, json_img_dict=updated_img_list)

            # Need to build conflict dictionary to be displayed on matrix page.
            # check for image conflicts function returns a dictionary of conflicts, keyed by the repos
            conflict_dict = check_for_image_conflicts(json_img_dict=updated_img_list)
            set_conflicts_for_acc(account_name=account.account_name, conflict_dict=conflict_dict)

        logger.info("Image collection complete, entering downtime")#, sleeping for 1 second")
        loop_counter = 0
        if(num_tx == 0):
            wait_period = config.image_collection_interval
        else:
            wait_period = 0
            
        while(loop_counter<wait_period):
            time.sleep(5)
            num_tx = get_num_transactions()
            #check for new transactions
            if(num_tx>0):
                break
            #check if repos have been added or deleted
            if(check_for_repo_changes()):
                repo_proccesed()
                break

            #check if httpd is running
            output = subprocess.check_output(['ps', '-A'])
            if 'httpd' not in output:
                #apache has shut down, time for image collection to do the same
                logger.info("httpd offile, terminating")
                term_signal = True
                break
            loop_counter = loop_counter+1
        num_tx = get_num_transactions()




# Accepts Image info, project name, and a repo object
# Must find and download the appropriate image (by name) and then upload it
# to the given image ID
@app.task(bind=True)
def transfer_image(self, image_name, image_id, account_name, auth_url, project_tenant, username, password, requesting_user, project_alias):
    logger.info("User %s attempting to transfer %s - %s to repo '%s'" % (requesting_user, image_name, image_id, project_tenant))
    #First check if this thread's scratch folder exists:
    scratch_dir = "/tmp/" + self.request.id + "/"
    if not os.path.exists(scratch_dir):
        os.makedirs(scratch_dir)

    # Find image by name in another repo where the state=present
    # returns tuple: (auth_url, tenant, username, password, img_id)
    src_img_info = find_image_by_name(account_name=account_name, image_name=image_name)


    # Download said img to a scratch folder /tmp/ for now
    logger.info("Downloading Image from %s" % src_img_info[1])
    src_rcon = repo_connector(auth_url=src_img_info[0], project=src_img_info[1], username=src_img_info[2], password=src_img_info[3])
    src_rcon.download_image(image_name=image_name, image_id=src_img_info[4], scratch_dir=scratch_dir)

    # Upload said image to the new repo
    logger.info("Uploading Image to %s" % project_tenant)
    dest_rcon = repo_connector(auth_url=auth_url, project=project_tenant, username=username, password=password)
    dest_rcon.upload_image(image_id=image_id, image_name=image_name, scratch_dir=scratch_dir)
 
    queue_state_change(account_name=account_name, repo=project_alias, img_id=image_id, state='Present')
    logger.info("Image transfer finished")
    decrement_transactions()
    return True

# Accepts image id, project name, and repo object to delete image ID from.
@app.task(bind=True)
def delete_image(self, image_id, image_name, account_name, auth_url, project_tenant, username, password, requesting_user, project_alias):
    logger.info("User %s attempting to delete %s - %s from repo '%s'" % (requesting_user, image_name, image_id, project_tenant))
    if check_delete_restrictions(image_id=image_id, account_name=account_name, project_alias=project_alias):
        rcon = repo_connector(auth_url=auth_url, project=project_tenant, username=username, password=password)
        result = rcon.delete_image(image_id)
        if result:
            queue_state_change(account_name=account_name, repo=project_alias, img_id=image_id, state='deleted')
            logger.info("Image Delete finished")
            decrement_transactions()
            return True
        logger.error("Unknown error deleting %s  (result = %s)" % (image_id, result))
        decrement_transactions()
        return False
    else:
        logger.error("Delete request violates delete rules, image either shared or the last copy.")
        queue_state_change(account_name=account_name, repo=project_alias, img_id=image_id, state='present')
        decrement_transactions()
        return False

