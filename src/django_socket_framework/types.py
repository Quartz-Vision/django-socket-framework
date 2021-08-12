from dataclasses import dataclass
from enum import Enum


class EventType:
    ERROR = "error"


class ErrorType:
    SYSTEM_ERROR = "system_error"
    ACCESS_ERROR = "access_error"
    AUTHORIZATION_ERROR = "authorization_error"
    FIELD_ERROR = "field_error"


class ConsumerError(RuntimeError):
    def __init__(self, msg, error_type=ErrorType.SYSTEM_ERROR, *args, **kwargs):
        super(ConsumerError, self).__init__(msg, *args)
        self.error_type = error_type
        self.addition_parameters = kwargs
