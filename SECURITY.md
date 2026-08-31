# Security Policy

## Security Overview
Chargeback Sentinel takes security and privacy seriously. As an enterprise dispute defense engine, maintaining confidentiality and integrity of payment metadata is critical.

## Reporting Vulnerabilities
If you discover a potential security vulnerability within this project, please report it immediately:

- **Email**: security@bakhtiarsiddiqui.dev
- **Response Time**: We acknowledge reports within 24 business hours.

Please **do not** open public issues for security vulnerabilities.

## Best Practices for Deployment
1. Never commit `.env` files, API keys, or raw payment card data (PANs/CVVs).
2. Ensure API endpoints are deployed behind an HTTPS reverse proxy (e.g. Nginx, Cloudflare).
3. Restrict CORS origins in production environments.
