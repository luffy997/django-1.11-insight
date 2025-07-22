## ✅ 一、Django 事务机制核心概览

### 1.1 基本概念

- Django 的事务管理依赖 **数据库的原生事务能力**，由 Python 层进行封装。
- 支持 ACID 中的 **原子性**，事务中的操作要么全部成功，要么全部失败回滚。
- 支持 **嵌套事务**（通过保存点实现）以及 **多线程安全**（使用 `threading.local()`）。

### 1.2 主要组件

| 类 / 函数                 | 作用                             |
| ------------------------- | -------------------------------- |
| `transaction.atomic`      | 装饰器或上下文管理器，用于事务块 |
| `savepoint()`             | 创建保存点，返回 `sid`           |
| `savepoint_rollback(sid)` | 回滚到指定保存点                 |
| `savepoint_commit(sid)`   | 提交并释放保存点                 |
| `set_autocommit(False)`   | 显式控制事务起始                 |
| `commit()` / `rollback()` | 显式提交或回滚整个事务           |

------

## 🚀 二、Django 事务的四种用法

### 2.1 装饰器方式（推荐）

```python
@transaction.atomic
def view_func(request):
    # 事务块
```

### 2.2 上下文管理器方式

```python
with transaction.atomic():
    # 事务块
```

### 2.3 显式控制事务（用于复杂逻辑）

```python
transaction.set_autocommit(False)
try:
    # 操作
    transaction.commit()
except:
    transaction.rollback()
```

### 2.4 嵌套保存点控制（局部回滚）

```python
with transaction.atomic():
    sid = transaction.savepoint()
    try:
        # 内层操作
    except:
        transaction.savepoint_rollback(sid)
```

------

## 🔍 三、底层原理：保存点实现机制

### 3.1 核心机制

- **保存点依赖数据库原生支持（如 PostgreSQL / MySQL / SQLite）**

- 执行 SQL 指令如：

  ```sql
  SAVEPOINT s1;
  ROLLBACK TO SAVEPOINT s1;
  RELEASE SAVEPOINT s1;
  ```

### 3.2 Django 的封装实现（源码位置：`django/db/backends/base/base.py`）

- 创建保存点：

  ```python
  def savepoint(self):
      sid = "s%s" % self.savepoint_state
      self.cursor().execute("SAVEPOINT %s" % sid)
      return sid
  ```

- 回滚保存点：

  ```python
  def savepoint_rollback(self, sid):
      self.cursor().execute("ROLLBACK TO SAVEPOINT %s" % sid)
  ```

- 提交保存点：

  ```python
  def savepoint_commit(self, sid):
      self.cursor().execute("RELEASE SAVEPOINT %s" % sid)
  ```

------

## 🌟 四、设计亮点与注意事项

### 4.1 设计优势

- ✅ **跨数据库统一行为**：开发者不需关心 SQL 差异。
- ✅ **事务嵌套灵活**：支持复杂业务中的局部失败。
- ✅ **线程安全**：事务状态使用 `threading.local()` 存储。
- ✅ **性能优化**：懒连接机制 + 可调 `CONN_MAX_AGE`。

### 4.2 注意事项

- 捕获异常后应显式回滚，否则 Django 无法感知事务失败。
- SQLite 的内存数据库依然支持保存点，但不推荐用于生产。
- 在使用多个数据库时，需要显式指定 `using='xxx'`。

------

## ✅ 总结一句话

> Django 的事务机制是对数据库原生事务功能的高层封装，通过 `atomic` 和 `savepoint` 等 API，既实现了易用性，也保留了高级控制能力，适合从简单事务到复杂嵌套场景的各类需求。