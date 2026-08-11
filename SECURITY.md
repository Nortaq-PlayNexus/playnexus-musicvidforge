# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅ |

## Reporting a vulnerability

MusicVidForge runs entirely locally and makes no network requests. If you still
find a security issue — for example in how media files are parsed — please
**do not open a public issue**. Instead report it privately via the
[GitHub Security Advisory](https://github.com/Nortaq-PlayNexus/playnexus-musicvidforge/security/advisories/new)
or email the maintainers through your GitHub contact.

Please include:

- A short description of the issue and its impact.
- Steps to reproduce.
- The affected version(s).

We aim to respond within 5 business days.

## Security notes

- MusicVidForge never uploads your audio, images or rendered videos anywhere.
- Only install the project from this repository or PyPI-hosted dependency
  sources — never from random mirrors.
- Keep your Python environment updated (`pip install -U pip`).
