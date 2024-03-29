import json
import re

from elasticsearch7 import Elasticsearch
from flask import Flask, render_template, request
from pymongo import MongoClient
from bson import json_util

import config
import search_helpers

# Set up Flask, Mongo and Elasticsearch
app = Flask(__name__)

client = MongoClient("mongo")

elastic = Elasticsearch(config.ELASTIC_URL)


# Process elasticsearch hits and return flights records
def process_search(results):
    records = []
    if results["hits"] and results["hits"]["hits"]:
        total = results["hits"]["total"]
        hits = results["hits"]["hits"]
        for hit in hits:
            record = hit["_source"]
            records.append(record)
    return records, total


# Calculate offsets for fetching lists of flights from MongoDB
def get_navigation_offsets(offset1, offset2, increment):
    offsets = {}
    offsets["Previous"] = {
        "top_offset": max(offset2 - increment, 0),
        "bottom_offset": max(offset1 - increment, 0),
    }  # Don't go < 0
    offsets["Next"] = {
        "top_offset": offset2 + increment,
        "bottom_offset": offset1 + increment,
    }
    return offsets


# Strip the existing start and end parameters from the query string
def strip_place(url):
    try:
        p = re.match("(.+)&start=.+&end=.+", url).group(1)
    except AttributeError as e:
        return url
    return p


# Chapter 5 controller: Fetch a flight and display it
@app.route("/on_time_performance")
def on_time_performance():

    carrier = request.args.get("Carrier")
    flight_date = request.args.get("FlightDate")
    flight_num = request.args.get("FlightNum")

    flight = client.agile_data_science.on_time_performance.find_one(
        {"Carrier": carrier, "FlightDate": flight_date, "FlightNum": flight_num}
    )

    return render_template("flight.html", flight=flight)


# Chapter 5 controller: Fetch all flights between cities on a given day and display them
@app.route("/flights/<origin>/<dest>/<flight_date>")
def list_flights(origin, dest, flight_date):

    flights = client.agile_data_science.on_time_performance.find(
        {"Origin": origin, "Dest": dest, "FlightDate": flight_date},
        sort=[
            ("DepTime", 1),
            ("ArrTime", 1),
        ],
    )
    flight_count = flights.count()

    return render_template(
        "flights.html",
        flights=flights,
        flight_date=flight_date,
        flight_count=flight_count,
    )


# Controller: Fetch a flight table
@app.route("/total_flights")
def total_flights():
    total_flights = client.agile_data_science.flights_by_month.find(
        {}, sort=[("Year", 1), ("Month", 1)]
    )
    return render_template("total_flights.html", total_flights=total_flights)


# Serve the chart's data via an asynchronous request (formerly known as 'AJAX')
@app.route("/total_flights.json")
def total_flights_json():
    total_flights = client.agile_data_science.flights_by_month.find(
        {}, sort=[("Year", 1), ("Month", 1)]
    )
    return json_util.dumps(total_flights, ensure_ascii=False)


# Controller: Fetch a flight chart
@app.route("/total_flights_chart")
def total_flights_chart():
    total_flights = client.agile_data_science.flights_by_month.find(
        {}, sort=[("Year", 1), ("Month", 1)]
    )
    return render_template("total_flights_chart.html", total_flights=total_flights)


@app.route("/airplanes")
@app.route("/airplanes/")
def search_airplanes():

    search_config = [
        {"field": "TailNum", "label": "Tail Number"},
        {"field": "Owner", "sort_order": 0},
        {"field": "OwnerState", "label": "Owner State"},
        {"field": "Manufacturer", "sort_order": 1},
        {"field": "Model", "sort_order": 2},
        {"field": "ManufacturerYear", "label": "MFR Year"},
        {"field": "SerialNumber", "label": "Serial Number"},
        {"field": "EngineManufacturer", "label": "Engine MFR", "sort_order": 3},
        {"field": "EngineModel", "label": "Engine Model", "sort_order": 4},
    ]

    # Pagination parameters
    start = request.args.get("start") or 0
    start = int(start)
    end = request.args.get("end") or config.AIRPLANE_RECORDS_PER_PAGE
    end = int(end)

    # Navigation path and offset setup
    nav_path = search_helpers.strip_place(request.url)
    nav_offsets = search_helpers.get_navigation_offsets(
        start, end, config.AIRPLANE_RECORDS_PER_PAGE
    )

    # Build the base of our elasticsearch query
    query = {
        "query": {"bool": {"must": []}},
        "from": start,
        "size": config.AIRPLANE_RECORDS_PER_PAGE,
    }

    arg_dict = {}
    for item in search_config:
        field = item["field"]
        value = request.args.get(field)
        arg_dict[field] = value
        if value:
            query["query"]["bool"]["must"].append({"match": {field: value}})

    # Query elasticsearch, process to get records and count
    results = elastic.search(query, index="agile_data_science")
    airplanes, airplane_count = search_helpers.process_search(results)

    # Persist search parameters in the form template
    return render_template(
        "all_airplanes.html",
        search_config=search_config,
        args=arg_dict,
        airplanes=airplanes,
        airplane_count=airplane_count,
        nav_path=nav_path,
        nav_offsets=nav_offsets,
    )


@app.route("/airplanes/chart/manufacturers.json")
@app.route("/airplanes/chart/manufacturers.json")
def airplane_manufacturers_chart():
    mfr_chart = client.agile_data_science.airplane_manufacturer_totals.find_one()
    return json.dumps(mfr_chart)


# Controller: Fetch a flight and display it
@app.route("/airplane/<tail_number>")
@app.route("/airplane/flights/<tail_number>")
def flights_per_airplane(tail_number):
    flights = client.agile_data_science.flights_per_airplane.find_one(
        {"TailNum": tail_number}
    )
    print(flights)
    return render_template(
        "flights_per_airplane.html", flights=flights, tail_number=tail_number
    )


# Controller: Fetch an airplane entity page
@app.route("/airlines/<carrier_code>")
def airline(carrier_code):
    airline_airplanes = client.agile_data_science.airplanes_per_carrier.find_one(
        {"Carrier": carrier_code}
    )
    airline_airports = client.agile_data_science.airports_per_carrier.find_one(
        {"Carrier": carrier_code}
    )
    return render_template(
        "airlines.html",
        airline_airplanes=airline_airplanes,
        carrier_code=carrier_code,
        airline_airports=airline_airports,
    )


# Controller: Fetch an airplane entity page
@app.route("/airport/<airport_code>")
def airport(airport_code):
    carriers_per_airport = client.agile_data_science.carriers_per_airport.find_one(
        {"Airport": airport_code}
    )
    airport_metadata = client.agile_data_science.airport_metadata.find_one(
        {"AirportCode": airport_code}
    )

    return render_template(
        "airport.html",
        airport_code=airport_code,
        carriers_per_airport=carriers_per_airport,
        airport_metadata=airport_metadata,
    )


# Controller: Fetch an airplane entity page
@app.route("/airlines2/<carrier_code>")
def airline2(carrier_code):
    airline_summary = client.agile_data_science.airlines.find_one(
        {"CarrierCode": carrier_code}
    )
    airline_airplanes = client.agile_data_science.airplanes_per_carrier.find_one(
        {"Carrier": carrier_code}
    )
    airline_airports = client.agile_data_science.airports_per_carrier.find_one(
        {"Carrier": carrier_code}
    )
    return render_template(
        "airlines2.html",
        airline_summary=airline_summary,
        airline_airplanes=airline_airplanes,
        airline_airports=airline_airports,
        carrier_code=carrier_code,
    )


# Controller: Fetch an airplane entity page
@app.route("/")
@app.route("/airlines")
@app.route("/airlines/")
def airlines():
    airlines = client.agile_data_science.airplanes_per_carrier.find()
    return render_template("all_airlines.html", airlines=airlines)


@app.route("/flights/search")
@app.route("/flights/search/")
def search_flights():

    # Search parameters
    carrier = request.args.get("Carrier")
    flight_date = request.args.get("FlightDate")
    origin = request.args.get("Origin")
    dest = request.args.get("Dest")
    tail_number = request.args.get("TailNum")
    flight_number = request.args.get("FlightNum")

    # Pagination parameters
    start = request.args.get("start") or 0
    start = int(start)
    end = request.args.get("end") or config.RECORDS_PER_PAGE
    end = int(end)

    # Navigation path and offset setup
    nav_path = search_helpers.strip_place(request.url)
    nav_offsets = search_helpers.get_navigation_offsets(
        start, end, config.RECORDS_PER_PAGE
    )

    # Build the base of our elasticsearch query
    query = {
        "query": {"bool": {"must": []}},
        "sort": [{"FlightDate": "asc"}, "_score"],
        "from": start,
        "size": config.RECORDS_PER_PAGE,
    }

    # Add any search parameters present
    if carrier:
        query["query"]["bool"]["must"].append({"match": {"Carrier": carrier}})
    if flight_date:
        query["query"]["bool"]["must"].append({"match": {"FlightDate": flight_date}})
    if origin:
        query["query"]["bool"]["must"].append({"match": {"Origin": origin}})
    if dest:
        query["query"]["bool"]["must"].append({"match": {"Dest": dest}})
    if tail_number:
        query["query"]["bool"]["must"].append({"match": {"TailNum": tail_number}})
    if flight_number:
        query["query"]["bool"]["must"].append({"match": {"FlightNum": flight_number}})

    # Query elasticsearch, process to get records and count
    results = elastic.search(query, index="agile_data_science")
    flights, flight_count = process_search(results)

    # Persist search parameters in the form template
    return render_template(
        "search.html",
        flights=flights,
        flight_date=flight_date,
        flight_count=flight_count,
        nav_path=nav_path,
        nav_offsets=nav_offsets,
        carrier=carrier,
        origin=origin,
        dest=dest,
        tail_number=tail_number,
        flight_number=flight_number,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
