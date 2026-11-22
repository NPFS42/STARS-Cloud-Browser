# Small glibc Linux base. Alpine/musl is not supported by Chromium/Playwright.
# Resolve and pin python:3.12-slim-bookworm to an approved digest before production.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    STARS_BROWSER_PROFILE=/data/profile \
    STARS_BROWSER_EXECUTABLE=/usr/bin/chromium \
    STARS_BROWSER_CHROMIUM_SANDBOX=1 \
    HOME=/home/browser \
    XDG_CACHE_HOME=/home/browser/.cache \
    XDG_CONFIG_HOME=/data/profile/.config

# Install ONLY distro Chromium and required CA/fonts; Debian supplies native libs.
# --no-install-recommends avoids desktop UI, printing stack, and extra browsers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       chromium ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && groupadd -g 10001 browser \
    && useradd -u 10001 -g browser -d /home/browser -M -s /usr/sbin/nologin browser \
    && install -d -m 0700 -o browser -g browser /home/browser /home/browser/.cache /data /data/profile

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY --chown=browser:browser browser_control /app/browser_control

USER 10001:10001
EXPOSE 8811
CMD ["python", "-m", "uvicorn", "browser_control.service:app", "--host", "0.0.0.0", "--port", "8811", "--no-access-log", "--workers", "1"]
