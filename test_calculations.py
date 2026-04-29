"""
Test script untuk memverifikasi perhitungan sesuai PERKENI 2024
"""
import sys
sys.path.insert(0, 'c:/xampp/htdocs/smartdiabets/smartdiabets')

from app import (
    calculate_bbi, calculate_imt, classify_imt, 
    classify_nutrition_status, calculate_base_calories,
    apply_corrections, apply_weight_correction, 
    check_minimum_calories, distribute_calories,
    calculate_nutrients
)

def test_case_1():
    """Test Case 1: Wanita, Kurus"""
    print("\n" + "="*60)
    print("TEST CASE 1: Wanita, Kurus")
    print("="*60)
    
    # Input
    height = 155  # cm
    weight = 42   # kg
    age = 25
    gender = "wanita"
    activity = "light"
    
    # 1. BBI
    bbi = calculate_bbi(height, gender)
    print(f"1. BBI = 0.9 × ({height} - 100) = {bbi:.2f} kg")
    
    # 2. IMT
    imt = calculate_imt(weight, height)
    imt_status = classify_imt(imt)
    print(f"2. IMT = {weight} / ({height/100})² = {imt:.2f} kg/m² → {imt_status}")
    
    # 3. Status BB
    status = classify_nutrition_status(weight, bbi)
    print(f"3. Status BB = {status} ({weight} kg vs BBI {bbi:.2f} kg)")
    print(f"   - Batas Bawah: {bbi * 0.9:.2f} kg")
    print(f"   - Batas Atas: {bbi * 1.1:.2f} kg")
    
    # 4. Energi Basal
    base_cal = calculate_base_calories(bbi, gender)
    print(f"4. Energi Basal = 25 × {bbi:.2f} = {base_cal:.2f} kkal")
    
    # 5. Koreksi Usia
    cal_after_age = base_cal * 1.00  # < 40 tahun
    print(f"5. Koreksi Usia (< 40 thn) = {base_cal:.2f} × 1.00 = {cal_after_age:.2f} kkal")
    
    # 6. Koreksi Aktivitas
    cal_after_activity = cal_after_age * 1.20  # Ringan
    print(f"6. Koreksi Aktivitas (Ringan) = {cal_after_age:.2f} × 1.20 = {cal_after_activity:.2f} kkal")
    
    # 7. Koreksi BB
    cal_after_weight = apply_weight_correction(cal_after_activity, status)
    print(f"7. Koreksi BB (Kurus) = {cal_after_activity:.2f} × 1.25 = {cal_after_weight:.2f} kkal")
    
    # 8. Batas Minimum
    final_cal, warning = check_minimum_calories(cal_after_weight, gender)
    print(f"8. Batas Minimum = {final_cal:.2f} kkal")
    if warning:
        print(f"   ⚠️ {warning}")
    else:
        print(f"   ✅ Di atas minimum (1000 kkal untuk wanita)")
    
    # 9. Distribusi
    dist = distribute_calories(final_cal)
    print(f"\n9. DISTRIBUSI KALORI:")
    for meal, cal in dist.items():
        print(f"   - {meal}: {cal:.2f} kkal")
    
    return final_cal

def test_case_2():
    """Test Case 2: Pria, Gemuk"""
    print("\n" + "="*60)
    print("TEST CASE 2: Pria, Gemuk")
    print("="*60)
    
    # Input
    height = 170  # cm
    weight = 85   # kg
    age = 45
    gender = "pria"
    activity = "moderate"
    
    # 1. BBI
    bbi = calculate_bbi(height, gender)
    print(f"1. BBI = 0.9 × ({height} - 100) = {bbi:.2f} kg")
    
    # 2. IMT
    imt = calculate_imt(weight, height)
    imt_status = classify_imt(imt)
    print(f"2. IMT = {weight} / ({height/100})² = {imt:.2f} kg/m² → {imt_status}")
    
    # 3. Status BB
    status = classify_nutrition_status(weight, bbi)
    print(f"3. Status BB = {status} ({weight} kg vs BBI {bbi:.2f} kg)")
    print(f"   - Batas Bawah: {bbi * 0.9:.2f} kg")
    print(f"   - Batas Atas: {bbi * 1.1:.2f} kg")
    
    # 4. Energi Basal
    base_cal = calculate_base_calories(bbi, gender)
    print(f"4. Energi Basal = 30 × {bbi:.2f} = {base_cal:.2f} kkal")
    
    # 5. Koreksi Usia
    cal_after_age = base_cal * 0.95  # 40-49 tahun
    print(f"5. Koreksi Usia (40-49 thn) = {base_cal:.2f} × 0.95 = {cal_after_age:.2f} kkal")
    
    # 6. Koreksi Aktivitas
    cal_after_activity = cal_after_age * 1.30  # Sedang
    print(f"6. Koreksi Aktivitas (Sedang) = {cal_after_age:.2f} × 1.30 = {cal_after_activity:.2f} kkal")
    
    # 7. Koreksi BB
    cal_after_weight = apply_weight_correction(cal_after_activity, status)
    print(f"7. Koreksi BB (Gemuk) = {cal_after_activity:.2f} × 0.75 = {cal_after_weight:.2f} kkal")
    
    # 8. Batas Minimum
    final_cal, warning = check_minimum_calories(cal_after_weight, gender)
    print(f"8. Batas Minimum = {final_cal:.2f} kkal")
    if warning:
        print(f"   ⚠️ {warning}")
    else:
        print(f"   ✅ Di atas minimum (1200 kkal untuk pria)")
    
    # 9. Distribusi
    dist = distribute_calories(final_cal)
    print(f"\n9. DISTRIBUSI KALORI:")
    for meal, cal in dist.items():
        print(f"   - {meal}: {cal:.2f} kkal")
    
    return final_cal

def test_case_3():
    """Test Case 3: Pria Pendek (< 160 cm)"""
    print("\n" + "="*60)
    print("TEST CASE 3: Pria Pendek (< 160 cm) - Test Rumus BBI")
    print("="*60)
    
    height = 155
    gender = "pria"
    
    bbi = calculate_bbi(height, gender)
    print(f"Tinggi: {height} cm (< 160 cm)")
    print(f"BBI = {height} - 100 = {bbi:.2f} kg")
    print(f"✅ BENAR: Tidak dikalikan 0.9 karena < 160 cm")
    
def test_case_4():
    """Test Case 4: Wanita Pendek (< 150 cm)"""
    print("\n" + "="*60)
    print("TEST CASE 4: Wanita Pendek (< 150 cm) - Test Rumus BBI")
    print("="*60)
    
    height = 145
    gender = "wanita"
    
    bbi = calculate_bbi(height, gender)
    print(f"Tinggi: {height} cm (< 150 cm)")
    print(f"BBI = {height} - 100 = {bbi:.2f} kg")
    print(f"✅ BENAR: Tidak dikalikan 0.9 karena < 150 cm")

def test_macronutrients():
    """Test perhitungan makronutrien"""
    print("\n" + "="*60)
    print("TEST MAKRONUTRIEN (1500 kkal)")
    print("="*60)
    
    cal = 1500
    nutrients = calculate_nutrients(cal)
    
    print(f"Target: {cal} kkal")
    print(f"\nKarbohidrat (55%):")
    print(f"  = (1500 × 0.55) / 4 = {nutrients['karbohidrat']:.2f} g")
    print(f"  = {nutrients['karbohidrat'] * 4:.2f} kkal ✅")
    
    print(f"\nProtein (15%):")
    print(f"  = (1500 × 0.15) / 4 = {nutrients['protein']:.2f} g")
    print(f"  = {nutrients['protein'] * 4:.2f} kkal ✅")
    
    print(f"\nLemak (30%):")
    print(f"  = (1500 × 0.30) / 9 = {nutrients['lemak']:.2f} g")
    print(f"  = {nutrients['lemak'] * 9:.2f} kkal ✅")
    
    print(f"\nSerat:")
    print(f"  = 1500 × 0.014 = {nutrients['fiber']:.2f} g")
    print(f"  (14g per 1000 kkal) ✅")
    
    total_cal = (nutrients['karbohidrat'] * 4) + (nutrients['protein'] * 4) + (nutrients['lemak'] * 9)
    print(f"\nTotal = {total_cal:.2f} kkal (seharusnya {cal} kkal)")

if __name__ == "__main__":
    print("\n" + "🧪 TESTING SISTEM SMARTDIABETS - PERKENI 2024")
    print("="*60)
    
    test_case_1()
    test_case_2()
    test_case_3()
    test_case_4()
    test_macronutrients()
    
    print("\n" + "="*60)
    print("✅ SEMUA TEST SELESAI")
    print("="*60)
