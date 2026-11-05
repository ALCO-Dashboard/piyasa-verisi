@echo off
rem Bloomberg koprusunu hafta ici 14:15, 17:45 ve 19:15'te calisacak sekilde Gorev Zamanlayici'ya ekler.
rem Bu dosyayi kopru.py ile ayni klasorden cift tiklayarak bir kez calistirin.
set KLASOR=%~dp0
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 14:15 /TN "ALCO Bloomberg 1415" /TR "cmd /c cd /d \"%KLASOR%\" && py kopru.py"
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:45 /TN "ALCO Bloomberg 1745" /TR "cmd /c cd /d \"%KLASOR%\" && py kopru.py"
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 19:15 /TN "ALCO Bloomberg 1915" /TR "cmd /c cd /d \"%KLASOR%\" && py kopru.py"
echo.
echo Gorevler eklendi. Kontrol icin: Gorev Zamanlayici ^> Gorev Zamanlayici Kitapligi ^> "ALCO Bloomberg ..."
pause
