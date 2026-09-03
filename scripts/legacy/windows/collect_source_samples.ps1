param(
    [string]$OutputRoot = "data/source_samples"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputPath = Join-Path $repoRoot $OutputRoot
$retrievedAt = [DateTimeOffset]::UtcNow.ToString("o")
$manifest = [System.Collections.Generic.List[object]]::new()

function Ensure-Directory([string]$Path) {
    [System.IO.Directory]::CreateDirectory($Path) | Out-Null
}

function Write-Utf8([string]$Path, [string]$Content) {
    $parent = Split-Path -Parent $Path
    Ensure-Directory $parent
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Write-Json([string]$Path, $Value, [int]$Depth = 30) {
    Write-Utf8 $Path ($Value | ConvertTo-Json -Depth $Depth)
}

function Add-Manifest([string]$Source, [string]$Kind, [string]$Status, [string]$Path, [string]$Url, [string]$Note) {
    $manifest.Add([ordered]@{
        source = $Source
        kind = $Kind
        status = $Status
        sample_path = $Path.Replace($repoRoot + [System.IO.Path]::DirectorySeparatorChar, "").Replace("\", "/")
        url = $Url
        retrieved_at = $retrievedAt
        note = $Note
    })
}

function Fetch-Text([string]$Source, [string]$Kind, [string]$Url, [string]$RelativePath, [string]$Note = "") {
    $target = Join-Path $repoRoot $RelativePath
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -Headers @{"User-Agent" = "YGO-Bench schema audit/0.1"} -TimeoutSec 45
        $buffer = [System.IO.MemoryStream]::new()
        $response.RawContentStream.Position = 0
        $response.RawContentStream.CopyTo($buffer)
        $content = [System.Text.Encoding]::UTF8.GetString($buffer.ToArray())
        $buffer.Dispose()
        Write-Utf8 $target $content
        Add-Manifest $Source $Kind "ok" $target $Url $Note
        return $content
    } catch {
        Add-Manifest $Source $Kind "error" $target $Url $_.Exception.Message
        return $null
    }
}

function Parse-Ydk([string]$Path) {
    $result = [ordered]@{main = @(); extra = @(); side = @()}
    $section = "main"
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $value = $line.Trim()
        if ($value -eq "#main") { $section = "main"; continue }
        if ($value -eq "#extra") { $section = "extra"; continue }
        if ($value -eq "!side") { $section = "side"; continue }
        if ($value -match "^\d+$") { $result[$section] += [int64]$value }
    }
    return $result
}

Ensure-Directory $outputPath

# BabelCDB: relational card data and localized text.
$cdbDir = Join-Path $outputPath "babelcdb"
Ensure-Directory $cdbDir
$cdbPath = Join-Path $repoRoot "references/babelcdb/cards.cdb"
try {
    $schema = & sqlite3.exe $cdbPath ".schema"
    Write-Utf8 (Join-Path $cdbDir "schema.sql") ($schema -join "`n")
    $rowsRaw = & sqlite3.exe -json $cdbPath "SELECT d.id,d.ot,d.alias,d.setcode,d.type,d.atk,d.def,d.level,d.race,d.attribute,d.category,t.name,t.desc,t.str1,t.str2 FROM datas d JOIN texts t USING(id) WHERE d.id IN (89631139,46986414,14558127) ORDER BY d.id;"
    Write-Utf8 (Join-Path $cdbDir "cards.sample.json") ($rowsRaw -join "`n")
    Add-Manifest "ProjectIgnis/BabelCDB" "sqlite" "ok" (Join-Path $cdbDir "cards.sample.json") "https://github.com/ProjectIgnis/BabelCDB" "Three joined datas/texts rows plus full SQLite schema."
} catch {
    Add-Manifest "ProjectIgnis/BabelCDB" "sqlite" "error" (Join-Path $cdbDir "cards.sample.json") "https://github.com/ProjectIgnis/BabelCDB" $_.Exception.Message
}

# CardScripts: executable Lua, keyed by card passcode in the filename.
$scriptsDir = Join-Path $outputPath "cardscripts"
Ensure-Directory $scriptsDir
$luaSource = Join-Path $repoRoot "references/cardscripts/official/c14558127.lua"
try {
    $luaTarget = Join-Path $scriptsDir "c14558127.lua"
    [System.IO.File]::Copy($luaSource, $luaTarget, $true)
    $hash = (Get-FileHash -LiteralPath $luaSource -Algorithm SHA256).Hash
    Write-Json (Join-Path $scriptsDir "sample.meta.json") ([ordered]@{card_id = 14558127; script = "c14558127.lua"; sha256 = $hash})
    Add-Manifest "ProjectIgnis/CardScripts" "lua" "ok" $luaTarget "https://github.com/ProjectIgnis/CardScripts" "Ash Blossom and Joyous Spring script sample."
} catch {
    Add-Manifest "ProjectIgnis/CardScripts" "lua" "error" (Join-Path $scriptsDir "c14558127.lua") "https://github.com/ProjectIgnis/CardScripts" $_.Exception.Message
}

# LFLists: current list name and card limit rows.
$lfDir = Join-Path $outputPath "lflists"
Ensure-Directory $lfDir
foreach ($fileName in @("OCG.lflist.conf", "0TCG.lflist.conf")) {
    $sourcePath = Join-Path $repoRoot ("references/lflists/" + $fileName)
    try {
        $listName = ""
        $section = ""
        $entries = [System.Collections.Generic.List[object]]::new()
        foreach ($line in [System.IO.File]::ReadAllLines($sourcePath)) {
            if ($line.StartsWith("!")) { $listName = $line.Substring(1).Trim(); continue }
            if ($line -match "^#(Forbidden|Limited|Semi-Limited|Unlimited)") { $section = $Matches[1]; continue }
            if ($line -match "^(\d+)\s+([0-3])\s+--(.*)$") {
                $entries.Add([ordered]@{card_id = [int64]$Matches[1]; limit = [int]$Matches[2]; section = $section; name_comment = $Matches[3].Trim()})
                if ($entries.Count -ge 8) { break }
            }
        }
        $target = Join-Path $lfDir ($fileName + ".sample.json")
        Write-Json $target ([ordered]@{list_name = $listName; entries = $entries})
        Add-Manifest "ProjectIgnis/LFLists" "line_config" "ok" $target "https://github.com/ProjectIgnis/LFLists" "Header plus eight card-limit rows."
    } catch {
        Add-Manifest "ProjectIgnis/LFLists" "line_config" "error" (Join-Path $lfDir ($fileName + ".sample.json")) "https://github.com/ProjectIgnis/LFLists" $_.Exception.Message
    }
}

# ygo-agent: deck encoding and supported-card registry.
$agentDir = Join-Path $outputPath "ygo-agent"
Ensure-Directory $agentDir
try {
    $deckPath = Join-Path $repoRoot "references/ygo-agent/assets/deck/Branded.ydk"
    $deck = Parse-Ydk $deckPath
    Write-Json (Join-Path $agentDir "Branded.sample.json") ([ordered]@{name = "Branded"; format = "ydk"; main = $deck.main; extra = $deck.extra; side = $deck.side})
    $codeRows = [System.Collections.Generic.List[object]]::new()
    foreach ($line in [System.IO.File]::ReadLines((Join-Path $repoRoot "references/ygo-agent/scripts/code_list.txt"))) {
        if ($line -match "^(\d+)\s+([01])$") {
            $codeRows.Add([ordered]@{card_id = [int64]$Matches[1]; has_script = [bool]([int]$Matches[2])})
            if ($codeRows.Count -ge 8) { break }
        }
    }
    Write-Json (Join-Path $agentDir "code_list.sample.json") $codeRows
    Add-Manifest "sbl1996/ygo-agent" "ydk_and_registry" "ok" (Join-Path $agentDir "Branded.sample.json") "https://github.com/sbl1996/ygo-agent" "One parsed YDK and eight code_list rows."
} catch {
    Add-Manifest "sbl1996/ygo-agent" "ydk_and_registry" "error" (Join-Path $agentDir "Branded.sample.json") "https://github.com/sbl1996/ygo-agent" $_.Exception.Message
}

# Public JSON APIs.
$ygoproCard = Fetch-Text "YGOPRODeck API v7" "json_api" "https://db.ygoprodeck.com/api/v7/cardinfo.php?id=89631139&misc=yes" "data/source_samples/ygoprodeck/card_89631139.json" "One card with misc/release metadata."
Fetch-Text "YGOPRODeck API v7" "json_api" "https://db.ygoprodeck.com/api/v7/checkDBVer.php" "data/source_samples/ygoprodeck/db_version.json" "Database version endpoint." | Out-Null
Fetch-Text "ygocdb API" "json_api" "https://ygocdb.com/api/v0/card/89631139?show=all" "data/source_samples/ygocdb/card_89631139.json" "One card with multilingual names and official cid." | Out-Null
Fetch-Text "YGOResources API" "json_api" "https://db.ygoresources.com/data/card/4007" "data/source_samples/ygoresources/card_4007.json" "One card keyed by KONAMI database id." | Out-Null

# HTML/editorial sources. Preserve one page and derive only stable embedded fields.
Fetch-Text "KONAMI Card Database" "html" "https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=4007&request_locale=en" "data/source_samples/konami/card_cid_4007.html" "Official card detail page; no public bulk JSON API." | Out-Null

$deckHtml = Fetch-Text "YGOPRODeck Tournament Meta Decks" "html_embedded_json" "https://ygoprodeck.com/deck/kewl-tune-721844" "data/source_samples/ygoprodeck_tournament/deck_721844.html" "Curated tournament deck page."
if ($deckHtml) {
    $sample = [ordered]@{deck_id = 721844; source_url = "https://ygoprodeck.com/deck/kewl-tune-721844"}
    foreach ($pair in @(@("main", "maindeckjs"), @("extra", "extradeckjs"), @("side", "sidedeckjs"))) {
        if ($deckHtml -match ("var\s+" + $pair[1] + "\s*=\s*'([^']+)'")) {
            $values = ConvertFrom-Json -InputObject $Matches[1]
            $normalized = foreach ($value in $values) { [int64]$value }
            $sample[$pair[0]] = @($normalized)
        } else {
            $sample[$pair[0]] = @()
        }
    }
    Write-Json (Join-Path $outputPath "ygoprodeck_tournament/deck_721844.parsed.json") $sample
}
Fetch-Text "YGOPRODeck Tournament Meta Decks" "html_embedded_json" "https://ygoprodeck.com/deck/kewl-tune-722486" "data/source_samples/ygoprodeck_tournament/deck_722486.html" "OCG Japan Championship 2026 Top 16 deck; event provenance is cross-checked against the official KONAMI event page." | Out-Null

Fetch-Text "KONAMI Neuron Deck Search" "html" "https://www.db.yugioh-card.com/yugiohdb/member_deck.action?cgid=3902370b33a337ad5c336bb5ca25da0e&dno=24&request_locale=en" "data/source_samples/neuron_deck/wcq_spanish_winner_2026.html" "Public full deck page; tournament label requires provenance validation." | Out-Null
Fetch-Text "Road of the King" "html_editorial" "https://roadoftheking.com/ocg-2026-04-metagame/" "data/source_samples/road_of_the_king/ocg_2026_04_metagame.html" "Editorial aggregate, not a documented API." | Out-Null
Fetch-Text "KONAMI Event Page" "html" "https://www.yugioh-card.com/eu/event/300th-yu-gi-oh-championship-series-dortmund-2026/" "data/source_samples/konami_event/ycs_dortmund_2026.html" "Official event metadata/coverage page." | Out-Null

# No public schema was found for these mini-program sources.
Add-Manifest -Source "Lets Duel mini program" -Kind "private_mini_program" -Status "not_sampled" -Path (Join-Path $outputPath "mini_programs/lets_duel.json") -Url "N/A" -Note "No documented public API or export. Request organizer or platform export."
Add-Manifest -Source "YGO Card Search mini program" -Kind "private_mini_program" -Status "not_sampled" -Path (Join-Path $outputPath "mini_programs/ygo_card_search.json") -Url "https://cms.jihuanshe.com/" -Note "Public CMS describes features, but tournament/deck API is not documented."

Write-Json (Join-Path $outputPath "manifest.json") $manifest 20
Write-Host ("Collected {0} source entries into {1}" -f $manifest.Count, $outputPath)
