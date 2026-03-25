$proc = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn main:app --port 5001"
Write-Host "Server starting on port 5001..."
Start-Sleep -Seconds 5
python test_endpoint.py
Write-Host "Stopping server..."
Stop-Process -Id $proc.Id -Force
