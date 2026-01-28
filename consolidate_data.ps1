$sourceDir = "C:\tunai"
$destDir = "C:\tunai\all_datasets"
$extensions = @(".json", ".jsonl", ".txt", ".csv")
$excludeDirs = @(".venv", ".venv311", ".git", "__pycache__", "node_modules", "all_datasets")

# Create destination directory
if (-not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir | Out-Null
    Write-Host "Created directory: $destDir"
}

# Find files
$files = Get-ChildItem -Path $sourceDir -Recurse -File | Where-Object {
    $ext = $_.Extension
    if ($null -ne $ext) {
        $extensions -contains $ext.ToLower()
    } else {
        $false
    }
}

$count = 0

foreach ($file in $files) {
    # Check exclusions
    $relPath = $file.FullName.Substring($sourceDir.Length)
    $skip = $false
    foreach ($exclude in $excludeDirs) {
        if ($relPath -match "\\$exclude\\") {
            $skip = $true
            break
        }
    }
    if ($skip) { continue }

    # Construct new name
    $parentName = $file.Directory.Name
    $newName = $file.Name
    $destPath = Join-Path $destDir $newName

    # Handle collision by prepending parent folder name if file exists
    if (Test-Path $destPath) {
        $newName = "${parentName}_" + $file.Name
        $destPath = Join-Path $destDir $newName
    }
    
    # Double check collision (nested same names)
    while (Test-Path $destPath) {
         $rand = Get-Random -Minimum 1000 -Maximum 9999
         $newName = "${rand}_" + $newName
         $destPath = Join-Path $destDir $newName
    }

    Copy-Item -Path $file.FullName -Destination $destPath
    Write-Host "Copied: $($file.Name) -> $newName"
    $count++
}

Write-Host "--------------------------------"
Write-Host "Total files copied: $count"
