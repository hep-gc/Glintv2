from django.contrib import admin


from .models import Project, Glint_User, User_Projects

admin.site.register(Project)
admin.site.register(Glint_User)
admin.site.register(User_Projects)
