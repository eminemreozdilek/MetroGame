def lookup_station_coords(station_names, stations_dict):
    coords = []
    for st_name in station_names:
        for st_id, st_data in stations_dict.items():
            if st_data["name"] == st_name:
                coords.append(st_data["coords"])
                break
    return coords
