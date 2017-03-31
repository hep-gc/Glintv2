from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^project_details/(?P<account_name>.+)/$', views.project_details, name='project_details'),
    url(r'^add_repo/(?P<account_name>.+)/$', views.add_repo, name='add_repo'),
    url(r'^manage_repos/(?P<account_name>.+)/$', views.manage_repos, name='manage_repos'),
    url(r'^update_repo/(?P<account_name>.+)/$', views.update_repo, name='update_repo'),
    url(r'^delete_repo/(?P<account_name>.+)/$', views.delete_repo, name='delete_repo'),
    url(r'^save_images/(?P<account_name>.+)/$', views.save_images, name='save_images'),
    url(r'^resolve_conflict/(?P<account_name>.+)/(?P<repo_name>.+)/$', views.resolve_conflict, name='resolve_conflict'),
]