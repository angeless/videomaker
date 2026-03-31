"""VideoEditor 自定义异常体系。

所有模块级异常必须继承 VideoEditorError，不得直接继承 Exception。
"""


class VideoEditorError(Exception):
    """所有 VideoEditor 异常的基类。"""
    pass
