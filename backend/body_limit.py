"""Bound request memory before Starlette/Pydantic parses untrusted JSON."""
from fastapi.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, maximum=500000):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        chunks, total = [], 0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            chunk=message.get('body',b'')
            total+=len(chunk)
            if total>self.maximum:
                response=JSONResponse({'detail':'Conteúdo excede o limite de edição.'},status_code=413,headers={'Cache-Control':'no-store'})
                return await response(scope,receive,send)
            chunks.append(chunk)
            if not message.get('more_body',False):
                break
        body=b''.join(chunks)
        sent=False
        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent=True
                return {'type':'http.request','body':body,'more_body':False}
            return await receive()
        return await self.app(scope,bounded_receive,send)
