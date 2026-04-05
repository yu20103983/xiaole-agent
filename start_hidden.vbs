Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "D:\workdir\xiaole-agent\start.cmd" & chr(34), 7, False
' WindowStyle 7 = 最小化且不激活窗口
