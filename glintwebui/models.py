from __future__ import unicode_literals

from django.db import models


class Project(models.Model):
    project_name = models.CharField(max_length=40)
    #credentials?

    def __str__(self):
        return self.project_name


class Repo(models.Model):
    repo_name = models.CharField(max_length=40)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    def __str__(self):
        return "%s: %s" % (self.project, self.repo_name)


class User(models.Model):
    user_id = models.AutoField(primary_key=True)
    public_key = models.CharField(max_length=200)

    def __str__(self):
        return "%d" % (self.user_id)


#not sure if this one is neccesary??
class User_Projects(models.Model):
	project = models.ForeignKey(Project, on_delete=models.CASCADE)
	user_id = models.ForeignKey(User, on_delete=models.CASCADE)

	def __str__(self):
		return "%s: %s" % (self.project, self.user_id)
