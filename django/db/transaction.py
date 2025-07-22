from django.db import (
    DEFAULT_DB_ALIAS, DatabaseError, Error, ProgrammingError, connections,
)
from django.utils.decorators import ContextDecorator


class TransactionManagementError(ProgrammingError):
    """
    This exception is thrown when transaction management is used improperly.
    """
    pass


def get_connection(using=None):
    """
    Get a database connection by name, or the default database connection
    if no name is provided. This is a private API.
    """
    if using is None:
        using = DEFAULT_DB_ALIAS
    return connections[using]


def get_autocommit(using=None):
    """
    Get the autocommit status of the connection.
    """
    return get_connection(using).get_autocommit()


def set_autocommit(autocommit, using=None):
    """
    Set the autocommit status of the connection.
    """
    return get_connection(using).set_autocommit(autocommit)


def commit(using=None):
    """
    Commits a transaction.
    """
    get_connection(using).commit()


def rollback(using=None):
    """
    Rolls back a transaction.
    """
    get_connection(using).rollback()


def savepoint(using=None):
    """
    Creates a savepoint (if supported and required by the backend) inside the
    current transaction. Returns an identifier for the savepoint that will be
    used for the subsequent rollback or commit.
    创建一个保存点，如果支持并且需要的话，返回一个标识符，用于后续的回滚或提交。
    """
    return get_connection(using).savepoint()


def savepoint_rollback(sid, using=None):
    """
    Rolls back the most recent savepoint (if one exists). Does nothing if
    savepoints are not supported.
    回滚最近的保存点，如果保存点不存在，则什么都不做。
    """
    get_connection(using).savepoint_rollback(sid)


def savepoint_commit(sid, using=None):
    """
    Commits the most recent savepoint (if one exists). Does nothing if
    savepoints are not supported.
    提交最近一次保存点，如果保存点不存在则什么都不做
    """
    get_connection(using).savepoint_commit(sid)


def clean_savepoints(using=None):
    """
    Resets the counter used to generate unique savepoint ids in this thread.
    重置用于生成唯一保存点标识符的计数器。
    """
    get_connection(using).clean_savepoints()


def get_rollback(using=None):
    """
    Gets the "needs rollback" flag -- for *advanced use* only.
    获取"需要回滚"标志，仅用于*高级用法*。
    """
    return get_connection(using).get_rollback()


def set_rollback(rollback, using=None):
    """
    Sets or unsets the "needs rollback" flag -- for *advanced use* only.
    设置或取消"需要回滚"标志，仅用于*高级用法*。

    When `rollback` is `True`, it triggers a rollback when exiting the
    innermost enclosing atomic block that has `savepoint=True` (that's the
    default). Use this to force a rollback without raising an exception.

    When `rollback` is `False`, it prevents such a rollback. Use this only
    after rolling back to a known-good state! Otherwise, you break the atomic
    block and data corruption may occur.
    当`rollback`为`True`时，在退出最内层的`atomic`块时触发回滚，
    使用这个标志来强制回滚，而不抛出异常。
    当`rollback`为`False`时，防止这种回滚。
    只有在回滚到已知的好状态后才能使用这个标志！
    否则，你破坏了`atomic`块，数据可能会损坏。
    """
    return get_connection(using).set_rollback(rollback)


def on_commit(func, using=None):
    """
    Register `func` to be called when the current transaction is committed.
    If the current transaction is rolled back, `func` will not be called.
    注册一个函数，当当前事务提交时调用。
    如果当前事务回滚，则不调用该函数。
    """
    get_connection(using).on_commit(func)


#################################
# Decorators / context managers #
#################################

class Atomic(ContextDecorator):
    """
    This class guarantees<保证> the atomic execution of a given block.
    这个类保证给定块的原子执行。

    An instance can be used either as a decorator or as a context manager.
    实例可以作为装饰器或上下文管理器使用。

    When it's used as a decorator, __call__ wraps the execution of the
    decorated function in the instance itself, used as a context manager.
    当它被用作装饰器时，__call__ 包装在实例本身中执行的装饰函数，用作上下文管理器。

    When it's used as a context manager, __enter__ creates a transaction or a
    savepoint, depending on whether a transaction is already in progress, and
    __exit__ commits the transaction or releases the savepoint on normal exit,
    and rolls back the transaction or to the savepoint on exceptions.
    当它被用作上下文管理器时，__enter__ 创建一个事务或一个保存点，
    取决于是否已经存在一个事务。    
    __exit__ 在正常退出时提交事务，或释放保存点，
    在异常退出时回滚事务或回滚到保存点。

    It's possible to disable the creation of savepoints if the goal is to
    ensure that some code runs within a transaction without creating overhead.
    如果目标是确保某些代码在事务中运行，而不创建开销，可以禁用保存点的创建。

    A stack of savepoints identifiers is maintained as an attribute of the
    connection. None denotes the absence of a savepoint.

    This allows reentrancy even if the same AtomicWrapper is reused. For
    example, it's possible to define `oa = @atomic('other')` and use `@oa` or
    `with oa:` multiple times.

    Since database connections are thread-local, this is thread-safe.

    This is a private API.
    """

    def __init__(self, using, savepoint):
        self.using = using
        self.savepoint = savepoint

    def __enter__(self):
        connection = get_connection(self.using)

        if not connection.in_atomic_block:
            # Reset state when entering an outermost atomic block.
            # 当进入最外层的atomic块时，重置状态。
            connection.commit_on_exit = True
            connection.needs_rollback = False
            if not connection.get_autocommit():
                # Some database adapters (namely sqlite3) don't handle
                # transactions and savepoints properly when autocommit is off.
                # Turning autocommit back on isn't an option; it would trigger
                # a premature commit. Give up if that happens.
                if connection.features.autocommits_when_autocommit_is_off:
                    raise TransactionManagementError(
                        "Your database backend doesn't behave properly when "
                        "autocommit is off. Turn it on before using 'atomic'.")
                # Pretend we're already in an atomic block to bypass the code
                # that disables autocommit to enter a transaction, and make a
                # note to deal with this case in __exit__.
                connection.in_atomic_block = True
                connection.commit_on_exit = False

        if connection.in_atomic_block:
            # We're already in a transaction; create a savepoint, unless we
            # were told not to or we're already waiting for a rollback. The
            # second condition avoids creating useless savepoints and prevents
            # overwriting needs_rollback until the rollback is performed.
            # 我们已经在事务中；创建一个保存点，除非我们被告诉不要创建，或者我们已经在等待回滚。
            # 第二个条件避免创建无用的保存点，并防止在回滚执行之前覆盖needs_rollback。
            if self.savepoint and not connection.needs_rollback:
                sid = connection.savepoint()
                connection.savepoint_ids.append(sid)
            else:
                connection.savepoint_ids.append(None)
        else:
            connection.set_autocommit(False, force_begin_transaction_with_broken_autocommit=True)
            connection.in_atomic_block = True

    def __exit__(self, exc_type, exc_value, traceback):
        connection = get_connection(self.using)

        if connection.savepoint_ids:
            sid = connection.savepoint_ids.pop()
        else:
            # Prematurely unset this flag to allow using commit or rollback.
            # 过早的取消这个标志以允许提交或回滚
            connection.in_atomic_block = False

        try:
            if connection.closed_in_transaction:
                # The database will perform a rollback by itself.
                # 数据库会自动回滚。
                # Wait until we exit the outermost block.
                pass

            elif exc_type is None and not connection.needs_rollback:
                if connection.in_atomic_block:
                    # Release savepoint if there is one
                    # 如果存在保存点，则释放它。
                    if sid is not None:
                        try:
                            connection.savepoint_commit(sid)
                        except DatabaseError:
                            try:
                                connection.savepoint_rollback(sid)
                                # The savepoint won't be reused. Release it to
                                # minimize overhead for the database server.
                                # 这个保存点不会被使用，释放它来尽量减少数据库服务器的开销
                                connection.savepoint_commit(sid)
                            except Error:
                                # If rolling back to a savepoint fails, mark for
                                # rollback at a higher level and avoid shadowing
                                # the original exception.
                                connection.needs_rollback = True
                            raise
                else:
                    # Commit transaction
                    try:
                        connection.commit()
                    except DatabaseError:
                        try:
                            connection.rollback()
                        except Error:
                            # An error during rollback means that something
                            # went wrong with the connection. Drop it.
                            connection.close()
                        raise
            else:
                # This flag will be set to True again if there isn't a savepoint
                # allowing to perform the rollback at this level.
                # 这个标志将在没有保存点时再次设置为True，允许在当前级别执行回滚。
                connection.needs_rollback = False
                if connection.in_atomic_block:
                    # Roll back to savepoint if there is one, mark for rollback
                    # otherwise.
                    # 如果存在保存点，则回滚到保存点，否则标记为需要回滚。
                    if sid is None:
                        connection.needs_rollback = True
                    else:
                        try:
                            connection.savepoint_rollback(sid)
                            # The savepoint won't be reused. Release it to
                            # minimize overhead for the database server.
                            connection.savepoint_commit(sid)
                        except Error:
                            # If rolling back to a savepoint fails, mark for
                            # rollback at a higher level and avoid shadowing
                            # the original exception.
                            connection.needs_rollback = True
                else:
                    # Roll back transaction
                    try:
                        connection.rollback()
                    except Error:
                        # An error during rollback means that something
                        # went wrong with the connection. Drop it.
                        connection.close()

        finally:
            # Outermost block exit when autocommit was enabled.
            # 最外层的块退出时，autocommit为真。
            if not connection.in_atomic_block:
                if connection.closed_in_transaction:
                    connection.connection = None
                else:
                    connection.set_autocommit(True)
            # Outermost block exit when autocommit was disabled.
            # 最外层的块退出时，autocommit为假。
            elif not connection.savepoint_ids and not connection.commit_on_exit:
                if connection.closed_in_transaction:
                    connection.connection = None
                else:
                    connection.in_atomic_block = False


def atomic(using=None, savepoint=True):
    # Bare decorator: @atomic -- although the first argument is called
    # `using`, it's actually the function being decorated.
    if callable(using):
        return Atomic(DEFAULT_DB_ALIAS, savepoint)(using)
    # Decorator: @atomic(...) or context manager: with atomic(...): ...
    else:
        return Atomic(using, savepoint)


def _non_atomic_requests(view, using):
    try:
        view._non_atomic_requests.add(using)
    except AttributeError:
        view._non_atomic_requests = {using}
    return view


def non_atomic_requests(using=None):
    if callable(using):
        return _non_atomic_requests(using, DEFAULT_DB_ALIAS)
    else:
        if using is None:
            using = DEFAULT_DB_ALIAS
        return lambda view: _non_atomic_requests(view, using)
