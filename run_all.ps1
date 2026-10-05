Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         Starting BARRIER X Safety Intelligence            " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan

$root = $PSScriptRoot

$mlPython = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $mlPython)) {
    Write-Host "      .venv not found - falling back to 'py' (needs onnxruntime)" -ForegroundColor DarkYellow
    $mlPython = "py"
}

Write-Host "[1/4] Starting SIF ML Scoring Service on :8000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$mlPython' -m uvicorn api.main:app --port 8000"

Write-Host "[2/4] Starting Go API Gateway on :9000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\gateway'; go run main.go"

$agentCmd = "cd '$root\agent_service'; py -m uvicorn app.main:app --port 8001"

$caBundle = $env:BARRIERX_CA_BUNDLE
if (-not $caBundle) { $caBundle = "$env:USERPROFILE\gotoolchain\windows-roots.pem" }
if (Test-Path $caBundle) {
    Write-Host "      using CA bundle: $caBundle" -ForegroundColor DarkGray
    $agentCmd = "`$env:SSL_CERT_FILE='$caBundle'; " + $agentCmd
}

Write-Host "[3/4] Starting AI HSE Agent Service on :8001..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", $agentCmd

Write-Host "[4/4] Starting Frontend Dev Server on :5173..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " All services launching in separate terminal windows!" -ForegroundColor Green
Write-Host " • Frontend URL:    http://localhost:5173" -ForegroundColor White
Write-Host " • Go Gateway URL:  http://localhost:9000" -ForegroundColor White
Write-Host " • Agent Service:   http://localhost:8001" -ForegroundColor White
Write-Host " • ML Scoring:      http://localhost:8000/health" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " The ML service loads a 568 MB model and takes longest to answer." -ForegroundColor DarkGray
Write-Host " Check model_ready:true on :8000/health before demoing a score." -ForegroundColor DarkGray
