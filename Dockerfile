# ===== 基础镜像：与本地开发一致的 Python 3.11 =====
FROM python:3.11-slim

WORKDIR /app

# 不缓冲 stdout：日志实时进 docker logs，不被 Python 攒着不吐
ENV PYTHONUNBUFFERED=1

# ===== 先只复制依赖清单再安装：利用层缓存 =====
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ===== 复制项目代码（.dockerignore 在这里生效）=====
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
