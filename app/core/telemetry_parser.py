import pandas as pd
import xml.etree.ElementTree as ET
import os
import struct
import numpy as np

def parse_ld_file(file_path):
    """
    Parsea un archivo .ld de MoTeC (binario) y extrae los datos de los canales.
    Soporta formatos MoTeC LD v1.1 y posteriores.
    """
    try:
        with open(file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            
            if file_size < 68:
                raise ValueError("El archivo .ld es demasiado pequeño.")
            
            f.seek(0)
            magic = struct.unpack('<I', f.read(4))[0]
            
            if magic == 0x40: # MoTeC LD v1.1 (Común en rFactor 2)
                f.seek(8)
                next_chan_ptr = struct.unpack('<I', f.read(4))[0]
                chan_header_struct = '<IIIHHH' # MoTeC v1.1 structure
                chan_header_size = 18
            else: # MoTeC LD v2.x
                f.seek(64)
                next_chan_ptr = struct.unpack('<I', f.read(4))[0]
                chan_header_struct = '<IIIHHH' # Similar but offset might differ
                chan_header_size = 18
            
            channels_data = {}
            
            for _ in range(512):
                if next_chan_ptr == 0 or next_chan_ptr >= file_size:
                    break
                
                f.seek(next_chan_ptr)
                # La cabecera MoTeC v1.1 es de 128 bytes.
                header_bytes = f.read(128)
                if len(header_bytes) < 64:
                    break
                
                # MoTeC v1.1: next_ptr(4), data_ptr(4), n_samples(4), reserved(2), d_type(2), freq(2)
                # El d_type 3 es float32, 1 o 0 es int16
                next_ptr_v1, data_ptr, n_samples, _, d_type, freq = struct.unpack('<IIIHHH', header_bytes[:18])
                name = header_bytes[32:64].split(b'\x00')[0].decode('ascii', errors='ignore').strip()
                
                # MoTeC v1.1 rFactor 2: Siguiente puntero a menudo en offset 124
                next_ptr_v2 = struct.unpack('<I', header_bytes[124:128])[0]
                next_ptr = next_ptr_v1 if next_ptr_v1 != 0 else next_ptr_v2
                
                # Validar datos y extraer
                if n_samples > 0 and data_ptr > 0:
                    # MoTeC v1.1 Ground Speed tiene d_type 0 en offset 14
                    # Si d_type es 3 es float32, si es 0 es int16
                    # Pero en rFactor 2 a veces los datos están escalados.
                    
                    if d_type == 3: # float32
                        size = 4
                        fmt = f'<{n_samples}f'
                    else: # int16 por defecto para v1.1
                        size = 2
                        fmt = f'<{n_samples}h'
                    
                    if data_ptr + (n_samples * size) <= file_size:
                        try:
                            f.seek(data_ptr)
                            chan_bytes = f.read(n_samples * size)
                            if len(chan_bytes) == n_samples * size:
                                data = struct.unpack(fmt, chan_bytes)
                                # Conversión básica para canales conocidos si son int16
                                if d_type != 3:
                                    # Velocidad en rFactor 2 MoTeC suele estar en km/h * 10 o m/s * 10
                                    # Si vemos valores enormes como 13384 para algo que debería ser 0-300, 
                                    # es posible que necesite un factor. 
                                    # Por ahora lo dejamos crudo pero el agente lo interpretará.
                                    pass
                                channels_data[name] = data
                        except Exception:
                            pass
                
                next_chan_ptr = next_ptr
            
            # Si solo extrajo 1 canal o ninguno, escaneo de seguridad para rFactor 2
            if len(channels_data) < 2:
                f.seek(8)
                start_search = struct.unpack('<I', f.read(4))[0]
                if start_search > 0 and start_search < 100000:
                    f.seek(start_search)
                    search_area = f.read(20000) 
                    
                    i = 0
                    while i < len(search_area) - 128:
                        cand_next, cand_data, cand_samples = struct.unpack('<III', search_area[i:i+12])
                        if 10 < cand_samples < 1000000 and start_search < cand_data < file_size:
                            cand_name = search_area[i+32:i+64].split(b'\x00')[0].decode('ascii', errors='ignore').strip()
                            if cand_name and len(cand_name) > 2 and cand_name not in channels_data:
                                if all(32 <= ord(c) <= 126 for c in cand_name):
                                    # Para evitar nombres que son sufijos de otros canales encontrados por el escaneo de 4 en 4
                                    # (e.g. 'nd Speed' de 'Ground Speed'), comprobamos si el bloque actual es coherente.
                                    # En MoTeC v1.1, los nombres están alineados en bloques de 128 o 248.
                                    # Pero como no sabemos la alineación exacta, filtramos por calidad.
                                    is_duplicate_suffix = any(cand_name != existing and existing.endswith(cand_name) for existing in channels_data)
                                    if not is_duplicate_suffix:
                                        try:
                                            f.seek(cand_data)
                                            cand_type = struct.unpack('<H', search_area[i+14:i+16])[0]
                                            size = 4 if cand_type == 3 else 2
                                            fmt = f'<{cand_samples}f' if cand_type == 3 else f'<{cand_samples}h'
                                            if cand_data + (cand_samples * size) <= file_size:
                                                chan_bytes = f.read(cand_samples * size)
                                                if len(chan_bytes) == cand_samples * size:
                                                    channels_data[cand_name] = struct.unpack(fmt, chan_bytes)
                                                    i += 124 # Saltar al final del bloque probable
                                        except Exception: pass
                        i += 4
            
            if not channels_data:
                raise ValueError("No se pudieron extraer canales de telemetría del archivo .ld. Formato no soportado o archivo dañado.")
                
            # Limpieza de nombres de canales (algunos vienen con basura o espacios extra)
            clean_channels = {}
            for k, v in channels_data.items():
                # Limpiar caracteres no imprimibles y basura al inicio
                clean_name = "".join(c for c in k if 32 <= ord(c) <= 126).strip()
                # Quitar prefijos comunes de basura en rFactor 2
                for prefix in ['s', 'd', 'el ', 'e ']:
                    if clean_name.startswith(prefix) and len(clean_name) > len(prefix):
                        # Solo quitar si el resto parece un nombre válido
                        if clean_name[len(prefix):][0].isupper():
                            clean_name = clean_name[len(prefix):]
                
                if clean_name == "Longitude": clean_name = "GPS Longitude"
                if clean_name == "Latitude": clean_name = "GPS Latitude"
                clean_channels[clean_name] = list(v)

            # Alinear canales a la misma longitud y renombrar duplicados
            if not clean_channels:
                raise ValueError("No se pudieron procesar canales limpios del archivo .ld.")

            min_len = min(len(v) for v in clean_channels.values())
            for k in clean_channels:
                clean_channels[k] = clean_channels[k][:min_len]
                
            df = pd.DataFrame(clean_channels)
            
            # Suavizado de GPS para evitar picos que rompen el mapa
            for col in ['GPS Latitude', 'GPS Longitude']:
                if col in df.columns:
                    # Rellenar ceros si existen (suelen ser fallos de señal)
                    # Convertir a float por si acaso
                    df[col] = df[col].astype(float)
                    
                    # En rF2, a veces las coordenadas vienen escaladas por 10^7
                    if df[col].abs().max() > 1000:
                        df[col] = df[col] / 10000000.0
                        
                    df[col] = df[col].replace(0, np.nan).ffill().bfill()
                    
                    # Filtro de outliers (Z-score básico sobre la serie)
                    median = df[col].median()
                    std = df[col].std()
                    if std > 0:
                        # Si el valor se aleja mucho de la mediana, es probablemente un error de captura
                        # Bajamos el umbral a 1.5 para ser más agresivos con el ruido de GPS rF2
                        df[col] = df[col].mask((df[col] - median).abs() > 1.5 * std, median)
                    
                    # Suavizado suave para el trazado
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
