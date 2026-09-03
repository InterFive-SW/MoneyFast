# Stage 1: frontend build
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim
WORKDIR /app

# DejaVu, PDF raporu için. `fpdf`'in gömülü çekirdek fontları latin-1 ve
# Türkçe'nin ı, ş, ğ harflerini taşımıyor; mevcut KVKK dışa aktarımı bu
# yüzden "Kisisel", "Olusturulma" diye yazmak zorunda kalmıştı. Rapor
# kullanıcıya gösterilen bir belge ve aksanları düşürülmüş Türkçe, yanlış
# yazılmış Türkçedir.
#
# Depoya ikili dosya koymak yerine paket: sürümü apt yönetiyor, lisansı
# (Bitstream Vera / Public Domain) dağıtıma uygun ve kurulu boyut ~2 MB.
RUN apt-get update     && apt-get install --no-install-recommends -y fonts-dejavu-core     && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend-builder /frontend/dist ./frontend/dist
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
