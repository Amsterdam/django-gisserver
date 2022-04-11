# This is a dockerfile to run the unit tests against the Travis Ubuntu version,
# to allow debugging proj/gdal differences between your local machine and Travis.
FROM ubuntu:focal
ARG POSTGRES_VERSION=13
ARG POSTGIS_VERSION=3
ARG DEBIAN_FRONTEND=noninteractive
ARG PG_CTL=/usr/lib/postgresql/${POSTGRES_VERSION}/bin/pg_ctl

# Allow pg_ctl to work without -D
ENV PGDATA=/var/lib/postgresql/${POSTGRES_VERSION}/main/

# Install PostgreSQL apt repository
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg \
 && echo "deb http://apt.postgresql.org/pub/repos/apt focal-pgdg main" > /etc/apt/sources.list.d/pgdg.list

# No longer using ppa:ubuntugis repo, everything is part of ubuntu:focal
# python3-dev is needed for lru_dict
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
       python3 \
       python3-pip \
       python3-setuptools \
       python3-wheel \
       python3-dev gcc \
       make \
       postgresql-${POSTGRES_VERSION}-postgis-${POSTGIS_VERSION} \
       postgresql-${POSTGRES_VERSION}-postgis-${POSTGIS_VERSION}-scripts \
 && echo "PostGIS is linked to:" \
 && ldd /usr/lib/postgresql/*/lib/postgis-*.so | grep -E '(libproj|libgeos)'

# Install dependencies first (so layer is cached for fast rebuilds)
# Need to create some stubs for setup.py to run.
WORKDIR /host/
COPY setup.py setup.cfg ./
RUN mkdir gisserver \
 && touch README.md \
 && echo '__version__ = "0.1.dev0"' > gisserver/__init__.py \
 && sed -i -e 's/ >= / == /' ./setup.py \
 && pip3 wheel --no-cache-dir --wheel-dir=/wheelhouse/ .[tests] \
 && rm -vf /wheelhouse/django_gisserver* \
 && pip3 install --no-cache-dir /wheelhouse/*

# Install app
COPY . /host/
RUN pip3 install --find-links=/wheelhouse/ -e .[tests]
ENV LANG=C.UTF-8 DATABASE_URL=postgresql://postgres@localhost/django-gisserver

# Make sure Postgres starts on startup
RUN echo   > ${PGDATA}/pg_ident.conf   "" \
 && echo   > ${PGDATA}/postgresql.conf "listen_addresses '127.0.0.1'" \
 && printf > ${PGDATA}/pg_hba.conf     "# host-based-access controls\n\
local  all  all                trust\n\
host   all  all  127.0.0.1/32  trust\n" \
 && printf > /entrypoint.sh "#!/bin/sh\n\
su postgres -c '${PG_CTL} status || ${PG_CTL} start'\n\
exec \"\$@\"\n" \
 && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
