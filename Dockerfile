FROM mcr.microsoft.com/windows/servercore:ltsc2019

# Match the Windows containers used by the existing Compose services.
RUN powershell -NoProfile -Command \
    $ErrorActionPreference = 'Stop'; \
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python-installer.exe'; \
    Start-Process -FilePath '.\python-installer.exe' -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' -Wait; \
    Remove-Item -LiteralPath 'python-installer.exe'

# ONNX Runtime's supported Windows C++ runtime, installed from Microsoft.
RUN powershell -NoProfile -Command \
    $ErrorActionPreference = 'Stop'; \
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'vc_redist.exe'; \
    $install = Start-Process -FilePath '.\vc_redist.exe' -ArgumentList '/install /quiet /norestart' -Wait -PassThru; \
    if ($install.ExitCode -notin @(0, 3010)) { throw 'C++ runtime installation failed' }; \
    Remove-Item -LiteralPath 'vc_redist.exe'

WORKDIR C:/app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m pip install --no-cache-dir piper-tts==1.8.0
RUN python -m pip install --no-cache-dir certifi
COPY scripts/download_piper.py ./scripts/download_piper.py
RUN python scripts/download_piper.py
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .[speech]
RUN python -c "from english_bot.config import Settings; from english_bot.speech import PiperSpeech; audio=PiperSpeech(Settings('test','test','chat','audio',':memory:',frozenset())).synthesise('Hello! Your English voice is ready.'); assert len(audio) > 1000; print('Offline Piper speech check passed')"
RUN powershell -NoProfile -Command "New-Item -ItemType Directory -Force C:\app\data | Out-Null"
CMD ["python", "-m", "english_bot"]
