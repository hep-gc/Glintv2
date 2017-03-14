from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^project_details/(?P<project_name>.+)/$', views.project_details, name='project_details'),
    url(r'^add_repo/(?P<project_name>.+)/$', views.add_repo, name='add_repo'),
    url(r'^save_images/(?P<project_name>.+)/$', views.save_images, name='save_images'),
    url(r'^resolve_conflict/(?P<project_name>.+)/(?P<repo_name>.+)/$', views.resolve_conflict, name='resolve_conflict'),
]