Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\workdir\xiaole-agent"
WshShell.Run "cmd /c start.bat", 1, False
