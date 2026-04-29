#!/bin/sh
set -e

VENV_DIR="/home/app/venv"
DJANGO_CMD="$VENV_DIR/bin/python /home/app/application_api/manage.py"

. "$VENV_DIR/bin/activate"

# Attendre que la DB soit prête (le service app fait migrate en premier)
echo "Scheduler: démarrage du planificateur..."

exec $DJANGO_CMD runapscheduler
