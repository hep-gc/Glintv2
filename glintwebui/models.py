from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User


'''
The Glint User table provides the second layer of authentication and provides room for future developments
of alternative authenication methods (ssh, user/pw, etc)
'''
class Glint_User(models.Model):
    user_name = models.CharField(max_length=32)
    # May need another table for these instead of just a generic string field
    authentication_method = models.CharField(max_length=32, default="x509")
    common_name = models.CharField(max_length=64, default="")
    distinguished_name = models.CharField(max_length=64)    


    def __str__(self):
        return "%s" % (self.user_name)


'''
The project table will contain all information about a given project.
Atributes:
    - Project Name
    - URI
    - tenant(repo)
    - username (glint user for that cloud)
    - password (glint user pw for that cloud)
'''
class Project(models.Model):
    project_name = models.CharField(max_length=32)
    auth_url = models.CharField(max_length=256, default="")
    tenant = models.CharField(max_length=128, default="")
    #credentials? How to encrypt?
    username = models.CharField(max_length=64, default="")
    password = models.CharField(max_length=64, default="")

    def __str__(self):
        return self.project_name + ": " + self.tenant


'''
The User_Projects table will contain the correlation between users and the projects they have access to.
Attributes:
    - Project Name
    - User  (...glint user?)
    - Date last used
'''
class User_Projects(models.Model):
    project_name = models.CharField(max_length=32)
    user = models.ForeignKey(Glint_User, on_delete=models.CASCADE)
    last_used = models.DateTimeField()

    def __str__(self):
        return "%s: %s" % (self.project_name, self.user)
