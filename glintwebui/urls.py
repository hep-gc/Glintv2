from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^users/$', views.users, name='users'),
    url(r'^projects/$', views.user_projects, name='user_projects'),
    url(r'^project_details/(?P<project_name>.+)/$', views.project_details, name='project_details'),
]