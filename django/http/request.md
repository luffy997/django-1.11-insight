# Django HTTP Request 处理架构深度解析

## 概述

Django的HTTP请求处理是一个分层架构，以`HttpRequest`作为基础抽象类，`WSGIRequest`作为实际生产环境中使用的实现类。通过中间件系统，Django动态地扩展请求对象的功能，提供了完整的Web请求处理能力。

## 核心架构

### 1. 类继承关系

```python
# 基础抽象类
class HttpRequest(object)

# 实际使用的WSGI实现  
class WSGIRequest(HttpRequest)

# 专用的查询字典
class QueryDict(MultiValueDict)
```

### 2. 主要组件

- **HttpRequest**: 基础HTTP请求抽象
- **WSGIRequest**: WSGI环境下的具体实现
- **QueryDict**: 处理查询字符串和表单数据
- **MultiValueDict**: 支持一键多值的字典实现

## HttpRequest 基础类详解

### 核心属性

```python
def __init__(self):
    self.GET = QueryDict(mutable=True)          # GET参数
    self.POST = QueryDict(mutable=True)         # POST数据  
    self.COOKIES = {}                           # Cookie数据
    self.META = {}                              # HTTP头和环境变量
    self.FILES = MultiValueDict()               # 上传文件
    
    self.path = ''                              # 请求路径
    self.path_info = ''                         # 路径信息
    self.method = None                          # HTTP方法
    self.resolver_match = None                  # URL解析匹配
    self._post_parse_error = False              # POST解析错误标志
    self.content_type = None                    # 内容类型
    self.content_params = None                  # 内容参数
```

### 主机和安全处理

#### 主机头验证 (防Host头攻击)
```python
def get_host(self):
    """返回HTTP主机，进行安全验证"""
    host = self._get_raw_host()
    
    # 调试模式下允许localhost变体
    allowed_hosts = settings.ALLOWED_HOSTS
    if settings.DEBUG and not allowed_hosts:
        allowed_hosts = ['localhost', '127.0.0.1', '[::1]']
    
    domain, port = split_domain_port(host)
    if domain and validate_host(domain, allowed_hosts):
        return host
    else:
        # 抛出DisallowedHost异常，防止Host头攻击
        raise DisallowedHost("Invalid HTTP_HOST header")
```

**安全价值**：防止攻击者通过伪造Host头进行缓存污染或密码重置攻击。

#### 签名Cookie支持
```python
def get_signed_cookie(self, key, default=RAISE_ERROR, salt='', max_age=None):
    """获取签名cookie，防止篡改"""
    try:
        cookie_value = self.COOKIES[key]
        value = signing.get_cookie_signer(salt=key + salt).unsign(
            cookie_value, max_age=max_age)
        return value
    except signing.BadSignature:
        # 签名验证失败
        if default is not RAISE_ERROR:
            return default
        else:
            raise
```

#### HTTPS检测
```python
@property
def scheme(self):
    # 支持代理服务器的HTTPS检测
    if settings.SECURE_PROXY_SSL_HEADER:
        header, value = settings.SECURE_PROXY_SSL_HEADER
        if self.META.get(header) == value:
            return 'https'
    return self._get_scheme()

def is_secure(self):
    return self.scheme == 'https'
```

### URL构建功能

```python
def get_full_path(self, force_append_slash=False):
    """获取完整路径包含查询字符串"""
    return '%s%s%s' % (
        escape_uri_path(self.path),
        '/' if force_append_slash and not self.path.endswith('/') else '',
        ('?' + iri_to_uri(self.META.get('QUERY_STRING', ''))) if self.META.get('QUERY_STRING', '') else ''
    )

def build_absolute_uri(self, location=None):
    """构建绝对URI"""
    if location is None:
        location = '//%s' % self.get_full_path()
    # ... 处理相对路径和绝对路径的逻辑
    return iri_to_uri(location)
```

### 编码处理

```python
@encoding.setter
def encoding(self, val):
    """设置GET/POST访问的编码"""
    self._encoding = val
    # 编码改变时重新创建GET和POST字典
    if hasattr(self, 'GET'):
        del self.GET
    if hasattr(self, '_post'):
        del self._post
```

### 文件上传处理

```python
def _initialize_handlers(self):
    """初始化文件上传处理器"""
    self._upload_handlers = [uploadhandler.load_handler(handler, self)
                             for handler in settings.FILE_UPLOAD_HANDLERS]

@property
def upload_handlers(self):
    if not self._upload_handlers:
        self._initialize_handlers()
    return self._upload_handlers

@upload_handlers.setter  
def upload_handlers(self, upload_handlers):
    if hasattr(self, '_files'):
        raise AttributeError("You cannot set the upload handlers after the upload has been processed.")
    self._upload_handlers = upload_handlers
```

### 请求体处理

```python
@property
def body(self):
    if not hasattr(self, '_body'):
        if self._read_started:
            raise RawPostDataException("You cannot access body after reading from request's data stream")

        # 检查请求体大小限制
        if (settings.DATA_UPLOAD_MAX_MEMORY_SIZE is not None and
                int(self.META.get('CONTENT_LENGTH') or 0) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE):
            raise RequestDataTooBig('Request body exceeded settings.DATA_UPLOAD_MAX_MEMORY_SIZE.')

        try:
            self._body = self.read()
        except IOError as e:
            six.reraise(UnreadablePostError, UnreadablePostError(*e.args), sys.exc_info()[2])
        self._stream = BytesIO(self._body)
    return self._body
```

### POST数据解析

```python
def _load_post_and_files(self):
    """根据content-type解析POST数据和文件"""
    if self.method != 'POST':
        self._post, self._files = QueryDict(encoding=self._encoding), MultiValueDict()
        return
    
    if self.content_type == 'multipart/form-data':
        # 处理文件上传
        if hasattr(self, '_body'):
            data = BytesIO(self._body)
        else:
            data = self
        try:
            self._post, self._files = self.parse_file_upload(self.META, data)
        except MultiPartParserError:
            self._mark_post_parse_error()
            raise
    elif self.content_type == 'application/x-www-form-urlencoded':
        # 处理表单数据
        self._post, self._files = QueryDict(self.body, encoding=self._encoding), MultiValueDict()
    else:
        # 其他类型（如JSON）
        self._post, self._files = QueryDict(encoding=self._encoding), MultiValueDict()
```

### 流式接口

```python
def read(self, *args, **kwargs):
    """读取请求体数据"""
    self._read_started = True
    try:
        return self._stream.read(*args, **kwargs)
    except IOError as e:
        six.reraise(UnreadablePostError, UnreadablePostError(*e.args), sys.exc_info()[2])

def __iter__(self):
    """支持迭代器协议，用于大文件流处理"""
    return self.xreadlines()

def xreadlines(self):
    """生成器形式的逐行读取"""
    while True:
        buf = self.readline()
        if not buf:
            break
        yield buf
```

## WSGIRequest 实际实现

### 与HttpRequest的区别

**关键差异**：
1. **不调用父类__init__**：直接重新实现所有初始化逻辑
2. **直接使用WSGI环境**：`self.META = environ`
3. **流处理优化**：使用`LimitedStream`进行安全的请求体读取

### 初始化过程

```python
class WSGIRequest(http.HttpRequest):
    def __init__(self, environ):
        # 解析WSGI路径信息
        script_name = get_script_name(environ)
        path_info = get_path_info(environ)
        if not path_info:
            path_info = '/'
            
        # 直接设置属性，不调用父类__init__
        self.environ = environ
        self.path_info = path_info
        self.path = '%s/%s' % (script_name.rstrip('/'), path_info.replace('/', '', 1))
        self.META = environ  # 直接使用WSGI环境作为META
        self.META['PATH_INFO'] = path_info
        self.META['SCRIPT_NAME'] = script_name
        
        # HTTP方法和内容类型处理
        self.method = environ['REQUEST_METHOD'].upper()
        self.content_type, self.content_params = cgi.parse_header(environ.get('CONTENT_TYPE', ''))
        
        # 字符编码处理
        if 'charset' in self.content_params:
            try:
                codecs.lookup(self.content_params['charset'])
                self.encoding = self.content_params['charset']
            except LookupError:
                pass
        
        # 设置限制流用于安全读取请求体
        try:
            content_length = int(environ.get('CONTENT_LENGTH'))
        except (ValueError, TypeError):
            content_length = 0
        self._stream = LimitedStream(self.environ['wsgi.input'], content_length)
        self._read_started = False
```

### 延迟属性加载

```python
@cached_property
def GET(self):
    """延迟加载GET参数"""
    raw_query_string = get_bytes_from_wsgi(self.environ, 'QUERY_STRING', '')
    return http.QueryDict(raw_query_string, encoding=self._encoding)

@cached_property  
def COOKIES(self):
    """延迟加载Cookie"""
    raw_cookie = get_str_from_wsgi(self.environ, 'HTTP_COOKIE', '')
    return http.parse_cookie(raw_cookie)

@property
def FILES(self):
    """延迟加载文件数据"""
    if not hasattr(self, '_files'):
        self._load_post_and_files()
    return self._files

# POST使用property而不是cached_property，允许动态修改
POST = property(_get_post, _set_post)
```

### LimitedStream 安全流

```python
class LimitedStream(object):
    """限制大小的流，防止内存耗尽攻击"""
    def __init__(self, stream, limit, buf_size=64 * 1024 * 1024):
        self.stream = stream
        self.remaining = limit
        self.buffer = b''
        self.buf_size = buf_size

    def _read_limited(self, size=None):
        if size is None or size > self.remaining:
            size = self.remaining
        if size == 0:
            return b''
        result = self.stream.read(size)
        self.remaining -= len(result)
        return result
```

## QueryDict 专用字典

### 设计目标

QueryDict解决了Web表单的特殊需求：
- **多值支持**：一个键可以有多个值（如复选框）
- **不可变性**：默认不可变，防止意外修改
- **编码处理**：自动处理字符编码转换

### 核心特性

```python
class QueryDict(MultiValueDict):
    """专门处理查询字符串的MultiValueDict"""
    
    # 默认不可变
    _mutable = True
    _encoding = None
    
    def __init__(self, query_string=None, mutable=False, encoding=None):
        super(QueryDict, self).__init__()
        if not encoding:
            encoding = settings.DEFAULT_CHARSET
        self.encoding = encoding
        
        # 解析查询字符串
        for key, value in limited_parse_qsl(query_string, **parse_qsl_kwargs):
            self.appendlist(key, value)
        
        self._mutable = mutable
```

### 不可变性保护

```python
def _assert_mutable(self):
    if not self._mutable:
        raise AttributeError("This QueryDict instance is immutable")

def __setitem__(self, key, value):
    self._assert_mutable()
    key = bytes_to_text(key, self.encoding)
    value = bytes_to_text(value, self.encoding)
    super(QueryDict, self).__setitem__(key, value)
```

### MultiValueDict设计问题

**问题**：`__setitem__` 会替换整个列表
```python
d = MultiValueDict()
d.appendlist('name', 'Adrian')
d.appendlist('name', 'Simon')  # ['Adrian', 'Simon']
d['name'] = 'John'             # ['John'] - 数据丢失！
```

**设计考虑**：
- **兼容性**：保持与标准字典相似的接口
- **Web语义**：HTML表单中同名字段通常意味着"替换"
- **向后兼容**：大量现有代码依赖当前行为

**推荐做法**：
- 明确使用 `appendlist()` 来追加
- 明确使用 `setlist()` 来替换
- 避免混用 `d[key] = value` 和 `appendlist()`

## 中间件扩展机制

Django通过中间件系统动态地向HttpRequest对象添加属性：

### 用户认证
```python
# AuthenticationMiddleware
class AuthenticationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.user = SimpleLazyObject(lambda: get_user(request))
```

### 会话支持
```python  
# SessionMiddleware
class SessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        request.session = self.SessionStore(session_key)
```

### CSRF保护
```python
# CsrfViewMiddleware
# 添加 csrf_token, META['CSRF_COOKIE'] 等属性
```

### 消息框架
```python
# MessageMiddleware
# 添加 request._messages
```

## 安全特性总结

### 1. 主机验证
- **Host头攻击防护**：验证Host头在ALLOWED_HOSTS中
- **调试模式安全**：调试时允许localhost变体
- **详细错误信息**：提供明确的配置指导

### 2. Cookie安全
- **签名验证**：防止客户端篡改cookie数据
- **时间验证**：支持cookie过期时间检查
- **盐值支持**：增强签名安全性

### 3. 请求体保护
- **大小限制**：防止内存耗尽攻击
- **流式处理**：支持大文件而不占用过多内存
- **错误恢复**：IO错误时的优雅处理

### 4. 编码安全
- **字符集处理**：正确处理各种字符编码
- **错误替换**：编码错误时的安全降级
- **Unicode标准化**：防止编码相关的安全问题

## 性能优化特性

### 1. 延迟加载
- **属性延迟**：GET、COOKIES等属性按需创建
- **POST延迟**：只有访问时才解析POST数据
- **文件延迟**：文件上传数据的延迟处理

### 2. 内存管理
- **流式读取**：大请求的分块处理
- **资源清理**：确保文件句柄正确释放
- **缓存机制**：适当的属性缓存

### 3. 编码优化
- **编码缓存**：避免重复的编码转换
- **批量处理**：QueryDict的批量操作优化

## 错误处理机制

### 异常体系
```python
class UnreadablePostError(IOError)          # POST数据无法读取
class RawPostDataException(Exception)       # 原始数据访问错误  
class DisallowedHost(Exception)            # 不允许的主机
class RequestDataTooBig(Exception)         # 请求数据过大
```

### 错误恢复
```python
def _mark_post_parse_error(self):
    """POST解析错误时的恢复机制"""
    self._post = QueryDict()
    self._files = MultiValueDict()
    self._post_parse_error = True
```

### 资源清理
```python
def close(self):
    """确保上传文件得到正确清理"""
    if hasattr(self, '_files'):
        for f in chain.from_iterable(l[1] for l in self._files.lists()):
            f.close()
```

## 设计模式和原则

### 1. 模板方法模式
- **HttpRequest**：定义基本流程和接口
- **WSGIRequest**：实现具体的WSGI环境处理
- **钩子方法**：`_get_scheme()` 等可重写方法

### 2. 代理模式
- **SimpleLazyObject**：延迟加载用户对象
- **cached_property**：属性级别的延迟计算

### 3. 策略模式
- **上传处理器**：可插拔的文件处理策略
- **编码处理**：不同编码方式的处理策略

### 4. 责任链模式
- **中间件系统**：请求处理的责任链
- **上传处理器链**：文件处理的责任链

## 实际应用场景

### 1. Web应用开发
```python
def view(request):
    # 基本信息访问
    method = request.method
    path = request.path
    user = request.user
    
    # 参数获取
    search = request.GET.get('q', '')
    username = request.POST.get('username')
    
    # 文件处理
    if 'avatar' in request.FILES:
        avatar = request.FILES['avatar']
    
    # 安全功能
    if request.is_secure():
        # HTTPS处理
        pass
```

### 2. API开发
```python
def api_view(request):
    # JSON数据处理
    if request.content_type == 'application/json':
        data = json.loads(request.body)
    
    # 认证检查
    if not request.user.is_authenticated:
        return HttpResponseUnauthorized()
    
    # 构建响应URL
    callback_url = request.build_absolute_uri('/callback/')
```

### 3. 文件上传服务
```python
def upload_view(request):
    # 自定义上传处理器
    request.upload_handlers = [CustomUploadHandler()]
    
    # 处理多文件上传
    for field_name, file_obj in request.FILES.items():
        # 处理文件
        pass
```

## 总结

Django的HTTP请求处理架构体现了以下设计理念：

### 安全第一
- 多层次的安全防护机制
- 输入验证和输出编码
- 攻击向量的全面防范

### 性能优化
- 延迟加载和按需计算
- 流式处理大数据
- 内存使用的精细控制

### 扩展性强
- 中间件的动态扩展机制
- 可插拔的处理器系统
- 清晰的继承和重写接口

### 标准兼容
- 完整的HTTP协议支持
- WSGI标准的完美实现
- RFC规范的严格遵循

通过HttpRequest基础类和WSGIRequest实现类的分层设计，Django提供了既抽象又实用的HTTP请求处理能力，为Web应用开发提供了强大而安全的基础设施。
