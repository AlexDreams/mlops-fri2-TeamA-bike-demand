FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY data ./data
COPY configs ./configs
COPY src ./src
COPY artifacts/model.joblib artifacts/model-metadata.json ./artifacts/
RUN uv sync --locked

COPY README.md ./
COPY reports/week-01-team.md ./reports/week-01-team.md
COPY .github/workflows/ci.yml ./.github/workflows/ci.yml
COPY tests ./tests

ARG BIKE_DEMAND_REVISION=unknown
ENV BIKE_DEMAND_REVISION=${BIKE_DEMAND_REVISION}
EXPOSE 8000
CMD ["uv", "run", "--locked", "uvicorn", "bike_demand.api:app", "--host", "0.0.0.0", "--port", "8000"]