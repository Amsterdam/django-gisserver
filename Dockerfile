FROM python:3.13-bookworm
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# Install system packages for GeoDjango and our dependencies
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
       libgdal32 \
       libpq-dev \
       cargo \
       make \
       postgresql-client

# Install dependencies first (so layer is cached for fast rebuilds)
# Need to create some stubs for setup.py to run.
WORKDIR /host/
COPY setup.py ./
RUN mkdir gisserver \
 && touch README.md \
 && echo '__version__ = "0.1.dev0"' > gisserver/__init__.py \
 && pip wheel --no-cache-dir --wheel-dir=/wheelhouse/ .[tests] \
 && rm -vf /wheelhouse/django_gisserver* \
 && pip install --no-cache-dir /wheelhouse/* \
 && rm -rf /wheelhouse/ \
 && curl -o /tmp/provinces.geojson 'https://cartomap.github.io/nl/wgs84/provincie_2025.geojson'

# Install app, allow to be overwritten with a volume.
VOLUME /code/
EXPOSE 8000
COPY . /code/
ENV PYTHONPATH=/code/
CMD ["/code/example/manage.py", "runserver", "0.0.0.0:8000"]
