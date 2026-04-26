#Requires -Version 5.1
<#
.SYNOPSIS
  Repeatable 5–10 minute demo: chat → pending approval → approve → job → delivery → audit.

.DESCRIPTION
  No product logic—calls the existing API only. Requires the API and worker to be running.
  - API:  uvicorn app.main:app --host 127.0.0.1 --port <port>
  - Worker: python -m workers.runner

  Set OPERATOR_API_KEY in the environment if your server uses it (or pass -OperatorKey).

.EXAMPLE
  .\scripts\demo_gmail_control_plane.ps1 -ThreadId "FMfcgzQgLXpfTSwvwXbQZbkgvVSJdRXv" -BaseUrl "http://127.0.0.1:8010"

.EXAMPLE
  $env:OPERATOR_API_KEY = "your-key"
  .\scripts\demo_gmail_control_plane.ps1 -ThreadId "abc123" -Message "Custom send email on thread=abc123: ..."
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "Gmail thread id (use thread= in the built-in message)")]
    [string] $ThreadId,

    [string] $BaseUrl = "http://127.0.0.1:8000",

    [string] $OperatorKey = $env:OPERATOR_API_KEY,

    [string] $Message = $null,

    [string] $SessionId = "demo-gmail-$(Get-Date -Format 'yyyyMMdd-HHmmss')",

    [string] $Actor = "operator",

    [int] $ChatJobWaitSeconds = 90,

    [int] $ApprovalWaitSeconds = 90,

    [int] $SendJobWaitSeconds = 180
)

$ErrorActionPreference = "Stop"

if (-not $Message) {
    $Message = "Send email on thread=$($ThreadId): thank them for reaching out, confirm I received their message, and ask for two 30-minute windows this week for a call. Keep it concise and professional."
}

function Get-OpHeaders {
    $h = @{}
    if ($OperatorKey) {
        $h["X-Operator-Key"] = $OperatorKey
    }
    return $h
}

function Write-Step {
    param([string] $Text)
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Get-PendingApprovalForChatJob {
    <#
      Resolves the approval created for this /chat run (source_job_id == chat job id).
      Does not use list order alone; avoids approving an unrelated older pending row.
    #>
    param([string] $SourceJobId, [int] $MaxSeconds)
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        $r = Invoke-RestMethod -Uri "$BaseUrl/approvals?status=pending&limit=50" -Method Get -Headers (Get-OpHeaders)
        if ($r.items) {
            foreach ($item in $r.items) {
                $d = Invoke-RestMethod -Uri "$BaseUrl/approvals/$($item.id)" -Method Get -Headers (Get-OpHeaders)
                if ($d.source_job_id -eq $SourceJobId) {
                    return $d
                }
            }
        }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Wait-JobTerminal {
    param([string] $JobId, [int] $MaxSeconds)
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        $j = Invoke-RestMethod -Uri "$BaseUrl/jobs/$JobId" -Method Get -Headers (Get-OpHeaders)
        if ($j.status -in @("succeeded", "failed")) {
            return $j
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

# --- 0) Health
Write-Step "0. Health"
try {
    $null = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    Write-Host "OK: $BaseUrl/health" -ForegroundColor Green
} catch {
    Write-Host "FAIL: Is uvicorn running? $BaseUrl" -ForegroundColor Red
    throw
}

# --- 1) Chat (no operator key)
Write-Step "1. POST /chat (queues chat.orchestrate; worker must be running)"
$chatBody = @{
    session_id = $SessionId
    message    = $Message
    max_steps  = 8
} | ConvertTo-Json
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat" -Method Post -Body $chatBody -ContentType "application/json; charset=utf-8"
$chatJobId = $chat.job_id
Write-Host "Chat job_id: $chatJobId" -ForegroundColor Green

# --- 1b) Wait for chat.orchestrate to finish (worker must run)
Write-Step "1b. GET /jobs/{chat_job_id} (wait for chat.orchestrate to complete)"
$orch = Wait-JobTerminal -JobId $chatJobId -MaxSeconds $ChatJobWaitSeconds
if (-not $orch) {
    Write-Host "Timeout waiting for chat.orchestrate job. Is the worker running?" -ForegroundColor Red
    exit 1
}
if ($orch.status -ne "succeeded") {
    Write-Host "chat.orchestrate failed: status=$($orch.status) last_error=$($orch.last_error)" -ForegroundColor Red
    $orch | ConvertTo-Json -Depth 6 | Write-Host
    exit 1
}
Write-Host "Chat orchestration succeeded." -ForegroundColor Green

# --- 2) Pending approval for *this* chat only (source_job_id match)
Write-Step "2. GET /approvals?status=pending (find row where source_job_id = this chat job, up to $ApprovalWaitSeconds s)"
$detailBefore = Get-PendingApprovalForChatJob -SourceJobId $chatJobId -MaxSeconds $ApprovalWaitSeconds
if (-not $detailBefore) {
    Write-Host "No pending approval linked to chat job $chatJobId. Check policy (need outbound send) and worker logs." -ForegroundColor Red
    exit 1
}
$approvalId = $detailBefore.id
Write-Host "Pending approval_id (for this /chat only): $approvalId" -ForegroundColor Green

Write-Step "2b. Approval detail (control point: payload should include gated-send context when live)"
$detailBefore | ConvertTo-Json -Depth 6 | Write-Host

# --- 3) Approve
Write-Step "3. POST /approvals/{id}/approve (human-in-the-loop)"
$approveBody = @{
    actor = $Actor
    note  = "demo approved send"
} | ConvertTo-Json
$decision = Invoke-RestMethod -Uri "$BaseUrl/approvals/$approvalId/approve" -Method Post -Body $approveBody -ContentType "application/json; charset=utf-8" -Headers (Get-OpHeaders)
$executionJobId = $decision.execution_job_id
$decision | ConvertTo-Json -Depth 6 | Write-Host
if (-not $executionJobId) {
    Write-Host "WARNING: execution_job_id is null - approval may lack gmail_draft_id (wrong policy path or failed draft). See GET /approvals above." -ForegroundColor Yellow
    exit 1
}
Write-Host "execution_job_id: $executionJobId" -ForegroundColor Green

# --- 4) Wait for send job
Write-Step "4. GET /jobs/{execution_job_id} (wait until terminal status)"
$sendJob = Wait-JobTerminal -JobId $executionJobId -MaxSeconds $SendJobWaitSeconds
if (-not $sendJob) {
    Write-Host "Timeout waiting for email.send_approved job to finish." -ForegroundColor Red
    exit 1
}
$sendJob | ConvertTo-Json -Depth 8 | Write-Host
if ($sendJob.status -ne "succeeded") {
    Write-Host "Send job did not succeed: status=$($sendJob.status) last_error=$($sendJob.last_error)" -ForegroundColor Red
    exit 1
}

# --- 5) Delivery
Write-Step "5. GET /email/deliveries/by-job/{execution_job_id} (outcome)"
try {
    $delivery = Invoke-RestMethod -Uri "$BaseUrl/email/deliveries/by-job/$executionJobId" -Method Get -Headers (Get-OpHeaders)
    $delivery | ConvertTo-Json -Depth 6 | Write-Host
} catch {
    Write-Host "No delivery row (or API error). Check message above." -ForegroundColor Yellow
}

# --- 6) Audit
Write-Step "6. GET /audit?limit=100 (trace)"
$audit = Invoke-RestMethod -Uri "$BaseUrl/audit?limit=100" -Method Get -Headers (Get-OpHeaders)
$audit.items | ForEach-Object {
    [PSCustomObject]@{
        action   = $_.action
        resource = "$($_.resource_type)/$($_.resource_id)"
        created  = $_.created_at
    }
} | Format-Table -AutoSize

Write-Host ""
Write-Host "Done. Look for: approval.created, approval.approved, email.send_approved.enqueued, email.send_approved.succeeded" -ForegroundColor Green
Write-Host "Chat (orchestrate) job: $chatJobId | Send job: $executionJobId" -ForegroundColor DarkGray
