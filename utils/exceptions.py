class StorageError(Exception):
    """存储层统一异常：连接失败/写入失败/参数错误都用它。"""
