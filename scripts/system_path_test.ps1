$lines = New-Object System.Collections.Generic.List[string]

$lines.Add("TIME: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$lines.Add("USER: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)")
$lines.Add("PROCESS_BITNESS: $([Environment]::Is64BitProcess)")

$paths = @(
    "C:\warehouse",
    "C:\warehouse\backups",
    "C:\warehouse\backups\daily",
    "C:\warehouse\backups\weekly",
    "C:\warehouse\backups\monthly",
    "C:\warehouse\logs"
)

foreach ($path in $paths) {
    try {
        $exists = Test-Path -LiteralPath $path
        $lines.Add("$path | EXISTS=$exists")

        if ($exists) {
            $item = Get-Item -LiteralPath $path
            $lines.Add("$path | ATTRIBUTES=$($item.Attributes)")
        }
    }
    catch {
        $lines.Add("$path | ERROR=$($_.Exception.Message)")
    }
}

try {
    $testFile = "C:\warehouse\backups\daily\system_write_test.txt"
    Set-Content -LiteralPath $testFile -Value "SYSTEM_WRITE_OK" -Encoding ASCII
    $lines.Add("WRITE_TEST: $(Test-Path -LiteralPath $testFile)")
}
catch {
    $lines.Add("WRITE_TEST_ERROR: $($_.Exception.Message)")
}

$lines | Set-Content `
    -LiteralPath "C:\Windows\Temp\warehouse_system_path_test.txt" `
    -Encoding UTF8
