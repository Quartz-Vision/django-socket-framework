from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import AccessToken

from django_socket_framework.auth.types import ConsumerAuthorizationError
from django_socket_framework.middlewares import ConsumerMiddleware

__all__ = ['BaseTokenAuthMiddleware', 'JWTAuthMiddleware']


class BaseTokenAuthMiddleware(ConsumerMiddleware):
    async def get_user_by_token(self, token):
        """Performs token checking and returns it's owner"""
        pass

    async def handle(self, consumer, data, *args, **kwargs):
        """Performs user authentication"""
        if consumer.authenticated:
            return data

        token = data.get('access_token')
        if not token:
            raise ConsumerAuthorizationError(_("There is no access token."))
        user = await self.get_user_by_token(token)
        
        if not user:
            raise ConsumerAuthorizationError(_("Authorization failed."))
        await consumer.authenticate(user)

        return data


class JWTAuthMiddleware(BaseTokenAuthMiddleware):
    async def get_user_by_token(self, token):
        """Performs token checking and returns it's owner"""
        try:
            token = AccessToken(token)
            return await sync_to_async(get_user_model().objects.get)(id=token['user_id'])
        except Exception as e:
            return None
