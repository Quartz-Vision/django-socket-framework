from django.utils.translation import gettext_lazy as _

from django_socket_framework.method_lists import BaseConsumerMethodList


class UserReturnEventListMixin(BaseConsumerMethodList):
    async def user_return__(self, data=None, *args, **kwargs):
        """Just send given data to the user"""
        try:
            await self.consumer.send_json(data)
        except KeyError as e:
            await self.consumer.send_error(_("No data for the user_return."))

