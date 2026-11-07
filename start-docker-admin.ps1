$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath 'D:\Project'
$logPath = 'D:\Project\English_telegram_bot\docker-start.log'
try {
    & 'D:\Project\docker-compose.exe' -f 'D:\Project\docker-compose.yml' -f 'D:\Project\scripts\compose-existing-network.yml' up -d --build --no-deps englishbot *> $logPath
    $result = $LASTEXITCODE
    if ($result -eq 0) {
        & 'D:\Project\docker-compose.exe' -f 'D:\Project\docker-compose.yml' -f 'D:\Project\scripts\compose-existing-network.yml' ps englishbot *>> $logPath
    }
    Set-Content -LiteralPath 'D:\Project\English_telegram_bot\docker-start.exitcode' -Value $result
} catch {
    Set-Content -LiteralPath 'D:\Project\English_telegram_bot\docker-start.exitcode' -Value 1
    $_.Exception.Message | Add-Content -LiteralPath $logPath
}

