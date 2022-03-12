import asyncio
import json
from collections.abc import Sequence

from channels.consumer import AsyncConsumer
from channels.exceptions import DenyConnection, StopConsumer
from django.conf import settings

from django_socket_framework.method_lists import BaseConsumerMethodList
from django_socket_framework.types import (
    ClientEventType,
    ErrorType,
    BaseConsumerError,
    ClientEvent,
    ConsumerSystemError,
    ConsumerTypeError
)

__all__ = ['BaseConsumer', 'JsonConsumer', 'JsonMethodConsumer']


class BaseConsumer(AsyncConsumer):
    """
    Base consumer class that provides user authorization,
    separated API methods and events interfaces
    """

    base_groups: Sequence = []
    active_groups: set = set()

    async def attach_group(self, group_name: str) -> bool:
        """
        Adds a new group to the layer
        Returns:
            True - group has been added
            False - group are already presented in the list
        """
        if group_name not in self.active_groups:
            self.active_groups.add(group_name)
            await self.channel_layer.group_add(group_name, self.channel_name)
            return True
        return False

    async def detach_group(self, group_name: str) -> bool:
        """
        Removes a group from the layer
        Returns:
            True - group has been removed
            False - group are already not in the list
        """
        if group_name in self.active_groups:
            self.active_groups.remove(group_name)
            await self.channel_layer.group_discard(group_name, self.channel_name)
            return True
        return False

    async def detach_all_groups(self):
        """
        Detaches all the groups from the layer
        """
        fs = [
            self.detach_group(group)
            for group in set(self.active_groups)
        ]
        if fs:
            await asyncio.wait(fs)

    async def init_base_groups(self):
        """
        Activates all groups from base_groups
        """
        fs = [
            self.attach_group(group)
            for group in self.base_groups
        ]
        if fs:
            await asyncio.wait(fs)

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
            text = str(error)
            error_type = getattr(error, 'error_type', ErrorType.SYSTEM_ERROR)
            additions = getattr(error, 'addition_parameters', {})

        return await self.send_json(ClientEvent(
            ClientEventType.ERROR,
            detail=text,
            type=error_type,
            **additions
        ))

    async def handle_error(self, error, *args, **kwargs):
        """This method decides what to do with errors"""
        if isinstance(error, BaseConsumerError):
            error.addition_parameters.update(kwargs)
        else:
            error = ConsumerSystemError(
                str(error) if getattr(settings, "DEBUG", False) else "Internal Server Error",
                **kwargs
            )
        await self.send_error(error=error)

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

    event_method_list_class: BaseConsumerMethodList = BaseConsumerMethodList
    event_method_list: BaseConsumerMethodList = None

    api_middlewares = tuple()
    event_middlewares = tuple()

    def __init__(self, *args, **kwargs):
        self.init_api_method_list()
        self.init_event_method_list()

    def init_api_method_list(self):
        self.api_method_list = self.api_method_list_class(self)

    def init_event_method_list(self):
        self.event_method_list = self.event_method_list_class(self)

    async def send_group_event(self, group_name, event_name, kwargs={}, args=[]):
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
                raise ConsumerTypeError("The data have to be a JSON-object.")
            await self.call_method(data)
        except Exception as e:
            await self.handle_error(
                error=e,
                __echo_client_data=(data or {}).get("kwargs", {}).get("__echo_client_data")
            )

    async def call_method(self, data):
        """
        Calls an API method
        """
        for middleware in self.api_middlewares:
            data = await middleware(self, data)

        res = await self.api_method_list.__call_method__(
            data.get('method'), data.get("kwargs", {}), data.get("args", [])
        )
        if res is not None:
            await self.send_json(res)

    async def receive_event(self, data):
        try:
            await self.call_event(data)
        except Exception as e:
            await self.handle_error(
                error=e,
                __echo_client_data=(data or {}).get("kwargs", {}).get("__echo_client_data")
            )

    async def call_event(self, event):
        for middleware in self.event_middlewares:
            event = await middleware(self, event)

        await self.event_method_list.__call_method__(
            event.get('event_name'), event.get('kwargs', {}), event.get('args', [])
        )
