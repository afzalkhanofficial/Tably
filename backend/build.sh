#!/usr/bin/env bash
# Render runs this as the Build Command. Exit immediately on any error.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
