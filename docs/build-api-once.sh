#!/bin/sh -e
#
# First time creation of the API packages.
# This generates a lot of files, but gives a good starting point.
#

API_MODULES="gisserver"

cd `dirname $0`
DOCS_DIR=`pwd`
API_DIR="$DOCS_DIR/api"
cd ../

# Make sure all split packages are not duplicated in the API:
API_EXCLUDES="gisserver/compat.py gisserver/conf.py gisserver/db.py $(find . \
     -path '*/migrations/*.py' \
  -o -type f -name admin.py \
  -o -type f -name 'urls*.py' \
  -o -path '*/management/__init__.py' -o -path '*/management/commands/__init__py' \
  -o '(' -path './gisserver/operations/*.py' -a ! -name "base.py" ')' \
  -o '(' -path './gisserver/parsers/*/*.py' -a ! -name '__init__.py' ')' \
  -o '(' -path './gisserver/output/*.py' -a ! -name '__init__.py' -a ! -name "utils.py" ')' \
)"

# -- Generate API docs

sphinx-apidoc -o "$API_DIR" --separate --maxdepth=1 -H "API Documentation" "$API_MODULES" $API_EXCLUDES

# Remove needless subtitles
# Using perl, avoid issues with OSX sed differences
cd $DOCS_DIR
perl -i -pe 'BEGIN{undef $/;} s/Subpackages\n-----------/Subpackages:/smg' $API_DIR/*.rst
perl -i -pe 'BEGIN{undef $/;} s/Submodules\n----------/Submodules:/smg' $API_DIR/*.rst


# -- Compile html files

#make -C "$DOCS_DIR" html
