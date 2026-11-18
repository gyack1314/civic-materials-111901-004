"""访问本地资料来源的 HTTP 客户端。

只与来源服务通信:目录查询走 /captures,字节只从 /capture/{id} 读取。
不跟随重定向、不访问原始网址,重定向目标交回采集逻辑按存档目录解析。
"""
import http.client
import json
from urllib.parse import urlencode, urlsplit


class SourceError(Exception):
    """来源访问失败。"""


class CaptureResponse:
    """一次 /capture/{id} 的原始响应,不做任何隐含处理。"""

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body.decode('utf-8'))


class SourceClient:
    """对本地合成存档来源的只读访问。"""

    def __init__(self, base, timeout=10):
        parts = urlsplit(base)
        if parts.scheme not in ('http', ''):
            raise SourceError('只支持 http 来源: ' + base)
        self.base = base.rstrip('/')
        self.host = parts.hostname or '127.0.0.1'
        self.port = parts.port or 8765
        self.timeout = timeout

    def _get(self, path):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            conn.request('GET', path)
            resp = conn.getresponse()
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.getheaders()}
            return CaptureResponse(resp.status, headers, body)
        finally:
            conn.close()

    def captures(self, url=None):
        """查询存档目录,返回 (捕获列表, 实际请求路径)。url 为原始网址。"""
        path = '/captures'
        if url is not None:
            path += '?' + urlencode({'url': url})
        resp = self._get(path)
        if resp.status != 200:
            raise SourceError('目录查询失败 %s: %r' % (resp.status, resp.body[:200]))
        return resp.json().get('captures', []), path

    def capture(self, capture_id):
        """读取单条捕获记录,返回 (原始响应, 实际请求路径)。不跟随重定向。"""
        path = '/capture/' + capture_id
        return self._get(path), path
