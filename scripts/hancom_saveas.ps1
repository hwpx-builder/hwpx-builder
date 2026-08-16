# Drive the locally installed Hancom Office via COM: report its version and
# optionally Open a document and SaveAs. Called by hwpxkit.hwp_export -- not
# meant to be run by hand.
#
# With no -Source, only the version is reported (never opens a document --
# opening an HWPX on Hangul 2010 parses the ZIP as text and can take minutes,
# which is why capability detection must not open anything).
#
# Writes a UTF-8 JSON result file ({version, opened, saved, error}) to
# -OutJson instead of stdout, because PowerShell 5.1 stdout re-encodes Korean
# text through the console codepage.
param(
    [string] $Source = "",
    [string] $Dest = "",
    [string] $Format = "HWP",
    [Parameter(Mandatory = $true)][string] $OutJson
)

$ErrorActionPreference = "Stop"
$version = ""
$opened = $false
$saved = $false
$err = $null
$hwp = $null
try {
    $hwp = New-Object -ComObject "HWPFrame.HwpObject"
    # Suppress the file-path security prompt where the module is registered;
    # opening from a staged temp copy (the caller's job) covers the rest.
    try { $null = $hwp.RegisterModule("FilePathCheckerModule", "FilePathCheckerModuleExample") } catch {}
    try { $version = [string]$hwp.Version } catch {}
    if ($Source) {
        # This COM interface has no 1-arg overload: Open(path, format, arg).
        # Empty format lets Hancom infer from the extension (.hwpx/.html/.hwp).
        $opened = [bool]$hwp.Open($Source, "", "")
        if ($opened -and $Dest) {
            $saved = [bool]$hwp.SaveAs($Dest, $Format, "")
        }
    }
} catch {
    $err = $_.Exception.Message
} finally {
    if ($null -ne $hwp) {
        try { $hwp.Clear(1) | Out-Null } catch {}
        try { $hwp.Quit() | Out-Null } catch {}
        try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
    }
}
@{ version = $version; opened = $opened; saved = $saved; error = $err } |
    ConvertTo-Json -Compress |
    Out-File -FilePath $OutJson -Encoding utf8
