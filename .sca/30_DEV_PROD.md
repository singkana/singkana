# DEV / PROD Split

## DEV Environment
- `flask run` (development server)
- DEBUG on
- local `.env` file
- no HTTPS assumption
- localhost:5000

## PROD Environment
- `gunicorn` (production server)
- DEBUG off
- secrets from systemd env
- HTTPS enforced
- proper domain configuration

## Safety Rules
- Never commit `.env` or secrets
- Always check environment before making changes
- Test in DEV before deploying to PROD
- Document any environment-specific changes
