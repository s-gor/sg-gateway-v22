# Полное удаление SG-Gateway

## Команда

```bash
curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/full-uninstall-ubuntu.sh | sudo bash
```

Подтверждение:

```text
DELETE SG-GATEWAY
```

## Что удаляется

- `/opt/sg-gateway`;
- `/etc/sg-gateway`;
- `/var/lib/sg-gateway`;
- `/var/log/sg-gateway`;
- systemd-службы SG-Gateway;
- управляемые конфигурации Xray;
- AmneziaWG;
- Mihomo;
- sing-box;
- WARP helper;
- Nginx-файлы SG-Gateway;
- renewal hooks;
- sysctl и UFW-правила, созданные установщиком.

## Что сохраняется

Общие пакеты Ubuntu, Python, Nginx и Certbot не удаляются, потому что они могут использоваться другими приложениями.

Перед удалением сохраните нужные клиентские конфигурации и резервные копии.
