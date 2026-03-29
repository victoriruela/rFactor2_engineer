import pandas as pd
import numpy as np
import csv
import scipy.io


def _filter_incomplete_laps(df):
    """
    Filtra vueltas incompletas del DataFrame.
    Una vuelta se considera incompleta si su distancia recorrida es
    menor que el 100% de la distancia máxima recorrida.
    También se excluye la vuelta 0 (out-lap).
    """
    # Buscar columna de número de vuelta
    lap_col = None
    for c in df.columns:
        if 'lap' in c.lower() and 'number' in c.lower():
            lap_col = c
            break
    if lap_col is None:
        # Intentar con Lap_Number
        if 'Lap_Number' in df.columns:
            lap_col = 'Lap_Number'
        else:
            return df

    # Buscar columna de distancia de vuelta
    dist_col = None
    for c in df.columns:
        if 'distance' in c.lower() and 'lap' in c.lower():
            dist_col = c
            break
    if dist_col is None:
        for c in df.columns:
            if 'distance' in c.lower():
                dist_col = c
                break

    laps = sorted([l for l in df[lap_col].unique() if l > 0])
    if len(laps) <= 1:
        # Si solo hay una vuelta, no filtrar
        return df[df[lap_col] > 0] if 0 in df[lap_col].values else df

    if dist_col is not None:
        # Calcular distancia recorrida por vuelta
        lap_distances = {}
        for lap in laps:
            lap_df = df[df[lap_col] == lap]
            if not lap_df.empty:
                d = lap_df[dist_col].dropna()
                if not d.empty:
                    lap_distances[lap] = d.max() - d.min()
                else:
                    lap_distances[lap] = 0
            else:
                lap_distances[lap] = 0

        max_dist = max(lap_distances.values()) if lap_distances else 0
        threshold = max_dist * 1.0
        complete_laps = [l for l, d in lap_distances.items() if d >= threshold]
    else:
        # Sin columna de distancia, usar número de muestras como proxy
        lap_samples = {}
        for lap in laps:
            lap_samples[lap] = len(df[df[lap_col] == lap])
        max_samples = max(lap_samples.values()) if lap_samples else 0
        threshold = max_samples * 1.0
        complete_laps = [l for l, s in lap_samples.items() if s >= threshold]

    if not complete_laps:
        complete_laps = laps

    # Filtrar out-laps/in-laps por duración anómala (primera/última vuelta)
    # Buscar columna de tiempo
    time_col = None
    for c in df.columns:
        if c == 'Session_Elapsed_Time':
            time_col = c
            break
    if time_col is not None and len(complete_laps) > 2:
        lap_durations = {}
        for lap in complete_laps:
            lap_df = df[df[lap_col] == lap]
            t = lap_df[time_col].dropna()
            if not t.empty:
                lap_durations[lap] = t.max() - t.min()
            else:
                lap_durations[lap] = 0
        # Calcular mediana de duración (excluyendo primera y última)
        middle_laps = complete_laps[1:-1] if len(complete_laps) > 2 else complete_laps
        median_dur = np.median([lap_durations[l] for l in middle_laps if lap_durations[l] > 0])
        if median_dur > 0:
            # Filtrar vueltas con duración > 110% de la mediana (out-laps/in-laps)
            dur_threshold = median_dur * 1.10
            complete_laps = [l for l in complete_laps if lap_durations[l] <= dur_threshold]

    if not complete_laps:
        complete_laps = laps

    return df[df[lap_col].isin(complete_laps)].reset_index(drop=True)


def parse_mat_file(file_path):
    """
    Parsea un archivo .mat (Matlab) exportado desde MoTeC i2.
    Extrae los canales y los alinea en un DataFrame de pandas.
    """
    try:
        # Cargar archivo .mat con estructura simplificada
        mat = scipy.io.loadmat(file_path, struct_as_record=False, squeeze_me=True)

        channels = {}
        for key in mat.keys():
            if key.startswith('__'):
                continue

            # Cada entrada suele ser una mat_struct con campos 'Value', 'Time', 'Units'
            obj = mat[key]
            if hasattr(obj, 'Value'):
                channels[key] = obj.Value

        if not channels:
            raise ValueError("No se encontraron canales válidos en el archivo .mat")

        # Alinear canales (usar la longitud de 'Session_Elapsed_Time' si existe, o el máximo)
        base_col = 'Session_Elapsed_Time' if 'Session_Elapsed_Time' in channels else next(iter(channels))
        max_len = len(channels[base_col])

        aligned = {}
        for k, v in channels.items():
            if not isinstance(v, (np.ndarray, list)):
                continue

            if len(v) == max_len:
                aligned[k] = v
            else:
                # Si la longitud difiere, rellenamos con NaN o truncamos
                # Para telemetría de MoTeC, suelen estar alineados si vienen del mismo export
                if len(v) > max_len:
                    aligned[k] = v[:max_len]
                else:
                    padded = np.full(max_len, np.nan)
                    padded[:len(v)] = v
                    aligned[k] = padded

        df = pd.DataFrame(aligned)

        # Renombrar canales comunes para consistencia si es necesario
        rename_map = {
            'GPS_Latitude': 'GPS Latitude',
            'GPS_Longitude': 'GPS Longitude',
            'Throttle_Pos': 'Throttle',
            'Brake_Pos': 'Brake',
            'Steering_Wheel_Position': 'Steering',
            'Engine_RPM': 'RPM',
            'Ground_Speed': 'Speed'
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Suavizado de GPS
        for col in ['GPS Latitude', 'GPS Longitude']:
            if col in df.columns:
                df[col] = df[col].astype(float)
                df[col] = df[col].replace(0, np.nan).ffill().bfill()
                median = df[col].median()
                std = df[col].std()
                if std > 0:
                    df[col] = df[col].mask((df[col] - median).abs() > 1.5 * std, median)
                df[col] = df[col].rolling(window=11, center=True).mean().bfill().ffill()

        # Filtrar vueltas incompletas
        df = _filter_incomplete_laps(df)

        return df

    except Exception as e:
        raise ValueError(f"Error parseando .mat: {str(e)}")


def parse_csv_file(file_path):
    """
    Parsea un archivo CSV exportado desde MoTeC (1000Hz).
    Las primeras 12 líneas son metadatos, la línea 13 son los encabezados,
    la línea 14 son las unidades, y los datos empiezan en la línea 15.
    Devuelve un DataFrame de pandas con los canales.
    """
    try:
        # Leer metadatos (primeras 14 líneas: 12 de metadatos + 2 vacías)
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for _ in range(14):
                next(reader, None)
            headers = next(reader, None)  # línea 15 (0-indexed 14): encabezados
            next(reader, None)             # línea 16 (0-indexed 15): unidades (skip)

        if not headers:
            raise ValueError("No se encontraron encabezados en el CSV.")

        # Limpiar encabezados de comillas y espacios
        headers = [h.strip() for h in headers]

        # Leer datos desde la línea 17 (0-indexed 16) en adelante
        df = pd.read_csv(file_path, skiprows=16, header=None, names=headers,
                         low_memory=False)

        # Convertir columnas numéricas
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Eliminar filas completamente vacías
        df = df.dropna(how='all')

        if df.empty:
            raise ValueError("El archivo CSV no contiene datos válidos.")

        # Suavizado de GPS
        for col in ['GPS Latitude', 'GPS Longitude']:
            if col in df.columns:
                df[col] = df[col].astype(float)
                df[col] = df[col].replace(0, np.nan).ffill().bfill()
                median = df[col].median()
                std = df[col].std()
                if std > 0:
                    df[col] = df[col].mask((df[col] - median).abs() > 1.5 * std, median)
                df[col] = df[col].rolling(window=11, center=True).mean().bfill().ffill()

        return df

    except Exception as e:
        raise ValueError(f"Error parseando CSV: {str(e)}")


def parse_svm_file(file_path):
    """
    Parsea un archivo .svm de rFactor 2 (setup del coche).
    Suelen ser archivos de texto con una estructura tipo INI.
    """
    setup = {}
    try:
        # Intentamos UTF-16 primero que es común en rFactor 2
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.readlines()
        except UnicodeError:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.readlines()

        current_section = None
        for line in content:
            line = line.strip()
            if not line or line.startswith('//'):
                continue

            if '[' in line and ']' in line:
                current_section = line[1:-1]
                setup[current_section] = {}
            elif '=' in line and current_section:
                key, value = line.split('=', 1)
                setup[current_section][key.strip()] = value.strip()

        if not setup:
            raise ValueError("El archivo .svm parece estar vacío o no contiene secciones de setup válidas.")
        return setup
    except Exception as e:
        raise ValueError(f"Error parseando .svm: {str(e)}")
