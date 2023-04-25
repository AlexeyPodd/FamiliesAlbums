def set_random_album_cover(album):
    if album.is_private:
        cover = album.photos_set.order_by('?').first()
    else:
        cover = album.photos_set.filter(is_private=False).order_by('?').first()

    album.miniature = cover
    album.save()


def clear_photo_favorites_and_faces(photo, commit=True):
    photo.in_users_favorites.clear()
    if photo.faces_extracted:
        for face in photo.faces_set.all():
            face.delete()
        photo.faces_extracted = False

    if commit:
        photo.save()
