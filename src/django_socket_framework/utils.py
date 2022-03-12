import base64
import mimetypes

from django.core.files.base import ContentFile

__all__ = ['base64_to_django_file']


def base64_to_django_file(data, name=None):
    file_mime, file_data = data.split(';base64,')
    file_mime = file_mime.replace('data:', '')
    name = name or ("Unknown" + (mimetypes.guess_extension(file_mime) or ''))
    return ContentFile(base64.b64decode(file_data), name=name)
