from __future__ import annotations


class AppError(Exception):
    """项目业务异常基类。"""

    code = 50000
    message = "系统异常"

    def __init__(self, message: str | None = None, code: int | None = None) -> None:
        self.code = code if code is not None else self.code
        self.message = message or self.message
        super().__init__(self.message)


class ValidationError(AppError):
    """参数校验异常。"""

    code = 40001
    message = "参数错误"


class DataNotFoundError(AppError):
    """数据不存在异常。"""

    code = 40002
    message = "数据不存在"


class DataQualityError(AppError):
    """数据质量不足异常。"""

    code = 40003
    message = "数据质量不足"


class DatabaseError(AppError):
    """数据库异常。"""

    code = 50001
    message = "数据库异常"


class FileProcessError(AppError):
    """文件处理异常。"""

    code = 50002
    message = "文件处理异常"


class ReportGenerateError(AppError):
    """报告生成异常。"""

    code = 50003
    message = "报告生成异常"


class BigDataTaskError(AppError):
    """Hive、Spark 等大数据任务异常。"""

    code = 50004
    message = "大数据任务异常"
