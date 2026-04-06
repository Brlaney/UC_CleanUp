#!/bin/sh
set -e

echo "Waiting for PostGIS at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
  sleep 1
done

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Seeding district data..."
python manage.py seed_district \
  --file static/data/putnam_county_boundary.geojson \
  --name "Putnam County" \
  --slug putnam-county || true
python manage.py seed_district \
  --file static/data/district_3_boundary.geojson \
  --name "District 3" \
  --slug district-3 || true

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

if [ "${DEBUG:-1}" = "1" ]; then
  echo "Starting Django development server..."
  exec python manage.py runserver 0.0.0.0:8000
fi

echo "Starting Gunicorn..."
exec gunicorn putnam_trashmap.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --access-logfile - \
  --error-logfile -
