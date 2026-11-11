#!/bin/bash
# nginx (public :8080) + launcher (loopback :8082, starts/stops riftbound on :8081).
# If either dies, exit so Fly restarts the machine.
set -u
AUTH=""
if [ -n "${GAME_PASSWORD:-}" ]; then
  printf 'player:%s\n' "$(openssl passwd -apr1 "$GAME_PASSWORD")" > /etc/nginx/htpasswd
  AUTH='auth_basic "alpharune"; auth_basic_user_file /etc/nginx/htpasswd;'
  echo "[entrypoint] password protection ON (user: player)"
else
  echo "[entrypoint] WARNING: no GAME_PASSWORD set, anyone with the URL can play"
fi
sed "s|__AUTH__|$AUTH|" /app/nginx.conf.template > /etc/nginx/nginx.conf

python3 -u /app/launcher.py &
LA=$!
nginx -g 'daemon off;' &
NG=$!
wait -n "$LA" "$NG"
echo "[entrypoint] a process exited, shutting down" >&2
kill "$LA" "$NG" 2>/dev/null
exit 1
