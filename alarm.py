import time, subprocess
time.sleep(60)
subprocess.run(['powershell', '-Command', '[console]::beep(1000,500);[console]::beep(1000,500);[console]::beep(1000,500);[console]::beep(1200,800)'])
