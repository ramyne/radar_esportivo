@echo off
rem Atualiza as notícias de todas as categorias (usado pelo Agendador de Tarefas)
cd /d "%~dp0"
call venv\Scripts\activate.bat
python coletar_todas.py >> coleta.log 2>&1