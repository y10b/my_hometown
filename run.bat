@echo off
REM 윈도우 작업 스케줄러에 등록해서 주기 실행 (예: 6시간마다)
REM 작업 스케줄러 > 작업 만들기 > 동작: 프로그램 시작 > 이 .bat 지정
cd /d "%~dp0"
python bot.py --once
