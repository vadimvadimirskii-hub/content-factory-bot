#!/bin/bash
echo "🚀 Deploying Content Factory Bot..."
docker-compose down 2>/dev/null
docker-compose up -d --build
echo "✅ Bot is running! Check logs: docker-compose logs -f"
