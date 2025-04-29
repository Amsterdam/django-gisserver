.PHONY: help install test retest coverage dist docs format

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

help:
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/##//'

install:       ## Install the package into the current virtualenv
	pip install -e .[tests]
	pip install pre-commit
	pre-commit install

test:          ## Run the tests
	PYTHONPATH=. GISSERVER_USE_DB_RENDERING=1 pytest -vs
	PYTHONPATH=. GISSERVER_USE_DB_RENDERING=0 pytest -vs

ogctest:       ## Start the OGC teamserver
	@echo "* Start the example app"
	@echo "* Open http://localhost:8081/teamengine/viewSessions.jsp"
	@echo "* Login with ogctest:ogctest"
	@echo "* And test against: http://host.docker.internal:8000/wfs/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities"
	docker run  --rm -p 8081:8080 ogccite/ets-wfs20

docker-test:   ## Run the tests against Linux GIS library versions
	docker build . -t django-gisserver
	docker run -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e GISSERVER_USE_DB_RENDERING=1 --rm -it django-gisserver pytest -vvs
	docker run -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e GISSERVER_USE_DB_RENDERING=0 --rm -it django-gisserver pytest -vvs

retest:        ## Rerun the last failed tests.
	PYTHONPATH=. pytest -vs --lf

coverage:      ## Run the tests with coverage
	PYTHONPATH=. pytest --cov=gisserver --cov-report=term-missing --cov-report=html

dist:          ## Generate the sdist/wheel (can be uploaded with twine)
	rm -rf build/ dist/
	python -m build

format:        ## Fix code formatting using pre-commit hooks
	pre-commit run -a
