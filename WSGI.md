 # Django WSGI 架构深度解析

## 概述

本文档详细解析了Django的WSGI架构，包括开发环境的`runserver`命令、`WSGIHandler`请求处理器、`WSGIServer`服务器，以及生产环境的服务器选择。

## 1. Django runserver 命令解析

### 1.1 命令概述

```python
class Command(BaseCommand):
    help = "Starts a lightweight Web server for development."
```

`runserver`是Django提供的**轻量级开发服务器**，专门用于开发环境，**不适用于生产环境**。

### 1.2 命令行参数

```python
def add_arguments(self, parser):
    parser.add_argument(
        'addrport', nargs='?',
        help='Optional port number, or ipaddr:port'
    )
    parser.add_argument(
        '--ipv6', '-6', action='store_true', dest='use_ipv6', default=False,
        help='Tells Django to use an IPv6 address.',
    )
    parser.add_argument(
        '--nothreading', action='store_false', dest='use_threading', default=True,
        help='Tells Django to NOT use threading.',
    )
    parser.add_argument(
        '--noreload', action='store_false', dest='use_reloader', default=True,
        help='Tells Django to NOT use the auto-reloader.',
    )
```

### 1.3 启动流程

```
用户执行: python manage.py runserver
    ↓
1. 解析命令行参数
    ├─ addrport (地址:端口)
    ├─ --ipv6 (IPv6支持)
    ├─ --nothreading (禁用线程)
    └─ --noreload (禁用重载)
    ↓
2. 验证配置
    ├─ 检查 DEBUG 和 ALLOWED_HOSTS
    ├─ 验证 IPv6 支持
    └─ 解析地址和端口
    ↓
3. 选择运行模式
    ├─ 自动重载模式 (默认)
    │   ├─ 启动监控线程
    │   ├─ 检测文件变化
    │   └─ 自动重启服务器
    └─ 直接运行模式
    ↓
4. 系统检查
    ├─ 模型验证
    ├─ 迁移检查
    └─ 配置验证
    ↓
5. 启动Web服务器
    ├─ 获取WSGI处理器
    ├─ 创建socket监听
    ├─ 启动请求处理循环
    └─ 处理HTTP请求
```

### 1.4 自动重载机制

```python
def run(self, **options):
    use_reloader = options['use_reloader']
    
    if use_reloader:
        autoreload.main(self.inner_run, None, options)  # 自动重载模式
    else:
        self.inner_run(None, **options)  # 直接运行模式
```

自动重载通过以下方式工作：
1. **文件监控**: 监控Python文件的变化
2. **进程重启**: 检测到变化时重启整个进程
3. **无缝切换**: 用户无感知的服务器重启

## 2. WSGIHandler 请求处理器

### 2.1 本质理解

**重要概念**: `WSGIHandler` **不是服务器，而是请求处理器**，负责处理单个请求。

### 2.2 核心职责

```python
class WSGIHandler(base.BaseHandler):
    request_class = WSGIRequest

    def __call__(self, environ, start_response):
        # 1. 设置脚本前缀
        set_script_prefix(get_script_name(environ))
        
        # 2. 发送请求开始信号
        signals.request_started.send(sender=self.__class__, environ=environ)
        
        # 3. 创建Django请求对象
        request = self.request_class(environ)
        
        # 4. 获取响应
        response = self.get_response(request)
        
        # 5. 设置响应头
        status = '%d %s' % (response.status_code, response.reason_phrase)
        response_headers = [(str(k), str(v)) for k, v in response.items()]
        
        # 6. 处理Cookie
        for c in response.cookies.values():
            response_headers.append((str('Set-Cookie'), str(c.output(header=''))))
        
        # 7. 调用WSGI的start_response
        start_response(force_str(status), response_headers)
        
        # 8. 返回响应内容
        return response
```

### 2.3 三个核心职责

#### 职责1: 环境字典 → Django请求对象
```python
# 输入: WSGI环境字典
environ = {
    'REQUEST_METHOD': 'GET',
    'PATH_INFO': '/hello/',
    'QUERY_STRING': 'name=world',
    'HTTP_HOST': 'localhost:8000',
    'wsgi.input': <file-like object>,
    # ... 其他环境变量
}

# WSGIHandler 转换
request = WSGIRequest(environ)
# 结果: Django HttpRequest 对象
```

#### 职责2: 走Django中间件流程
```python
def get_response(self, request):
    # 1. 中间件 process_request
    for middleware in self._request_middleware:
        response = middleware.process_request(request)
        if response:
            return response
    
    # 2. 路由解析
    resolver_match = resolver.resolve(request.path_info)
    request.resolver_match = resolver_match
    
    # 3. 中间件 process_view
    for middleware in self._view_middleware:
        response = middleware.process_view(request, callback, callback_args, callback_kwargs)
        if response:
            return response
    
    # 4. 执行视图函数
    response = callback(request, *callback_args, **callback_kwargs)
    
    # 5. 中间件 process_response
    for middleware in reversed(self._response_middleware):
        response = middleware.process_response(request, response)
    
    return response
```

#### 职责3: Django响应 → WSGI响应
```python
# 输入: Django HttpResponse
response = HttpResponse("Hello World")
response.status_code = 200
response['Content-Type'] = 'text/html'

# WSGIHandler 转换
status = '200 OK'
response_headers = [('Content-Type', 'text/html'), ('Content-Length', '11')]
start_response(status, response_headers)
return [b"Hello World"]
```

### 2.4 完整的请求处理流程

```
HTTP请求到达
    ↓
WSGIServer 接收请求
    ↓
调用 WSGIHandler.__call__(environ, start_response)
    ↓
创建 WSGIRequest 对象（从environ字典）
    ↓
调用 self.get_response(request)
    ↓
经过中间件处理
    ↓
路由到对应的视图函数
    ↓
返回 HttpResponse 对象
    ↓
WSGIHandler 将响应转换为WSGI格式
    ↓
调用 start_response(status, headers)
    ↓
返回响应内容
```

## 3. WSGIServer Socket服务器

### 3.1 继承关系

```python
# django/core/servers/basehttp.py
class WSGIServer(simple_server.WSGIServer, object):
    """BaseHTTPServer that implements the Python WSGI protocol"""

# wsgiref/simple_server.py (Python标准库)
class WSGIServer(HTTPServer):
    """BaseHTTPServer that implements the Python WSGI protocol"""

# http/server.py (Python标准库)
class HTTPServer(socketserver.TCPServer):
    """HTTP server that implements the Python WSGI protocol"""

# socketserver.py (Python标准库)
class TCPServer(socketserver.BaseServer):
    """TCP server class"""
```

**继承链**:
```
WSGIServer → simple_server.WSGIServer → HTTPServer → TCPServer → BaseServer
```

### 3.2 Socket服务器本质

```python
def serve_forever(self, poll_interval=0.5):
    """Handle one request at a time until shutdown."""
        self.__is_shut_down.clear()
        try:
            # XXX: Consider using another file descriptor or connecting to the
            # socket to wake this up instead of polling. Polling reduces our
            # responsiveness to a shutdown request and wastes cpu at all other
            # times.
            # 使用 selectors 进行非阻塞 I/O
            with _ServerSelector() as selector:
                selector.register(self, selectors.EVENT_READ)  # 监听读事件

                while not self.__shutdown_request:
                    ready = selector.select(poll_interval)  # 等待 socket 可读
                    # bpo-35017: shutdown() called during select(), exit immediately.
                    if self.__shutdown_request:  # 如果需要关闭，则退出循环
                        break
                    if ready:
                        self._handle_request_noblock()  # 处理新请求

                    self.service_actions()  # 处理其他操作
        finally:
            self.__shutdown_request = False
            self.__is_shut_down.set()
```

### 3.3 Socket服务器工作流程

#### 1. 创建Socket
```python
# 在 WSGIServer 初始化时
def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
    # 创建 TCP socket
    self.socket = socket.socket(self.address_family, self.socket_type)
    self.socket.setsockopt(socket.SOL_SOCKIT, socket.SO_REUSEADDR, 1)
    self.socket.bind(server_address)  # 绑定地址和端口
    self.socket.listen(self.request_queue_size)  # 开始监听
```

#### 2. 监听循环
```python
# 持续监听连接
while not self.__shutdown_request:
    ready = selector.select(poll_interval)  # 等待客户端连接
    if ready:
        self._handle_request_noblock()  # 处理新连接
```

#### 3. 处理请求
```python
def _handle_request_noblock(self):
    try:
        request, client_address = self.socket.accept()  # 接受连接
        self.process_request(request, client_address)   # 处理请求
    except socket.error:
        pass
```

### 3.4 完整的HTTP处理流程

```
1. Socket 监听 (8000端口)
   ↓
2. 客户端连接 (浏览器)
   ↓
3. Socket.accept() 接受连接
   ↓
4. 创建 RequestHandler 处理 HTTP 请求
   ↓
5. 解析 HTTP 请求头
   ↓
6. 创建 WSGI 环境字典
   ↓
7. 调用 WSGIHandler(environ, start_response)
   ↓
8. WSGIHandler 处理请求并返回响应
   ↓
9. 发送 HTTP 响应给客户端
   ↓
10. 关闭连接，继续监听下一个请求
```

## 4. 开发环境 vs 生产环境

### 4.1 开发环境 (runserver)

```python
# django/core/management/commands/runserver.py
def inner_run(self, *args, **options):
    handler = self.get_handler(*args, **options)  # 获取 WSGIHandler
    run(self.addr, int(self.port), handler,       # 启动 WSGIServer
        ipv6=self.use_ipv6, threading=threading, server_cls=self.server_cls) # server_cls就是WSGIServer
```

**架构**:
```
浏览器 → WSGIServer → WSGIHandler → Django应用
```

### 4.2 生产环境

在生产环境中，通常使用专业的 WSGI 服务器：

#### Gunicorn
```bash
# 启动命令
gunicorn myproject.wsgi:application

# 架构
浏览器 → Nginx → Gunicorn → WSGIHandler → Django应用
```

#### uWSGI
```bash
# 启动命令
uwsgi --http :8000 --module myproject.wsgi:application

# 架构
浏览器 → Nginx → uWSGI → WSGIHandler → Django应用
```

#### mod_wsgi (Apache)
```apache
# Apache 配置
LoadModule wsgi_module modules/mod_wsgi.so
WSGIScriptAlias / /path/to/myproject/wsgi.py

# 架构
浏览器 → Apache → mod_wsgi → WSGIHandler → Django应用
```

### 4.3 Django的WSGI入口

无论使用哪种服务器，Django的入口都是相同的：

```python
# myproject/wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
application = get_wsgi_application()  # 返回 WSGIHandler 实例
```

### 4.4 关键区别

#### 开发环境
```python
# Django 自己启动服务器
from django.core.servers.basehttp import WSGIServer, run

handler = get_wsgi_application()  # WSGIHandler
run('127.0.0.1', 8000, handler, server_cls=WSGIServer)  # Django 启动 WSGIServer
```

#### 生产环境
```python
# 外部服务器启动，Django 只提供 WSGI 应用
# gunicorn/uwsgi/apache 启动
application = get_wsgi_application()  # 只返回 WSGIHandler，不启动服务器
```

## 5. 生产级WSGI服务器

### 5.1 Gunicorn Socket实现

```python
# Gunicorn Master 进程 (简化版)
class Master:
    def __init__(self, bind_addr, workers=4):
        # 创建主 Socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(bind_addr)  # 绑定地址和端口
        self.socket.listen(1024)     # 开始监听
        
        # 启动多个 Worker 进程
        self.workers = []
        for i in range(workers):
            worker = Worker(self.socket)  # 传递 Socket 给 Worker
            worker.start()
            self.workers.append(worker)
```

### 5.2 Gunicorn架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Gunicorn 架构                            │
├─────────────────────────────────────────────────────────────┤
│  Master Process (主进程)                                    │
│  ├─ 监听 Socket (主 Socket)                                │
│  ├─ 管理 Worker 进程                                       │
│  └─ 负载均衡                                               │
├─────────────────────────────────────────────────────────────┤
│  Worker Processes (工作进程)                                │
│  ├─ Worker 1: Socket + WSGIHandler                        │
│  ├─ Worker 2: Socket + WSGIHandler                        │
│  ├─ Worker 3: Socket + WSGIHandler                        │
│  └─ Worker N: Socket + WSGIHandler                        │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 与Django WSGIServer的对比

#### Django WSGIServer (简单Socket)
```python
# 单进程，单线程
class WSGIServer:
    def serve_forever(self):
        while True:
            client, addr = self.socket.accept()  # 阻塞等待
            self.handle_request(client)          # 处理请求
            client.close()                       # 关闭连接
```

#### Gunicorn (高级Socket)
```python
# 多进程，每个进程可以多线程
class GunicornMaster:
    def run(self):
        # 1. 创建主 Socket
        self.socket = socket.socket()
        self.socket.bind(('0.0.0.0', 8000))
        self.socket.listen(1024)
        
        # 2. 启动多个 Worker 进程
        for i in range(4):
            worker = Process(target=self.worker_process)
            worker.start()
```

### 5.4 生产级服务器的优势

1. **多进程/多线程**: 并发处理多个请求
2. **高性能**: 优化的 C 实现
3. **负载均衡**: 自动分发请求
4. **进程管理**: 自动重启、健康检查
5. **安全特性**: 请求限制、超时控制

## 6. 实际部署示例

### 6.1 使用Gunicorn

```bash
# 安装
pip install gunicorn

# 启动
gunicorn --workers 4 --bind 127.0.0.1:8000 myproject.wsgi:application

# 配置文件 gunicorn.conf.py
bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
max_requests = 1000
max_requests_jitter = 100
timeout = 30
```

### 6.2 使用uWSGI

```bash
# 安装
pip install uwsgi

# 启动
uwsgi --http :8000 --module myproject.wsgi:application --processes 4 --threads 2

# 配置文件 uwsgi.ini
[uwsgi]
http = :8000
module = myproject.wsgi:application
processes = 4
threads = 2
master = true
vacuum = true
```

### 6.3 Nginx配置

```nginx
server {
    listen 80;
    server_name example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;  # 转发到 Gunicorn
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /static/ {
        alias /path/to/static/;  # 直接服务静态文件
    }
}
```

### 6.4 生产环境完整架构

```txt
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   浏览器     │───▶│    Nginx     │───▶│  Gunicorn   │───▶│ WSGIHandler │
│             │    │  (反向代理)   │    │ (WSGI服务器) │    │ (Django)    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

## 7. 总结

### 7.1 核心概念

1. **WSGIHandler**: 不是服务器，而是请求处理器，负责将WSGI环境转换为Django请求对象，并走Django中间件流程
2. **WSGIServer**: 基于Socket的简单Web服务器，用于开发环境
3. **runserver**: Django的管理命令，启动WSGIServer并调用WSGIHandler
4. **生产级服务器**: Gunicorn、uWSGI等，基于Socket但提供高级特性

### 7.2 架构对比

| 组件 | 开发环境 | 生产环境 |
|------|----------|----------|
| 服务器 | WSGIServer | Gunicorn/uWSGI/Apache |
| 请求处理器 | WSGIHandler | WSGIHandler |
| 并发能力 | 单进程单线程 | 多进程多线程 |
| 性能 | 低 | 高 |
| 功能 | 简单 | 丰富 |

### 7.3 关键理解

- **Django内部处理请求的始终是WSGIHandler**
- **开发环境使用WSGIServer，生产环境使用专业WSGI服务器**
- **所有WSGI服务器都基于Socket实现，但复杂度不同**
- **WSGI协议让Django能够运行在任何WSGI服务器上**

这种设计让Django：
1. **专注于业务逻辑**: 不关心网络和并发处理
2. **与服务器解耦**: 可以运行在任何WSGI服务器上
3. **性能优化**: 使用专业的WSGI服务器处理并发
4. **部署灵活**: 可以根据需求选择不同的服务器