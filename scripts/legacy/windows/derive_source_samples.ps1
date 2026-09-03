param(
    [string]$SampleRoot = "data/source_samples"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$root = Join-Path $repoRoot $SampleRoot

function Write-Json([string]$Path, $Value, [int]$Depth = 30) {
    $json = $Value | ConvertTo-Json -Depth $Depth
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

function Decode([string]$Value) {
    return [System.Net.WebUtility]::HtmlDecode(($Value -replace "<[^>]+>", " " -replace "\s+", " ").Trim())
}

function Match-Value([string]$Text, [string]$Pattern) {
    $match = [regex]::Match($Text, $Pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($match.Success) { return (Decode $match.Groups[1].Value) }
    return $null
}

# KONAMI official card page.
$konamiPath = Join-Path $root "konami/card_cid_4007.html"
$konami = [System.IO.File]::ReadAllText($konamiPath)
$speciesBlock = Match-Value $konami '<p class="species">(.*?)</p>'
$konamiCard = [ordered]@{
    cid = 4007
    name = Match-Value $konami '<div class="sp cardname">\s*<h1>\s*([^<]+)'
    attribute = Match-Value $konami 'attribute_icon_[^\"]+\.png" alt="([^\"]+)"'
    level = [int](Match-Value $konami '<span class="item_box_value">\s*Level\s+(\d+)')
    atk = [int](Match-Value $konami '<span class="item_box_title">\s*ATK\s*</span>\s*<span class="item_box_value">\s*(\d+)')
    def = [int](Match-Value $konami '<span class="item_box_title">\s*DEF\s*</span>\s*<span class="item_box_value">\s*(\d+)')
    species_display = $speciesBlock
    description_meta = Match-Value $konami '<meta name="description" content="([^\"]+)"'
    source_url = "https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=4007&request_locale=en"
}
Write-Json (Join-Path $root "konami/card_cid_4007.parsed.json") $konamiCard

# YGOPRODeck curated tournament deck page.
$ygoproPath = Join-Path $root "ygoprodeck_tournament/deck_721844.html"
$ygoproHtml = [System.IO.File]::ReadAllText($ygoproPath)
$deck = Get-Content (Join-Path $root "ygoprodeck_tournament/deck_721844.parsed.json") -Raw -Encoding utf8 | ConvertFrom-Json
$ygoproDeck = [ordered]@{
    deck_id = [int64]$deck.deck_id
    deck_name = Match-Value $ygoproHtml '<h1[^>]*>(.*?)</h1>'
    category = Match-Value $ygoproHtml 'Category:\s*([^<]+)</p>'
    creator = Match-Value $ygoproHtml 'Creator:\s*([^<]+)</p>'
    tournament = Match-Value $ygoproHtml 'Tournament:\s*([^<]+)</p>'
    placement = Match-Value $ygoproHtml 'Placement:\s*([^<]+)</p>'
    main = @($deck.main)
    extra = @($deck.extra)
    side = @($deck.side)
    source_url = $deck.source_url
}
Write-Json (Join-Path $root "ygoprodeck_tournament/deck_721844.parsed.json") $ygoproDeck

# KONAMI Neuron deck page. Cards are keyed by KONAMI cid, not passcode.
$neuronPath = Join-Path $root "neuron_deck/wcq_spanish_winner_2026.html"
$neuron = [System.IO.File]::ReadAllText($neuronPath)
function Parse-NeuronTable([string]$TableId, [string]$Zone) {
    $tablePattern = '(?s)<table id="{0}".*?</table>' -f [regex]::Escape($TableId)
    $table = [regex]::Match($neuron, $tablePattern)
    $rows = [System.Collections.Generic.List[object]]::new()
    if (-not $table.Success) { return $rows }
    $pattern = '(?s)<tr[^>]*>.*?<td class="card_name">.*?<span>(.*?)</span>.*?cid=(\d+).*?<td class="num">\s*<span>\s*(\d+)\s*</span>'
    foreach ($match in [regex]::Matches($table.Value, $pattern)) {
        $rows.Add([ordered]@{
            zone = $Zone
            cid = [int64]$match.Groups[2].Value
            name = Decode $match.Groups[1].Value
            quantity = [int]$match.Groups[3].Value
        })
    }
    return $rows
}
$mainCards = @()
$mainCards += Parse-NeuronTable "monster_list" "main"
$mainCards += Parse-NeuronTable "spell_list" "main"
$mainCards += Parse-NeuronTable "trap_list" "main"
$extraCards = @(Parse-NeuronTable "extra_list" "extra")
$sideCards = @(Parse-NeuronTable "side_list" "side")
$neuronDeck = [ordered]@{
    deck_key = [ordered]@{cgid = "3902370b33a337ad5c336bb5ca25da0e"; dno = 24}
    title = Match-Value $neuron '<meta name="keywords" content="([^,]+),'
    deck_type = Match-Value $neuron '<span>Deck Type</span>.*?<dd[^>]*>.*?<span>(.*?)</span>'
    playstyle = Match-Value $neuron '<span>Deck Playstyle</span>.*?<dd[^>]*>.*?<span>(.*?)</span>'
    registered_category = Match-Value $neuron '<span>Registered Category</span>.*?<dd[^>]*>(.*?)</dd>'
    comment = Match-Value $neuron '<span class="biko">(.*?)</span>'
    totals = [ordered]@{
        main = [int](Match-Value $neuron 'Total in Main Deck</h4>\s*<span>(\d+)')
        extra = [int](Match-Value $neuron 'Total in Extra Deck</h4>\s*<span>(\d+)')
        side = [int](Match-Value $neuron 'Total in Side Deck</h4>\s*<span>(\d+)')
    }
    main = $mainCards
    extra = $extraCards
    side = $sideCards
    source_url = "https://www.db.yugioh-card.com/yugiohdb/member_deck.action?cgid=3902370b33a337ad5c336bb5ca25da0e&dno=24&request_locale=en"
}
Write-Json (Join-Path $root "neuron_deck/wcq_spanish_winner_2026.parsed.json") $neuronDeck

# Road of the King editorial metagame aggregate.
$rotkPath = Join-Path $root "road_of_the_king/ocg_2026_04_metagame.html"
$rotk = [System.IO.File]::ReadAllText($rotkPath)
$breakdown = [System.Collections.Generic.List[object]]::new()
$breakdownBlock = [regex]::Match($rotk, '(?s)Metagame Breakdown</h2>.*?<ul>(.*?)</ul>')
if ($breakdownBlock.Success) {
    foreach ($item in [regex]::Matches($breakdownBlock.Groups[1].Value, '<li>(.*?)</li>')) {
        $text = Decode $item.Groups[1].Value
        if ($text -match '^(\d+)\s+([^\(]+?)(?:\s+\((.*)\))?$') {
            $breakdown.Add([ordered]@{count = [int]$Matches[1]; archetype = $Matches[2].Trim(); variants_text = $Matches[3]})
        }
    }
}
$rotkSample = [ordered]@{
    post_id = 53999
    title = Match-Value $rotk '<h1 class="page-title">(.*?)</h1>'
    published_at = Match-Value $rotk '<time[^>]*datetime="([^"]+)"'
    environment = "OCG 2026.04"
    period_start = "2026-04-01"
    period_end = "2026-06-30"
    top_placing_decks = 1084
    tournaments = 185
    regions = @("Japan", "China Mainland", "Hong Kong", "Indonesia", "Malaysia", "Philippines", "Singapore", "Taiwan", "Thailand", "South Korea", "Vietnam")
    breakdown = $breakdown
    source_url = "https://roadoftheking.com/ocg-2026-04-metagame/"
}
Write-Json (Join-Path $root "road_of_the_king/ocg_2026_04_metagame.parsed.json") $rotkSample

# Official event page.
$eventPath = Join-Path $root "konami_event/ycs_dortmund_2026.html"
$eventHtml = [System.IO.File]::ReadAllText($eventPath)
$eventSample = [ordered]@{
    event_name = Match-Value $eventHtml '<h1[^>]*>\s*([^<]*Dortmund 2026[^<]*)</h1>'
    event_date_display = Match-Value $eventHtml '<div class="font-semibold text-xs mb-0 mt-2">\s*Event Date:&nbsp;\s*(.*?)</div>'
    city = "Dortmund"
    country = "Germany"
    event_type = "YCS"
    coverage_anchor = "coverage"
    source_url = "https://www.yugioh-card.com/eu/event/300th-yu-gi-oh-championship-series-dortmund-2026/"
}
Write-Json (Join-Path $root "konami_event/ycs_dortmund_2026.parsed.json") $eventSample

Write-Host "Derived structured samples from four HTML sources."
