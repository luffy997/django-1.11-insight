"""
Global Django exception and warning classes.
"""
from django.utils import six
from django.utils.encoding import force_text


class FieldDoesNotExist(Exception):
    """The requested model field does not exist
    用途：当访问模型中不存在的字段时抛出
    使用场景：ORM查询中引用了不存在的字段
    """
    pass


class DjangoRuntimeWarning(RuntimeWarning):
    """
    用途：Django运行时警告
    使用场景：在开发过程中，Django会抛出一些警告，这些警告通常是一些潜在的问题，需要开发人员注意
    """
    pass


class AppRegistryNotReady(Exception):
    """The django.apps registry is not populated yet
    用途：当Django的app注册表未初始化时抛出
    使用场景：在Django启动时，app注册表未初始化完成，导致无法加载应用
    """
    pass


class ObjectDoesNotExist(Exception):
    """The requested object does not exist
    用途：当查询不存在的对象时抛出
    使用场景：ORM查询中引用了不存在的对象
    """
    silent_variable_failure = True


class MultipleObjectsReturned(Exception):
    """The query returned multiple objects when only one was expected.
    用途：当查询返回多个对象时抛出
    使用场景：ORM查询中引用了不存在的对象
    """
    pass


class SuspiciousOperation(Exception):
    """The user did something suspicious
    用途：当用户执行了可疑的操作时抛出
    使用场景：用户执行了可疑的操作，如访问不存在的页面、提交恶意数据等
    """
    pass


class SuspiciousMultipartForm(SuspiciousOperation):
    """Suspect MIME request in multipart form data
    用途：当检测到可疑的MIME请求时抛出
    使用场景：用户提交了可疑的MIME请求，如包含恶意代码的文件上传
    """
    pass


class SuspiciousFileOperation(SuspiciousOperation):
    """A Suspicious filesystem operation was attempted
    用途：当检测到可疑的文件系统操作时抛出
    使用场景：用户提交了可疑的文件系统操作，如访问不存在的文件、提交恶意文件等
    """
    pass


class DisallowedHost(SuspiciousOperation):
    """HTTP_HOST header contains invalid value
    用途：当HTTP_HOST头包含无效值时抛出
    使用场景：用户提交了无效的HTTP_HOST头，如包含恶意代码的请求
    """
    pass


class DisallowedRedirect(SuspiciousOperation):
    """Redirect to scheme not in allowed list
    用途：当重定向的URL的协议不在允许的列表中时抛出
    使用场景：用户提交了重定向的URL，但URL的协议不在允许的列表中
    """
    pass


class TooManyFieldsSent(SuspiciousOperation):
    """
    The number of fields in a GET or POST request exceeded
    settings.DATA_UPLOAD_MAX_NUMBER_FIELDS.

    用途：当请求中的字段数量超过设置的最大字段数时抛出
    使用场景：用户提交了过多的字段，导致请求被拒绝
    """
    pass


class RequestDataTooBig(SuspiciousOperation):
    """
    The size of the request (excluding any file uploads) exceeded
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE.

    用途：当请求的大小超过设置的最大内存大小时抛出
    使用场景：用户提交了过大的请求，导致请求被拒绝
    """
    pass


class PermissionDenied(Exception):
    """The user did not have permission to do that
    用途：当用户没有权限执行某个操作时抛出
    使用场景：用户没有权限执行某个操作，如访问不存在的页面、提交恶意数据等
    """
    pass


class ViewDoesNotExist(Exception):
    """The requested view does not exist
    用途：当请求的视图不存在时抛出
    使用场景：用户请求了不存在的视图，如访问不存在的页面、提交恶意数据等
    """
    pass


class MiddlewareNotUsed(Exception):
    """This middleware is not used in this server configuration
    用途：当中间件未被使用时抛出
    使用场景：中间件未被使用，导致无法执行中间件的逻辑
    """
    pass


class ImproperlyConfigured(Exception):
    """Django is somehow improperly configured
    用途：当Django配置不正确时抛出
    使用场景：Django配置不正确，导致无法启动
    """
    pass


class FieldError(Exception):
    """Some kind of problem with a model field.
    用途：当模型字段出现问题时抛出
    使用场景：模型字段出现问题，导致无法正常使用
    """
    pass


NON_FIELD_ERRORS = '__all__'


class ValidationError(Exception):
    """An error while validating data.
    用途：当数据验证失败时抛出
    使用场景：用户提交了无效的数据，导致无法正常使用
    """
    def __init__(self, message, code=None, params=None):
        """
        The `message` argument can be a single error, a list of errors, or a
        dictionary that maps field names to lists of errors. What we define as
        an "error" can be either a simple string or an instance of
        ValidationError with its message attribute set, and what we define as
        list or dictionary can be an actual `list` or `dict` or an instance
        of ValidationError with its `error_list` or `error_dict` attribute set.
        """

        # PY2 can't pickle naive exception: http://bugs.python.org/issue1692335.
        super(ValidationError, self).__init__(message, code, params)
        # self.error_dict = {}    # 字段级错误：{'field': [errors]}
        # self.error_list = []    # 错误列表：[error1, error2]
        # self.message = message  # 单个错误消息
        if isinstance(message, ValidationError):
            if hasattr(message, 'error_dict'):
                message = message.error_dict
            # PY2 has a `message` property which is always there so we can't
            # duck-type on it. It was introduced in Python 2.5 and already
            # deprecated in Python 2.6.
            elif not hasattr(message, 'message' if six.PY3 else 'code'):
                message = message.error_list
            else:
                message, code, params = message.message, message.code, message.params

        if isinstance(message, dict):
            self.error_dict = {}
            for field, messages in message.items():
                if not isinstance(messages, ValidationError):
                    messages = ValidationError(messages)
                self.error_dict[field] = messages.error_list

        elif isinstance(message, list):
            self.error_list = []
            for message in message:
                # Normalize plain strings to instances of ValidationError.
                if not isinstance(message, ValidationError):
                    message = ValidationError(message)
                if hasattr(message, 'error_dict'):
                    self.error_list.extend(sum(message.error_dict.values(), []))
                else:
                    self.error_list.extend(message.error_list)

        else:
            self.message = message
            self.code = code
            self.params = params
            self.error_list = [self]

    @property
    def message_dict(self):
        # Trigger an AttributeError if this ValidationError
        # doesn't have an error_dict.
        getattr(self, 'error_dict')

        return dict(self)

    @property
    def messages(self):
        if hasattr(self, 'error_dict'):
            # 扁平化，sum(iterable, [])，有点黑科技那味了
            return sum(dict(self).values(), [])
        return list(self)

    def update_error_dict(self, error_dict):
        if hasattr(self, 'error_dict'):
            for field, error_list in self.error_dict.items():
                error_dict.setdefault(field, []).extend(error_list)
        else:
            error_dict.setdefault(NON_FIELD_ERRORS, []).extend(self.error_list)
        return error_dict

    def __iter__(self):
        if hasattr(self, 'error_dict'):
            for field, errors in self.error_dict.items():
                yield field, list(ValidationError(errors))
        else:
            for error in self.error_list:
                message = error.message
                if error.params:
                    message %= error.params
                yield force_text(message)

    def __str__(self):
        if hasattr(self, 'error_dict'):
            return repr(dict(self))
        return repr(list(self))

    def __repr__(self):
        return 'ValidationError(%s)' % self


class EmptyResultSet(Exception):
    """A database query predicate is impossible."""
    pass
