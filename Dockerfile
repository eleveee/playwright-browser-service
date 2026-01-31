FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["bash", "-lc", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

`README.md`
```markdown
# Playwright Browser Service (FastAPI)

--
`Dockerfile`
```Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["bash", "-lc", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

`README.md`
```markdown
# Playwright Browser Service (FastAPI)
