"""
WSGI config for glintv2 project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.10/howto/deployment/wsgi/
"""

import os
import atexit

from django.core.wsgi import get_wsgi_application

def cleanup():
	#perform cleanup
	from glintv2.utils import term_image_collection
	print("STOP IMAGE COLLECTION")
	term_image_collection()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "glintv2.settings")

application = get_wsgi_application()

atexit.register(cleanup)