param([Parameter(Mandatory)][string[]]$Files,
      [string]$Editor = "C:\Program Files\GIANTS Software\GIANTS_Editor_10.0.14\editor.exe")
# Opens each .i3d in GIANTS Editor, triggers File > Save via WM_COMMAND (no focus/keystrokes), closes the editor.
Add-Type @"
using System;using System.Runtime.InteropServices;using System.Text;
public class GeWin{
[DllImport("user32.dll")]public static extern IntPtr GetMenu(IntPtr h);
[DllImport("user32.dll")]public static extern IntPtr GetSubMenu(IntPtr m,int i);
[DllImport("user32.dll")]public static extern int GetMenuItemCount(IntPtr m);
[DllImport("user32.dll")]public static extern uint GetMenuItemID(IntPtr m,int i);
[DllImport("user32.dll",CharSet=CharSet.Unicode)]public static extern int GetMenuString(IntPtr m,uint i,StringBuilder s,int n,uint f);
[DllImport("user32.dll")]public static extern bool PostMessage(IntPtr h,uint msg,IntPtr w,IntPtr l);}
"@
function Find-MenuId($menu, $label) {
    for ($i = 0; $i -lt [GeWin]::GetMenuItemCount($menu); $i++) {
        $sb = New-Object Text.StringBuilder 256
        [GeWin]::GetMenuString($menu, $i, $sb, 256, 0x400) | Out-Null
        if (($sb.ToString() -split "`t")[0].Replace('&','').Trim() -eq $label) { return [GeWin]::GetMenuItemID($menu, $i) }
    }
    return $null
}
foreach ($file in $Files) {
    $file = (Resolve-Path $file).Path
    $name = Split-Path $file -Leaf
    $before = (Get-Item $file).LastWriteTime
    $p = Start-Process $Editor -ArgumentList "`"$file`"" -PassThru
    $loaded = $false
    for ($i = 0; $i -lt 60; $i++) { Start-Sleep 1; $p.Refresh(); if ($p.HasExited) { break }; if ($p.MainWindowTitle -like "*$name*") { $loaded = $true; break } }
    if (-not $loaded) { "FAIL ${name}: editor did not load the file (title '$($p.MainWindowTitle)')"; continue }
    Start-Sleep 2
    $hwnd = $p.MainWindowHandle
    $menu = [GeWin]::GetMenu($hwnd)
    $saveId = if ($menu -ne [IntPtr]::Zero) { Find-MenuId ([GeWin]::GetSubMenu($menu, 0)) 'Save' }
    if ($null -eq $saveId) { "FAIL ${name}: could not find File > Save menu item"; $p.CloseMainWindow() | Out-Null; continue }
    [GeWin]::PostMessage($hwnd, 0x0111, [IntPtr][int]$saveId, [IntPtr]::Zero) | Out-Null
    $saved = $false
    for ($i = 0; $i -lt 30; $i++) { Start-Sleep 1; if ((Get-Item $file).LastWriteTime -ne $before) { $saved = $true; break } }
    Start-Sleep 2
    $p.CloseMainWindow() | Out-Null
    if (-not $p.WaitForExit(15000)) { "WARN ${name}: editor still open after close request (dialog?) pid $($p.Id)" }
    $shapes = Test-Path "$file.shapes"
    "$(if($saved){'OK  '}else{'FAIL'}) ${name}: saved=$saved shapes=$shapes size=$((Get-Item $file).Length) time=$((Get-Item $file).LastWriteTime)"
}
