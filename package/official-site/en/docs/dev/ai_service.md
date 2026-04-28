# AI Service Design

The AI service hosts TrailSnap AI capabilities (e.g. OCR, face recognition, scene classification, image analysis). The backend task system calls it when needed.

## How it runs

- In Docker Compose deployment, it is provided as the `trailsnap-ai` service.
- Backend calls it via the internal network by default: `AI_API_URL=http://ai:8001`

## Common endpoints

- Swagger docs: `http://<host>:8801/docs` (depends on your Docker port mapping)

## Troubleshooting

- AI service not reachable: check `AI_API_URL` and Docker networking.
- Tasks not progressing: check task status/errors in **Settings → Task Management**.
