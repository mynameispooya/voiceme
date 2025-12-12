# استفاده از نسخه سبک پایتون
FROM python:3.10-slim

# تنظیم دایرکتوری
WORKDIR /app

# جلوگیری از کش و بافرینگ پایتون (برای لاگ‌های بهتر)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# نصب کتابخانه‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کدها
COPY . .

# پورت پیش‌فرض Koyeb معمولا 8000 است
EXPOSE 8000

# اجرای برنامه با Gunicorn روی پورت 8000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120"]
