#!/bin/bash
# Runs riftbound (loopback only) and nginx (public). If either dies, exit so
# Fly restarts the machine.
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

stdbuf -oL ./riftbound --agent1 human --agent2 mcts:sims=50 \
  --deck1 decks/fiora.txt --deck2 decks/yi_rebuild.txt \
  --bind 127.0.0.1 --port 8081 --god-mode off &
RB=$!
nginx -g 'daemon off;' &
NG=$!
wait -n "$RB" "$NG"
echo "[entrypoint] a process exited, shutting down" >&2
kill "$RB" "$NG" 2>/dev/null
exit 1
