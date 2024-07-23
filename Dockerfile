# 使用 Python 3.11 作為基礎映像
FROM python:3.11-slim

# 設置工作目錄
WORKDIR /app

# 只複製必要的文件
COPY app2.py .
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口
EXPOSE 8080

# 設置容器啟動命令
ENTRYPOINT ["streamlit", "run", "app2.py", "--server.port=8080", "--server.address=0.0.0.0"]