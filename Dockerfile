# This is a dockerfile to run the unit tests against the Travis Ubuntu version,
# to allow debugging proj/gdal differences between your local machine and Travis.
FROM python:3.13-bookworm
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# No longer using ppa:ubuntugis repo, everything is part of ubuntu:focal
# python3-dev is needed for lru_dict
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
       libgdal32 \
       libpq-dev \
       cargo \
       make

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
 && rm -rf /wheelhouse/

# Install app, allow to be overwritten with a volume.
VOLUME /code/
EXPOSE 8000
COPY . /code/
ENV PYTHONPATH=/code/
CMD ["/code/example/manage.py", "runserver", "0.0.0.0:8000"]
