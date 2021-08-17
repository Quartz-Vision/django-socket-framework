class ConsumerMiddleware:
    @classmethod
    def as_function(cls):
        return lambda *args, **kwargs: cls().handle(*args, **kwargs)

    async def handle(self, *args, **kwargs):
        pass
