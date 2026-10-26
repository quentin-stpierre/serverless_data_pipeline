from fast_flights import FlightQuery, Passengers, create_query, get_flights
from fast_flights.integrations.base import FetchIntegration
from primp import Client


class ConsentAwareFetchIntegration(FetchIntegration):
    def fetch_html(self, q) -> str:
        return Client(impersonate="chrome_145").get(
            "https://www.google.com/travel/flights/search",
            params=q.params(),
            headers={"cookie": "SOCS=CAESEwgDEgk2ODEwNTc2NjIaAmVuIAEaBgiA_LyaBg"},
        ).text


integration = ConsentAwareFetchIntegration()

outbound_query = create_query(
    flights=[
        FlightQuery(date="2027-06-01", from_airport="BRU", to_airport="YUL", max_stops=0),
        FlightQuery(date="2027-06-25", from_airport="YUL", to_airport="BRU", max_stops=0),
    ],
    trip="round-trip",
    seat="economy",
    currency="EUR",
    max_stops=0,
    passengers=Passengers(adults=1),
)

return_query = create_query(
    flights=[
        FlightQuery(date="2027-06-25", from_airport="YUL", to_airport="BRU", max_stops=0),
    ],
    trip="one-way",
    seat="economy",
    currency="EUR",
    max_stops=0,
    passengers=Passengers(adults=1),
)


results = {
    "round_trip_outbound": get_flights(outbound_query, integration=integration),
    "return_leg": get_flights(return_query, integration=integration),
}
print(results)
