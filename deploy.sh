#!/bin/bash
# Deployment script for FraudDetectPro
# Usage: ./deploy.sh [production|staging|development]

set -e

ENVIRONMENT=${1:-development}
echo "🚀 Deploying FraudDetectPro in $ENVIRONMENT mode..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Check if firebase.json exists
if [ ! -f "firebase.json" ]; then
    echo "⚠️  Warning: firebase.json not found. Firebase authentication will not work."
    echo "   Please ensure FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_BASE64 is set."
fi

# Build and start services
echo "📦 Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check backend health
echo "🏥 Checking backend health..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend is healthy"
else
    echo "⚠️  Backend health check failed. Check logs with: docker-compose logs backend"
fi

# Check frontend
echo "🌐 Checking frontend..."
if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo "✅ Frontend is accessible"
else
    echo "⚠️  Frontend check failed. Check logs with: docker-compose logs frontend"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Access points:"
echo "   - Frontend: http://localhost:3000"
echo "   - Backend API: http://localhost:8000"
echo "   - API Docs: http://localhost:8000/docs"
echo ""
echo "📋 Useful commands:"
echo "   - View logs: docker-compose logs -f"
echo "   - Stop services: docker-compose down"
echo "   - Restart services: docker-compose restart"
echo ""

