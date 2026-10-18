param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][ValidateSet("pdf", "html")][string]$Format
)
$ErrorActionPreference = "Stop"
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($InputPath, $false, $true, $false)
    if ($Format -eq "pdf") {
        $document.ExportAsFixedFormat($OutputPath, 17)
    } else {
        $document.WebOptions.Encoding = 65001
        $document.SaveAs2($OutputPath, 10)
    }
} finally {
    if ($null -ne $document) {
        $document.Close(0)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $word) {
        $word.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
}
