from django import forms

class addRepoForm(forms.Form):
    auth_url = forms.CharField(label="auth_url", max_length=256)
    tenant = forms.CharField(label="tenant", max_length=128)
    username = forms.CharField(label="username", max_length=64)
    password = forms.CharField(widget=forms.PasswordInput(), label="password", max_length=64)

