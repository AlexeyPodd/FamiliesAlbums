from django.forms import BooleanField


class VerifyMatchField(BooleanField):
    def __init__(self, new_per_img, old_per_img, *args, **kwargs):
        self.new_per_img = new_per_img
        self.old_per_img = old_per_img
        super().__init__(*args, **kwargs)
