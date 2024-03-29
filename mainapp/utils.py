import os
from datetime import datetime
import tempfile
import zipfile
from math import ceil
from wsgiref.util import FileWrapper

from django.core.paginator import Paginator
from django.db import models

from photoalbums.settings import BASE_DIR


def get_photo_save_path(instance, filename):
    date = datetime.now().strftime("%Y/%m/%d")
    return f'photos/{date}/{instance.album.slug}/{instance.slug}.{filename.split(".")[-1]}'


def get_photos_title(filename):
    return filename[:filename.rindex('.')]


def get_zip(album, private_access=False):
    temp = tempfile.TemporaryFile()
    archive = zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED)

    if private_access:
        photos = album.photos_set.all()
    else:
        photos = album.photos_set.filter(is_private=False)

    photos_filename_titles = []
    for photo in photos:
        filepath = os.path.abspath(os.path.join(BASE_DIR, photo.original.url[1:]))
        file_title = photo.title

        # Making sure filename is uniq
        if file_title in photos_filename_titles:
            i = 1
            while file_title + f"({i})" in photos_filename_titles:
                i += 1
            file_title += f"({i})"
        photos_filename_titles.append(file_title)

        filename = file_title + os.path.splitext(filepath)[-1]
        archive.write(filepath, filename)

    archive.close()
    temp.seek(0)

    return FileWrapper(temp)


def delete_from_favorites(user, obj):
    obj.in_users_favorites.remove(user)
    obj.save()


class FavoritesPaginator(Paginator):
    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True, deltafirst=1):
        self.deltafirst = deltafirst
        super().__init__(object_list, per_page, orphans=orphans, allow_empty_first_page=allow_empty_first_page)

    def page(self, number):
        """Returns a Page object for the given 1-based page number."""
        number = self.validate_number(number)
        if number == 1:
            bottom = 0
            top = self.per_page - self.deltafirst
        else:
            bottom = (number - 1) * self.per_page - self.deltafirst
            top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count
        return self._get_page(self.object_list[bottom:top], number, self)

    @property
    def num_pages(self):
        if self.count == 0 and not self.allow_empty_first_page:
            return 0
        count = max(self.count - self.per_page + self.deltafirst, 0)
        hits = max(0, count - self.orphans)
        return 1 + ceil(hits / self.per_page)
        

class TruncatingCharField(models.CharField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value:
            return value[:self.max_length]
        return value


class AboutPageInfo:
    def __init__(self, section_id, text_first, img_url, title, paragraphs):
        self.section_id = section_id
        self.text_first = text_first
        self.img_url = img_url
        self.paragraphs = paragraphs
        self.title = title
