Glint Version 2 aims to replicate the functionality of the original Glint
while simplifying it by decoupling it from an Openstack instance.

The basic premise is to use grid certificates to authenticate users and 
allow them to transfer virtual machine images between project repositories.
This is accomplished by running a Django webserver using apache+mod_ssl
and maintaining a mapping of user to projects in the glint database.
Once a user has authenticated Glint knows what project they are able to
access and uses a generic set of credentials to access the glance API
to move the images.



Development notes:
- Database file must be read/writable by the apache user and be living in
a folder that is read/writable by the apache user.
- The server certificate and key files are not in Github and must be installed
manually
- There is still no ansible deployment script, but eventually everything except
the private key and cert files should be installed by ansible
- The grid certificate is registered to glintv2.heprc.uvic.ca so your browser
and apache instance may get warnings until we register the domain name.
- Anyone with a grid certificate is added as an auth_user but there will be
stops put in place to restrict their access until they are registered to some
projets by an Admin.