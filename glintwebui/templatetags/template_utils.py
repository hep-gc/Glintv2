from django.template.defaulttags import register
from django import template

register = template.Library()

@register.filter()
def get_item(template_dict, key):    
    return template_dict.get(key)
