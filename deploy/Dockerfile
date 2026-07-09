# Continuous committee daemon. Build: docker build -t autox-committee -f deploy/Dockerfile .
# Run:   docker run -d --restart=always -e GOOGLE_MAPS_API_KEY=... autox-committee
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir shapely openpyxl
COPY . /app
ENV CYCLE_SLEEP_SEC=900 CENSUS_EVERY_N=24 GEOCODE_BATCH=50
CMD ["python3", "committee/daemon.py"]
