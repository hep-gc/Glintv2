"""glintv2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import RedirectView

from .celery_app import image_collection
from .utils import check_collection_task, set_collection_task

urlpatterns = [
    #url(r'^glintwebui/', include('glintwebui.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^$', RedirectView.as_view(url='ui/')), #root index goes to the glintwebui
    url(r'^ui/', include('glintwebui.urls')), 
    url(r'^users/', include('glintwebui.urls')), 
    url(r'^projects/', include('glintwebui.urls')), 
    url(r'^project_details/', include('glintwebui.urls')), 
]

# Check if the image collection task is running, if not start it and set it to running
collection_started = check_collection_task()
if not collection_started:
    image_collection.delay()
    set_collection_task(True)
