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

#### Skips of stages:
1. 1 -> no_faces *(no faces found)*
2. 2 -> no_faces *(no faces verified)*
3. 2 -> 6 *(1 face verified and saved faces exists)*
4. 2 -> 9 *(1 face verified and no saved faces exists)*
5. 3 -> 4 -> 5 *(every pattern has one face)*
6. 4 -> 6 *(1 pattern formed and saved faces exists)*
7. 4 -> 9 *(1 pattern formed and no saved faces exists)*
8. 5 -> 9 *(no saved faces exists)*
9. 6 -> 8 *(no tech paired created and saved people)*
10. 7 -> 9 *(no not paired created or saved people)*

#### Recognised faces data storing in Data Base
&nbsp;&nbsp;&nbsp;&nbsp;Each face entry contains link to photo, location in photo and encoding.   
&nbsp;&nbsp;&nbsp;&nbsp;Each pattern entry contains faces, that belong to the same person and were identified 
by the program as belonging to the same person.   
&nbsp;&nbsp;&nbsp;&nbsp;Each person entry contains group of patterns, and link to user, in whose photos were found 
faces of its patterns.

&nbsp;&nbsp;&nbsp;&nbsp;Also for faster search of similar people,
patterns are united into clusters by the principle of similarity.

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
Album processing needs to store data between process stages somewhere. This purpose is performed by redis.
Redis stores the following keys:

**Album processing**:
1. album_{pk}: dict
   - current_stage: int: range(1, 10)
   - status: processing / completed
   - number_of_processed_photos: int
   - number_of_verified_patterns: int
   - people_amount: int
2. photo_{pk}: dict: (i >= 1)
   - face_{i}_location: byte.tuple
   - face_{i}_encoding: byte.numpy_array
   - faces_amount: int
3. album_{pk}_photos: list: slugs
4. album_{pk}\_pattern\_{i}: dict (i >= 1, j >= 1, k >= 1)
   - face_{j}: photo_{pk}\_face\_{k}
   - faces_amount: int
   - person: int
5. album_{pk}\_person\_{i}: dict (i >= 1, j >= 1, k >= 1)
   - pattern_{j}: int (link to p.4)
   - tech_pair: person_{pk}
   - real_pair: person_{pk}
6. album_{pk}_finished: no_faces / 1

**Searching for similar people**:
1. person_{pk}_processed_patterns_amount: int
2. nearest_people_to_{pk}: list: int