# User Guide

## The matrix page:
The matrix page hosts the core functionality of the glint service. From here a user is able to download, upload, delete and transfer images between repos. A user can also switch between accounts, add repositories and review image conflicts detected by glint.
![/docs/Matrix.png]

1. Active account, to change account simply select the account you wish to switch to from the drop down menu.   
2. Link to manage the cloud repositories related to the active account. Allows you to Add/Delete/Edit repos.
3. If you have admin access you will see the "Admin Tools" dropdown. This menu gives you options to manage users and accounts.
4. If glint detects any conflicts of the images available on one account you will see this message and will be able to click the "View Image Conflicts" to view the details of the conflict(s).
5. The Image group selection lets you toggle between "Glint Images" and "Hidden Images" which are hidden in the matrix to reduce clutter. By default shared and public images are hidden.
6. The image text filter lets you filter the list of images in the matrix by text matching. Simply type in the name of the image you are interested in and the matrix will be filtered down to match your search.
7. The image matrix itself allows you to select images to be deleted or transfered. If there is an unchecked box it means the image isn't present on that repository- if you were to check that box and click the "Save Images" button Glint will scan the matrix and look for changes and perform the required deletes and transfers to match the state of the repositories to that of the matrix. Additionally a user can directly download an image by clicking the green arrow beside the associated image name.
8. Glint also allows for direct image uploads. Simply select the "Upload Image" button and provide a link to the image or a local file, choose the target repositories and finalize the upload.
9. The "Save Images" button saves the state of the matrix and performs any required actions to make the cloud repositories match the state of the matrix.


## Image Conflicts
Glint defines 3 types of image conflicts:

Type 1 - Image1 and Image2 have the same name but are different images.
Type 2 - Image1 and Image2 have the same name and are the same images.
Type 3 - Image1 and image 2 have different names but are the same images.

In the future we hope to have glint perform automatic name conflict resolution but for now all it does is detect these conflicts and displays them to the user who can take action where appropriate.
![/docs/Image_conflicts.png]


## Hidden Images
![/docs/Hidden_images.png]
By default all non-private images are hidden as glint typically does not have the privliges to manipulate these images. However, glint is capable of making copies of these images on a new repo so it may be useful to expose these images to the image Matrix. Shown in the image above, if an image is checked then it is hidden from glint. However, an image will not be hidden unless all copies (from different repos) of the image are hidden. To hide/expose an image from the glint image matrix simply toggle the check box to the desired state and select the "Hide/Show Images" button at the bottom of the table.


## Repository Management
The repo management page displays some information about the matrix and provides options to Edit (or delete) or add additional repos.
![/docs/Manage_repos1.png]


## User Management
Admin users will have the ability to add and edit glint users.
![/docs/User_management.png]


To add a new user simply select the "Add User" button and you will be supplied with a small form to input a new users information.
![/docs/Add_user.png]



## Account Management
Admin users will have the ability to add new accounts and manage user access to existing accounts.
![/docs/Account_management1]

1. To provide users access to an existing acount selec the "+" button and you will be provided with a dropdown of existing users to add to the account.
2. To edit the name of an account or delete it- select the "Edit" button and you will be provided with a small form edit or delete the account.
3. To add a new Account select the "Add Account" button and you will be provided with a form to enter the account information.
![/docs/Account_management2]