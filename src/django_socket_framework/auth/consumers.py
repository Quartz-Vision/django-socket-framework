from django_socket_framework.auth.event_lists import UserReturnEventListMixin
from django_socket_framework.consumers import JsonMethodConsumer


class AuthConsumer(JsonMethodConsumer):
    """
    Base consumer class that provides user authorization,
    separated API methods events interfaces
    """
    authenticated: bool = False

    user: 'User' = None
    user_group_prefix: str = '__user'
    user_group_name: str = None

    def init_event_method_list(self):
        class AuthEventList(self.event_method_list_class, UserReturnEventListMixin):
            pass
        self.event_method_list = AuthEventList(self)

    async def send_group_event(self, group_name, event_name, kwargs={}, args=[]):
        """Adds initiator id to the kwargs"""
        kwargs['__initiator_id'] = str(self.user.id) if self.authenticated else None
        return await super(AuthConsumer, self).send_group_event(
            group_name, event_name, kwargs, args
        )

    async def send_to_user(self, user_id, event_name, kwargs={}, args=[]):
        """Shorthand for send_group_event with user group"""
        return await self.send_group_event(self.user_group_prefix + str(user_id), event_name, kwargs, args)

    async def user_return(self, kwargs={}, args=[]):
        """Sends the data to all points where the authenticated user is logged from"""
        await self.send_group_event(self.user_group_name, 'user_return__', kwargs, args)

    async def authenticate(self, user):
        self.user = user
        self.user_group_name = self.user_group_prefix + str(user.id)
        self.authenticated = True
        await self.attach_group(self.user_group_name)
