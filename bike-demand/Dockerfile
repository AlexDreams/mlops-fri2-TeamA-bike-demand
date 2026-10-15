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
RUN uv sync --locked

COPY README.md ./
COPY reports/week-01-team.md ./reports/week-01-team.md
COPY .github/workflows/ci.yml ./.github/workflows/ci.yml
COPY tests ./tests

CMD ["uv", "run", "--locked", "python", "-m", "bike_demand.train", "--config", "configs/baseline.yaml"]