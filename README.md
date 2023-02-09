# Families Albums website
## About site
The site is a cloud storage for family albums and a platform for finding photos of your relatives or acquaintances in photos of other users (in their public albums).

## How does it work
To use the site, you must register and verify your email address. Right after that you will be able to upload your photos. If you don't want other users to see them, mark them as private. If you are interested to know if your friends are in the photos of other users - you should go through a simple procedure for processing your photos, and immediately after that you will be able to search for people who are in your photos!

## Technical description
The site uses django as a backend, bootstrap for layouts, as well as redis and a celery library for slow photo processing. The backend is divided into three applications. Each of them has its own purpose - registration/authorization, uploading/viewing/editing descriptions of photos, and identifying/searching for faces in other user's photos.