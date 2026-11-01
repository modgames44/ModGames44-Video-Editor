"""Proyección de tiempo de reproducción en el reloj de la Timeline."""
def projected_time(base_ms, elapsed_wall_ms, speed, duration_ms):
    if speed <= 0:
        raise ValueError('Velocidad inválida')
    return max(0,min(duration_ms,base_ms+elapsed_wall_ms*speed))
