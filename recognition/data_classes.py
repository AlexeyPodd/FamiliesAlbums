import face_recognition as fr


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
        self._central_face = face

    def add_face(self, face):
        if type(face) is not FaceData:
            raise TypeError("Must be Face.")
        self._faces.append(face)

    def find_central_face(self):
        min_dist_sum = central_face = None
        for face in self._faces:
            compare_face_list = self._faces.copy()
            compare_face_list.remove(face)
            compare_encs = list(map(lambda f: f.encoding, compare_face_list))
            distances = fr.face_distance(compare_encs, face.encoding)
            dist_sum = sum(distances)
            if min_dist_sum is None or dist_sum < min_dist_sum:
                min_dist_sum = dist_sum
                central_face = face

        self._central_face = central_face

    @property
    def central_face(self):
        return self._central_face

    @central_face.setter
    def central_face(self, value):
        if value not in self._faces:
            raise ValueError("Central face must be one of its faces.")
        self._central_face = value

    @central_face.setter
    def central_face(self, value):
        if type(value) != FaceData or value not in self._faces:
            raise ValueError("Center parameter must be face of this pattern.")
        self._central_face = value

    def __iter__(self):
        return iter(self._faces)

    def __len__(self):
        return len(self._faces)


class PersonData:
    def __init__(self, redis_indx=None, pk=None, pair_pk=None):
        self._patterns = []
        self._redis_indx = redis_indx
        self._pk = pk
        self._pair_pk = pair_pk

    def add_pattern(self, pattern):
        if type(pattern) is not PatternData:
            raise TypeError("Must be Pattern.")
        self._patterns.append(pattern)

    def __iter__(self):
        return iter(self._patterns)

    def __getitem__(self, item):
        return self._patterns[item]

    @property
    def redis_indx(self):
        return self._redis_indx

    @property
    def pk(self):
        return self._pk

    @property
    def pair_pk(self):
        return self._pair_pk
