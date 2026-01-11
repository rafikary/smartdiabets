from flask import Flask, render_template, request
from model import generate_recommendations_per_jadwal
from datetime import datetime
import logging
import numpy as np
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

VALID_ACT = {"rest", "light", "moderate", "heavy", "very_heavy"}

# mapping dari value form (indo / english) ke internal code
ACTIVITY_MAP = {
    # sangat ringan / istirahat
    "istirahat": "rest",
    "sangat_ringan": "rest",
    "rest": "rest",

    # ringan
    "ringan": "light",
    "light": "light",

    # sedang
    "sedang": "moderate",
    "moderate": "moderate",

    # berat
    "berat": "heavy",
    "heavy": "heavy",

    # sangat berat
    "sangat_berat": "very_heavy",
    "very_heavy": "very_heavy",
}

#Normalisasi input aktivitas dari form ke kode internal (rest/light/moderate/heavy/very_heavy)
def normalize_activity(raw: str) -> str:
    if not raw:
        return "light"
    raw = raw.strip().lower()
    act = ACTIVITY_MAP.get(raw, raw)
    return act if act in VALID_ACT else "light"

#Cek keberadaan file yang diperlukan
def ensure_files(*paths: str):
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"File hilang: {', '.join(missing)}")

#Ambil data alergi dari form (checkbox atau toggle)
def parse_allergies(form) -> list:
    kw_check = ['kacang', 'susu', 'seafood', 'telur', 'kedelai', 'gluten']
    from_checkboxes = [a.strip().lower()
                       for a in form.getlist('allergies') if a.strip()]
    from_toggles = [k for k in kw_check if form.get(f'allergy_{k}') == 'on']
    merged = from_checkboxes + from_toggles

    seen = set()
    cleaned = []
    for x in merged:
        t = x.strip().lower()
        if t and t not in seen:
            seen.add(t)
            cleaned.append(t)

    logger.debug(f"Allergies parsed: {cleaned}")
    return cleaned

#Parse makanan yang dikecualikan dari form (untuk fitur Ganti Menu)
def parse_exclude_foods(form) -> list:
    raw = form.get('exclude_foods', '')
    parts = [p.strip() for p in raw.split(',')] if raw else []
    seen, out = set(), []
    for p in parts:
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    logger.debug(f"Exclude foods parsed: {out}")
    return out

#Hitung Berat Badan Ideal dengan Rumus Broca (Pria: 0.9×(TB-100), Wanita: 0.85×(TB-100))
def calculate_bbi(height: float, gender: str) -> float:
    if gender == "pria":
        return 0.9 * (height - 100)
    else:
        return 0.85 * (height - 100)

#Klasifikasi status gizi berdasarkan %BB/BBI (<90%: Kurus, 90-110%: Normal, >110%: Gemuk)
def classify_nutrition_status(weight: float, bbi: float):
    percentage = (weight / bbi) * 100 if bbi > 0 else 0
    if percentage < 90:
        return "Kurus", percentage
    elif 90 <= percentage <= 110:
        return "Normal", percentage
    return "Gemuk", percentage

#Hitung energi basal (Pria: 30×BBI, Wanita: 25×BBI kkal/hari)
def calculate_base_calories(bbi: float, gender: str) -> float:
    return bbi * (30 if gender == "pria" else 25)

#Koreksi kalori berdasarkan usia dan tingkat aktivitas fisik (PAL)
def apply_corrections(calories: float, age: int, activity: str) -> float:
    
    if age < 40:
        calories *= 1.00
    elif 40 <= age < 50:
        calories *= 0.95
    elif 50 <= age < 60:
        calories *= 0.90
    elif 60 <= age < 70:
        calories *= 0.85
    else:
        calories *= 0.80

    pal_values = {
        "rest": 1.20,
        "light": 1.375,
        "moderate": 1.55,
        "heavy": 1.725,
        "very_heavy": 1.90,
    }
    act_norm = normalize_activity(activity)
    return calories * pal_values.get(act_norm, 1.375)

#Cek dan enforce batas minimum kalori aman (Wanita: 1000-1200, Pria: 1200-1600 kkal)
def check_minimum_calories(calories: float, gender: str):
    min_cal = {"pria": (1200, 1600), "wanita": (1000, 1200)}
    low, high = min_cal[gender]
    warning = None

    if calories < low:
        warning = (
            f"Kebutuhan kalori terhitung {calories:.1f} kkal, "
            f"di bawah batas minimum aman ({low}–{high} kkal untuk {gender}). "
            f"Disesuaikan ke {low} kkal."
        )
        calories = low
    elif calories < high:
        warning = (
            f"Kebutuhan kalori berada di batas bawah rentang aman "
            f"({low}–{high} kkal untuk {gender})."
        )

    return calories, warning

#Distribusi kalori ke 5 jadwal makan (Pagi 20%, Siang 30%, Sore 25%, Snack1 10%, Snack2 15%)
def distribute_calories(cal: float) -> dict:
    return {
        "Pagi": cal * 0.20,
        "Siang": cal * 0.30,
        "Sore/Malam": cal * 0.25,
        "Snack 1": cal * 0.10,
        "Snack 2": cal * 0.15,
    }

#Hitung target makronutrien per jadwal (Karbo 55%, Protein 15%, Lemak 30%, Serat 14g/1000kkal)
def calculate_nutrients(cal: float) -> dict:
    return {
        "karbohidrat": (cal * 0.55) / 4.0,
        "protein": (cal * 0.15) / 4.0,
        "lemak": (cal * 0.30) / 9.0,
        "fiber": (cal * 0.014),
    }

#Hitung RMSE untuk evaluasi akurasi nutrisi
def calculate_rmse(actual_values, predicted_values) -> float:
    diff = np.array(actual_values) - np.array(predicted_values)
    return float(np.sqrt((diff ** 2).mean()))

#Jumlahkan nutrisi total dari semua makanan dalam menu
def sum_meal_nutrients(meal_list: list) -> dict:
    total = {"kalori": 0.0, "protein": 0.0,
             "lemak": 0.0, "karbohidrat": 0.0, "serat": 0.0}
    for food in meal_list:
        for kat in ['Pokok', 'Lauk', 'Sayur', 'Buah']:
            item = food.get(kat)
            if not item:
                continue
            total["kalori"] += float(item.get("calories", 0) or 0)
            total["protein"] += float(item.get("protein", 0) or 0)
            total["lemak"] += float(item.get("fat", 0) or 0)
            total["karbohidrat"] += float(item.get("carbs", 0) or 0)
            total["serat"] += float(item.get("fiber", 0) or 0)
    return total

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/calculator')
def calculator():
    return render_template('calculator.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/outputs', methods=['POST'])
def output():
    try:
        name = request.form['name']
        age = int(request.form['age'])
        gender = request.form['gender']
        weight = float(request.form['weight'])
        height = float(request.form['height'])

        act_raw = request.form['activity']
        activity_level = normalize_activity(act_raw)

        allergies = parse_allergies(request.form)
        exclude_foods = parse_exclude_foods(request.form)
        swap_meal = request.form.get('swap_meal', '')

        bbi = calculate_bbi(height, gender)
        status, percentage = classify_nutrition_status(weight, bbi)
        base_calories = calculate_base_calories(bbi, gender)
        calories = apply_corrections(base_calories, age, activity_level)
        final_calories, warning = check_minimum_calories(calories, gender)

        distribution = distribute_calories(final_calories)
        nutrients = {mt: calculate_nutrients(kal) for mt, kal in distribution.items()}

        jadwal_nutrients_dict = {
            mt: {
                'Energi (kal)': distribution[mt],
                'Protein (g)': nutrients[mt]['protein'],
                'Lemak (g)': nutrients[mt]['lemak'],
                'Karbohidrat (g)': nutrients[mt]['karbohidrat'],
                'Serat (g)': nutrients[mt]['fiber'],
            } for mt in distribution.keys()
        }

        raw_file = 'clean_food_processed_no_scaling.xlsx'
        ensure_files(raw_file)

        try:
            meals = generate_recommendations_per_jadwal(
                raw_file, jadwal_nutrients_dict,
                allergies=allergies,
                exclude_foods=exclude_foods
            )
        except TypeError:
            meals = generate_recommendations_per_jadwal(
                raw_file, jadwal_nutrients_dict
            )

        rmse_per_jadwal = {}
        for mt in distribution:
            total_meal = sum_meal_nutrients(meals.get(mt, []))
            target = nutrients[mt]
            rmse_per_jadwal[mt] = {
                "kalori": calculate_rmse(
                    [total_meal["kalori"]], [distribution[mt]]),
                "protein": calculate_rmse(
                    [total_meal["protein"]], [target["protein"]]),
                "lemak": calculate_rmse(
                    [total_meal["lemak"]], [target["lemak"]]),
                "karbohidrat": calculate_rmse(
                    [total_meal["karbohidrat"]], [target["karbohidrat"]]),
                "serat": calculate_rmse(
                    [total_meal["serat"]], [target["fiber"]]),
            }

        for mt, v in rmse_per_jadwal.items():
            logger.info(
                f"RMSE {mt}: Kal {v['kalori']:.2f} Prot {v['protein']:.2f} "
                f"Lem {v['lemak']:.2f} Karbo {v['karbohidrat']:.2f} Serat {v['serat']:.2f}"
            )

        date_today = datetime.now().strftime("%d %B %Y")
        gender_display = "Laki-laki" if gender == "pria" else "Perempuan"
        activity_display_map = {
            "rest": "Istirahat",
            "light": "Ringan",
            "moderate": "Sedang",
            "heavy": "Berat",
            "very_heavy": "Sangat Berat",
        }
        activity_display = activity_display_map.get(activity_level, "Ringan")

        active_meal = swap_meal if swap_meal else 'Pagi'
        exclude_foods_str = ', '.join(exclude_foods)

        return render_template(
            'outputs.html',
            name=name,
            age=age,
            gender_display=gender_display,
            weight=weight,
            height=height,
            activity_level=activity_display,
            date_today=date_today,
            bbi=bbi,
            status=status,
            percentage=percentage,
            caloric_needs=final_calories,
            warning=warning,
            distribution=distribution,
            nutrients=nutrients,
            meals=meals,
            allergies=allergies,
            exclude_foods=exclude_foods_str,
            active_meal=active_meal,
            rmse_per_jadwal=rmse_per_jadwal,
        )

    except Exception as e:
        logger.exception("Error in outputs route")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    logger.info("Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=5000)
