class FaceData:
    def __init__(self, photo_pk, index, location, encoding):
        self._photo_pk = photo_pk
        self._index = index
        self._location = location
        self._encoding = encoding

    @property
    def photo_pk(self):
        return self._photo_pk

    @property
    def index(self):
        return self._index

    @property
    def location(self):
        return self._location

    @property
    def encoding(self):
        return self._encoding


class PatternData:
    def __init__(self, face):
        self._faces = [face]

    def add_face(self, face):
        if type(face) is not FaceData:
            raise TypeError("Must be Face.")
        self._faces.append(face)

    def __iter__(self):
        return iter(self._faces)

    def __len__(self):
        return len(self._faces)


class PersonData:
    def __init__(self):
        self._patterns = []

    def add_pattern(self, pattern):
        if type(pattern) is not PatternData:
            raise TypeError("Must be Pattern.")
        self._patterns.append(pattern)
