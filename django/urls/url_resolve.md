# Django URL匹配算法详解

## 核心思想：分层递归匹配

Django的URL匹配就像**剥洋葱**一样，一层一层地处理URL，每一层只负责匹配自己的部分，然后把剩下的部分交给下一层继续处理。

## 算法流程图

```
请求URL: /api/v1/users/123/profile/
                ↓
        [第1层] 根解析器 r'^/'
         匹配成功，剩余：api/v1/users/123/profile/
                ↓
        [第2层] API解析器 r'^api/v(\d+)/'
         匹配成功，剩余：users/123/profile/
         捕获参数：version='1'
                ↓
        [第3层] Users解析器 r'^users/'
         匹配成功，剩余：123/profile/
                ↓
        [第4层] Profile模式 r'^(?P<user_id>\d+)/profile/$'
         匹配成功，剩余：空
         捕获参数：user_id='123'
                ↓
        最终结果：views.profile(request, version='1', user_id='123')
```

## 具体示例说明

### 1. URL配置结构

```python
# 主urls.py (根URLconf)
urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^api/v(\d+)/', include('api.urls')),  # API版本控制
    url(r'^blog/', include('blog.urls')),
]

# api/urls.py
urlpatterns = [
    url(r'^users/', include('users.urls')),
    url(r'^posts/', include('posts.urls')),
]

# users/urls.py
urlpatterns = [
    url(r'^$', views.user_list, name='user-list'),
    url(r'^(?P<user_id>\d+)/$', views.user_detail, name='user-detail'),
    url(r'^(?P<user_id>\d+)/profile/$', views.user_profile, name='user-profile'),
]
```

### 2. 匹配过程详解

当用户访问 `/api/v1/users/123/profile/` 时：

#### 第1步：根解析器处理
```python
# RegexURLResolver(r'^/', 主urls.py)
path = '/api/v1/users/123/profile/'
match = r'^/'.search(path)  # 匹配成功
new_path = 'api/v1/users/123/profile/'  # 去掉开头的 '/'
```

#### 第2步：遍历主URLconf的模式
```python
for pattern in [admin_pattern, api_pattern, blog_pattern]:
    # 尝试 r'^api/v(\d+)/' 模式
    sub_match = api_pattern.resolve('api/v1/users/123/profile/')
```

#### 第3步：API解析器处理
```python
# RegexURLResolver(r'^api/v(\d+)/', 'api.urls')
path = 'api/v1/users/123/profile/'
match = r'^api/v(\d+)/'.search(path)  # 匹配成功
# 捕获组：groups() = ('1',)  # 版本号
new_path = 'users/123/profile/'  # 剩余路径
```

#### 第4步：Users解析器处理
```python
# RegexURLResolver(r'^users/', 'users.urls') 
path = 'users/123/profile/'
match = r'^users/'.search(path)  # 匹配成功
new_path = '123/profile/'  # 剩余路径
```

#### 第5步：Profile模式匹配
```python
# RegexURLPattern(r'^(?P<user_id>\d+)/profile/$', views.user_profile)
path = '123/profile/'
match = r'^(?P<user_id>\d+)/profile/$'.search(path)  # 匹配成功
# 命名组：groupdict() = {'user_id': '123'}
new_path = ''  # 完全匹配，无剩余
```

#### 第6步：参数合并
```python
# 合并所有层级的参数
final_args = ('1',)  # 来自第3步的位置参数
final_kwargs = {'user_id': '123'}  # 来自第5步的命名参数

# 创建最终结果
return ResolverMatch(
    func=views.user_profile,
    args=('1',),
    kwargs={'user_id': '123'},
    url_name='user-profile',
    app_names=[],
    namespaces=[]
)
```

## 关键算法特点

### 1. 分层匹配策略
- **每层只管自己的事**：每个URLResolver只匹配自己的正则表达式
- **剩余路径传递**：匹配成功后，将剩余部分传给下一层
- **递归处理**：通过 `pattern.resolve(new_path)` 实现递归

### 2. 参数处理规则
```python
# 规则：有命名参数时，忽略位置参数
if not sub_match_dict:  # 如果没有命名参数
    sub_match_args = match.groups() + sub_match.args  # 合并位置参数
else:  # 有命名参数
    sub_match_args = sub_match.args  # 只使用子层的位置参数
```

**示例对比**：
```python
# 情况1：混合参数
r'^api/v(\d+)/'  →  r'^users/(?P<user_id>\d+)/$'
# 结果：args=(), kwargs={'user_id': '123'}  # 忽略版本号位置参数

# 情况2：纯位置参数  
r'^api/v(\d+)/'  →  r'^users/(\d+)/$'
# 结果：args=('1', '123'), kwargs={}  # 合并位置参数
```

### 3. 错误追踪机制
```python
# 记录所有尝试过的模式，用于生成404错误信息
tried = []
for pattern in self.url_patterns:
    try:
        sub_match = pattern.resolve(new_path)
    except Resolver404 as e:
        tried.extend([pattern] + t for t in e.args[0].get('tried', []))
```

## 性能优化策略

### 1. 正则表达式缓存
```python
@cached_property  
def regex(self):
    return re.compile(self._regex, re.UNICODE)
```

### 2. URLconf模块缓存
```python
@lru_cache.lru_cache(maxsize=None)
def get_resolver(urlconf=None):
    return RegexURLResolver(r'^/', urlconf)
```

### 3. 反向查找字典预构建
```python
def _populate(self):
    # 一次性构建所有反向查找字典
    # 避免运行时重复计算
```

## 实际应用场景

### 复杂嵌套URL
```python
# 电商网站示例
urlpatterns = [
    url(r'^shop/', include([
        url(r'^categories/(?P<cat_id>\d+)/', include([
            url(r'^products/', include([
                url(r'^(?P<product_id>\d+)/', include([
                    url(r'^$', views.product_detail),
                    url(r'^reviews/$', views.product_reviews),
                    url(r'^buy/$', views.purchase),
                ])),
            ])),
        ])),
    ])),
]

# URL: /shop/categories/5/products/123/reviews/
# 最终调用: views.product_reviews(request, cat_id='5', product_id='123')
```

### 命名空间支持
```python
# 多版本API
urlpatterns = [
    url(r'^api/v1/', include('api.v1.urls', namespace='v1')),
    url(r'^api/v2/', include('api.v2.urls', namespace='v2')),
]

# 反向解析
reverse('v1:user-list')  # /api/v1/users/
reverse('v2:user-list')  # /api/v2/users/
```

## 总结

Django的URL匹配算法核心是**分层递归**：

1. **分层**：将复杂URL分解为多个简单层级
2. **递归**：每层处理自己的部分，递归处理剩余部分  
3. **高效**：通过缓存和预编译提升性能
4. **灵活**：支持复杂嵌套和命名空间
5. **调试友好**：完整记录匹配尝试过程

这种设计让Django能够优雅地处理各种复杂的URL结构，同时保持代码的可读性和可维护性。
