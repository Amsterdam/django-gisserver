.PHONY: help install test retest coverage dist docs format

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

help:
	@grep -F -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | perl -pe 's/^([\w\-]+):(.+?)##/"  $$1:" . " " x (20 - length($$1))/e' | perl -pe 's/^## ?//'

## Makefile to perform all tasks for development.
##
## Developer install:
##

install:       ## Install the package into the current virtualenv
	pip install --require-virtualenv -e .[tests]
	pip install --require-virtualenv pre-commit
	pre-commit install

##
## Running tests:
##

test:          ## Run the tests
	PYTHONPATH=. GISSERVER_USE_DB_RENDERING=1 pytest -vs
	PYTHONPATH=. GISSERVER_USE_DB_RENDERING=0 pytest -vs

ogctest:       ## Start the OGC teamserver
	@echo "* Start the example app"
	@echo "* Open http://localhost:8081/teamengine/viewSessions.jsp"
	@echo "* Login with ogctest:ogctest"
	@echo "* And test against: http://host.docker.internal:8000/wfs/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities"
	docker run  --rm -p 8081:8080 ogccite/ets-wfs20

docker-test:   ## Run the tests in docker against Linux GIS library versions
	docker build . -t django-gisserver
	docker run -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e GISSERVER_USE_DB_RENDERING=1 --rm -it django-gisserver pytest -vvs
	docker run -v $(ROOT_DIR):/host/ -e PYTHONPATH=. -e GISSERVER_USE_DB_RENDERING=0 --rm -it django-gisserver pytest -vvs

retest:        ## Rerun the last failed tests.
	PYTHONPATH=. pytest -vs --lf

coverage:      ## Run the tests with coverage.
	PYTHONPATH=. pytest --cov=gisserver --cov-report=term-missing --cov-report=html

##
## Developer tools
##

messages:         ## Update the .po files with the latest translations.
	PYTHONPATH=. django-admin makemessages --settings=tests.settings --ignore="example/*" -a

compilemessages:  ## Compile the .po files into .mo files.
	PYTHONPATH=. django-admin compilemessages --settings=tests.settings

format:           ## Fix code formatting using pre-commit hooks
	pre-commit run -a

##
## Release packaging:
##

dist: clean       ## Generate the sdist/wheel (can be uploaded with twine)
	python -m build

clean:            ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info/
