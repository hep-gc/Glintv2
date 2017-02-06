from django import forms

class addRepoForm(forms.Form):
    project_name = forms.CharField(label='project_name', max_length=32)
    auth_url = forms.CharField(label="auth_url", max_length=256)
    tenant = forms.CharField(label="tenant", max_length=128)
    tenant_id = forms.CharField(label="tenant_id", max_length=64)
    username = forms.CharField(label="username", max_length=64)
    password1 = forms.CharField(widget=forms.PasswordInput(), label="password", max_length=64)
    password2 = forms.CharField(widget=forms.PasswordInput(), label="password", max_length=64)


