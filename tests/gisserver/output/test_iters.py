import django
import pytest
from django.db.models import Prefetch

from gisserver.output.iters import ChunkedQuerySetIterator, CountingIterator
from tests.test_gisserver.models import City, OpeningHour, Restaurant, RestaurantReview
from tests.utils import get_sql


@pytest.mark.django_db
class TestCountingIterator:
    """Prove that the counting iterator works as expected.
    The counting iterator is used while results are streamed.
    """

    def test_can_count(self):
        """Prove we can count."""
        it = CountingIterator("abcdef")
        assert "".join(it) == "abcdef"
        assert it.number_returned == 6
        assert not it.has_more

    def test_sentinel(self):
        """Prove that checking whether there is more works."""
        it = CountingIterator("abcdef", max_results=4)
        assert "".join(it) == "abcd"
        assert it.number_returned == 4
        assert it.has_more


@pytest.mark.django_db
class TestChunkedQuerySetIterator:
    """Prove that our takeover of prefetch_related() can restore data from caches."""

    @pytest.mark.skipif(django.VERSION >= (5, 2), reason="Django 5.2 gives different SQL output")
    def test_foreign_key(self, city, django_assert_num_queries, caplog):
        """Prove that foreign key data is restored from cache in the next chunk.
        Also tests correct instances are assigned.
        """
        city2 = City.objects.create(name="City2", region="Region2")
        original_objects = Restaurant.objects.bulk_create(
            [
                Restaurant(name="A1-get", city=city),
                Restaurant(name="A2-get", city=city),
                Restaurant(name="B1-cache", city=city),
                Restaurant(name="B2-cache", city=city),
                Restaurant(name="C1-new", city=city2),
                Restaurant(name="C2-new", city=city2),
                Restaurant(name="D-empty", city=None),
            ]
        )
        with django_assert_num_queries(0):
            qs = (
                Restaurant.objects.only("id", "name", "city")
                .prefetch_related(Prefetch("city", queryset=City.objects.only("id", "name")))
                .order_by("name")
            )
            it = ChunkedQuerySetIterator(qs, chunk_size=2)

        with django_assert_num_queries(3) as queries:
            restaurants = list(it)

        # Prove that the data was correctly fetched and restored
        with django_assert_num_queries(0):
            for original, retrieved in zip(original_objects, restaurants):
                if original.city:
                    assert original.city.name == retrieved.city.name
                else:
                    assert retrieved.city is None

        assert caplog.messages == [
            "Perform additional prefetches for 2 objects",
            "Creating cache for prefetches of 'city'",
            "Restoring prefetches for 'city'",
            "Restored all prefetches from cache",  # Bingo!!
            "Restoring prefetches for 'city'",
            "Perform additional prefetches for 2 objects",  # city2
            "Restoring prefetches for 'city'",
            "Restored all prefetches from cache",  # None to restore.
        ]
        sql = get_sql(queries)
        assert sql == [
            (
                "SELECT"
                ' "test_gisserver_restaurant"."id",'
                ' "test_gisserver_restaurant"."name",'
                ' "test_gisserver_restaurant"."city_id" '
                'FROM "test_gisserver_restaurant"'
                ' ORDER BY "test_gisserver_restaurant"."name" ASC'
            ),
            (
                "SELECT"
                ' "test_gisserver_city"."id",'
                ' "test_gisserver_city"."name" '
                'FROM "test_gisserver_city" '
                f'WHERE "test_gisserver_city"."id" IN ({city.id})'
            ),
            (
                "SELECT"
                ' "test_gisserver_city"."id",'
                ' "test_gisserver_city"."name" '
                'FROM "test_gisserver_city" '
                f'WHERE "test_gisserver_city"."id" IN ({city2.id})'
            ),
        ]

    def test_reverse_foreign_key(self, django_assert_num_queries, caplog):
        """Prove that reverse FK fields are properly handled."""
        original_restaurants = Restaurant.objects.bulk_create(
            [Restaurant(name=f"Restaurant {i}") for i in range(5)]
        )
        RestaurantReview.objects.bulk_create(
            [
                RestaurantReview(restaurant=original_restaurants[y], review=f"Yum {y}.{x}")
                for x in range(2)
                for y in range(5)
            ]
        )

        with django_assert_num_queries(0):
            qs = Restaurant.objects.only("id", "name").prefetch_related("reviews").order_by("name")
            it = ChunkedQuerySetIterator(qs, chunk_size=2)

        with django_assert_num_queries(4):  # 1 for main object, 3 prefetch chunks
            restaurants = list(it)

        assert caplog.messages == [
            "Perform additional prefetches for 2 objects",
            "Perform additional prefetches for 2 objects",
            "Perform additional prefetches for 1 objects",
        ]

        # Prove that the data was correctly fetched and restored
        # Compare this with the original results from the ORM.
        plain_django_restaurants = list(
            Restaurant.objects.prefetch_related("reviews").order_by("name")
        )
        with django_assert_num_queries(0):
            for original, retrieved in zip(plain_django_restaurants, restaurants):
                assert repr(original.reviews.all()) == repr(retrieved.reviews.all())

    def test_reverse_m2m(self, restaurant_m2m, caplog, django_assert_num_queries):
        """Prove that reverse M2M are silently passed."""
        with django_assert_num_queries(0):
            qs = OpeningHour.objects.only("id", "weekday").prefetch_related(
                Prefetch("restaurant_set", queryset=Restaurant.objects.only("id", "name"))
            )
            it = ChunkedQuerySetIterator(qs, chunk_size=2)

        with django_assert_num_queries(3) as queries:
            opening_hours = list(it)

        assert caplog.messages == [
            "Perform additional prefetches for 2 objects",
            "Perform additional prefetches for 1 objects",
        ]
        sql = get_sql(queries)
        assert sql == [
            (
                "SELECT"
                ' "test_gisserver_openinghour"."id", "test_gisserver_openinghour"."weekday" '
                'FROM "test_gisserver_openinghour" '
                'ORDER BY "test_gisserver_openinghour"."weekday" ASC'
            ),
            (
                f"SELECT"
                f' ("test_gisserver_restaurant_opening_hours"."openinghour_id") AS "_prefetch_related_val_openinghour_id",'
                f' "test_gisserver_restaurant"."id",'
                f' "test_gisserver_restaurant"."name" '
                f'FROM "test_gisserver_restaurant" '
                f'INNER JOIN "test_gisserver_restaurant_opening_hours"'
                f' ON ("test_gisserver_restaurant"."id" = "test_gisserver_restaurant_opening_hours"."restaurant_id") '
                f'WHERE "test_gisserver_restaurant_opening_hours"."openinghour_id" IN ({opening_hours[0].id}, {opening_hours[1].id}) '
                f'ORDER BY "test_gisserver_restaurant"."id" ASC'
            ),
            (
                f"SELECT"
                f' ("test_gisserver_restaurant_opening_hours"."openinghour_id") AS "_prefetch_related_val_openinghour_id",'
                f' "test_gisserver_restaurant"."id",'
                f' "test_gisserver_restaurant"."name" '
                f'FROM "test_gisserver_restaurant" '
                f'INNER JOIN "test_gisserver_restaurant_opening_hours"'
                f' ON ("test_gisserver_restaurant"."id" = "test_gisserver_restaurant_opening_hours"."restaurant_id") '
                f'WHERE "test_gisserver_restaurant_opening_hours"."openinghour_id" IN ({opening_hours[2].id}) '
                f'ORDER BY "test_gisserver_restaurant"."id" ASC'
            ),
        ]
