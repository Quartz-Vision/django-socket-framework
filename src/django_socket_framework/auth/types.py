from django_socket_framework.types import BaseConsumerError, BaseErrorType


class AuthErrorType(BaseErrorType):
    AUTHORIZATION_ERROR = "authorization_error"


class ConsumerAuthorizationError(BaseConsumerError):
    def __init__(self, *args, **kwargs):
        super(ConsumerAuthorizationError, self).__init__(*args, **kwargs, error_type=AuthErrorType.AUTHORIZATION_ERROR)
