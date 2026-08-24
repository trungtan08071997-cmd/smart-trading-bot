# Sử dụng Python ổn định
FROM python:3.12.10

# Thiết lập thư mục làm việc
WORKDIR /app

# Copy toàn bộ mã nguồn vào container
COPY . .

# Cài đặt các thư viện cần thiết
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Thiết lập biến môi trường (nếu cần)
ENV PYTHONUNBUFFERED=1

# Lệnh khởi chạy bot
CMD ["python", "ai_optimizer_bot.py"]
