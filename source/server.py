"""本地合成资料来源，仅提供来源行为与观察记录。"""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

DATA = Path(__file__).resolve().parents[1] / 'data'

class Source:
    def __init__(self):
        self.lock = threading.RLock()
        self.clock = 0
        self.phase = 0
        self.log = []
        self.extra = {}

    def response(self, method, raw_path, headers, body):
        path = urlsplit(raw_path).path
        q = {k:v[-1] for k,v in parse_qs(urlsplit(raw_path).query).items()}
        with self.lock:
            self.log.append({'method':method,'path':raw_path,'time':self.clock,
                             'headers':{k.lower():v for k,v in headers.items()}})
            if path == '/health': return 200, {}, {'来源':'本地合成资料','phase':self.phase,'time':self.clock}
            if path == '/__admin/log': return 200, {}, self.log[:-1]
            if path == '/__admin/advance' and method == 'POST':
                value=json.loads(body or b'{}')
                self.clock += int(value.get('seconds',0))
                self.phase = int(value.get('phase',self.phase))
                return 200, {}, {'phase':self.phase,'time':self.clock}
            if path.startswith('/__admin/'):
                return 404, {}, {'error':'未知演练控制'}
            return self.product(method,path,q,{k.lower():v for k,v in headers.items()},body)

    def captures(self):
        return [
          {'id':'H1','url':'https://city.invalid/policy','at':'2023-06-01','status':200,'kind':'page'},
          {'id':'H2','url':'https://city.invalid/policy','at':'2025-06-01','status':200,'kind':'page'},
          {'id':'F1','url':'https://city.invalid/docs/2023.txt','at':'2023-05-01','status':200,'kind':'file','edition':'2023'},
          {'id':'F2','url':'https://city.invalid/docs/2023.txt','at':'2024-01-01','status':200,'kind':'revisit','ref':'F1','edition':'2023'},
          {'id':'F3','url':'https://city.invalid/docs/2023.txt','at':'2025-01-01','status':200,'kind':'file','edition':'2025'},
          {'id':'L1','url':'https://city.invalid/next','at':'2023-06-01','status':302,'location':'/loop'},
          {'id':'L2','url':'https://city.invalid/loop','at':'2023-06-01','status':302,'location':'/next'}]
    def product(self,method,path,q,h,body):
        if path=='/captures':return 200,{}, {'captures':[x for x in self.captures() if not q.get('url') or x['url']==q['url']]}
        if path.startswith('/capture/'):
            key=path.rsplit('/',1)[-1];item=next((x for x in self.captures() if x['id']==key),None)
            if not item:return 404,{}, {'error':'捕获不存在'}
            if self.phase==1 and key=='F1':return 404,{}, {'error':'存档内容缺失'}
            headers={'X-Original-URL':item['url'],'X-Captured-At':item['at'],'X-Capture-Id':key}
            if item.get('kind')=='revisit':return 200,headers,{'ref':item['ref'],'record_type':'revisit'}
            if item['status']==302:return 302,{**headers,'Location':item['location']},b''
            if item.get('kind')=='page':
                return 200,headers,'<base href="https://city.invalid/docs/"><main><h1>城市政策</h1><a rel="document" data-edition="2023" href="/replay/2023/https://city.invalid/docs/2023.txt">2023册</a><a rel="next" href="https://city.invalid/next">续页</a><img src="decor.png"></main>'
            return 200,{**headers,'Content-Type':'text/plain'},('历史合成原件 '+item.get('edition','')).encode()
        return 404,{}, {'error':'请通过存档目录读取'}

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self,*args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        size=int(self.headers.get('Content-Length','0'))
        try:
            status,headers,body=self.server.source.response(self.command,self.path,self.headers,self.rfile.read(size))
            if not isinstance(body,(str,bytes)):
                body=json.dumps(body,ensure_ascii=False).encode();headers.setdefault('Content-Type','application/json; charset=utf-8')
            elif isinstance(body,str):
                body=body.encode();headers.setdefault('Content-Type','text/html; charset=utf-8')
        except (ValueError,KeyError,TypeError) as exc:
            status,headers,body=400,{'Content-Type':'application/json'},json.dumps({'error':str(exc)},ensure_ascii=False).encode()
        if status==0:
            self.close_connection=True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,str(v))
        self.send_header('Content-Length',len(body))
        self.end_headers()
        if body:self.wfile.write(body)

@contextmanager
def running_source(port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.source=Source()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield 'http://127.0.0.1:'+str(server.server_port),server.source
    finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='启动本地资料来源')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('0.0.0.0',args.port),Handler);server.source=Source()
    print('资料来源已启动，端口 '+str(args.port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
