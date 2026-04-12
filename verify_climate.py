import math

def get_climate(wx, wz, wy):
    # Latitude logic: temperature drops as we move away from Z=0
    # Range is 450 units from equator to pole
    dist_from_equator = abs(wz)
    lat_temp = max(0.0, 1.0 - (dist_from_equator / 450.0))
    
    # Elevation logic: temperature drops 0.1 per 10 units height
    alt_temp = max(0.0, 1.0 - (wy / 100.0))
    
    temp = (lat_temp * 0.7 + alt_temp * 0.3)
    return temp

# Test Equator (Z=0, H=0)
t1 = get_climate(0, 0, 0)
# Test High Lat (Z=450, H=0)
t2 = get_climate(0, 450, 0)
# Test Alt (Z=0, H=100)
t3 = get_climate(0, 0, 100)

print(f"Equator: {t1:.2f} (Expected: 1.0)")
print(f"Pole (Z=450): {t2:.2f} (Expected: ~0.3 since lat_temp=0, alt_temp=1)")
print(f"Mountain Peak: {t3:.2f} (Expected: ~0.7 since lat_temp=1, alt_temp=0)")

assert t1 > t2, "Equator should be warmer than Pole"
assert t1 > t3, "Sea level should be warmer than Mountain Peak"
print("Climate calibration verified.")
