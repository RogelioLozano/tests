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
