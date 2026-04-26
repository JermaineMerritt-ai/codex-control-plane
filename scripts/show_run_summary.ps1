#Requires -Version 5.1
<#
.SYNOPSIS
  Print a human-readable execution + delivery + audit summary for an existing email.send_approved job.

.EXAMPLE
  .\scripts\show_run_summary.ps1 -ExecutionJobId "babd9be5-87a7-4690-b2bd-438eface6768" -BaseUrl "http://127.0.0.1:8010"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ExecutionJobId,

    [string] $BaseUrl = "http://127.0.0.1:8000",

    [string] $OperatorKey = $env:OPERATOR_API_KEY
)

$ErrorActionPreference = "Stop"

function Get-OpHeaders {
    $h = @{}
    if ($OperatorKey) { $h["X-Operator-Key"] = $OperatorKey }
    return $h
}

$job = Invoke-RestMethod -Uri "$BaseUrl/jobs/$ExecutionJobId" -Method Get -Headers (Get-OpHeaders)
if ($job.type -ne "email.send_approved") {
    Write-Host "Warning: job type is $($job.type), not email.send_approved" -ForegroundColor Yellow
}
$aid = $job.payload.approval_id
if (-not $aid) {
    $body = $job.payload
    if ($body -is [string]) { } else { $aid = $body.approval_id }
}
$approvalId = $aid

$delivery = $null
try {
    $delivery = Invoke-RestMethod -Uri "$BaseUrl/email/deliveries/by-job/$ExecutionJobId" -Method Get -Headers (Get-OpHeaders)
} catch { }

$audit = Invoke-RestMethod -Uri "$BaseUrl/audit?limit=200" -Method Get -Headers (Get-OpHeaders)

Write-Host ""
Write-Host "=========================" -ForegroundColor White
Write-Host "RUN SUMMARY" -ForegroundColor White
Write-Host "=========================" -ForegroundColor White
Write-Host "Execution job: $ExecutionJobId" -ForegroundColor Gray
Write-Host "Status:         $($job.status)" -ForegroundColor $(if ($job.status -eq "succeeded") { "Green" } else { "Yellow" })
if ($approvalId) { Write-Host "Approval id:   $approvalId" -ForegroundColor Gray }
if ($null -ne $delivery) {
    Write-Host "Delivery:      $($delivery.status)  message_id=$($delivery.gmail_message_id)" -ForegroundColor Gray
} else {
    Write-Host "Delivery:      (none)" -ForegroundColor DarkYellow
}
Write-Host ""
Write-Host "AUDIT (filter: approval or this job id)" -ForegroundColor Cyan
$relevant = @()
if ($audit.items) {
    foreach ($ev in $audit.items) {
        if ($ev.resource_id -eq $approvalId -or $ev.resource_id -eq $ExecutionJobId) {
            $relevant += $ev
        }
    }
}
$relevant = $relevant | Sort-Object { $_.created_at }
foreach ($ev in $relevant) {
    Write-Host "  $($ev.action)  $($ev.resource_type)/$($ev.resource_id)" -ForegroundColor Green
}
