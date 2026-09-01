$ErrorActionPreference = "Stop"
Write-Host "== MizuLauncher Edge Functions Deploy ==" -ForegroundColor Cyan
npx supabase --version
npx supabase login
$projectRef = Read-Host "Wklej Supabase Project Reference ID"
npx supabase link --project-ref $projectRef
$functions = @(
  "mizu-admin-action",
  "mizu-telemetry",
  "mizu-drm-issue",
  "mizu-drm-verify"
)
foreach ($fn in $functions) {
  Write-Host "`nDeploying $fn ..." -ForegroundColor Yellow
  npx supabase functions deploy $fn --debug
}
Write-Host "`nGotowe. Sprawdź Supabase -> Edge Functions." -ForegroundColor Green
