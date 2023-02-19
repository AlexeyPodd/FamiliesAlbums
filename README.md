# Families Albums website
## About site
The site is a cloud storage for family albums and a platform for finding photos of your relatives or acquaintances in
photos of other users (in their public albums).

## How does it work
To use the site, you must register and verify your email address. Right after that you will be able to upload your
photos. If you don't want other users to see them, mark them as private. If you are interested to know if your friends 
are in the photos of other users - you should go through a simple procedure for processing your photos, and immediately
after that you will be able to search for people who are in your photos!

## Technical description
### General
The site uses django as a backend, bootstrap for layouts, as well as redis and a celery library for slow photo 
processing. The backend is divided into three applications. Each of them has its own purpose -
registration/authorization, uploading/viewing/editing descriptions of photos, and identifying/searching 
for faces in other user's photos.

### Recognition app
Recognition app does two things: process the album creates patterns of people depicted in his photographs and search
for other images of one of these people in other peoples' photos.

#### Album processing stages:
1. **Face searching.** *(celery task)*
2. **Verification of founded faces.** *(manual)* Deletion of program mistakes.
3. **Faces compare and creating patterns.** *(celery task)*
4. **Verification of patterns.** *(manual)* Separating the faces of different people into different patterns
5. **Uniting patterns into people images.** *(manual)*
6. **Uniting people images of this album and other previously processed.** *(celery task)*
7. **Verification of unions.** *(manual)*
8. **Manual uniting people images.** *(manual)* If the program did not recognize images of one person, you can merge 
them manually.
9. **Saving new faces datas to Data Base** *(task)* Saved patterns are storing in clusters, those are forming fractal
tree.

#### Fractal tree clusters storing of patterns
The following structure has been developed specifically for the convenience of finding the most similar patterns.
Initially, there is an empty root cluster. Patterns are added to it as users' albums are processed. Once the cluster
limit is reached, the following happens:
1. Search for pattern that is most similar to the one being added.
2. It is retrieved from the cluster.
3. A new empty cluster is created and placed in its place.
4. Both patterns are placed in the newly created child cluster.
5. The new pattern will be filled with patterns until it reaches its limit. And then child clusters will also
6. be created in it.

#### Redis temporary data storing
Album processing needs to store data between process stages somewhere. For this purpose is performed by redis.
Redis stores the following keys:
1. album_{pk}: dict
   1. current_stage: int: range(1, 10)
   2. status: processing / completed
   3. number_of_processed_photos: int
   4. number_of_verified_patterns: int
   5. people_amount: int
2. photo_{pk}: dict: (i >= 1)
   1. face_{i}_location: byte.tuple
   2. face_{i}_encoding: byte.numpy_array
   3. faces_amount: int
3. album_{pk}_photos: list: slugs
4. album_{pk}\_pattern\_{i}: dict (i >= 1, j >= 1, k >= 1)
   1. face_{j}: photo_{pk}\_face\_{k}
   2. faces_amount: int
   3. person: int
5. album_{pk}\_person\_{i}: dict (i >= 1, j >= 1, k >= 1)
   1. pattern_{j}: int (link to p.4)
   2. tech_pair: person_{pk}
   3. real_pair: person_{pk}
6. album_{pk}_finished: no_faces / 1