# SG-Gateway 021 pinned third-party runtime media

This directory intentionally stores the exact upstream artifacts used by a clean SG-Gateway 021 installation.
The installer does not resolve `latest` versions and does not download these runtimes from upstream during installation.

Pinned set:
- Xray-core v26.6.27 — `Xray-linux-64.zip`
- Mihomo v1.19.29 — `mihomo-linux-amd64-v1.19.29.gz`
- sing-box v1.13.14 — `sing-box-1.13.14-linux-amd64.tar.gz`
- wgcf-cli v0.3.6 — `wgcf-cli-linux-64.tar.zstd`
- AmneziaWG tools 1.0.20260618-2 — source archive
- AmneziaWG Linux kernel module 1.0.20260329-2 — source archive, installed through DKMS

The original upstream licenses and notices contained in each project remain applicable.
SHA-256 values used by SG-Gateway are stored in `SHA256SUMS`.
