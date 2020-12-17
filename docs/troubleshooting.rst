Troubleshooting
===============

While most errors should be self-explanatory,
this page lists anything that might be puzzling.


Operation on mixed SRID geometries
----------------------------------

The error "Operation on mixed SRID geometries" often indicates
that the database table uses a different SRID
then the ``GeometryField(srid=..)`` configuration in Django assumes.


Only numeric values of degree units are allowed on geographic DWithin queries
-----------------------------------------------------------------------------

The ``DWithin`` / ``Beyond`` can only use unit-based distances when the model
field defines a projected system (e.g. ``PointField(srid=...)``).
Otherwise, only the units of the geometry field are supported (e.g. degrees for WGS84).
If it's possible to work around this limitation, a pull request is welcome.


ProgrammingError / InternalError database exceptions
----------------------------------------------------

When an ``ProgrammingError`` or ``InternalError`` happens, this likely means the database
table schema doesn't match with the Django model. As WFS queries allow clients to
construct complex queries against a table, any discrepancies between the Django model
and database table are bound to show up.

For example, if your database table uses an ``INTEGER`` or ``CHAR(1)`` type,
but declares a ``BooleanField`` in Django this will cause errors.
Django can only construct queries in reliably when the database schema
matches the model definition.

Make sure your Django model migrations have been applied,
or that any imported database tables matches the model definition.


InvalidCursorName cursor "_django_curs_..." does not exist
----------------------------------------------------------

This error happens when the database connection passes through a connection pooler
(e.g. PgBouncer). One workaround is wrapping the view inside ``@transaction.atomic``,
or disabling server-side cursors entirely by adding ``DISABLE_SERVER_SIDE_CURSORS = True`` to the settings.

For details,
see: https://docs.djangoproject.com/en/stable/ref/databases/#transaction-pooling-server-side-cursors


Sentry SDK truncates the exceptions for filters
-----------------------------------------------

The Sentry SDK truncates log messages after 512 characters.
This typically truncates the contents of the ``FILTER`` parameter,
as it's XML notation is quite verbose.
Add the following to your settings file to see the complete message:

.. code-block:: python

    import sentry_sdk.utils

    sentry_sdk.utils.MAX_STRING_LENGTH = 2048  # for WFS FILTER exceptions
