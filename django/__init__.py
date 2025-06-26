from __future__ import unicode_literals

from django.utils.version import get_version

VERSION = (1, 11, 0, 'final', 1)

__version__ = get_version(VERSION)


def setup(set_prefix=True):
    """
    Configure the settings (this happens as a side effect of accessing the
    first setting), configure logging and populate the app registry.
    Set the thread-local urlresolvers script prefix if `set_prefix` is True.
    """
    from django.apps import apps
    from django.conf import settings
    from django.urls import set_script_prefix
    from django.utils.encoding import force_text
    from django.utils.log import configure_logging

    configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)
    if set_prefix:
        set_script_prefix(
            '/' if settings.FORCE_SCRIPT_NAME is None else force_text(settings.FORCE_SCRIPT_NAME)
        )
    # 加载settings.INSTALLED_APPS中的应用程序配置和模型
    # 1. 创建AppConfig对象
    # 2. 将AppConfig对象添加到apps.app_configs中
    # 3. 将AppConfig对象的apps属性设置为apps
    # 4. 将AppConfig对象的models属性设置为models
    # 5. 将AppConfig对象的ready方法设置为ready
    # 把app注册到一个OrderedDict中，key是app的label，value是AppConfig对象，保证顺序，注册前还
    # 做了重复性校验，用线程锁保证多个线程同时注册时不会重复注册
    apps.populate(settings.INSTALLED_APPS)
