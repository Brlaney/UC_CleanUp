#!/bin/sh
set -e

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Seeding county boundary..."
python manage.py seed_district \
  --file static/data/putnam_county_boundary.geojson \
  --name "Putnam County" \
  --slug putnam-county || true

echo "Fetching and seeding all commission districts from TNMap..."
python manage.py fetch_districts || true

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
