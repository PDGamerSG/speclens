# Expose the app over HTTPS so a phone can use its camera (getUserMedia needs a secure origin).
# Requires cloudflared on PATH. Open the printed https://*.trycloudflare.com URL on the phone.
cloudflared tunnel --url http://localhost:8765
