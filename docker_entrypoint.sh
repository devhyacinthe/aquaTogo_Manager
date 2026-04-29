#!/bin/sh
set -e

VENV_DIR="/home/app/venv"
DJANGO_CMD="$VENV_DIR/bin/python /home/app/application_api/manage.py"
SOCK="/var/run/control.unit.sock"
WAITLOOPS=15
SLEEPSEC=1

. "$VENV_DIR/bin/activate"

$DJANGO_CMD migrate --noinput
$DJANGO_CMD collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_MAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "from django.contrib.auth.models import User; \
User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or \
User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_MAIL', '$DJANGO_SUPERUSER_PASSWORD')" \
        | $DJANGO_CMD shell
fi

chown unit:unit -R /home/app/application_api/staticfiles 2>/dev/null || true
chown unit:unit -R /home/app/application_api/media 2>/dev/null || true

# Démarrer Unit en arrière-plan pour pousser la config
unitd --control unix://"$SOCK"

# Attendre que le socket soit disponible
i=0
while [ $i -lt $WAITLOOPS ]; do
    if [ -S "$SOCK" ]; then
        break
    fi
    sleep $SLEEPSEC
    i=$((i + 1))
done

if [ ! -S "$SOCK" ]; then
    echo "ERROR: Unit control socket not available after $WAITLOOPS seconds" >&2
    exit 1
fi

curl -s -X PUT \
    --data-binary @/home/app/application_api/configurations/unit.config \
    --unix-socket "$SOCK" \
    http://localhost/config

# Arrêter proprement Unit - il sera relancé par CMD
kill -TERM "$(cat /var/run/unit.pid)"

i=0
while [ $i -lt $WAITLOOPS ]; do
    if [ -S "$SOCK" ]; then
        sleep $SLEEPSEC
        i=$((i + 1))
    else
        break
    fi
done

echo "Unit configuré, démarrage production..."

exec "$@"
