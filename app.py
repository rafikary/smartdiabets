from flask import Flask, render_template, request
from model import generate_recommendations_per_jadwal  # Mengimpor fungsi dari model.py
from datetime import datetime
import logging
import numpy as np

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Fungsi untuk menghitung BBI (Broca)
def calculate_bbi(height, gender):
    logger.debug(f"Calculating BBI for height={height}, gender={gender}")
    if (gender == "pria" and height >= 160) or (gender == "wanita" and height >= 150):
        return 0.9 * (height - 100)
    return height - 100

# Fungsi untuk klasifikasi status gizi
def classify_nutrition_status(weight, bbi):
    percentage = (weight / bbi) * 100
    logger.debug(f"Nutrition status: weight={weight}, bbi={bbi}, percentage={percentage}")
    if percentage < 90:
        return "Kurus", percentage
    elif 90 <= percentage <= 110:
        return "Normal", percentage
    else:
        return "Gemuk", percentage

# Fungsi untuk menghitung kalori dasar (PERKENI)
def calculate_base_calories(bbi, gender):
    calories = bbi * 30 if gender == "pria" else bbi * 25
    logger.debug(f"Base calories: bbi={bbi}, gender={gender}, calories={calories}")
    return calories

# Fungsi untuk koreksi usia dan aktivitas
def apply_corrections(calories, age, activity):
    logger.debug(f"Applying corrections: calories={calories}, age={age}, activity={activity}")
    # Koreksi usia
    if 40 <= age <= 49:
        calories *= 0.95
    elif 50 <= age <= 69:
        calories *= 0.90
    elif age > 70:
        calories *= 0.80
    # Koreksi aktivitas
    activity_corrections = {
        "rest": 1.1,
        "light": 1.2,
        "moderate": 1.3,
        "heavy": 1.4,
        "very_heavy": 1.5
    }
    return calories * activity_corrections[activity]

# Fungsi untuk cek batas minimum kalori
def check_minimum_calories(calories, gender, activity):
    logger.debug(f"Checking minimum calories: calories={calories}, gender={gender}, activity={activity}")
    min_calories = {"pria": (1200, 1600), "wanita": (1000, 1200)}
    low, high = min_calories[gender]
    if calories < low:
        warning = f"Kebutuhan kalori asli ({calories:.1f} kalori) di bawah batas minimum ({low}–{high} kalori untuk {gender})."
        if activity in ["moderate", "heavy", "very_heavy"]:
            return high, warning
        return low, warning
    return calories, None

# Fungsi untuk distribusi kalori ke jadwal (Diet 3J)
def distribute_calories(calories):
    distribution = {
        "Pagi": calories * 0.2,
        "Siang": calories * 0.3,
        "Sore/Malam": calories * 0.25,
        "Snack 1": calories * 0.1,
        "Snack 2": calories * 0.15
    }
    logger.debug(f"Distribution: {distribution}")
    return distribution

# Fungsi untuk menghitung gizi per jadwal
def calculate_nutrients(calories):
    return {
        "karbohidrat": (calories * 0.6) / 4,  # 60%
        "lemak": (calories * 0.25) / 9,       # 25%
        "protein": (calories * 0.15) / 4,      # 15%
        "fiber": (calories * 0.014)  
    }

# Fungsi untuk menghitung RMSE (ini masih untuk rmse saja)
def calculate_rmse(actual_values, predicted_values):
    differences = np.array(actual_values) - np.array(predicted_values)  # Selisih antara nilai aktual dan nilai prediksi
    squared_differences = differences ** 2  # Kuadratkan selisihnya
    mean_squared_difference = squared_differences.mean()  # Rata-rata kuadrat selisih
    rmse = np.sqrt(mean_squared_difference)  # Akar kuadrat dari rata-rata kuadrat selisih
    return rmse

def sum_meal_nutrients(meal_list):
    total = {"kalori": 0, "protein": 0, "lemak": 0, "karbohidrat": 0, "serat": 0}
    for food in meal_list:
        for kategori in ['Pokok', 'Lauk', 'Sayur', 'Buah']:
            if food.get(kategori):
                total["kalori"] += food[kategori].get("calories", 0)
                total["protein"] += food[kategori].get("protein", 0)
                total["lemak"] += food[kategori].get("lemak", 0)
                total["karbohidrat"] += food[kategori].get("carbs", 0)
                total["serat"] += food[kategori].get("fiber", 0)
    return total

# Route utama
@app.route('/')
def home():
    logger.debug("Accessing home route")
    return render_template('index.html')

# Route untuk form kalkulator
@app.route('/calculator')
def calculator():
    logger.debug("Accessing calculator route")
    return render_template('calculator.html')

# Route untuk hasil perhitungan
@app.route('/outputs', methods=['POST'])
def output():
    try:
        logger.debug("Processing outputs route")
        
        # Input dari form
        name = request.form['name']
        age = int(request.form['age'])
        gender = request.form['gender']
        weight = float(request.form['weight'])
        height = float(request.form['height'])
        activity_level = request.form['activity']

        # Perhitungan kalori
        bbi = calculate_bbi(height, gender)
        status, percentage = classify_nutrition_status(weight, bbi)
        base_calories = calculate_base_calories(bbi, gender)
        calories = apply_corrections(base_calories, age, activity_level)
        final_calories, warning = check_minimum_calories(calories, gender, activity_level)

        # Distribusi kalori per jadwal (setelah koreksi minimum)
        distribution = distribute_calories(final_calories)
        # Nutrisi aktual per jadwal (setelah koreksi minimum)
        nutrients = {meal_time: calculate_nutrients(cal) for meal_time, cal in distribution.items()}

        # Menyusun jadwal nutrisi berdasarkan distribusi kalori dan gizi
        jadwal_nutrients_dict = {
            'Pagi': {
                'Energi (kal)': distribution['Pagi'],
                'Protein (g)': nutrients['Pagi']['protein'],
                'Lemak (g)': nutrients['Pagi']['lemak'],
                'Karbohidrat (g)': nutrients['Pagi']['karbohidrat'],
                'Serat (g)': nutrients['Pagi']['fiber']
            },
            'Siang': {
                'Energi (kal)': distribution['Siang'],
                'Protein (g)': nutrients['Siang']['protein'],
                'Lemak (g)': nutrients['Siang']['lemak'],
                'Karbohidrat (g)': nutrients['Siang']['karbohidrat'],
                'Serat (g)': nutrients['Siang']['fiber']
            },
            'Sore/Malam': {
                'Energi (kal)': distribution['Sore/Malam'],
                'Protein (g)': nutrients['Sore/Malam']['protein'],
                'Lemak (g)': nutrients['Sore/Malam']['lemak'],
                'Karbohidrat (g)': nutrients['Sore/Malam']['karbohidrat'],
                'Serat (g)': nutrients['Sore/Malam']['fiber']
            },
            'Snack 1': {
                'Energi (kal)': distribution['Snack 1'],
                'Protein (g)': nutrients['Snack 1']['protein'],
                'Lemak (g)': nutrients['Snack 1']['lemak'],
                'Karbohidrat (g)': nutrients['Snack 1']['karbohidrat'],
                'Serat (g)': nutrients['Snack 1']['fiber']
            },
            'Snack 2': {
                'Energi (kal)': distribution['Snack 2'],
                'Protein (g)': nutrients['Snack 2']['protein'],
                'Lemak (g)': nutrients['Snack 2']['lemak'],
                'Karbohidrat (g)': nutrients['Snack 2']['karbohidrat'],
                'Serat (g)': nutrients['Snack 2']['fiber']
            }
        }

        # Mengambil rekomendasi makanan dari model.py
        raw_file = 'clean_food_processed_no_scaling.xlsx'
        norm_pickle = 'data_normalized.pkl'
        scaler_pickle = 'minmax_scaler.pkl'
        recommendations = generate_recommendations_per_jadwal(raw_file, norm_pickle, scaler_pickle, jadwal_nutrients_dict)

        # === Evaluasi RMSE antara kebutuhan gizi (target) dan total gizi makanan rekomendasi (realisasi) ===
        rmse_per_jadwal = {}
        for meal_time in distribution:
            total_meal = sum_meal_nutrients(recommendations[meal_time])
            target = nutrients[meal_time]
            rmse_per_jadwal[meal_time] = {
                "kalori": calculate_rmse([total_meal["kalori"]], [distribution[meal_time]]),
                "protein": calculate_rmse([total_meal["protein"]], [target["protein"]]),
                "lemak": calculate_rmse([total_meal["lemak"]], [target["lemak"]]),
                "karbohidrat": calculate_rmse([total_meal["karbohidrat"]], [target["karbohidrat"]]),
                "serat": calculate_rmse([total_meal["serat"]], [target["fiber"]])
            }

        print("=== RMSE Evaluasi Rekomendasi ===")
        for meal_time, nilai in rmse_per_jadwal.items():
            print(f"RMSE {meal_time}:")
            print(f"  Kalori: {nilai['kalori']:.2f}")
            print(f"  Protein: {nilai['protein']:.2f}")
            print(f"  Lemak: {nilai['lemak']:.2f}")
            print(f"  Karbohidrat: {nilai['karbohidrat']:.2f}")
            print(f"  Serat: {nilai['serat']:.2f}")

        # Format tanggal
        date_today = datetime.now().strftime("%d %B %Y")

        # Format tampilan untuk front-end
        gender_display = "Laki-laki" if gender == "pria" else "Perempuan"
        activity_display = {
            "rest": "Istirahat",
            "light": "Ringan",
            "moderate": "Sedang",
            "heavy": "Berat",
            "very_heavy": "Sangat Berat"
        }[activity_level]

        # Kirim data ke outputs.html TANPA hasil evaluasi RMSE
        return render_template('outputs.html', 
                              name=name,
                              age=age,
                              gender_display=gender_display,
                              weight=weight,
                              height=height,
                              activity_level=activity_display,
                              caloric_needs=final_calories,
                              date_today=date_today,
                              status=status,
                              percentage=percentage,
                              warning=warning,
                              bbi=bbi,
                              distribution=distribution,
                              nutrients=nutrients,
                              meals=recommendations)

    except Exception as e:
        logger.error(f"Error in outputs route: {str(e)}")
        return f"Error: {str(e)}", 500


if __name__ == "__main__":
    logger.info("Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=5000)
