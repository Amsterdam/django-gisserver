.PHONY: help install test retest coverage dist docs format

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

help:
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/##//'

install:       ## Install the package into the current virtualenv
	pip install -e .[test]
	pip install pre-commit
	pre-commit install

test:          ## Run the tests
	GISSERVER_USE_DB_RENDERING=1 pytest -vs
	GISSERVER_USE_DB_RENDERING=0 pytest -vs

docker-test:   ## Run the tests against Linux GIS library versions
	docker build . -t django-gisserver
	docker run -v $(ROOT_DIT):/host/ -e GISSERVER_USE_DB_RENDERING=1 --rm -it django-gisserver make test
	docker run -v $(ROOT_DIT):/host/ -e GISSERVER_USE_DB_RENDERING=0 --rm -it django-gisserver make test

retest:        ## Rerun the last failed tests.
	pytest -vs --lf

coverage:      ## Run the tests with coverage
	pytest --cov=gisserver --cov-report=term-missing --cov-report=html

dist:          ## Generate the sdist/wheel (can be uploaded with twine)
	rm -rf build/ dist/
	./setup.py sdist bdist_wheel

format:        ## Fix code formatting using pre-commit hooks
	pre-commit run -a
