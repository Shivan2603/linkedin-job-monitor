@echo off
cd /d "E:\SivaShankar\jobbot"
echo [%date% %time%] Starting Job Bot Scheduler Run... >> data\scheduler_run.log
"C:\Users\SIVASHANKAR V\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.10_qbz5n2kfra8p0\python.exe" -u bot\main.py 4 >> data\scheduler_run.log 2>&1
echo [%date% %time%] Job Bot Scheduler Run Finished or Stopped. >> data\scheduler_run.log
