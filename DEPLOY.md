# Deploying alpharune to Fly.io

Packages the [alpharune](https://github.com/chorlick/alpharune) web UI
(human vs MCTS-50, Fiora vs Yi) as a single Fly machine.

## Deploy

```bash
# once: install flyctl and log in
curl -L https://fly.io/install.sh | sh
fly auth login

# from the repo root. Edit `app` in fly.toml to a unique name first.
fly launch --copy-config --no-deploy      # creates the app
fly deploy --remote-only                  # builds on Fly (~10-20 min first time)
fly scale count 1                         # game state is in memory: keep ONE machine
```

## Open the game

The server requires an access token and prints it at startup:

```bash
fly logs        # look for: → Open http://0.0.0.0:8080/?token=XXXX
```

Open `http://<app>.fly.dev/?token=XXXX` — replace `0.0.0.0:8080` with your
app's host and **use `http://`, not `https://`**: the server only accepts a
WebSocket whose `Origin` is `http://<Host>`, so an HTTPS page is rejected.
(`force_https` is therefore off in `fly.toml`.)

## Caveats

- Anyone with the token URL can play. God-mode is off, so hands stay hidden.
- One game per process. When it ends the process exits and Fly restarts it,
  which prints a **new token** (check `fly logs` again).
- Traffic is unencrypted (http). Fine for a test; for real use, patch the
  Origin check upstream and enable HTTPS.
- Not built or deployed from the authoring environment (no Docker daemon,
  no Fly access). Verified locally: binary + `cards decks rules errata`,
  `--bind 0.0.0.0` returns 403 without the token and 200 with it.
