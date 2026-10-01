$ErrorActionPreference = "Stop"

$envFile = "C:\warehouse\backend\.env"
$pgDump = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
$pgRestore = "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe"

$backupRoot = "C:\warehouse\backups"
$dailyDir = Join-Path $backupRoot "daily"
$weeklyDir = Join-Path $backupRoot "weekly"
$monthlyDir = Join-Path $backupRoot "monthly"
$logFile = "C:\warehouse\logs\database_backup.log"

$directories = @($backupRoot, $dailyDir, $weeklyDir, $monthlyDir)

foreach ($directory in $directories) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

function Write-BackupLog {
    param([string]$Message)

    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $Message"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

try {
    if (-not (Test-Path $envFile)) {
        throw ".env file not found."
    }

    if (-not (Test-Path $pgDump)) {
        throw "pg_dump.exe not found."
    }

    if (-not (Test-Path $pgRestore)) {
        throw "pg_restore.exe not found."
    }

    $databaseLine = Get-Content $envFile |
        Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } |
        Select-Object -First 1

    if (-not $databaseLine) {
        throw "DATABASE_URL not found."
    }

    $databaseUrl = ($databaseLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
    $uri = [System.Uri]$databaseUrl

    $userInfo = $uri.UserInfo -split ':', 2
    $dbUser = [System.Uri]::UnescapeDataString($userInfo[0])
    $dbPassword = [System.Uri]::UnescapeDataString($userInfo[1])
    $dbHost = $uri.Host
    $dbPort = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
    $dbName = $uri.AbsolutePath.TrimStart('/')

    $now = Get-Date
    $timestamp = $now.ToString("yyyyMMdd_HHmmss")

    $dailyName = "${dbName}_daily_${timestamp}.backup"
    $dailyFile = Join-Path $dailyDir $dailyName

    $env:PGPASSWORD = $dbPassword

    Push-Location $dailyDir

    try {
        & $pgDump `
            "--host=$dbHost" `
            "--port=$dbPort" `
            "--username=$dbUser" `
            "--dbname=$dbName" `
            "--format=custom" `
            "--compress=9" `
            "--file=$dailyName"

        $dumpExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($dumpExitCode -ne 0) {
        throw "pg_dump failed with exit code $dumpExitCode."
    }

    $dailyBackup = Get-Item $dailyFile

    if ($dailyBackup.Length -le 0) {
        throw "Backup file is empty."
    }

    # بررسی اینکه فایل بکاپ قابل خواندن است
    & $pgRestore "--list" $dailyFile | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Backup archive validation failed."
    }

    # یک نسخه برای هر هفته
    $daysFromMonday = (([int]$now.DayOfWeek + 6) % 7)
    $weekStart = $now.Date.AddDays(-$daysFromMonday)
    $weekKey = $weekStart.ToString("yyyyMMdd")
    $weeklyFile = Join-Path $weeklyDir "${dbName}_weekly_${weekKey}.backup"

    if (-not (Test-Path $weeklyFile)) {
        Copy-Item $dailyFile $weeklyFile -Force
    }

    # یک نسخه برای هر ماه
    $monthKey = $now.ToString("yyyyMM")
    $monthlyFile = Join-Path $monthlyDir "${dbName}_monthly_${monthKey}.backup"

    if (-not (Test-Path $monthlyFile)) {
        Copy-Item $dailyFile $monthlyFile -Force
    }

    # نگهداری روزانه ۳۰ روز
    Get-ChildItem $dailyDir -Filter "${dbName}_daily_*.backup" -File |
        Where-Object { $_.LastWriteTime -lt $now.AddDays(-30) } |
        Remove-Item -Force

    # نگهداری هفتگی ۱۲ هفته
    Get-ChildItem $weeklyDir -Filter "${dbName}_weekly_*.backup" -File |
        Where-Object { $_.LastWriteTime -lt $now.AddDays(-84) } |
        Remove-Item -Force

    # نگهداری ماهانه ۲۴ ماه
    Get-ChildItem $monthlyDir -Filter "${dbName}_monthly_*.backup" -File |
        Where-Object { $_.LastWriteTime -lt $now.AddMonths(-24) } |
        Remove-Item -Force

    $hash = (Get-FileHash $dailyFile -Algorithm SHA256).Hash

    Write-BackupLog `
        "SUCCESS | DAILY=$dailyFile | SIZE=$($dailyBackup.Length) | SHA256=$hash"
}
catch {
    Write-BackupLog "FAILED | $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

