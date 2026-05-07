# Content Factory Bot — Server Deployment

## Quick Start

1. Скопируй папку на VPS:
   scp -r ~/Downloads/content_factory_deploy/ root@YOUR_SERVER_IP:/root/

2. Подключись к серверу:
   ssh root@YOUR_SERVER_IP

3. Установи Docker (если нет):
   curl -fsSL https://get.docker.com | sh

4. Запусти бота:
   cd /root/content_factory_deploy
   ./deploy.sh

5. Логи:
   docker-compose logs -f

## Обновить Instagram cookies
Открой docker-compose.yml, замени значение IG_COOKIES=
Потом: docker-compose up -d --build

## Остановить
docker-compose down

## Рекомендуемые VPS
- Hetzner CX22: €3.79/мес (лучший выбор)
- DigitalOcean Droplet: $4/мес
- TimeWeb: 200 руб/мес
