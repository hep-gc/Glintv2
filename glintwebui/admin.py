from django.contrib import admin


from .models import Project, Glint_User, Account, User_Account

admin.site.register(Project)
admin.site.register(Glint_User)
admin.site.register(Account)
admin.site.register(User_Account)
