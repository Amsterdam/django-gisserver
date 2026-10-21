.PHONY: help install test retest coverage dist docs format typecheck

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
TEST_DATABASE_URL = postgresql://postgres:insecure@localhost:15432/gisserver_example
DOCKER_TEST_DATABASE_URL = postgresql://postgres:insecure@host.docker.internal:15432/gisserver_example

help:
	@grep -F -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | perl -pe 's/^([\w\-]+):(.+?)##/"  $$1:" . " " x (20 - length($$1))/e' | perl -pe 's/^## ?//'

## Makefile to perform all tasks for development.
##
## Developer install:
##

install:       ## Install the package
	if ! command -v uv >/dev/null 2>&1; \
	then echo "uv not found, installing..." \
	&& curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	uv venv --clear
	uv sync --all-extras
	uv sync --group tests
	uv run pre-commit install

##
## Running tests:
##

test:          ## Run the tests
	DATABASE_URL=$(TEST_DATABASE_URL) GISSERVER_USE_DB_RENDERING=1 uv run pytest -v
	DATABASE_URL=$(TEST_DATABASE_URL) GISSERVER_USE_DB_RENDERING=0 uv run pytest -v

ogctest:       ## Start the OGC teamserver
	@echo "* Start the example app"
	@echo "* Open http://localhost:8081/teamengine/viewSessions.jsp"
	@echo "* Login with ogctest:ogctest"
	@echo "* And test against: http://host.docker.internal:8000/wfs/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities"
	docker run  --rm -p 8081:8080 ogccite/ets-wfs20

docker-test:   ## Run the tests in docker against Linux GIS library versions
	docker build . -t django-gisserver
	docker run --add-host=host.docker.internal:host-gateway -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e DATABASE_URL=$(DOCKER_TEST_DATABASE_URL) -e GISSERVER_USE_DB_RENDERING=1 -e UV_PROJECT_ENVIRONMENT=/tmp/django-gisserver-venv --rm -it django-gisserver uv run pytest -vvs
	docker run --add-host=host.docker.internal:host-gateway -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e DATABASE_URL=$(DOCKER_TEST_DATABASE_URL) -e GISSERVER_USE_DB_RENDERING=0 -e UV_PROJECT_ENVIRONMENT=/tmp/django-gisserver-venv --rm -it django-gisserver uv run pytest -vvs

retest:        ## Rerun the last failed tests.
	DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -vs --lf

coverage:      ## Run the tests with coverage.
	DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest --cov=gisserver --cov-report=term-missing --cov-report=html

##
## Developer tools
##

messages:         ## Update the .po files with the latest translations.
	PYTHONPATH=. django-admin makemessages --settings=tests.settings --ignore="example/*" -a

compilemessages:  ## Compile the .po files into .mo files.
	PYTHONPATH=. django-admin compilemessages --settings=tests.settings

format:           ## Fix code formatting using pre-commit hooks
	uv run pre-commit run -a
