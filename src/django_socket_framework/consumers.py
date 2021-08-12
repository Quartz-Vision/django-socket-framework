import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from .types import EventType, ErrorType, ConsumerError

from django.conf import settings

User = get_user_model()


class BaseConsumer(AsyncWebsocketConsumer):
    """
    Base consumer class that provides user authorization,
    separated API methods events interfaces
    """
    authorized = False
    user = None
    user_group_prefix = 'user__'
    user_group_name = None
    api_method_list_class = BaseConsumerMethodList
    api_method_list = None
    event_method_list_class = BaseConsumerMethodList
    event_method_list = None

    def __init__(self, *args, **kwargs):
        super(BaseConsumer, self).__init__(*args, **kwargs)
        self.api_method_list = self.api_method_list_class(self)
        self.event_method_list = self.event_method_list_class(self)

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        """On disconnect: remove the channel from the user group"""
        if self.authorized:
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def perform_authentication(self, token):
        """Performs token checking and current user gethering"""
        try:
            token = AccessToken(token)
            self.user = await sync_to_async(User.objects.get)(id=token['user_id'])
            self.user_group_name = self.user_group_prefix + str(self.user.pk)
            return True
        except Exception as e:
            return False

    async def authenticate(self, token):
        """Validates user token and gets the object using it"""
        if not token:
            raise ConsumerError("There is no access token.", ErrorType.FIELD_ERROR)
        if not self.perform_authentication(token):    
            raise ConsumerError("Authorization failed.", ErrorType.AUTHORIZATION_ERROR)

        self.authorized = True
        
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

    async def send(self, data=None, bytes_data=None, close=False):
        """Sends the data as JSON"""
        return await super(BaseConsumer, self).send(text_data=json.dumps(data))

    async def send_error(self, text=None, error_type=ErrorType.SYSTEM_ERROR, event_response_key=None, error=None):
        """Sends standard error messages of ERROR type"""
        additions = {}
        if error:
            text = str(error),
            error_type = getattr(error, "error_type", ErrorType.SYSTEM_ERROR),
            additions = getattr(error, 'addition_parameters', {})

        return await self.send({
            "type": EventType.ERROR,
            "data": {
                "detail": text,
                "type": error_type,
                "event_response_key": event_response_key,
                **additions
            }
        })

    async def send_group_event(self, group_name, method, data=None, event_response_key=None):
        """Sends event call to the group"""
        return await self.channel_layer.group_send(
            group_name, {
                'type': 'call_event',
                'event_response_key': event_response_key,
                'method_name': method,
                'initiator_id': self.user.id if self.authorized else None,
                'data': data
            }
        )

    async def send_to_user(self, user_id, method, data=None):
        """Shorthand for send_group_event with user group"""
        return await self.send_group_event(self.user_group_prefix + str(user_id), method, data)

    async def user_return(self, data):
        """Sends the data to all points where the user is logged from"""
        await self.send_to_user(self.user.id, 'common_return', data)

    async def handle_error(self, error, event_response_key=None):
        """This method decides what to do with errors"""
        await self.send_error(
            error=(
                error if isinstance(error, ConsumerError) or getattr(settings, "DEBUG", False)
                else "Internal Server Error"
            ),
            event_response_key=event_response_key
        )
        print(error, event_response_key)

    async def receive(self, text_data=None, bytes_data=None):
        """Tries to login the user and then calls methods"""
        data = {}
        try:
            data = json.loads(text_data)

            if type(data) != dict:
                data = {}
                raise ConsumerError("The data has to be a JSON-object.")

            if not self.authorized:
                await self.authenticate(data.get('access_token'))

            res = await self.api_method_list.__call_method__(
                data.get('method'), **data.get("args", {})
            )
            if res is not None:
                await self.send(res)

        except Exception as e:
            await self.handle_error(
                error=e,
                event_response_key=(data or {}).get("args", {}).get("event_response_key")
            )

    async def call_event(self, event):
        event_response_key = event.get('event_response_key')
        try:
            await self.event_method_list.__call_method__(
                event.get('method_name'),
                initiator_id=event.get('initiator_id'),
                data=event.get('data'),
                event_response_key=event_response_key
            )
        except Exception as e:
            await self.handle_error(
                error=e,
                event_response_key=event_response_key
            )
