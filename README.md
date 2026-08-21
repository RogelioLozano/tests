# tests

A repository for learning and experiments.

## Local HTTPS setup

This server uses HTTPS and expects certificate files. Do not commit private keys.

Recommended local workflow:

1. Keep certs outside git, or rely on ignored files (`*.pem` is ignored).
2. Point each worktree to your local cert paths with environment variables.

If you need to generate local-only certs:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
	-keyout key.pem -out cert.pem -subj "/CN=localhost"
python server.py
```

## How to render animations (Manim)

Animations are authored as Python scenes and rendered to `.mp4` files with
[Manim](https://www.manim.community/). The rendered videos are then served as
static assets.

Layout:

- `animations/scenes/` — source scenes you author (versioned).
- `animations/output/` — rendered `.mp4` artifacts (served by the app).

The `.venv/` and Manim's `media/` scratch dir are local-only and git-ignored;
recreate the environment from `requirements.txt`.

### One-time setup

```bash
# System dependencies (macOS / Homebrew)
brew install py3cairo ffmpeg pango pkg-config

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Render a scene

```bash
source .venv/bin/activate
manim -qh animations/scenes/example.py SquareToCircle \
	--media_dir animations/output
```

Flags: `-ql` (low quality, fast) / `-qh` (high quality). The resulting `.mp4`
can then be served by the static server or referenced from the Vue app.

### Serve it in the Vue app

The Vue app serves static assets from `web/public/`. Copy the rendered video
there (it's git-ignored — an artifact, not source):

```bash
cp animations/output/videos/example/480p15/SquareToCircle.mp4 \
	web/public/animations/SquareToCircle.mp4
```

The `/animations` route (`web/src/views/Animations.vue`) plays it from
`/animations/SquareToCircle.mp4`.
