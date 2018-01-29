from django.http import HttpResponse
from django.http import StreamingHttpResponse
#from django.template import loader

from django.core.exceptions import PermissionDenied


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from .models import Project, User_Account, Glint_User, Account
from .forms import addRepoForm
from .glint_api import repo_connector, validate_repo, change_image_name
from glintv2.utils import get_unique_image_list, get_images_for_proj, parse_pending_transactions, build_id_lookup_dict, repo_modified, get_conflicts_for_acc, find_image_by_name, add_cached_image, check_cached_images, increment_transactions, check_for_existing_images, get_hidden_image_list, parse_hidden_images
from glintv2.__version__ import version

import glintv2.config as config
import time
import os
import json
import logging
import redis
import urllib2
import bcrypt
import datetime

logger =  logging.getLogger('glintv2')


def getUser(request):
    user = request.META.get('REMOTE_USER')
    auth_user_list = Glint_User.objects.all()
    for auth_user in auth_user_list:
        if user == auth_user.common_name:
            user = auth_user.user_name
            break
    return user


def verifyUser(request):
    auth_user = getUser(request)
    auth_user_list = Glint_User.objects.all()
    for user in auth_user_list:
        if auth_user == user.user_name:
            return True

    return False

def getSuperUserStatus(request):
    auth_user = getUser(request)
    auth_user_obj = User.objects.get(username=auth_user)
    if auth_user_obj.is_superuser:
        return True

    else:
        # Since apache registers username and common name entries differently we also have to
        # check if the user's table entry for a common name, this probably isn't needed since
        # both table rows are updated on any change but better safe than sorry
        user = request.META.get('REMOTE_USER')
        auth_user_list = Glint_User.objects.all()
        for auth_user in auth_user_list:
            if user == auth_user.user_name:
                user = auth_user.common_name
        try:
            auth_user_obj = User.objects.get(username=user)
            return auth_user_obj.is_superuser
        except Exception as e:
            # if this fails it means the user has never authenticated with a certificate
            # and that they do not have super user status
            return False



def index(request):

    if not verifyUser(request):
        raise PermissionDenied

    # This is a good place to spawn the data-collection worker thread
    # The one drawback is if someone tries to go directly to another page before hitting this one
    # It may be better to put it in the urls.py file then pass in the repo/image info
    # If it cannot be accessed it means its deed and needs to be spawned again.
    active_user = getUser(request)
    user_obj = Glint_User.objects.get(user_name=active_user)
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




def project_details(request, account_name="No accounts available", message=None):
    # Since img name, img id is no longer a unique way to identify images across clouds
    # We will instead only use image name, img id will be used as a unique ID inside a given repo
    # this means we now have to create a new unique image set that is just the image names
    if not verifyUser(request):
        raise PermissionDenied
    active_user = getUser(request)
    user_obj = Glint_User.objects.get(user_name=active_user)
    if account_name is None or account_name in "No accounts available" :
        # First time user, lets put them at the first project the have access to
        try:
            account_name = User_Account.objects.filter(user=user_obj).first().account_name.account_name
            if not account_name:
                account_name="No accounts available"
        except:
            # catches nonetype error
            account_name="No accounts available"

    user_obj.active_project = account_name
    user_obj.save()


    repo_list = Project.objects.all()
    try:
        image_set = get_unique_image_list(account_name)
        hidden_image_set = get_hidden_image_list(account_name)
        image_dict = json.loads(get_images_for_proj(account_name))
        # since we are using name as the unique identifer we need to pass in a dictionary
        # that lets us get the image id (uuid) from the repo and image name
        # We will have to implement logic here that spots two images with the same name
        # and forces the user to resolve
        reverse_img_lookup = build_id_lookup_dict(image_dict)

    except:
        # No images in database yet, may want some logic here forcing it to wait a little on start up
        logger.info("No images yet in database, or possible error collecting image sets")
        image_set = None
        hidden_image_set = None
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

    conflict_dict = get_conflicts_for_acc(account_name)
    context = {
        'account_name': account_name,
        'account_list': account_list,
        'image_dict': image_dict,
        'image_set': image_set,
        'hidden_image_set': hidden_image_set,
        'image_lookup': reverse_img_lookup,
        'message': message,
        'is_superuser': getSuperUserStatus(request),
        'conflict_dict': conflict_dict,
        'version': version
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
            validate_resp = validate_repo(auth_url=form.cleaned_data['auth_url'], tenant_name=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'], user_domain_name=form.cleaned_data['user_domain_name'], project_domain_name=form.cleaned_data['project_domain_name'])
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
                #check if alias is already in use
                try:
                    if Project.objects.get(account_name=account_name, alias=form.cleaned_data['alias']) is not None:
                        #This alias already exists
                        context = {
                            'account_name': account_name,
                            'error_msg': "Alias already in use"
                        }
                        return render(request, 'glintwebui/add_repo.html', context, {'form': form})
                except Exception as e:
                    # this exception could be tightened around the django "DoesNotExist" exception
                    pass

                new_repo = Project(account_name=account_name, auth_url=form.cleaned_data['auth_url'], tenant=form.cleaned_data['tenant'], username=form.cleaned_data['username'], password=form.cleaned_data['password'], alias=form.cleaned_data['alias'], user_domain_name=form.cleaned_data['user_domain_name'], project_domain_name=form.cleaned_data['project_domain_name'])
                new_repo.save()
                repo_modified()


                #return to manage repos page after saving the new repo
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
            #these check lists will have all of the images that are checked and need to be cross referenced
            #against the images stored in redis to detect changes in state
            check_list = request.POST.getlist(repo.alias)
            parse_pending_transactions(account_name=account_name, repo_alias=repo.alias, image_list=check_list, user=user)

        #give collection thread a couple seconds to process the request
        #ideally this will be removed in the future
        time.sleep(2)
        message = "Please allow glint a few seconds to proccess your request."
        return project_details(request, account_name=account_name, message=message)
    #Not a post request, display matrix
    else:
        return project_details(request, account_name=account_name)


# this function accepts a post request and updates the hidden status of any images within.
def save_hidden_images(request, account_name):
    if not verifyUser(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = getUser(request)
        #get repos
        repo_list = Project.objects.filter(account_name=account_name)

        # need to iterate thru a for loop of the repos in this project and get the list for each and
        # check if we need to change any of the hidden states
        for repo in repo_list:
            check_list = request.POST.getlist(repo.alias)
            parse_hidden_images(account_name=account_name, repo_alias=repo.alias, image_list=check_list, user=user)

    message = "Please allow glint a few seconds to proccess your request."
    return project_details(request=request, account_name=account_name, message=message)


def resolve_conflict(request, account_name, repo_alias):
    if not verifyUser(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = getUser(request)
        repo_obj = Project.objects.get(account_name=account_name, alias=repo_alias)
        image_dict = json.loads(get_images_for_proj(account_name))
        changed_names = 0
        #key is img_id, calue is image name
        for key, value in request.POST.items():
            if key != 'csrfmiddlewaretoken':
                # check if the name has been changed, if it is different, send update
                if value != image_dict[repo_alias][key]['name']:
                    change_image_name(repo_obj=repo_obj, img_id=key, old_img_name=image_dict[repo_alias][key]['name'], new_img_name=value, user=user)
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

    repo_modified()
    #give the collection thread a couple seconds to update matrix or we will end right back at this page
    #This entire function will change as we change the way glint deals with duplicate images.
    time.sleep(6)
    return project_details(request, account_name, "")


# This page will render manage_repos.html which will allow users to add, edit, or delete repos
# It would be a good idea to redesign the add repo page to be used to update existing repos
# in addition to adding new ones. However it may be easier to just make a copy of it and modify
# it slightly for use updating existing repos.
def manage_repos(request, account_name, feedback_msg=None, error_msg=None):
    if not verifyUser(request):
        raise PermissionDenied
    active_user = getUser(request)
    user_obj = Glint_User.objects.get(user_name=active_user)
    repo_list = Project.objects.filter(account_name=account_name)

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
        'account': account_name,
        'account_list': account_list,
        'repo_list': repo_list,
        'feedback_msg': feedback_msg,
        'error_msg': error_msg,
        'is_superuser': getSuperUserStatus(request),
        'version': version

    }
    return render(request, 'glintwebui/manage_repos.html', context)


def update_repo(request, account_name):
    if not verifyUser(request):
        raise PermissionDenied
    logger.info("Attempting to update repo")
    if request.method == 'POST':
        #handle update may want to do some data cleansing here? I think django utils deals with most of it tho
        usr = request.POST.get('username')
        pwd = request.POST.get('password')
        auth_url = request.POST.get('auth_url')
        tenant = request.POST.get('tenant')
        proj_id = request.POST.get('proj_id')
        project_domain_name = request.POST.get('project_domain_name')
        user_domain_name = request.POST.get('user_domain_name')

        # probably a more effecient way to do the if below, perhaps to a try/catch without using .get
        if usr is not None and pwd is not None and auth_url is not None and tenant is not None and proj_id is not None:
            #data is there, check if it is valid
            validate_resp = validate_repo(auth_url=auth_url, tenant_name=tenant, username=usr, password=pwd, user_domain_name=user_domain_name, project_domain_name=project_domain_name)
            if (validate_resp[0]):
                # new data is good, grab the old repo and update to the new info
                repo_obj = Project.objects.get(proj_id=proj_id)
                repo_obj.username = usr
                repo_obj.auth_url = auth_url
                repo_obj.tenant_name = tenant
                repo_obj.password = pwd
                repo_obj.project_domain_name = project_domain_name
                repo_obj.user_domain_name = user_domain_name
                repo_obj.save()
            else:
                #invalid changes, reload manage_repos page with error msg
                return manage_repos(request=request, account_name=account_name, error_msg=validate_resp[1])
        repo_modified()
        return manage_repos(request=request, account_name=account_name, feedback_msg="Update Successful")

    else:
        #not a post, shouldnt be coming here, redirect to matrix page
        return project_details(request, account_name)

def delete_repo(request, account_name):
    if not verifyUser(request):
        logger.info("Verifying User")
        raise PermissionDenied
    if request.method == 'POST':
        #handle delete
        repo = request.POST.get('repo')
        repo_id = request.POST.get('repo_id')
        if repo is not None and repo_id is not None:
            logger.info("Attempting to delete repo: %s" % repo)
            Project.objects.filter(tenant=repo, proj_id=repo_id).delete()
            repo_modified()
            return HttpResponse(True)
        else:
            #invalid post, return false
            return HttpResponse(False)
        #Execution should never reach here, but it it does- return false
        return HttpResponse(False)
    else:
        #not a post, shouldnt be coming here, redirect to matrix page
        return project_details(request, account_name)


def add_user(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = request.POST.get('username')
        pass1 = request.POST.get('pass1')
        pass2 = request.POST.get('pass2')
        common_name = request.POST.get('common_name')
        distinguished_name = request.POST.get('distinguished_name')
        logger.info("Adding user %s" % user)
        try:
            # Check that the passwords are valid
            if pass1 is not None and pass2 is not None:
                if pass1 != pass2:
                    logger.error("Passwords do not match")
                    message = "Passwords did not match, add user cancelled"
                    return manage_users(request, message)
                elif len(pass1)<4:
                    logger.error("Password too short")
                    message = "Password too short, password must be at least 4 characters"
                    return manage_users(request, message)
            else:
                #else at least one of the passwords was empty
                logger.error("One or more passwords empty")
                message = "One or more passwords empty, please make sure they match"
                return manage_users(request, message)
            #passwords should be good at this point


            #check if username exists, if not add it
            user_found = Glint_User.objects.filter(user_name=user)
            logger.error("Found user %s, already in system" % user_found[0])
            #if we get here it means the user already exists
            message = "Unable to add user, username already exists"
            return manage_users(request, message)
        except Exception as e:
            #If we are here we are good since the username doesnt exist. add it and return
            glint_user = Glint_User(user_name=user, common_name=common_name, distinguished_name=distinguished_name, password=bcrypt.hashpw(pass1.encode(), bcrypt.gensalt(prefix=b"2a")))
            glint_user.save()
            message = "User %s added successfully" % user
            return manage_users(request, message)

    else:
        #not a post, should never come to this page
        pass


def self_update_user(request):
    if not verifyUser(request):
        raise PermissionDenied

    if request.method == 'POST':
        original_user = request.POST.get('old_usr')
        if not original_user == getUser(request):
            raise PermissionDenied
        pass1 = request.POST.get('pass1')
        pass2 = request.POST.get('pass2')
        common_name = request.POST.get('common_name')
        distinguished_name = request.POST.get('distinguished_name')

        # Check passwords for length and ensure they are both the same, if left empty the password wont be updated
        if pass1 and pass2:
            if pass1 != pass2:
                logger.error("new passwords do not match, unable to update user")
                message = "New passwords did not match, update cancelled"
                return user_settings(request, message)
            elif len(pass1)<4:
                logger.error("new password too short, cancelling update")
                message = "New password too short, password must be at least 4 characters, please try again"
                return user_settings(request, message)

        logger.info("Updating info for user %s" % original_user)
        try:
            glint_user_obj = Glint_User.objects.get(user_name=original_user)
            glint_user_obj.common_name = common_name
            glint_user_obj.distinguished_name = distinguished_name
            if len(pass1)>3:
                glint_user_obj.password = bcrypt.hashpw(pass1.encode(), bcrypt.gensalt(prefix=b"2a"))
            glint_user_obj.save()
            message = "User " + original_user + " updated successfully."
        except Exception as e:
            logger.error("Unable to retrieve user %s, there may be a database inconsistency." % original_user)
            logger.error(e)
            return user_settings(request)

        return redirect('project_details', message=message) 
    else:
        #not a post should never come to this page
        pass


def update_user(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        original_user = request.POST.get('old_usr')
        user = request.POST.get('username')
        pass1 = request.POST.get('pass1')
        pass2 = request.POST.get('pass2')
        common_name = request.POST.get('common_name')
        distinguished_name = request.POST.get('distinguished_name')
        admin_status = request.POST.get('admin')
        if admin_status is None:
            admin_status = False
        else:
            admin_status = True

        # Check passwords for length and ensure they are both the same, if left empty the password wont be updated
        if pass1 and pass2:
            if pass1 != pass2:
                logger.error("new passwords do not match, unable to update user")
                message = "New passwords did not match, update cancelled"
                return manage_users(request, message)
            elif len(pass1)<4:
                logger.error("new password too short, cancelling update")
                message = "New password too short, password must be at least 4 characters, please try again"
                return manage_users(request, message)

        logger.info("Updating info for user %s" % original_user)
        try:
            glint_user_obj = Glint_User.objects.get(user_name=original_user)
            glint_user_obj.user_name = user
            glint_user_obj.common_name = common_name
            glint_user_obj.distinguished_name = distinguished_name
            if len(pass1)>3:
                glint_user_obj.password = bcrypt.hashpw(pass1.encode(), bcrypt.gensalt(prefix=b"2a"))
            glint_user_obj.save()
            message = "User " + user + " updated successfully."
        except Exception as e:
            logger.error("Unable to retrieve user %s, there may be a database inconsistency." % original_user)
            logger.error(e)
            return manage_users(request)
        try:
            #its possible that one or both objects are still missing from the auth database
            user_obj = User.objects.get(username=common_name)
            user_obj.is_superuser = admin_status
            user_obj.save()
            user_obj = User.objects.get(username=user)
            user_obj.is_superuser = admin_status
            user_obj.save()
        except Exception as e:
            #if we get here the user has never connected with a certificate before so we need to manually insert them into the auth db
            #first check if they have done a password authentication
            try:
                user_obj = User.objects.get(username=user)
            except User.DoesNotExist:
                user_obj = None
            # If un/pw authentication is also missing lets make both from scratch
            if user_obj is None:
                new_user = User(username=common_name, is_superuser=admin_status, is_staff=admin_status,is_active=True, date_joined=datetime.datetime.now())
                new_user.save()
                new_user = User(username=user, is_superuser=admin_status, is_staff=admin_status,is_active=True, date_joined=datetime.datetime.now())
                new_user.save()

            #else we have the un/pw auth and we can copy it
            else:
                user_obj.is_superuser = admin_status
                user_obj.save()
                new_user = User(username=common_name, is_superuser=admin_status, is_staff=user_obj.is_staff,is_active=user_obj.is_active, date_joined=user_obj.date_joined)
                new_user.save()

        return manage_users(request, message) 
    else:
        #not a post should never come to this page
        pass

        
def delete_user(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = request.POST.get('user')
        logger.info("Attempting to delete user %s" % user)
        user_obj = Glint_User.objects.get(user_name=user)
        user_obj.delete()
        message = "User %s deleted." % user
        return manage_users(request, message)
    else:
        #not a post
        pass

#only glint admins can manage glint users
def manage_users(request, message=None):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    user_list = Glint_User.objects.all()
    user_obj_list = User.objects.filter(is_superuser=1)
    admin_list = []
    for usr in user_obj_list:
        admin_list.append(usr.username)
    context = {
        'user_list': user_list,
        'admin_list': admin_list,
        'message': message,
        'is_superuser': getSuperUserStatus(request),
        'version': version
    }
    return render(request, 'glintwebui/manage_users.html', context)


def user_settings(request, message=None):
    if not verifyUser(request):
        raise PermissionDenied
    user_obj = Glint_User.objects.get(user_name=getUser(request))

    context = {
        'message': message,
        'is_superuser': getSuperUserStatus(request),
        'user_obj': user_obj,
        'version': version
    }
    return render(request, 'glintwebui/user_settings.html', context)


def delete_user_account(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = request.POST.get('user')
        account = request.POST.get('account')
        logger.info("Attempting to delete user %s from account %s" % (user, account))
        user_obj = Glint_User.objects.get(user_name=user)
        user_obj.active_project = None
        user_obj.save()
        account_obj = Account.objects.get(account_name=account)
        user_account_obj = User_Account.objects.get(user=user_obj, account_name=account_obj)
        user_account_obj.delete()
        message = "User %s deleted from %s" % (user, account)
        return manage_users(request, message)
    else:
        #not a post
        pass

def add_user_account(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        user = request.POST.get('user')
        account = request.POST.get('account')
        user_obj = None
        account_obj = None
        logger.info("Attempting to add user %s to account %s" % (user, account))
        try:
            user_obj = Glint_User.objects.get(user_name=user)
            account_obj = Account.objects.get(account_name=account)
        except Exception as e:
            logger.error("Either user or account does not exist, could not add user_account.")
            logger.error(e)
        try:
            #check to make sure it's not already there
            logger.info("Checking if user already has access.")
            User_Account.objects.get(user=user_obj, account_name=account_obj)
            #if we continue here the user account already exists and we can return without adding it
            message = "%s already has access to %s" % (user, account)
            return manage_accounts(request, message)
        except Exception as e:
            #If we get here the user account wasn't present and we can safely add it
            logger.info("No previous entry, adding new user_account")
            new_usr_act = User_Account(user=user_obj, account_name=account_obj)
            new_usr_act.save()
            message = "User %s added to %s" % (user, account)
            return manage_accounts(request=request, message=message)
    else:
        #not a post
        pass

def delete_account(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        account = request.POST.get('account')
        logger.info("Attempting to delete account %s" % account)
        account_obj = Account.objects.get(account_name=account)
        account_obj.delete()
        message = "Account %s deleted." % account
        #need to also remove any instanced where this account was the active one for users.
        try:
            users = Glint_User.objects.get(active_project=account)
            if(users is not None):
                for user in users:
                    user.active_project = None
                    user.save()
        except:
            #No accounts tied to this account
            logger.info("No users to clean-up..")
        logger.info("Successfull delete of account %s" % account)
        return HttpResponse(True)
    else:
        #not a post
        pass
def update_account(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        old_account = request.POST.get('old_account')
        new_account = request.POST.get('account')
        logger.info("Attempting to update account name %s to %s" % (old_account, new_account))
        #check for accounts with the new name
        try:
            new_account_obj = Account.objects.get(account_name=new_account)\
            #name already taken, don't edit the name and return
            logger.info("Could not update account name to %s, name already in use" % new_account)
            message = "Could not update account name to %s, name already in use" % new_account
            return manage_accounts(request=request, message=message)
        except Exception as e:
            #No account has the new name, proceed freely
            account_obj = Account.objects.get(account_name=old_account)
            account_obj.account_name = new_account
            account_obj.save()
            message = "Successfully updated account name to %s" % new_account
            logger.info("Successfully updated account name to %s" % new_account)
            return manage_accounts(request=request, message=message)
    else:
        #not a post
        pass

#only glint admins can add new accounts
def add_account(request):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied
    if request.method == 'POST':
        account = request.POST.get('account')
        logger.info("Attempting to add account %s" % account)
        try:
            account_obj = Account.objects.get(account_name=account)
            #account exists, return without adding
            message = "Account with that name already exists"
            logger.info("Could not add account %s, name already in use." % account)
            return manage_accounts(request=request, message=message)
        except Exception as e:
            #account doesnt exist, we can go ahead and add it.
            new_act = Account(account_name=account)
            new_act.save()
            logging.info("Account '%s' created successfully" % account)
            message = "Account '%s' created successfully" % account
            return manage_accounts(request=request, message=message)
        pass
    else:
        #not a post should never come to this page, redirect to matrix?
        pass

def manage_accounts(request, message=None):
    if not verifyUser(request):
        raise PermissionDenied
    if not getSuperUserStatus(request):
        raise PermissionDenied

    #Retrieve accounts, build account:user dictionary
    account_user_dict = {}
    account_list = Account.objects.all()
    user_accounts = User_Account.objects.all()
    user_list = Glint_User.objects.all()
    for usr_act in user_accounts:
        #check if this account is in dict yet
        if usr_act.account_name in account_user_dict:
            #if so append this user to that key
            account_user_dict[usr_act.account_name].append(usr_act.user.user_name)
        else:
            #else create new key with user
            account_user_dict[usr_act.account_name] = list()
            account_user_dict[usr_act.account_name].append(usr_act.user.user_name)

    context = {
        'account_list': account_list,
        'account_user_dict': account_user_dict,
        'user_list': user_list,
        'message': message,
        'is_superuser': getSuperUserStatus(request),
        'version': version

    }
    return render(request, 'glintwebui/manage_accounts.html', context)


def download_image(request, account_name, image_name):
    if not verifyUser(request):
        raise PermissionDenied

    logger.info("Preparing to download image file.")
    # returns (repo_obj.auth_url, repo_obj.tenant, repo_obj.username, repo_obj.password, image_id, img_checksum)
    image_info = find_image_by_name(account_name=account_name, image_name=image_name)

    # Find image location
    image_id=image_info[4]

    # Check download location to see if image is there already
    # This function should update the timestamp if it finds a hit
    tentative_path = check_cached_images(image_name, image_info[5])
    if tentative_path is not None:
        #return the image using this path
        logger.info("Found cached local copy...")
        filename = image_name
        response = StreamingHttpResponse((line for line in open(tentative_path,'r')))
        response['Content-Disposition'] = "attachment; filename={0}".format(filename)
        response['Content-Length'] = os.path.getsize(tentative_path)
        return response

    # Download image

    if not os.path.exists("/var/www/glintv2/scratch/"):
        os.makedirs("/var/www/glintv2/scratch/")
    logger.info("No cached copy found, downloading image file.")
    rcon = repo_connector(auth_url=image_info[0], project=image_info[1], username=image_info[2], password=image_info[3])
    rcon.download_image(image_name=image_name, image_id=image_id, scratch_dir="/var/www/glintv2/scratch/")

    # add to download table in redis
    filename = image_name
    file_full_path = "/var/www/glintv2/scratch/" + image_name
    add_cached_image(image_name, image_checksum=image_info[5], full_path=file_full_path)


    response = StreamingHttpResponse((line for line in open(file_full_path,'r')))
    response['Content-Disposition'] = "attachment; filename={0}".format(filename)
    response['Content-Length'] = os.path.getsize(file_full_path)
    return response

def upload_image(request, account_name):
    if not verifyUser(request):
        raise PermissionDenied

    try:
        image_file = request.FILES['myfile']
    except Exception as e:
        # no file means it's not a POST or it's an upload by URL
        image_file = False

    if request.method == 'POST' and image_file:

        #process image upload
        image_file = request.FILES['myfile']
        file_path = "/var/www/glintv2/scratch/" + image_file.name

        #before we save it locally let us check if it is already in the repos
        cloud_alias_list = request.POST.getlist('clouds')
        bad_clouds = check_for_existing_images(account_name, cloud_alias_list, image_file.name)
        if len(bad_clouds)>0:
            for cloud in bad_clouds:
                cloud_alias_list.remove(cloud)
            message = "Upload failed for one or more projects because the image name was already in use."

        if len(cloud_alias_list)==0:
            #if we have eliminated all the target clouds, return with error message
            message = "Upload failed to all target projects because the image name was already in use."
            image_dict = json.loads(get_images_for_proj(account_name))
            context = {
                'account_name': account_name,
                'image_dict': image_dict,
                'max_repos': len(image_dict),
                'message': message
            }
            return render(request, 'glintwebui/upload_image.html', context)

        #And finally before we save locally double check that file doesn't already exist
        valid_path = True
        if(os.path.exists(file_path)):
            valid_path = False
            # Filename exists locally, we need to use a temp folder
            for x in range(0,10):
                #first check if the temp folder exists
                file_path = "/var/www/glintv2/scratch/" + str(x)
                if not os.path.exists(file_path):
                    #create temp folder and break since it is definitly empty
                    os.makedirs(file_path)
                    file_path = "/var/www/glintv2/scratch/" + str(x) + "/" + image_file.name
                    valid_path = True
                    break

                #then check if the file is in that folder
                file_path = "/var/www/glintv2/scratch/" + str(x) + "/" + image_file.name
                if not os.path.exists(file_path):
                    valid_path = True
                    break

        if not valid_path:
            #turn away request since there is already multiple files with this name being uploaded
            image_dict = json.loads(get_images_for_proj(account_name))
            context = {
                'account_name': account_name,
                'image_dict': image_dict,
                'max_repos': len(image_dict),
                'message': "Too many images by that name being uploaded, please try again in a few minutes."
            }
            return render(request, 'glintwebui/upload_image.html', context)

        disk_format = request.POST.get('disk_format')
        with open(file_path, 'wb+') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)

        # now queue the uploads to the destination clouds
        r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
        user = getUser(request)
        for cloud in cloud_alias_list:
            logger.info("Queing image upload to %s" % cloud)
            transaction = {
                'user': user,
                'action':  'upload',
                'account_name': account_name,
                'repo': cloud,
                'image_name': image_file.name,
                'local_path': file_path,
                'disk_format': disk_format,
                'container_format': "bare"
            }
            trans_key = account_name + "_pending_transactions"
            r.rpush(trans_key, json.dumps(transaction))
            increment_transactions()
            

        #return to project details page with message
        return redirect('project_details', account_name=account_name)

    elif request.method == 'POST' and request.POST.get('myfileurl'):

        #download the image
        img_url = request.POST.get('myfileurl')
        image_name = img_url.rsplit("/", 1)[-1]
        file_path = "/var/www/glintv2/scratch/" + image_name
        # check if a file with that name already exists
        valid_path = True
        if(os.path.exists(file_path)):
            valid_path = False
            # Filename exists locally, we need to use a temp folder
            for x in range(0,10):
                #first check if the temp folder exists
                file_path = "/var/www/glintv2/scratch/" + str(x)
                if not os.path.exists(file_path):
                    #create temp folder and break since it is definitly empty
                    os.makedirs(file_path)
                    file_path = "/var/www/glintv2/scratch/" + str(x) + "/" + image_name
                    valid_path = True
                    break

                #then check if the file is in that folder
                file_path = "/var/www/glintv2/scratch/" + str(x) + "/" + image_name
                if not os.path.exists(file_path):
                    valid_path = True
                    break

        if not valid_path:
            #turn away request since there is already multiple files with this name being uploaded
            image_dict = json.loads(get_images_for_proj(account_name))
            context = {
                'account_name': account_name,
                'image_dict': image_dict,
                'max_repos': len(image_dict),
                'message': "Too many images by that name being uploaded or bad URL, please check the url and try again in a few minutes."
            }
            return render(request, 'glintwebui/upload_image.html', context)

        # Probably could use some checks here to make sure it is a valid image file.
        # In reality the user should be smart enough to only put in an image file and
        # in the case where they aren't openstack will still except the garbage file
        # as a raw image.
        image_data = urllib2.urlopen(img_url)

        with open(file_path, "wb") as image_file:
            image_file.write(image_data.read())
        
        disk_format = request.POST.get('disk_format')
        # now upload it to the destination clouds
        cloud_alias_list = request.POST.getlist('clouds')
        r = redis.StrictRedis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
        user = getUser(request)
        for cloud in cloud_alias_list:
            transaction = {
                'user': user,
                'action':  'upload',
                'account_name': account_name,
                'repo': cloud,
                'image_name': image_name,
                'local_path': file_path,
                'disk_format': disk_format,
                'container_format': "bare"
            }
            trans_key = account_name + "_pending_transactions"
            r.rpush(trans_key, json.dumps(transaction))
            increment_transactions()
            

        #return to project details page with message
        return redirect('project_details', account_name=account_name)
    else:
        #render page to upload image

        image_dict = json.loads(get_images_for_proj(account_name))
        context = {
            'account_name': account_name,
            'image_dict': image_dict,
            'max_repos': len(image_dict),
            'message': None
        }
        return render(request, 'glintwebui/upload_image.html', context)
