"""Test business registry for integration testing.

When ENABLE_TEST_BUSINESSES is true, these businesses are checked at Step 0
of the resolution ladder -- before the fact cache or Google Places.

Each test business has a phone number you control (e.g. Google Voice). When
Goon decides to call the business, it calls YOUR phone. You answer as the
restaurant/barber/etc and talk to the AI voice agent. The result texts back
to you on your main phone.

This lets you test the full SMS -> agent -> voice call -> response circuit
without calling real businesses.
"""

from __future__ import annotations

from typing import Any

from app.config.settings import settings

# The registry. Phone numbers should point to a number you control for testing.
TEST_BUSINESSES: dict[str, dict[str, Any]] = {
    "riley's pizza": {
        "name": "Riley's Pizza",
        "phone": settings.test_business_phone,
        "place_id": "test_rileys_pizza",
        "address": "123 Test St, Palo Alto, CA",
        "category": "restaurant",
        "hours": "11am-10pm daily",
        "open_now": True,
        "attributes": {
            "reservable": True,
            "takeout": True,
            "delivery": False,
            "dine_in": True,
        },
        "cached_facts": {
            "hours": "11am-10pm, 7 days a week",
            "menu": "Margherita $14, Pepperoni $16, Sicilian $18, Calzone $15",
        },
    },
    "test barbershop": {
        "name": "Test Barbershop",
        "phone": settings.test_business_phone,
        "place_id": "test_barbershop",
        "address": "456 Test Ave, Palo Alto, CA",
        "category": "barber",
        "hours": "9am-6pm Tue-Sat",
        "open_now": True,
        "attributes": {
            "reservable": True,
        },
        "cached_facts": {
            "hours": "Tuesday through Saturday, 9am to 6pm",
        },
    },
}
