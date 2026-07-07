param(
  [string]$Model = "gpt-5.5",
  [string]$PaperGlob = "papers\*.md"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PromptTemplate = Get-Content -LiteralPath (Join-Path $Root "prompts\analyze_paper.md") -Raw

Get-ChildItem -LiteralPath (Join-Path $Root "papers") -Filter *.md | ForEach-Object {
  $note = $_.FullName
  $content = Get-Content -LiteralPath $note -Raw
  if ($content -match "Status:\s*analyzed") { return }
  if ($content -notmatch "Source PDF:\s*`([^`]+)`") { return }
  $pdf = Join-Path $Root $Matches[1]
  $prompt = $PromptTemplate.Replace("{paper_path}", $pdf) + "`n`n请把最终分析保存回这个笔记文件：$note"
  Write-Host "Analyzing $($_.Name)"
  codex exec --skip-git-repo-check --cd $Root -m $Model $prompt
}
