import pandas as pd
import requests
import json
import time

def fetch_iris():
    df = pd.read_csv('data/App_Carto_Solaire_Feux_2020_2025.csv', dtype={'codeIRIS': str})
    unique_iris = df['codeIRIS'].dropna().unique().tolist()
    
    print(f"Fetching {len(unique_iris)} unique IRIS codes...")
    
    iris_coords = {}
    
    # Chunk by 50 to avoid URL too long
    chunk_size = 50
    for i in range(0, len(unique_iris), chunk_size):
        chunk = unique_iris[i:i+chunk_size]
        in_clause = ",".join([f'"{code}"' for code in chunk])
        url = f"https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-france-iris-millesime/records?where=iris_code in ({in_clause})&limit=100"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for record in data.get('results', []):
                    code_list = record.get('iris_code')
                    if code_list and isinstance(code_list, list):
                        code = code_list[0]
                    else:
                        code = code_list
                    geo_point = record.get('geo_point_2d')
                    if code and geo_point:
                        if isinstance(geo_point, dict) and 'lat' in geo_point:
                            iris_coords[code] = (geo_point['lat'], geo_point['lon'])
                        elif isinstance(geo_point, dict) and 'latitude' in geo_point:
                            iris_coords[code] = (geo_point['latitude'], geo_point['longitude'])
            else:
                print(f"Error {resp.status_code} on chunk {i}")
        except Exception as e:
            print(f"Exception: {e}")
            
        time.sleep(0.5)
        
    print(f"Successfully fetched {len(iris_coords)} IRIS coordinates.")
    
    with open('data/iris_coordinates.json', 'w') as f:
        json.dump(iris_coords, f)

if __name__ == "__main__":
    fetch_iris()
