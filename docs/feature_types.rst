Feature Type Configuration
==========================

Having completed the :doc:`getting started <quickstart>` page, a server should be running.
The exposed feature types can be configured further.

.. tip::
    WFS uses the term "feature" reference any real-world pointable thing,
    which is typically called an "object instance" in Django terminology.
    Likewise, a "feature type" describes the definition, which Django calls a "model".


Defining the Exposed Fields
---------------------------

By default, only the geometry field is exposed as WFS attribute.
This avoids exposing any privacy sensitive fields.

While ``fields="__all__"`` works for convenience, it's better and more secure
to define the exact field names using the ``FeatureType(..., fields=[...])`` parameter:

.. code-block:: python

    from gisserver.features import FeatureType
    from gisserver.views import WFSView


    class CustomWFSView(WFSView):
        ...

        feature_types = [
            FeatureType(
                Restaurant.objects.all(),
                fields=[
                    "id",
                    "name",
                    "location",
                    "owner_id",
                    "created"
                ],
            ),
        ]


Renaming Fields
~~~~~~~~~~~~~~~

Using the ``model_attribute``, the field name can differ from the actual attribute:

.. code-block:: python

    from gisserver.features import FeatureType, field
    from gisserver.views import WFSView


    class CustomWFSView(WFSView):
        ...

        feature_types = [
            FeatureType(
                Restaurant.objects.all(),
                fields=[
                    "id",
                    "name",
                    field("location", model_attribute="point"),
                    field("owner.id", model_attribute="owner_id"),
                    "created"
                ],
            ),
        ]




Exposing Complex Fields
~~~~~~~~~~~~~~~~~~~~~~~

Foreign key relations can be exposed as "complex fields":

.. code-block:: python

    from gisserver.features import FeatureType, field
    from gisserver.views import WFSView


    class CustomWFSView(WFSView):
        ...

        feature_types = [
            FeatureType(
                Restaurant.objects.all(),
                fields=[
                    "id",
                    "name",
                    "location",
                    field("owner", fields=["id", "name", "phonenumber"])
                    "created"
                ],
            ),
        ]

These fields appear as nested properties in the ``GetFeature`` response.

Exposing Flattened Relations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Since various clients (like QGis) don't support complex types well,
relations can also be flattened by defining dotted-names.
This can be combined with `model_attribute` which allows to access a different field:

.. code-block:: python

    from gisserver.features import FeatureType, field
    from gisserver.views import WFSView


    class CustomWFSView(WFSView):
        ...

        feature_types = [
            FeatureType(
                Restaurant.objects.all(),
                fields=[
                    "id",
                    "name",
                    "location",
                    field("owner.id", model_attribute="owner_id")
                    "owner.name",
                    field("owner.phone", model_attribute="owner.telephone"),
                    "created"
                ],
            ),
        ]

If a dotted-name is found, the :func:`~gisserver.features.field` logic
assumes it's a flattened relation.

In the example above, the ``owner.id`` field is linked to the ``owner_id`` model attribute
so no additional JOIN is needed to filter against ``owner.id``.

Overriding Value Retrieval
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionchanged:: 1.0.4
   The ``xsd_class`` simplifies field overriding, and ``value_from_object()`` is now used.

Deep down, each feature fields are exposed as an ``XsdElement`` that
defines how the WFS-server generates it's type definitions and retrieves the value.
Field values are retrieved using ``XsdElement.get_value()``,
which calls Django's ``field.value_from_object()``.
This logic can be overwritten:

.. code-block:: python

    from gisserver.features import field
    from gisserver.types import XsdElement
    from gisserver.views import WFSView


    class CustomXsdElement(XsdElement):
        def get_value(self, instance):
            return self.source.object_from_image(instance)


    class CustomWFSView(WFSView):
        ...

        feature_types = [
            FeatureType(
                fields=[
                   "id",
                   "name",
                   field("image", xsd_class=CustomXsdElement),
                ]
            )
        ]
