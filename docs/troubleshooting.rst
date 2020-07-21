Troubleshooting
===============

While most errors should be self-explanatory,
this page lists anything that might be puzzling.

Operation on mixed SRID geometries
----------------------------------

The error "Operation on mixed SRID geometries" often indicates
that the database table uses a different SRID
then the ``GeometryField(srid=..)`` configuration in Django assumes.
