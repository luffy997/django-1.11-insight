# Django 签名系统详解

## 📚 概述

Django的签名系统是一个强大的安全工具，用于创建和验证**数字签名**，确保数据的完整性和真实性。它基于HMAC-SHA1算法，使用SECRET_KEY进行签名，防止数据被篡改或伪造。

## 🔐 核心概念

### 什么是数字签名？
数字签名是一种**加密技术**，用于：
1. **验证数据完整性** - 确保数据没有被篡改
2. **验证数据来源** - 确保数据确实来自你的服务器  
3. **防止伪造** - 防止恶意用户伪造数据

### 签名格式
```
ImhlbGxvIg:1QaUZC:YIye-ze3TTx7gtSv422nZA4sgmk
│─────────│──────│─────────────────────────────────│
│  数据   │时间戳│           HMAC签名              │
```

三部分用冒号分隔：
- **数据部分**：原始数据的Base64编码
- **时间戳**：Base62编码的时间戳（仅TimestampSigner）
- **签名部分**：HMAC-SHA1签名

## 🛠️ 核心类和函数

### 1. Signer类
基础签名器，提供基本的签名和验证功能。

```python
from django.core.signing import Signer

signer = Signer('my-secret-key')
signed_value = signer.sign('hello world')
print(signed_value)  # 'hello world:signature'

# 验证签名
original_value = signer.unsign(signed_value)
print(original_value)  # 'hello world'
```

### 2. TimestampSigner类
继承自Signer，添加时间戳功能，支持过期验证。

```python
from django.core.signing import TimestampSigner

signer = TimestampSigner('my-secret-key')
signed_value = signer.sign('hello world')
print(signed_value)  # 'hello world:timestamp:signature'

# 验证签名（不检查过期）
original_value = signer.unsign(signed_value)

# 验证签名（检查过期时间）
try:
    original_value = signer.unsign(signed_value, max_age=3600)  # 1小时有效
except SignatureExpired:
    print("签名已过期")
```

### 3. 便利函数：dumps() 和 loads()

#### dumps() - 序列化并签名
```python
from django.core import signing

# 基本用法
token = signing.dumps({'user_id': 123, 'action': 'reset_password'})
print(token)  # 'eyJ1c2VyX2lkIjoxMjMsImFjdGlvbiI6InJlc2V0X3Bhc3N3b3JkIn0:1QaUZC:abc123...'

# 启用压缩
compressed_token = signing.dumps(large_data, compress=True)

# 自定义salt
custom_token = signing.dumps(data, salt='my.custom.salt')
```

#### loads() - 验证并反序列化
```python
# 基本验证
try:
    data = signing.loads(token)
    print(data)  # {'user_id': 123, 'action': 'reset_password'}
except signing.BadSignature:
    print("签名无效")

# 带过期检查
try:
    data = signing.loads(token, max_age=3600)  # 1小时有效期
except signing.SignatureExpired:
    print("签名已过期")
except signing.BadSignature:
    print("签名无效")
```

## ⏰ 时间戳机制详解

### 时间戳生成
```python
def timestamp(self):
    return baseconv.base62.encode(int(time.time()))
```

### 时间戳验证
```python
def unsign(self, value, max_age=None):
    # 提取时间戳
    value, timestamp = result.rsplit(self.sep, 1)
    timestamp = baseconv.base62.decode(timestamp)
    
    if max_age is not None:
        # 计算签名年龄
        age = time.time() - timestamp
        if age > max_age:
            raise SignatureExpired(...)
    
    return value
```

### Base62编码
Django使用Base62编码时间戳，包含62个字符：
```python
BASE62_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
```

优势：
- **URL安全**：不包含特殊字符
- **紧凑性**：比十进制更短
- **可读性**：混合数字和字母

## 🎯 实际应用场景

### 1. CSRF防护
```python
# django/middleware/csrf.py
def get_token(request):
    csrf_secret = _get_new_csrf_string()
    request.META["CSRF_COOKIE"] = _salt_cipher_secret(csrf_secret)
    return _salt_cipher_secret(csrf_secret)
```

### 2. Session数据（签名Cookie）
```python
# django/contrib/sessions/backends/signed_cookies.py
def _get_session_key(self):
    session_cache = getattr(self, '_session_cache', {})
    return signing.dumps(
        session_cache, compress=True,
        salt='django.contrib.sessions.backends.signed_cookies',
    )

def load(self):
    return signing.loads(
        self.session_key,
        max_age=settings.SESSION_COOKIE_AGE,
        salt='django.contrib.sessions.backends.signed_cookies',
    )
```

### 3. 密码重置令牌
```python
# django/contrib/auth/forms.py
context = {
    'uid': urlsafe_base64_encode(force_bytes(user.pk)),
    'token': token_generator.make_token(user),
    'protocol': 'https' if use_https else 'http',
}
```

### 4. 邮件激活链接
```python
# 生成激活令牌
activation_token = signing.dumps({
    'user_id': user.id,
    'email': user.email,
    'action': 'activate_account'
})

# 验证激活令牌
try:
    data = signing.loads(token, max_age=24*3600)  # 24小时有效
    user_id = data['user_id']
    # 激活用户账户...
except signing.SignatureExpired:
    return HttpResponse("激活链接已过期")
```

## ⚙️ 配置设置

### 默认过期时间设置
```python
# django/conf/global_settings.py

# TimestampSigner本身：默认永不过期（max_age=None）
# 只有明确指定max_age参数才会检查过期

# Session会话：2周
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # 1,209,600秒

# 密码重置：3天  
PASSWORD_RESET_TIMEOUT_DAYS = 3  # 259,200秒

# CSRF令牌：1年
CSRF_COOKIE_AGE = 60 * 60 * 24 * 7 * 52  # 31,449,600秒
```

### 签名后端配置
```python
# 默认签名后端
SIGNING_BACKEND = 'django.core.signing.TimestampSigner'

# SECRET_KEY用于签名
SECRET_KEY = 'your-secret-key-here'
```

## 🔒 安全特性

### 1. 基于HMAC-SHA1
```python
def base64_hmac(salt, value, key):
    return b64_encode(salted_hmac(salt, value, key).digest())
```

### 2. 盐值机制
```python
def signature(self, value):
    signature = base64_hmac(self.salt + 'signer', value, self.key)
    return force_str(signature)
```

### 3. 常量时间比较
```python
def unsign(self, signed_value):
    # ...
    if constant_time_compare(sig, self.signature(value)):
        return force_text(value)
    raise BadSignature(...)
```

## 📋 异常处理

### 异常类型
```python
class BadSignature(Exception):
    """签名不匹配"""
    pass

class SignatureExpired(BadSignature):
    """签名时间戳超过required max_age"""
    pass
```

### 异常处理示例
```python
from django.core import signing

def verify_token(token):
    try:
        data = signing.loads(token, max_age=3600)
        return data, None
    except signing.SignatureExpired:
        return None, "令牌已过期，请重新获取"
    except signing.BadSignature:
        return None, "令牌无效，可能被篡改"
```

## 💡 最佳实践

### 1. 根据场景设置合适的有效期
```python
# 密码重置 - 较短有效期
password_reset_token = signing.dumps(user_data)
signing.loads(password_reset_token, max_age=3600)  # 1小时

# 记住登录 - 较长有效期  
remember_token = signing.dumps(user_data)
signing.loads(remember_token, max_age=30*24*3600)  # 30天

# 临时操作 - 很短有效期
temp_token = signing.dumps(operation_data)
signing.loads(temp_token, max_age=300)  # 5分钟
```

### 2. 使用不同的salt
```python
# 不同用途使用不同的salt
email_token = signing.dumps(data, salt='email.verification')
download_token = signing.dumps(data, salt='file.download')
api_token = signing.dumps(data, salt='api.access')
```

### 3. 处理异常
```python
def safe_loads(token, max_age=None):
    try:
        return signing.loads(token, max_age=max_age), None
    except signing.SignatureExpired:
        return None, "TOKEN_EXPIRED"
    except signing.BadSignature:
        return None, "TOKEN_INVALID"
```

### 4. 生产环境考虑
```python
# 确保SECRET_KEY安全
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# 考虑时钟偏移
max_age = 3600 + 60  # 多给60秒缓冲时间

# 日志记录
import logging
logger = logging.getLogger(__name__)

try:
    data = signing.loads(token, max_age=3600)
except signing.SignatureExpired:
    logger.warning(f"Token expired for user {request.user.id}")
    raise
```

## 🔄 完整工作流程

### 签名生成流程
1. **数据序列化**：将Python对象转换为JSON
2. **数据压缩**：可选，如果启用compress=True
3. **Base64编码**：将数据转换为URL安全格式
4. **添加时间戳**：TimestampSigner添加当前时间戳
5. **生成签名**：使用HMAC-SHA1和SECRET_KEY生成签名
6. **组合结果**：将数据、时间戳、签名用冒号连接

### 签名验证流程
1. **分离组件**：按冒号分离数据、时间戳、签名
2. **验证签名**：重新计算签名并与提供的签名比较
3. **检查时间**：如果指定max_age，检查是否过期
4. **解码数据**：Base64解码和JSON反序列化
5. **返回结果**：返回原始数据或抛出异常

## 🚀 示例：构建邮件验证系统

```python
from django.core import signing
from django.shortcuts import render, redirect
from django.http import HttpResponse
import datetime

def send_verification_email(request):
    """发送验证邮件"""
    user_email = request.POST.get('email')
    
    # 生成验证令牌（24小时有效）
    token_data = {
        'email': user_email,
        'action': 'verify_email',
        'user_id': request.user.id
    }
    
    verification_token = signing.dumps(token_data, salt='email.verification')
    
    # 构建验证链接
    verification_url = f"https://example.com/verify/{verification_token}/"
    
    # 发送邮件（这里省略邮件发送代码）
    # send_email(user_email, verification_url)
    
    return HttpResponse("验证邮件已发送")

def verify_email(request, token):
    """验证邮件"""
    try:
        # 验证令牌（24小时有效期）
        data = signing.loads(
            token, 
            salt='email.verification', 
            max_age=24*3600
        )
        
        # 提取数据
        email = data['email']
        user_id = data['user_id']
        action = data['action']
        
        if action != 'verify_email':
            return HttpResponse("无效的验证类型", status=400)
        
        # 更新用户邮箱验证状态
        # User.objects.filter(id=user_id).update(email_verified=True)
        
        return HttpResponse("邮箱验证成功！")
        
    except signing.SignatureExpired:
        return HttpResponse("验证链接已过期，请重新发送验证邮件", status=400)
    except signing.BadSignature:
        return HttpResponse("无效的验证链接", status=400)
```

## 📊 性能考虑

### 时间复杂度
- **签名生成**：O(n)，n为数据大小
- **签名验证**：O(n)，n为数据大小
- **时间戳编码/解码**：O(1)

### 空间效率
- **Base62编码**：比Base10更紧凑
- **压缩选项**：大数据可以启用compress=True
- **签名开销**：固定大小的签名部分

### 缓存策略
```python
# 可以缓存经常验证的令牌结果
from django.core.cache import cache

def cached_verify_token(token):
    cache_key = f"token_verify_{hash(token)}"
    result = cache.get(cache_key)
    
    if result is None:
        try:
            result = signing.loads(token, max_age=3600)
            cache.set(cache_key, result, timeout=300)  # 缓存5分钟
        except signing.BadSignature:
            result = False
            cache.set(cache_key, result, timeout=60)   # 缓存失败1分钟
    
    return result
```

## 🔍 调试技巧

### 查看签名组成
```python
def debug_signature(signed_value):
    """调试签名组成部分"""
    parts = signed_value.split(':')
    print(f"总共 {len(parts)} 部分:")
    
    if len(parts) >= 2:
        print(f"数据部分: {parts[0]}")
        print(f"最后部分(签名): {parts[-1]}")
        
        if len(parts) == 3:
            print(f"时间戳部分: {parts[1]}")
            from django.utils import baseconv
            timestamp = baseconv.base62.decode(parts[1])
            import datetime
            dt = datetime.datetime.fromtimestamp(timestamp)
            print(f"生成时间: {dt}")

# 使用示例
token = signing.dumps("hello world")
debug_signature(token)
```

### 测试不同场景
```python
import time
from django.core import signing

def test_signing_scenarios():
    """测试各种签名场景"""
    
    # 测试基本签名
    signer = signing.Signer()
    simple_signed = signer.sign("test data")
    print("基本签名:", simple_signed)
    
    # 测试时间戳签名
    timestamp_signer = signing.TimestampSigner()
    time_signed = timestamp_signer.sign("test data")
    print("时间戳签名:", time_signed)
    
    # 测试复杂数据
    complex_data = {
        'user_id': 123,
        'permissions': ['read', 'write'],
        'expires': '2024-12-31'
    }
    complex_signed = signing.dumps(complex_data)
    print("复杂数据签名:", complex_signed)
    
    # 测试压缩
    large_data = list(range(100))
    compressed = signing.dumps(large_data, compress=True)
    uncompressed = signing.dumps(large_data, compress=False)
    print(f"压缩后长度: {len(compressed)}")
    print(f"未压缩长度: {len(uncompressed)}")
    print(f"压缩率: {len(compressed)/len(uncompressed)*100:.1f}%")

test_signing_scenarios()
```

## 🎯 总结

Django的签名系统是一个精心设计的安全工具，具有以下特点：

### ✅ 优势
1. **安全可靠**：基于HMAC-SHA1，使用SECRET_KEY
2. **使用简单**：提供便利的dumps/loads接口
3. **功能完整**：支持时间戳、压缩、自定义salt
4. **性能良好**：高效的编码和签名算法
5. **应用广泛**：CSRF、Session、密码重置等场景

### ⚠️ 注意事项
1. **SECRET_KEY安全**：必须保证SECRET_KEY的安全性
2. **时间同步**：服务器时间需要准确同步
3. **过期处理**：合理设置max_age参数
4. **异常处理**：正确处理签名异常
5. **性能监控**：大量签名操作需要性能监控

### 🔮 适用场景
- ✅ 无状态令牌验证
- ✅ 临时链接生成
- ✅ 客户端数据存储
- ✅ API认证令牌
- ❌ 长期存储加密
- ❌ 敏感数据加密

Django签名系统为现代Web应用提供了强大的安全基础，是构建安全可靠应用的重要工具。
