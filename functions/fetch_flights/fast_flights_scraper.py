from datetime import datetime, timedelta
from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights
from fast_flights.integrations.base import FetchIntegration
from primp import Client


class ConsentAwareFetchIntegration(FetchIntegration):
    def fetch_html(self, q) -> str:
        return Client(impersonate="chrome_145").get(
            "https://www.google.com/travel/flights/search",
            params=q.params(),
            headers={"cookie": "SOCS=CAESEwgDEgk2ODEwNTc2NjIaAmVuIAEaBgiA_LyaBg"},
        ).text


def generate_flexible_date_pairs(
    start_date: str, trip_length: int, flexibility_window: int = 0
) -> list[tuple[str, str]]:
    """Generates (outbound_date, return_date) pairs symmetrically around start_date and trip_length."""
    base_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    pairs: list[tuple[str, str]] = []

    for out_offset in range(-flexibility_window, flexibility_window + 1):
        outbound_dt = base_date + timedelta(days=out_offset)
        for len_offset in range(-flexibility_window, flexibility_window + 1):
            current_length = trip_length + len_offset
            if current_length < 1:
                continue
            return_dt = outbound_dt + timedelta(days=current_length)
            pairs.append((outbound_dt.strftime("%Y-%m-%d"), return_dt.strftime("%Y-%m-%d")))

    return pairs


def _combine_flight_pair(outbound_flight, return_flight) -> dict:
    """Combines the outbound and matching return Flights objects into a single dictionary."""
    out_leg = outbound_flight.flights[0]
    ret_leg = return_flight.flights[0]

    out_y, out_m, out_d = out_leg.departure.date
    out_hr, out_min = out_leg.departure.time
    ret_y, ret_m, ret_d = ret_leg.departure.date
    ret_hr, ret_min = ret_leg.departure.time

    return {
        "source": "Google Flights",
        "round_trip_price": outbound_flight.price,
        "from_airport": out_leg.from_airport.code,
        "to_airport": out_leg.to_airport.code,
        "outbound_airline": ", ".join(outbound_flight.airlines),
        "outbound_date": f"{out_y:04d}-{out_m:02d}-{out_d:02d}",
        "outbound_departure_time": f"{out_hr:02d}:{out_min:02d}",
        "outbound_duration": out_leg.duration,
        "return_date": f"{ret_y:04d}-{ret_m:02d}-{ret_d:02d}",
        "return_departure_time": f"{ret_hr:02d}:{ret_min:02d}",
        "return_duration": ret_leg.duration,
    }


def fetch_flights_for_date_pairs(
    date_pairs: list[tuple[str, str]],
    origin: str = "BRU",
    destination: str = "YUL",
    seat: str = "economy",
    currency: str = "EUR",
    adults: int = 1,
    max_stops: int = 0,
) -> list[dict]:
    """Queries Google Flights for each date pair and returns the cheapest combined round-trip dictionary."""
    integration = ConsentAwareFetchIntegration()
    combined_results: list[dict] = []
    return_cache: dict[str, list] = {}

    for outbound_date, return_date in date_pairs:
        # 1. Fetch round-trip outbound options (includes bundled round-trip price)
        rt_query = create_query(
            flights=[
                FlightQuery(date=outbound_date, from_airport=origin, to_airport=destination, max_stops=max_stops),
                FlightQuery(date=return_date, from_airport=destination, to_airport=origin, max_stops=max_stops),
            ],
            trip="round-trip",
            seat=seat,
            currency=currency,
            max_stops=max_stops,
            passengers=Passengers(adults=adults),
        )
        try:
            rt_flights = [f for f in get_flights(rt_query, integration=integration) if f.price is not None]
        except FlightsNotFound:
            rt_flights = []

        if not rt_flights:
            continue

        # 2. Fetch return leg options (cached per unique return_date)
        if return_date not in return_cache:
            ret_query = create_query(
                flights=[
                    FlightQuery(date=return_date, from_airport=destination, to_airport=origin, max_stops=max_stops),
                ],
                trip="one-way",
                seat=seat,
                currency=currency,
                max_stops=max_stops,
                passengers=Passengers(adults=adults),
            )
            try:
                return_cache[return_date] = list(get_flights(ret_query, integration=integration))
            except FlightsNotFound:
                return_cache[return_date] = []

        cheapest_outbound = min(rt_flights, key=lambda f: f.price)
        matching_returns = [
            f for f in return_cache[return_date] if f.airlines == cheapest_outbound.airlines
        ]
        if not matching_returns:
            continue

        combined_results.append(_combine_flight_pair(cheapest_outbound, matching_returns[0]))

    return combined_results


if __name__ == "__main__":
    date_pairs = generate_flexible_date_pairs(
        start_date="2027-06-01",
        trip_length=24,
        flexibility_window=1,
    )
    results = fetch_flights_for_date_pairs(
        date_pairs=date_pairs,
        origin="BRU",
        destination="YUL",
    )
    print(results)
