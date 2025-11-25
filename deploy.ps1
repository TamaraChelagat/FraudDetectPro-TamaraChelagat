# Deployment script for FraudDetectPro (PowerShell)
# Usage: .\deploy.ps1 [production|staging|development]

param(
    [string]$Environment = "development"
)

Write-Host "🚀 Deploying FraudDetectPro in $Environment mode..." -ForegroundColor Cyan

# Check if Docker is installed
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if docker-compose is installed
if (-not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    Write-Host "❌ docker-compose is not installed. Please install docker-compose first." -ForegroundColor Red
    exit 1
}

# Check if firebase.json exists
if (-not (Test-Path "firebase.json")) {
    Write-Host "⚠️  Warning: firebase.json not found. Firebase authentication will not work." -ForegroundColor Yellow
    Write-Host "   Please ensure FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_BASE64 is set." -ForegroundColor Yellow
}

# Build and start services
Write-Host "📦 Building Docker images..." -ForegroundColor Cyan
docker-compose build

Write-Host "🚀 Starting services..." -ForegroundColor Cyan
docker-compose up -d

Write-Host "⏳ Waiting for services to be healthy..." -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Check backend health
Write-Host "🏥 Checking backend health..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Backend is healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  Backend health check failed. Check logs with: docker-compose logs backend" -ForegroundColor Yellow
}

# Check frontend
Write-Host "🌐 Checking frontend..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Frontend is accessible" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  Frontend check failed. Check logs with: docker-compose logs frontend" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📍 Access points:" -ForegroundColor Cyan
Write-Host "   - Frontend: http://localhost:3000"
Write-Host "   - Backend API: http://localhost:8000"
Write-Host "   - API Docs: http://localhost:8000/docs"
Write-Host ""
Write-Host "📋 Useful commands:" -ForegroundColor Cyan
Write-Host "   - View logs: docker-compose logs -f"
Write-Host "   - Stop services: docker-compose down"
Write-Host "   - Restart services: docker-compose restart"
Write-Host ""

