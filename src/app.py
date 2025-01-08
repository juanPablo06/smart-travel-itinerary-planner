import streamlit as st
import requests
import folium
import math
from streamlit_folium import st_folium
from io import BytesIO
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from heapq import heappop, heappush

# Constants
EARTH_RADIUS_KM = 6371
USER_AGENT = "SmartTravelItineraryPlanner/1.0 (juan34063@gmail.com)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

st.title("Smart Travel Itinerary Planner")
st.write("Enter locations and calculate the best routes for your trip!")

with st.sidebar:
    st.header("Parameters")
    locations = st.text_area("Enter Locations (one per line):").strip()
    city = st.text_input("City (optional):").strip()
    country = st.text_input("Country (optional):").strip()
    travel_mode = st.selectbox("Select Travel Mode:", ["driving", "walking", "bicycling"])
    daily_distance = st.number_input("Max Distance per Day (km):", min_value=1, value=100)
    days = st.number_input("Number of Days:", min_value=1, value=3)
    max_places_per_day = st.number_input("Max Places per Day:", min_value=1, value=5)

def geocode_location(location, city, country):
    if city:
        location += f", {city}"
    if country:
        location += f", {country}"
    params = {"q": location, "format": "json"}
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers)
        response_data = response.json()
        
        if response.ok and response_data:
            data = response_data[0]
            return {
                "name": location,
                "lat": float(data["lat"]),
                "lon": float(data["lon"]),
            }
        else:
            logging.warning(f"Location '{location}' not found or invalid response.")
            return None
    except Exception as e:
        logging.error(f"Error geocoding {location}: {e}")
        return None

def geocode_locations(locations, city, country):
    geocoded = []
    failed_locations = []
    
    for location in locations.split("\n"):
        location = location.strip()
        if not location:
            continue
        result = geocode_location(location, city, country)
        if result:
            geocoded.append(result)
        else:
            failed_locations.append(location)
    
    if failed_locations:
        st.warning(f"The following locations could not be geocoded: {', '.join(failed_locations)}")
    
    return geocoded

def haversine(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

def heuristic(loc1, loc2):
    return haversine(loc1["lat"], loc1["lon"], loc2["lat"], loc2["lon"])

def find_optimal_route(locations):
    start = locations[0]
    goal = locations[-1]
    open_set = []
    heappush(open_set, (0, [start])) 
    best_path = None
    best_cost = float('inf')
    g_costs = {start["name"]: 0}

    while open_set:
        cost, path = heappop(open_set)
        current = path[-1]

        if current == goal:
            if cost < best_cost:  
                best_cost = cost
                best_path = path
            continue

        for neighbor in locations:
            if neighbor in path:
                continue
            new_cost = g_costs[current["name"]] + haversine(current["lat"], current["lon"], neighbor["lat"], neighbor["lon"])
            if neighbor["name"] not in g_costs or new_cost < g_costs[neighbor["name"]]:
                g_costs[neighbor["name"]] = new_cost
                f_cost = new_cost + heuristic(neighbor, goal)
                heappush(open_set, (f_cost, path + [neighbor]))

    return best_path

def split_route_into_days(route, daily_distance, max_places_per_day, days):
    daily_routes = [] 
    current_day = []  
    current_distance = 0
    day_count = 0 

    for i in range(len(route)):
        if day_count >= days:
            break

        if i > 0:
            distance = haversine(route[i-1]["lat"], route[i-1]["lon"], route[i]["lat"], route[i]["lon"])
        else:
            distance = 0

        if (current_distance + distance > daily_distance or len(current_day) >= max_places_per_day) and current_day:
            daily_routes.append(current_day) 
            current_day = [] 
            current_distance = 0
            day_count += 1

        current_day.append(route[i])
        current_distance += distance

    if current_day and day_count < days:
        daily_routes.append(current_day)

    while len(daily_routes) < days:
        daily_routes.append([])

    return daily_routes[:days]

def plot_route(daily_routes):
    if not daily_routes:
        return None
    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue', 'darkpurple', 'white', 'pink', 'lightblue', 'lightgreen', 'gray', 'black', 'lightgray']
    m = folium.Map(location=[daily_routes[0][0]["lat"], daily_routes[0][0]["lon"]], zoom_start=13)
    for day, locations in enumerate(daily_routes):
        color = colors[day % len(colors)]
        for loc in locations:
            folium.Marker([loc["lat"], loc["lon"]], popup=loc["name"], icon=folium.Icon(color=color)).add_to(m)
        for i in range(len(locations) - 1):
            folium.PolyLine([(locations[i]["lat"], locations[i]["lon"]),
                             (locations[i+1]["lat"], locations[i+1]["lon"])], color=color).add_to(m)
    return m

def download_itinerary(route):
    itinerary = json.dumps(route, indent=4)
    b = BytesIO()
    b.write(itinerary.encode())
    b.seek(0)
    return b

if st.button("Generate Itinerary"):
    location_list = geocode_locations(locations, city, country)
    if location_list:
        optimal_route = find_optimal_route(location_list)
        daily_routes = split_route_into_days(optimal_route, daily_distance, max_places_per_day, days)
        
        st.session_state["optimal_route"] = optimal_route
        st.session_state["daily_routes"] = daily_routes
        
        st.write("Optimal Route:", [loc["name"] for loc in optimal_route])
        for i, daily_route in enumerate(daily_routes):
            st.write(f"Day {i+1}: {[loc['name'] for loc in daily_route]}")
        map_ = plot_route(daily_routes)
        if map_:
            st_folium(map_, width=800, key=f"map_day_{i+1}")
        itinerary_file = download_itinerary(daily_routes)
        st.download_button("Download Itinerary", itinerary_file, file_name="itinerary.json", key=f"download_button_{i}")
    else:
        st.error("No valid locations found. Please check your input.")

if "optimal_route" in st.session_state and "daily_routes" in st.session_state:
    st.write("Optimal Route:", [loc["name"] for loc in st.session_state["optimal_route"]])
    for i, daily_route in enumerate(st.session_state["daily_routes"]):
        st.write(f"Day {i+1}: {[loc['name'] for loc in daily_route]}")
    map_ = plot_route(st.session_state["daily_routes"])
    if map_:
        st_folium(map_, width=800, key=f"map_day_{i+1}")
