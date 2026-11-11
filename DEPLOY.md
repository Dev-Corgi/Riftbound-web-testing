# Deploying alpharune to Fly.io

Packages the [alpharune](https://github.com/chorlick/alpharune) web UI
(human vs MCTS-50, Fiora vs Yi) as a single Fly machine.

## How it works

The page at `/` is a phone-friendly card-game UI (`deploy/mobile/index.html`) with a
start form: pick your deck, the opponent's deck and the AI level
(easy = random, normal/hard/expert = `ismcts` with 50/200/500 simulations; these
AIs do not see your hand). `deploy/launcher.py` (loopback `:8082`, behind nginx
`/api/`) lists decks/images and (re)starts `riftbound` with the chosen options.
The stock UI is still at `/classic` while a game is running.

`riftbound` rejects any request whose `Host` is not an IP literal or
`localhost`, and any WebSocket whose `Origin` is not `http://<Host>`. So the
container runs it on `127.0.0.1:8081` (started by the launcher) (loopback => no access token) and puts
nginx on `:8080` in front, rewriting `Host`/`Origin` (`deploy/nginx.conf.template`,
`deploy/entrypoint.sh`). Open `https://<app>.fly.dev/` directly.

## Deploy

Fly redeploys from this branch on every push (GitHub integration), or:

```bash
fly deploy --remote-only
fly scale count 1       # game state is in memory: keep exactly ONE machine
```

## Password (recommended)

Without it, anyone who knows the URL can play. To require a login, set a
Fly secret (dashboard: app -> Secrets, or `fly secrets set GAME_PASSWORD=...`);
the browser then asks for user `player` and that password.

## Caveats

- One game per process. When the game ends the process exits and Fly restarts it.
- God-mode (shows all hands/decks) is forced off.
- Verified locally with the same layout: HTTP 200 with `Host: <app>.fly.dev`,
  a WebSocket with `Origin: https://<app>.fly.dev` opens, and with
  `GAME_PASSWORD` set requests get 401 without credentials and 200 with them.
  The Docker image itself was not built from the authoring environment.
