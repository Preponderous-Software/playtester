# playtester's Windows desktop helper (the windows driver; docs/PROFILES.md#drivers).
#
# One JSON request a line in, one JSON reply a line out (over the relay's
# connection): {"op": "...", ...} -> {"ok": true, ...} or {"ok": false, "error": "..."}.
# pt starts it once per session (through the session's relay), so the
# user32 bindings below are compiled once, not on every action.
#
# Coordinates are physical screen pixels (the process is made DPI aware).
# Keys are scancodes sent with SendInput and KEYEVENTF_SCANCODE: games that
# read DirectInput or raw scancodes ignore virtual-key-only events.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# The bootstrap pt starts (windows_driver.BOOTSTRAP) connects back to the
# session's relay over TCP, reads this script from that connection and leaves
# its reader and writer in $stdin and $stdout. (powershell.exe's standard input
# from WSL does not deliver lines promptly, so it is not used.)
$utf8 = New-Object System.Text.UTF8Encoding $false
if (-not $stdin) { $stdin = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), $utf8) }
if (-not $stdout) { $stdout = New-Object System.IO.StreamWriter([Console]::OpenStandardOutput(), $utf8); $stdout.AutoFlush = $true }
Add-Type -AssemblyName System.Drawing

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class PtWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort wVk, wScan; public uint dwFlags, time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Explicit)] struct INPUTUNION { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public INPUTUNION u; }
    public delegate bool EnumProc(IntPtr h, IntPtr l);

    [DllImport("user32.dll")] static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);

    public static List<IntPtr> TopWindows(uint pid) {
        var found = new List<IntPtr>();
        EnumWindows(delegate (IntPtr h, IntPtr l) {
            uint p; GetWindowThreadProcessId(h, out p);
            if ((pid == 0 || p == pid) && IsWindowVisible(h)) found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found;
    }
    public static string Title(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
    public static string ClassOf(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    public static uint PidOf(IntPtr h) { uint p; GetWindowThreadProcessId(h, out p); return p; }
    public static int[] Client(IntPtr h) {
        RECT r; GetClientRect(h, out r); POINT p = new POINT(); ClientToScreen(h, ref p);
        return new int[] { p.X, p.Y, r.Right - r.Left, r.Bottom - r.Top };
    }
    public static bool Focus(IntPtr h) {
        if (IsIconic(h)) ShowWindow(h, 9);  // SW_RESTORE: a minimised game renders nothing
        if (GetForegroundWindow() == h) return true;
        SetForegroundWindow(h);
        if (GetForegroundWindow() == h) return true;
        // Windows refuses SetForegroundWindow from a background process unless
        // it shares input with the foreground thread for a moment.
        uint ignored;
        uint fg = GetWindowThreadProcessId(GetForegroundWindow(), out ignored);
        uint me = GetCurrentThreadId();
        AttachThreadInput(me, fg, true);
        BringWindowToTop(h); SetForegroundWindow(h);
        AttachThreadInput(me, fg, false);
        if (GetForegroundWindow() == h) return true;
        // Measured 2026-11-12: with a console in front, the attach above was not
        // enough for Warband's launcher dialog. A key event of our own makes this
        // process the one with the last input, which Windows lets take the
        // foreground: tap Alt (no menu opens for a bare Alt tap sent this way
        // to a window that is not yet in front), then ask again.
        keybd_event(0x12, 0, 0, UIntPtr.Zero);
        keybd_event(0x12, 0, 2, UIntPtr.Zero);
        uint target = GetWindowThreadProcessId(h, out ignored);
        AttachThreadInput(me, target, true);
        BringWindowToTop(h); SetForegroundWindow(h);
        AttachThreadInput(me, target, false);
        return GetForegroundWindow() == h;
    }
    // Pixels within `tol` (largest channel difference) of colour (r, g, b) become
    // black, everything else white: text drawn in a probe colour, ready for OCR.
    public static void KeepColour(System.Drawing.Bitmap bmp, int r, int g, int b, int tol) {
        var rect = new System.Drawing.Rectangle(0, 0, bmp.Width, bmp.Height);
        var data = bmp.LockBits(rect, System.Drawing.Imaging.ImageLockMode.ReadWrite,
                                 System.Drawing.Imaging.PixelFormat.Format32bppArgb);
        int n = data.Stride * bmp.Height;
        byte[] px = new byte[n];
        Marshal.Copy(data.Scan0, px, 0, n);
        for (int i = 0; i + 3 < n; i += 4) {
            int db = Math.Abs(px[i] - b), dg = Math.Abs(px[i + 1] - g), dr = Math.Abs(px[i + 2] - r);
            byte v = (byte)((Math.Max(dr, Math.Max(dg, db)) <= tol) ? 0 : 255);
            px[i] = v; px[i + 1] = v; px[i + 2] = v; px[i + 3] = 255;
        }
        Marshal.Copy(px, 0, data.Scan0, n);
        bmp.UnlockBits(data);
    }
    static void Send(INPUT i) { SendInput(1, new INPUT[] { i }, Marshal.SizeOf(typeof(INPUT))); }
    public static void Key(int scan, bool extended, bool up) {
        INPUT i = new INPUT(); i.type = 1;
        i.u.ki.wScan = (ushort)scan;
        i.u.ki.dwFlags = 0x0008u | (extended ? 0x0001u : 0u) | (up ? 0x0002u : 0u);
        Send(i);
    }
    public static void Unicode(char c) {
        INPUT i = new INPUT(); i.type = 1; i.u.ki.wScan = c; i.u.ki.dwFlags = 0x0004u; Send(i);
        i.u.ki.dwFlags = 0x0004u | 0x0002u; Send(i);
    }
    public static void Mouse(uint flags, int dx, int dy, int data) {
        INPUT i = new INPUT(); i.type = 0;
        i.u.mi.dx = dx; i.u.mi.dy = dy; i.u.mi.mouseData = (uint)data; i.u.mi.dwFlags = flags;
        Send(i);
    }
}
"@ -ReferencedAssemblies System.Drawing

[void][PtWin]::SetProcessDPIAware()

function Describe([IntPtr]$h) {
    $c = [PtWin]::Client($h)
    $wpid = [PtWin]::PidOf($h)
    $p = Get-Process -Id $wpid -ErrorAction SilentlyContinue
    @{ hwnd = [int64]$h; pid = [int]$wpid; title = [PtWin]::Title($h); class = [PtWin]::ClassOf($h);
       process = $(if ($p) { $p.ProcessName } else { $null });
       client = @($c[0], $c[1], $c[2], $c[3]); minimized = [PtWin]::IsIconic($h);
       foreground = ([PtWin]::GetForegroundWindow() -eq $h) }
}

# What this session may touch, set once by pt start ('policy'): the registry
# values the profile names (HKCU only), the session's folder for screenshots,
# the game's executable, and the processes launched through 'launch'.
$PtPolicy = @{ set = $false; registry = @(); shotDir = ''; exe = ''; pids = New-Object System.Collections.ArrayList }

function KeyAllowed([string]$key) { return $PtPolicy.set -and ($PtPolicy.registry -contains $key) }
function PathAllowed([string]$path) {
    return $PtPolicy.set -and $PtPolicy.shotDir -and ($path -notmatch '\.\.') -and
        $path.StartsWith($PtPolicy.shotDir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}
function Refused([string]$why) { return @{ ok = $false; error = 'refused: ' + $why } }
function QuoteArg([string]$a) {
    # Start-Process joins -ArgumentList with spaces: quote what holds a space or a quote
    if ($a -eq '' -or $a -match '[\s"]') { return '"' + ($a -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' }
    return $a
}

function StartTicks($p) { try { return [string]$p.StartTime.ToUniversalTime().Ticks } catch { return $null } }

function Handle($r) {
    switch ($r.op) {
        'ping' { return @{ ok = $true; pid = $PID } }
        'policy' {
            if ($PtPolicy.set) { return Refused 'the policy is already set' }
            $keys = @($r.registry | Where-Object { ([string]$_).StartsWith('HKCU:\', [StringComparison]::OrdinalIgnoreCase) })
            $PtPolicy.registry = @($keys | ForEach-Object { [string]$_ })
            $PtPolicy.shotDir = [string]$r.shotDir
            $PtPolicy.exe = [string]$r.exe
            $PtPolicy.set = $true
            return @{ ok = $true; registry = $PtPolicy.registry }
        }
        'processes' {
            # every running process named $r.name (no .exe), with its start time
            $list = @(Get-Process -Name $r.name -ErrorAction SilentlyContinue | ForEach-Object {
                @{ pid = $_.Id; startTicks = (StartTicks $_); title = $_.MainWindowTitle; hwnd = [int64]$_.MainWindowHandle } })
            return @{ ok = $true; processes = $list }
        }
        'alive' {
            $p = Get-Process -Id ([int]$r.pid) -ErrorAction SilentlyContinue
            $alive = [bool]$p -and (-not $r.startTicks -or (StartTicks $p) -eq [string]$r.startTicks)
            return @{ ok = $true; alive = $alive }
        }
        'windows' {
            $list = @([PtWin]::TopWindows([uint32]$r.pid) | ForEach-Object { Describe $_ })
            return @{ ok = $true; windows = $list }
        }
        'window' {
            $h = [IntPtr][int64]$r.hwnd
            if (-not [PtWin]::IsWindow($h)) { return @{ ok = $false; error = 'the window is gone' } }
            return @{ ok = $true; window = (Describe $h) }
        }
        'focus' {
            $h = [IntPtr][int64]$r.hwnd
            if (-not [PtWin]::IsWindow($h)) { return @{ ok = $false; error = 'the window is gone' } }
            $wasMin = [PtWin]::IsIconic($h)
            $fg = [PtWin]::Focus($h)
            if ($wasMin) { Start-Sleep -Milliseconds 400 }  # let it draw again before a screenshot
            return @{ ok = $true; foreground = $fg; restored = $wasMin; window = (Describe $h) }
        }
        'key' {
            # keys: [[scan, extended], ...] pressed in order (down) or released in reverse (up)
            $keys = @($r.keys)
            if ($r.up) { [array]::Reverse($keys) }
            foreach ($k in $keys) { [PtWin]::Key([int]$k[0], [bool]$k[1], [bool]$r.up); Start-Sleep -Milliseconds 15 }
            return @{ ok = $true }
        }
        'text' {
            foreach ($ch in ([string]$r.text).ToCharArray()) { [PtWin]::Unicode($ch); Start-Sleep -Milliseconds 40 }
            return @{ ok = $true }
        }
        'strokes' {
            # strokes: [[[scan, extended], ...], ...]: each a combo (Shift_L + a letter, say) pressed in
            # order, held `hold` ms and released in reverse, then `gap` ms before the next (pt type --keys,
            # for text fields that ignore unicode events)
            $strokes = @($r.strokes)
            if ($strokes.Count -lt 1 -or $strokes.Count -gt 500) { return @{ ok = $false; error = 'strokes takes 1 to 500 keys' } }
            $hold = [Math]::Min(500, [Math]::Max(0, [int]$r.hold))
            $gap = [Math]::Min(1000, [Math]::Max(0, [int]$r.gap))
            foreach ($s in $strokes) { if (@($s).Count -lt 1 -or @($s).Count -gt 4) { return @{ ok = $false; error = 'a stroke is 1 to 4 keys' } } }
            foreach ($s in $strokes) {
                $keys = @($s)
                foreach ($k in $keys) { [PtWin]::Key([int]$k[0], [bool]$k[1], $false); Start-Sleep -Milliseconds 10 }
                Start-Sleep -Milliseconds $hold
                [array]::Reverse($keys)
                foreach ($k in $keys) { [PtWin]::Key([int]$k[0], [bool]$k[1], $true); Start-Sleep -Milliseconds 10 }
                Start-Sleep -Milliseconds $gap
            }
            return @{ ok = $true; strokes = $strokes.Count }
        }
        'move' { [void][PtWin]::SetCursorPos([int]$r.x, [int]$r.y); return @{ ok = $true } }
        'look' {
            # moves: [[dx, dy], ...] relative motions (MOUSEEVENTF_MOVE, no MOUSEEVENTF_ABSOLUTE: what a
            # game in mouse look reads), `pause` ms apart, so raw-input games see smooth motion
            $moves = @($r.moves)
            if ($moves.Count -lt 1 -or $moves.Count -gt 1000) { return @{ ok = $false; error = 'look takes 1 to 1000 moves' } }
            $pause = [Math]::Min(100, [Math]::Max(0, [int]$r.pause))
            foreach ($m in $moves) {
                if ([Math]::Abs([int]$m[0]) -gt 10000 -or [Math]::Abs([int]$m[1]) -gt 10000) { return @{ ok = $false; error = 'a look move is at most 10000 pixels' } }
            }
            foreach ($m in $moves) {
                [PtWin]::Mouse(0x0001, [int]$m[0], [int]$m[1], 0)
                if ($pause -gt 0) { Start-Sleep -Milliseconds $pause }
            }
            return @{ ok = $true; moves = $moves.Count }
        }
        'button' {
            # button 1 left, 2 middle, 3 right (X11 numbering, as everywhere in pt)
            $flags = @{ 1 = @(0x0002, 0x0004); 2 = @(0x0020, 0x0040); 3 = @(0x0008, 0x0010) }[[int]$r.button]
            if (-not $flags) { return @{ ok = $false; error = 'no mouse button ' + $r.button } }
            [PtWin]::Mouse($(if ($r.up) { $flags[1] } else { $flags[0] }), 0, 0, 0)
            return @{ ok = $true }
        }
        'wheel' { [PtWin]::Mouse(0x0800, 0, 0, [int]$r.amount); return @{ ok = $true } }
        'cursor' { $p = New-Object PtWin+POINT; [void][PtWin]::GetCursorPos([ref]$p); return @{ ok = $true; x = $p.X; y = $p.Y } }
        'shot' {
            # the screen inside rect [x, y, w, h], scaled to width x height, as PNG at path;
            # with keep = [r, g, b, tolerance], only that colour's pixels (black on white)
            if (-not (PathAllowed ([string]$r.path))) { return Refused 'screenshots go under the session folder' }
            $x, $y, $w, $h = [int]$r.rect[0], [int]$r.rect[1], [int]$r.rect[2], [int]$r.rect[3]
            $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
            $g.Dispose()
            $ow, $oh = [int]$r.width, [int]$r.height
            if ($ow -gt 0 -and $oh -gt 0 -and ($ow -ne $w -or $oh -ne $h)) {
                $small = New-Object System.Drawing.Bitmap $ow, $oh
                $g = [System.Drawing.Graphics]::FromImage($small)
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.DrawImage($bmp, 0, 0, $ow, $oh)
                $g.Dispose(); $bmp.Dispose(); $bmp = $small
            }
            if ($r.keep) { [PtWin]::KeepColour($bmp, [int]$r.keep[0], [int]$r.keep[1], [int]$r.keep[2], [int]$r.keep[3]) }
            $bmp.Save([string]$r.path, [System.Drawing.Imaging.ImageFormat]::Png)
            $size = @($bmp.Width, $bmp.Height)
            $bmp.Dispose()
            return @{ ok = $true; path = $r.path; size = $size }
        }
        'launch' {
            if (-not ($PtPolicy.set -and [string]::Equals([string]$r.path, $PtPolicy.exe, [StringComparison]::OrdinalIgnoreCase))) {
                return Refused 'only the profile''s game may be launched'
            }
            $sp = @{ FilePath = [string]$r.path; PassThru = $true }
            if ($r.cwd) { $sp.WorkingDirectory = [string]$r.cwd }
            if (@($r.args).Count -gt 0) { $sp.ArgumentList = (@($r.args) | ForEach-Object { QuoteArg ([string]$_) }) -join ' ' }
            $p = Start-Process @sp
            [void]$PtPolicy.pids.Add([int]$p.Id)
            return @{ ok = $true; pid = $p.Id; startTicks = (StartTicks $p) }
        }
        'close' {
            # graceful: WM_CLOSE to the main window, as the title bar's close button would
            if (-not ($PtPolicy.pids -contains [int]$r.pid)) { return Refused 'only a game pt launched may be closed' }
            $p = Get-Process -Id ([int]$r.pid) -ErrorAction SilentlyContinue
            if (-not $p) { return @{ ok = $true; sent = $false } }
            return @{ ok = $true; sent = $p.CloseMainWindow() }
        }
        'kill' {
            if (-not ($PtPolicy.pids -contains [int]$r.pid)) { return Refused 'only a game pt launched may be killed' }
            Stop-Process -Id ([int]$r.pid) -Force -ErrorAction SilentlyContinue
            return @{ ok = $true }
        }
        'regget' {
            if (-not (KeyAllowed ([string]$r.key))) { return Refused 'the profile does not name this registry key' }
            $v = Get-ItemProperty -Path ([string]$r.key) -Name ([string]$r.name) -ErrorAction SilentlyContinue
            if ($null -eq $v) { return @{ ok = $true; exists = $false; value = $null } }
            return @{ ok = $true; exists = $true; value = [string]$v.([string]$r.name) }
        }
        'regset' {
            if (-not (KeyAllowed ([string]$r.key))) { return Refused 'the profile does not name this registry key' }
            if (-not (Test-Path ([string]$r.key))) { [void](New-Item -Path ([string]$r.key) -Force) }
            Set-ItemProperty -Path ([string]$r.key) -Name ([string]$r.name) -Value ([string]$r.value)
            return @{ ok = $true }
        }
        'regdel' {
            # removes a value pt created (the key itself stays)
            if (-not (KeyAllowed ([string]$r.key))) { return Refused 'the profile does not name this registry key' }
            Remove-ItemProperty -Path ([string]$r.key) -Name ([string]$r.name) -ErrorAction SilentlyContinue
            return @{ ok = $true }
        }
        'bye' { return @{ ok = $true; bye = $true } }
        default { return @{ ok = $false; error = 'unknown op ' + $r.op } }
    }
}

while ($true) {
    $line = $stdin.ReadLine()
    if ($null -eq $line) { break }
    if (-not $line.Trim()) { continue }
    try {
        $req = $line | ConvertFrom-Json
        $reply = Handle $req
        $reply.op = $req.op
    } catch {
        $reply = @{ ok = $false; error = $_.Exception.Message }
    }
    $stdout.WriteLine(($reply | ConvertTo-Json -Compress -Depth 6))
    if ($reply.bye) { break }
}
