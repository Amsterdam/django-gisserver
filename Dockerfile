FROM ghcr.io/astral-sh/uv:python3.14-trixie

ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# Install system packages for GeoDjango and our dependencies
RUN apt-get update \
      && apt-get install -y --no-install-recommends \
      libgdal36 \
      libproj25 \
      libpq-dev \
      cargo \
      make \
      postgresql-client

# Install dependencies first (so layer is cached for fast rebuilds)
# Need minimal stubs so package metadata can be evaluated.
WORKDIR /host/
COPY pyproject.toml README.md ./
RUN mkdir gisserver \
      && uv sync --group tests \
      && curl -o /tmp/provinces.geojson 'https://cartomap.github.io/nl/wgs84/provincie_2025.geojson'

# Install app, allow to be overwritten with a volume.
VOLUME /code/
EXPOSE 8000
COPY . /code/
ENV PYTHONPATH=/code/
CMD ["/code/example/manage.py", "runserver", "0.0.0.0:8000"]
