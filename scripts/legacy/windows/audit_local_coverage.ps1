param(
    [string]$OutputPath = "data/coverage/local-coverage.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RepoPath([string]$RelativePath) {
    return Join-Path $repoRoot $RelativePath
}

function New-StringSet {
    return ,([System.Collections.Generic.HashSet[string]]::new())
}

function Normalize-CardId([string]$Value) {
    return ([int64]$Value).ToString()
}

$cdbPath = Resolve-RepoPath "references/babelcdb/cards.cdb"
$cdbIds = New-StringSet
$cardTypes = @{}
foreach ($line in & sqlite3.exe -separator "|" $cdbPath "SELECT id,type FROM datas;") {
    $parts = $line.Split("|")
    $id = Normalize-CardId $parts[0]
    $cdbIds.Add($id) | Out-Null
    $cardTypes[$id] = [int64]$parts[1]
}

$cdbCounts = (& sqlite3.exe -json $cdbPath "SELECT (SELECT COUNT(*) FROM datas) AS datas_rows,(SELECT COUNT(*) FROM texts) AS texts_rows,(SELECT COUNT(*) FROM datas d JOIN texts t USING(id)) AS joined_rows,(SELECT COUNT(*) FROM texts WHERE name IS NULL OR trim(name)='') AS empty_names;") | ConvertFrom-Json

$scriptIds = New-StringSet
foreach ($file in Get-ChildItem -LiteralPath (Resolve-RepoPath "references/cardscripts/official") -Filter "c*.lua" -File) {
    $scriptIds.Add((Normalize-CardId $file.BaseName.Substring(1))) | Out-Null
}

$scriptIdsInCdb = 0
foreach ($id in $scriptIds) {
    if ($cdbIds.Contains($id)) { $scriptIdsInCdb++ }
}

$deckIds = New-StringSet
$deckStats = [System.Collections.Generic.List[object]]::new()
$deckRoot = Resolve-RepoPath "references/ygo-agent/assets/deck"
foreach ($file in Get-ChildItem -LiteralPath $deckRoot -Filter "*.ydk" -File) {
    $zone = "main"
    $counts = @{main = 0; extra = 0; side = 0}
    foreach ($line in Get-Content -LiteralPath $file.FullName) {
        $value = $line.Trim()
        if ($value -eq "#main") { $zone = "main"; continue }
        if ($value -eq "#extra") { $zone = "extra"; continue }
        if ($value -eq "!side") { $zone = "side"; continue }
        if ($value -match "^\d+$") {
            $id = Normalize-CardId $value
            $deckIds.Add($id) | Out-Null
            $counts[$zone]++
        }
    }
    $deckStats.Add([ordered]@{
        deck = $file.BaseName
        main = $counts.main
        extra = $counts.extra
        side = $counts.side
    })
}

$deckIdsInCdb = 0
$deckIdsWithScript = 0
$expectedScriptless = [System.Collections.Generic.List[string]]::new()
$unexpectedScriptless = [System.Collections.Generic.List[string]]::new()
$missingDeckIds = [System.Collections.Generic.List[string]]::new()
foreach ($id in $deckIds) {
    if (-not $cdbIds.Contains($id)) {
        $missingDeckIds.Add($id)
        continue
    }
    $deckIdsInCdb++
    if ($scriptIds.Contains($id)) {
        $deckIdsWithScript++
        continue
    }
    $type = $cardTypes[$id]
    if (($type -band 16) -ne 0 -or ($type -band 16384) -ne 0) {
        $expectedScriptless.Add($id)
    } else {
        $unexpectedScriptless.Add($id)
    }
}

$banlistStats = [System.Collections.Generic.List[object]]::new()
foreach ($file in Get-ChildItem -LiteralPath (Resolve-RepoPath "references/lflists") -Filter "*.lflist.conf" -File) {
    $listName = $null
    $rowCount = 0
    $ids = New-StringSet
    foreach ($line in Get-Content -LiteralPath $file.FullName) {
        if (-not $listName -and $line.StartsWith("!")) { $listName = $line.Substring(1).Trim() }
        if ($line -match "^(\d+)\s+[0-3]\s+--") {
            $rowCount++
            $ids.Add((Normalize-CardId $Matches[1])) | Out-Null
        }
    }
    $inCdb = 0
    foreach ($id in $ids) {
        if ($cdbIds.Contains($id)) { $inCdb++ }
    }
    $banlistStats.Add([ordered]@{
        file = $file.Name
        list_name = $listName
        rows = $rowCount
        unique_card_ids = $ids.Count
        ids_in_cdb = $inCdb
        cdb_coverage_percent = if ($ids.Count) { [math]::Round(100 * $inCdb / $ids.Count, 2) } else { 0 }
    })
}

$report = [ordered]@{
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    card_database = [ordered]@{
        datas_rows = [int]$cdbCounts.datas_rows
        texts_rows = [int]$cdbCounts.texts_rows
        joined_rows = [int]$cdbCounts.joined_rows
        empty_names = [int]$cdbCounts.empty_names
    }
    official_scripts = [ordered]@{
        unique_script_ids = $scriptIds.Count
        script_ids_in_cdb = $scriptIdsInCdb
        cdb_cards_with_official_script_percent = [math]::Round(100 * $scriptIdsInCdb / $cdbIds.Count, 2)
    }
    ygo_agent_decks = [ordered]@{
        deck_count = $deckStats.Count
        unique_card_ids = $deckIds.Count
        ids_in_current_cdb = $deckIdsInCdb
        ids_with_official_script = $deckIdsWithScript
        expected_scriptless_normal_or_token_ids = @($expectedScriptless | Sort-Object)
        unexpected_scriptless_ids = @($unexpectedScriptless | Sort-Object)
        missing_current_cdb_ids = @($missingDeckIds | Sort-Object)
        engine_data_coverage_percent = [math]::Round(100 * $deckIdsInCdb / $deckIds.Count, 2)
        valid_main_decks = @($deckStats | Where-Object { $_.main -ge 40 -and $_.main -le 60 }).Count
        decks_with_side = @($deckStats | Where-Object { $_.side -gt 0 }).Count
        details = $deckStats
    }
    banlists = $banlistStats
    interpretation = @(
        "A missing Lua script is not automatically a coverage failure: normal monsters and tokens have no effect script by design.",
        "The three ygo-agent IDs absent from the current CDB are legacy token references and should be normalized during deck import.",
        "Current OCG/TCG/World lists align almost completely with the current CDB; cross-era and Rush formats require separate snapshots."
    )
}

$target = Resolve-RepoPath $OutputPath
[System.IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
[System.IO.File]::WriteAllText($target, ($report | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote coverage audit to $target"
