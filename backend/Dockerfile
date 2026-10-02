# Uretim imaji. APP_ENV varsayilan olarak "production"dir: sirlar
# (SESSION_SECRET, PHONE_HASH_SECRET, CRON_SECRET) verilmezse uygulama
# baslamaz. Migration'lar acilista, uvicorn'dan once calisir.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv \
    APP_ENV=production \
    UPLOAD_DIR=/data/uploads

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home --uid 1000 aurora \
    && mkdir -p /data/uploads \
    && chown aurora /data/uploads
USER aurora

# Yuklenen gorseller kalici bir volume'da tutulmali.
VOLUME ["/data/uploads"]
EXPOSE 8000

# --proxy-headers: gercek istemci IP'si (deneme sinirlari icin) ters
# proxy'nin X-Forwarded-For basligindan okunur. FORWARDED_ALLOW_IPS,
# proxy'nin (nginx / Next.js sunucusu) adresi olmalidir.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1} --workers ${WEB_CONCURRENCY:-2}"]
