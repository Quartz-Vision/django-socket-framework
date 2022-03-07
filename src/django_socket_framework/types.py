from enum import Enum


class BaseEventType(str, Enum):
    pass


class EventType(BaseEventType):
    ERROR = "error"


class Response(dict):
    """
    Response dict class with dedicated constructor
    __response_client_data - data, going from the client back 
        to itself in raw format. For example, front-end ids
    """
    def __init__(
        self,
        __response_type: BaseEventType,
        __response_client_data=None,
        *args,
        **kwargs
    ):
        super(Response, self).__init__({
            'type': __response_type,
            'data': {
                **kwargs,
                '__response_client_data': __response_client_data
            }
        })


class BaseErrorType(str, Enum):
    pass


class ErrorType(BaseErrorType):
    SYSTEM_ERROR = "system_error"
    ACCESS_ERROR = "access_error"
    AUTHORIZATION_ERROR = "authorization_error"
    TYPE_ERROR = "field_error"


class BaseConsumerError(RuntimeError):
    def __init__(
        self,
        msg: str,
        error_type: BaseErrorType = ErrorType.SYSTEM_ERROR,
        *args,
        **kwargs
    ):
        super(BaseConsumerError, self).__init__(msg, *args)
        self.error_type = error_type
        self.addition_parameters = kwargs


class ConsumerTypeError(BaseConsumerError):
    def __init__(self, *args, **kwargs):
        super(ConsumerTypeError, self).__init__(*args, **kwargs, error_type=ErrorType.TYPE_ERROR)


class ConsumerSystemError(BaseConsumerError):
    def __init__(self, *args, **kwargs):
        super(ConsumerSystemError, self).__init__(*args, **kwargs, error_type=ErrorType.SYSTEM_ERROR)


class ConsumerAccessError(BaseConsumerError):
    def __init__(self, *args, **kwargs):
        super(ConsumerAccessError, self).__init__(*args, **kwargs, error_type=ErrorType.ACCESS_ERROR)


class ConsumerAuthorizationError(BaseConsumerError):
    def __init__(self, *args, **kwargs):
        super(ConsumerAuthorizationError, self).__init__(*args, **kwargs, error_type=ErrorType.AUTHORIZATION_ERROR)
