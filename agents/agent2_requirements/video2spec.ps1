<#
video2spec.ps1 - Stages 1-4 of the Video2Spec pipeline (Windows / PowerShell port).

Usage:
    .\scripts\video2spec.ps1 -Video <video> -Out <output_dir> -Slug <slug> [-Model base]

Produces:
    <out>\<slug>.audio.wav
    <out>\frames\f_###.jpg
    <out>\contact_#.jpg          (AGENT must view these)
    <out>\<slug>.transcript_raw.txt

Mirrors scripts/video2spec.sh but uses the tools as named on Windows:
    ffmpeg / ffprobe (winget Gyan.FFmpeg), 'magick montage' (ImageMagick 7),
    and faster-whisper (scripts/transcribe_whisper.py) for Stage 4 instead of
    the bundled-offline PocketSphinx path. Stages 5-6 (HD capture + SRS authoring)
    are done by the agent after viewing the contact sheets.
#>
param(
    [Parameter(Mandatory = $true)][string]$Video,
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(Mandatory = $true)][string]$Slug,
    [string]$Model = "small",
    [string]$Python = ""
)

# Resolve a usable Python interpreter if one wasn't passed explicitly.
if (-not $Python) {
    $cand = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "python", "py"
    )
    foreach ($c in $cand) {
        $resolved = $null
        if ($c -like "*\*") {
            if (Test-Path $c) { $resolved = $c }
        } else {
            $resolved = (Get-Command $c -ErrorAction SilentlyContinue).Source
        }
        if ($resolved) { $Python = $resolved; break }
    }
    if (-not $Python) { throw "No Python interpreter found on PATH. Install Python 3 (https://python.org) and retry." }
}

$ErrorActionPreference = "Stop"
# Ensure ffmpeg / magick (installed per-user by winget) are on PATH for this process.
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + `
            [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $Video)) { throw "Video not found: $Video" }
New-Item -ItemType Directory -Force -Path "$Out\frames", "$Out\hd", "$Out\shots" | Out-Null

Write-Host "==> Stage 1: Probe"
$dur = (& ffprobe -v quiet -show_entries format=duration -of csv=p=0 $Video).Trim()
$durInt = [int][double]$dur
$res = (& ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height -of csv=p=0 $Video).Trim()
Write-Host ("    duration={0}s  resolution={1}" -f $durInt, $res)

if     ($durInt -le 300)  { $int = 8 }
elseif ($durInt -le 1200) { $int = 20 }
else                      { $int = 25 }
Write-Host ("    frame interval = {0}s" -f $int)

Write-Host "==> Stage 2: Extract audio (mono 16kHz)"
& ffmpeg -loglevel error -i $Video -ar 16000 -ac 1 "$Out\$Slug.audio.wav" -y

Write-Host "==> Stage 3: Survey frames + contact sheets"
& ffmpeg -loglevel error -i $Video -vf "fps=1/$int,scale=800:-1" -q:v 5 "$Out\frames\f_%03d.jpg" -y
$frames = @(Get-ChildItem "$Out\frames\f_*.jpg" | Sort-Object Name)
Write-Host ("    extracted {0} frames" -f $frames.Count)

# Contact sheets in batches of 30 (5x6 tiles), via ImageMagick 7's 'magick montage'.
$batch = 1
for ($i = 0; $i -lt $frames.Count; $i += 30) {
    $slice = $frames[$i..([Math]::Min($i + 29, $frames.Count - 1))].FullName
    & magick montage $slice -tile 5x6 -geometry "260x+2+2" -title "$Slug contact $batch" "$Out\contact_$batch.jpg"
    $batch++
}
Write-Host ("    built {0} contact sheet(s) - AGENT MUST view these" -f ($batch - 1))

Write-Host ("==> Stage 4: Transcribe (faster-whisper, model={0})" -f $Model)
$raw = "$Out\$Slug.transcript_raw.txt"
& $Python "$ScriptDir\transcribe_whisper.py" "$Out\$Slug.audio.wav" $Model | Out-File -Encoding utf8 $raw
$words = (Get-Content $raw | Measure-Object -Word).Words
Write-Host ("    transcript words: {0}" -f $words)

Write-Host ""
Write-Host ("==> Stages 1-4 complete for '{0}'." -f $Slug)
Write-Host ("    Audio:          {0}\{1}.audio.wav" -f $Out, $Slug)
Write-Host ("    Frames:         {0}\frames\ ({1})" -f $Out, $frames.Count)
Write-Host ("    Contact sheets: {0}\contact_*.jpg   (AGENT: view these now)" -f $Out)
Write-Host ("    Raw transcript: {0}" -f $raw)
Write-Host ""
Write-Host "NEXT (agent): view contact sheets, grab + read HD frames, then author the"
Write-Host "SRS with build_srs.py (see prompts/srs-authoring.md)."
