param(
    [string]$WebPort = "",
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"

function Resolve-BaseUrl {
    param(
        [string]$RequestedBaseUrl,
        [string]$RequestedWebPort
    )

    if ($RequestedBaseUrl) {
        return $RequestedBaseUrl.TrimEnd("/")
    }

    if ($RequestedWebPort) {
        return "http://127.0.0.1:$RequestedWebPort"
    }

    if ($env:E2E_BASE_URL) {
        return $env:E2E_BASE_URL.TrimEnd("/")
    }

    if ($env:WEB_PORT) {
        return "http://127.0.0.1:$($env:WEB_PORT)"
    }

    return "http://127.0.0.1:8000"
}

$resolvedBaseUrl = Resolve-BaseUrl -RequestedBaseUrl $BaseUrl -RequestedWebPort $WebPort
if (-not $WebPort) {
    if ($resolvedBaseUrl -match ":(\d+)$") {
        $WebPort = $Matches[1]
    } else {
        $WebPort = "8000"
    }
}

$env:WEB_PORT = $WebPort
$env:E2E_BASE_URL = $resolvedBaseUrl

Write-Host "Starting docker compose on port $WebPort..."
docker compose up -d

Write-Host "Running migrations..."
docker compose exec -T web python manage.py migrate --noinput

Write-Host "Seeding screenshot demo data..."
docker compose exec -T web python manage.py seed_screenshot_demo --reset

if (-not (Test-Path node_modules)) {
    Write-Host "Installing npm dependencies..."
    npm install
}

Write-Host "Ensuring Playwright Chromium is installed..."
npx playwright install chromium

$screenshotDir = Join-Path $PWD "artifacts\screenshots"
if (Test-Path $screenshotDir) {
    Remove-Item -Recurse -Force $screenshotDir
}

Write-Host "Capturing screenshots to $screenshotDir ..."
npm run e2e:screenshots

Write-Host ""
Write-Host "Screenshot capture complete."
Write-Host "Base URL: $resolvedBaseUrl"
Write-Host "Output: $screenshotDir"
