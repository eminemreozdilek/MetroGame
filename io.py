import pandas as pd

def save_data(station_data, line_data, filename):
    df_stations = pd.DataFrame(station_data)
    df_lines = pd.DataFrame(line_data)
    with pd.HDFStore(filename, mode='w') as store:
        store.put('stations', df_stations, format='table')
        store.put('lines', df_lines, format='table')

def import_data(filename):
    with pd.HDFStore(filename, mode='r') as store:
        df_stations = store.get('stations')
        df_lines = store.get('lines')
    station_data = df_stations.to_dict(orient='records')
    line_data = df_lines.to_dict(orient='records')
    return station_data, line_data
