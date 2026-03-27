import pandas as pd
import xml.etree.ElementTree as ET
import os
import struct
import numpy as np
import csv
import scipy.io


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
            units = next(reader, None)    # línea 16 (0-indexed 15): unidades

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


def _parse_ld_channels(file_path):
    """
    Parsea los canales de un archivo .ld de MoTeC (formato rFactor 2).
    Devuelve un dict {nombre: array_numpy_float} con valores físicos escalados.
    """
    with open(file_path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        # Leer puntero al primer canal (offset 8)
        f.seek(8)
        chan_ptr = struct.unpack('<I', f.read(4))[0]

        if chan_ptr == 0 or chan_ptr >= file_size:
            raise ValueError("Puntero de canal inválido en el archivo .ld")

        channels = {}
        pos = chan_ptr

        for _ in range(512):
            if pos == 0 or pos + 124 > file_size:
                break

            f.seek(pos)
            hdr = f.read(124)

            # Layout de cabecera de canal (124 bytes):
            # 0:  prev_ptr (4)
            # 4:  next_ptr (4)
            # 8:  data_ptr (4)   - offset absoluto al inicio de los datos
            # 12: n_samples (4)  - número de muestras
            # 14: d_type (2)     - tipo de dato: 0=uint16, 3=float32
            # 16: freq_num (2)   - numerador de frecuencia
            # 18: freq_den (2)   - denominador de frecuencia
            # 20: scale_mul (2)  - multiplicador de escala
            # 22: scale_div (2)  - divisor de escala
            # 32: name_long (32) - nombre largo del canal
            # 64: name_short (8) - nombre corto
            # 72: units (8)      - unidades
            # 88: min_raw (2)    - valor raw mínimo (no usado en escala)
            # 90: max_raw (2)    - valor raw máximo (no usado en escala)
            #
            # Fórmula de escala: physical = (raw - 32768) * scale_mul / scale_div / 10

            next_ptr  = struct.unpack('<I', hdr[4:8])[0]
            data_ptr  = struct.unpack('<I', hdr[8:12])[0]
            n_samples = struct.unpack('<I', hdr[12:16])[0]
            d_type    = struct.unpack('<H', hdr[14:16])[0]
            scale_mul = struct.unpack('<H', hdr[20:22])[0]
            scale_div = struct.unpack('<H', hdr[22:24])[0]
            name_long = hdr[32:64].split(b'\x00')[0].decode('ascii', errors='ignore').strip()

            if not name_long:
                if next_ptr == 0 or next_ptr >= file_size:
                    break
                pos = next_ptr
                continue

            # Leer datos
            if n_samples > 0 and data_ptr > 0:
                size_per = 4 if d_type == 3 else 2
                if data_ptr + n_samples * size_per <= file_size:
                    try:
                        f.seek(data_ptr)
                        raw_bytes = f.read(n_samples * size_per)
                        if len(raw_bytes) == n_samples * size_per:
                            if d_type == 3:
                                # float32: ya es valor físico directo
                                arr = np.array(struct.unpack(f'<{n_samples}f', raw_bytes), dtype=np.float32)
                            else:
                                # uint16: aplicar escala
                                arr_raw = np.array(struct.unpack(f'<{n_samples}H', raw_bytes), dtype=np.float64)
                                if scale_mul > 0 and scale_div > 0:
                                    arr = (arr_raw - 32768.0) * scale_mul / scale_div / 10.0
                                else:
                                    arr = arr_raw - 32768.0
                            channels[name_long] = arr
                    except Exception:
                        pass

            if next_ptr == 0 or next_ptr >= file_size:
                break
            pos = next_ptr

    return channels


def parse_ld_file(file_path):
    """
    Parsea un archivo .ld de MoTeC (binario) y extrae los datos de los canales.
    Devuelve un DataFrame de pandas con los canales escalados a valores físicos.
    """
    try:
        channels = _parse_ld_channels(file_path)

        if not channels:
            raise ValueError("No se pudieron extraer canales de telemetría del archivo .ld.")

        # Renombrar canales de GPS
        if 'Longitude' in channels and 'GPS Longitude' not in channels:
            channels['GPS Longitude'] = channels.pop('Longitude')
        if 'Latitude' in channels and 'GPS Latitude' not in channels:
            channels['GPS Latitude'] = channels.pop('Latitude')

        # Alinear canales: usar la longitud máxima, rellenar con NaN los más cortos
        max_len = max(len(v) for v in channels.values())
        aligned = {}
        for k, v in channels.items():
            if len(v) == max_len:
                aligned[k] = v
            else:
                padded = np.full(max_len, np.nan)
                padded[:len(v)] = v
                aligned[k] = padded

        df = pd.DataFrame(aligned)

        # Suavizado de GPS
        for col in ['GPS Latitude', 'GPS Longitude']:
            if col in df.columns:
                df[col] = df[col].astype(float)
                # Eliminar ceros (fallos de señal)
                df[col] = df[col].replace(0, np.nan).ffill().bfill()
                # Filtro de outliers
                median = df[col].median()
                std = df[col].std()
                if std > 0:
                    df[col] = df[col].mask((df[col] - median).abs() > 1.5 * std, median)
                # Suavizado
                df[col] = df[col].rolling(window=11, center=True).mean().bfill().ffill()

        return df

    except Exception as e:
        raise ValueError(f"Error parseando .ld: {str(e)}")


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
