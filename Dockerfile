FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN addgroup --system scheduler && adduser --system --ingroup scheduler scheduler
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER scheduler
ENTRYPOINT ["timetagger-scheduler"]
CMD ["--help"]

