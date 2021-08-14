import json
import asyncio
from collections.abc import Sequence

from asgiref.sync import sync_to_async
from channels.consumer import AsyncConsumer
from channels.exceptions import DenyConnection, StopConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from .method_list import BaseConsumerMethodList, BaseConsumerEventMethodList
from .types import EventType, ErrorType, BaseConsumerError, Response, ConsumerSystemError, ConsumerTypeError

from django.conf import settings

User = get_user_model()


class BaseConsumer(AsyncConsumer):
    """
    Base consumer class that provides user authorization,
    separated API methods and events interfaces
    """

    base_groups: Sequence = []
    active_groups: set = set()

    async def attach_group(self, group_name: str):
        """
        Adds a new group to the layer
        """
        if group_name not in self.active_groups:
            self.active_groups.add(group_name)
            await self.channel_layer.group_add(group_name, self.channel_name)

    async def detach_group(self, group_name: str):
        """
        Removes a group from the layer
        """
        if group_name in self.active_groups:
            self.active_groups.remove(group_name)
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def detach_all_groups(self):
        """
        Detaches all the groups from the layer
        """
        await asyncio.wait(
            self.detach_group(group)
            for group in set(self.active_groups)
        )

    async def init_base_groups(self):
        """
        Activates all groups from base_groups
        """
        await asyncio.wait(
            self.attach_group(group)
            for group in self.base_groups
        )

    async def websocket_connect(self, message):
        """
        Called when a WebSocket connection is opened.
        """
        try:
            await self.connect()
            await self.init_base_groups()
        except DenyConnection:
            await self.close()

    async def connect(self):
        await self.accept()

    async def accept(self, subprotocol=None):
        """
        Accepts an incoming socket
        """
        await super(BaseConsumer, self).send({"type": "websocket.accept", "subprotocol": subprotocol})

    async def websocket_receive(self, message):
        """
        Called when a WebSocket frame is received. Decodes it and passes it
        to receive().
        """
        if "text" in message:
            await self.receive_text(message["text"])
        else:
            await self.receive_bytes(message["bytes"])

    async def receive_text(self, data=None):
        """
        Called with a decoded WebSocket frame.
        """
        pass

    async def receive_bytes(self, data=None):
        """
        Called with a decoded WebSocket frame.
        """
        pass

    async def send_bytes(self, data):
        """
        Sends a bytes reply back down the WebSocket
        """
        await super(BaseConsumer, self).send({"type": "websocket.send", "bytes": data})

    async def send_text(self, data):
        """
        Sends a text reply back down the WebSocket
        """
        await super(BaseConsumer, self).send({"type": "websocket.send", "text": data})

    async def close(self, code=None):
        """
        Closes the WebSocket from the server end
        """
        if code is not None and code is not True:
            await super().send({"type": "websocket.close", "code": code})
        else:
            await super().send({"type": "websocket.close"})

    async def websocket_disconnect(self, message):
        """
        Called when a WebSocket connection is closed. Base level so you don't
        need to call super() all the time.
        """
        await self.disconnect(message["code"])
        raise StopConsumer()

    async def disconnect(self, close_code):
        """Called when a WebSocket connection is closed"""
        await self.detach_all_groups()


class JsonConsumer(BaseConsumer):
    async def send_json(self, data=None):
        """Sends the data as JSON"""
        return await self.send_text(json.dumps(data))

    async def send_error(self, text=None, error_type=ErrorType.SYSTEM_ERROR, error=None):
        """Sends standard error messages of ERROR type"""
        additions = {}
        if error:
            text = str(error),
            error_type = getattr(error, "error_type", ErrorType.SYSTEM_ERROR),
            additions = getattr(error, 'addition_parameters', {})

        return await self.send_json(Response(
            EventType.ERROR,
            detail=text,
            type=error_type,
            **additions
        ))

    async def handle_error(self, error):
        """This method decides what to do with errors"""
        await self.send_error(
            error=(
                error if isinstance(error, BaseConsumerError) or getattr(settings, "DEBUG", False)
                else "Internal Server Error"
            )
        )

    async def receive_text(self, text=None):
        """Tries to login the user and then calls methods"""
        try:
            await self.receive_json(json.loads(text))
        except Exception as e:
            await self.handle_error(BaseConsumerError(
                "The data are not of JSON type.", ErrorType.TYPE_ERROR
            ))

    async def receive_json(self, data=None):
        pass


class JsonMethodConsumer(JsonConsumer):
    api_method_list_class: BaseConsumerMethodList = BaseConsumerMethodList
    api_method_list: BaseConsumerMethodList = None

    event_method_list_class: BaseConsumerEventMethodList = BaseConsumerEventMethodList
    event_method_list: BaseConsumerEventMethodList = None

    def __init__(self, *args, **kwargs):
        self.api_method_list = self.api_method_list_class(self)
        self.event_method_list = self.event_method_list_class(self)

    async def handle_error(self, error, __response_client_data=None):
        """This method decides what to do with errors"""
        if isinstance(error, BaseConsumerError):
            error.addition_parameters['__response_client_data'] = __response_client_data
        else:
            error = ConsumerSystemError(
                str(error) if getattr(settings, "DEBUG", False) else "Internal Server Error",
                __response_client_data=__response_client_data
            )
        await self.send_error(error=error)

    async def send_group_event(self, group_name, event_name, args=[], kwargs={}):
        """Sends event call to the group"""
        return await self.channel_layer.group_send(
            group_name, {
                'type': 'receive_event',
                'event_name': event_name,
                'args': args,
                'kwargs': kwargs
            }
        )

    async def receive_json(self, data=None):
        try:
            if type(data) != dict:
                data = {}
                raise ConsumerTypeError("The data has to be a JSON-object.")
            await self.call_method(data)
        except Exception as e:
            await self.handle_error(
                error=e,
                __response_client_data=(data or {}).get("kwargs", {}).get("__response_client_data")
            )

    async def call_method(self, data):
        """
        Calls an API method
        """
        res = await self.api_method_list.__call_method__(
            data.get('method'), data.get("args", []), data.get("kwargs", {})
        )
        if res is not None:
            await self.send_json(res)

    async def receive_event(self, data):
        try:
            await self.call_event(data)
        except Exception as e:
            await self.handle_error(
                error=e,
                __response_client_data=(data or {}).get("kwargs", {}).get("__response_client_data")
            )

    async def call_event(self, event):
        await self.event_method_list.__call_method__(
            event.get('event_name'), event.get('args', []), event.get('kwargs', {})
        )


class TokenAuthConsumer(JsonMethodConsumer):
    """
    Base consumer class that provides user authorization,
    separated API methods events interfaces
    """
    authenticated: bool = False

    user: User = None
    user_group_prefix: str = '__user'
    user_group_name: str = None

    async def send_group_event(self, group_name, event_name, args=[], kwargs={}):
        """Adds initiator id to the kwargs"""
        kwargs['__initiator_id'] = self.user.id if self.authenticated else None
        return await super(TokenAuthConsumer, self).send_group_event(
            group_name, event_name, args, kwargs
        )

    async def send_to_user(self, user_id, event_name, args=[], kwargs={}):
        """Shorthand for send_group_event with user group"""
        return await self.send_group_event(self.user_group_prefix + str(user_id), event_name, args, kwargs)

    async def user_return(self, args=[], kwargs={}):
        """Sends the data to all points where the authenticated user is logged from"""
        await self.send_group_event(self.user_group_name, 'user_return', args, kwargs)

    async def get_user_by_token(self, token):
        """Performs token checking and returns it's owner"""
        try:
            token = AccessToken(token)
            return await sync_to_async(User.objects.get)(id=token['user_id'])
        except Exception as e:
            return None

    async def authenticate(self, token):
        """Performs user authentication"""
        if not token:
            raise BaseConsumerError("There is no access token.", ErrorType.FIELD_ERROR)

        self.user = await self.get_user_by_token(token)
        if not self.user:
            raise BaseConsumerError("Authorization failed.", ErrorType.AUTHORIZATION_ERROR)

        self.user_group_name = str(self.user.id)
        self.authenticated = True
        
        await self.attach_group(self.user_group_name)

    async def call_method(self, data):
        """Tries to login the user and then calls methods"""
        if not self.authenticated:
            await self.authenticate(data.get('access_token'))
        await super(TokenAuthConsumer, self).call_method(data)