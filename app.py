from flask import Flask, render_template, request
from model import generate_recommendations_per_jadwal
from datetime import datetime
import logging
import numpy as np
import os
from flask_login import LoginManager, login_required, current_user
from database import db, init_db, User
from admin_routes import admin_bp
from user_routes import user_bp

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Konfigurasi Flask
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'  # GANTI dengan random string!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartdiabetes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inisialisasi database
init_db(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'user.login'
login_manager.login_message = None  # Hilangkan flash message otomatis

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)

VALID_ACT = {"rest", "light", "moderate", "heavy", "very_heavy"}

# mapping dari value form (indo / english) ke internal code
ACTIVITY_MAP = {
    # istirahat / sangat ringan
    "istirahat": "rest",
    "sangat_ringan": "rest",
    "sedentary": "rest",
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
    "active": "heavy",

    # sangat berat
    "sangat_berat": "very_heavy",
    "very_heavy": "very_heavy",
    "very_active": "very_heavy",
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

#Hitung Berat Badan Ideal dengan Rumus Broca sesuai PERKENI 2024
def calculate_bbi(height: float, gender: str) -> float:
    # Rumus Broca (PERKENI 2024):
    # - Laki-laki ≥ 160 cm dan perempuan ≥ 150 cm: BBI = 0.9 × (TB - 100)
    # - Di bawah ambang tersebut: BBI = (TB - 100)
    if gender == "pria":
        if height >= 160:
            return 0.9 * (height - 100)
        else:
            return height - 100
    else:  # wanita
        if height >= 150:
            return 0.9 * (height - 100)
        else:
            return height - 100

#Hitung IMT (Indeks Massa Tubuh) sesuai PERKENI 2024
def calculate_imt(weight: float, height: float) -> float:
    # IMT = BB / (TB^2)
    # BB dalam kg, TB dalam meter
    height_m = height / 100.0
    return weight / (height_m ** 2)

#Klasifikasi IMT berdasarkan standar Asia-Pasifik (PERKENI 2024)
def classify_imt(imt: float) -> str:
    # Klasifikasi IMT (Asia-Pasifik):
    # BB kurang: < 18.5 kg/m²
    # BB normal: 18.5–22.9 kg/m²
    # BB lebih: ≥ 23.0 kg/m²
    #   - Risiko meningkat: 23.0–24.9 kg/m²
    #   - Obesitas I: 25.0–29.9 kg/m²
    #   - Obesitas II: ≥ 30.0 kg/m²
    if imt < 18.5:
        return "BB Kurang"
    elif 18.5 <= imt < 23.0:
        return "BB Normal"
    elif 23.0 <= imt < 25.0:
        return "BB Lebih (Risiko Meningkat)"
    elif 25.0 <= imt < 30.0:
        return "Obesitas I"
    else:
        return "Obesitas II"

#Klasifikasi status gizi berdasarkan BBI±10% (PERKENI 2024)
def classify_nutrition_status(weight: float, bbi: float):
    # Status berat badan berdasarkan BBI:
    # BB Normal: BBI ± 10%
    # Kurus: BB < (BBI - 10%)
    # Gemuk: BB > (BBI + 10%)
    lower_bound = bbi * 0.9  # BBI - 10%
    upper_bound = bbi * 1.1  # BBI + 10%
    
    if weight < lower_bound:
        return "Kurus"
    elif lower_bound <= weight <= upper_bound:
        return "Normal"
    else:
        return "Gemuk"

#Hitung energi basal (Pria: 30×BBI, Wanita: 25×BBI kkal/hari)
def calculate_base_calories(bbi: float, gender: str) -> float:
    # Kalori Basal berdasarkan jenis kelamin:
    # Pria   : BMR = 30 kkal/kg × BBI
    # Wanita : BMR = 25 kkal/kg × BBI
    return bbi * (30 if gender == "pria" else 25)

#Koreksi kalori berdasarkan status berat badan (kurus: +20-30%, gemuk: -20-30%)
def apply_weight_correction(calories: float, status: str) -> float:
    # Koreksi berat badan sesuai PERKENI 2024:
    # - Gemuk: pengurangan ~20-30% (gunakan -25% sebagai nilai tengah)
    # - Kurus: penambahan ~20-30% (gunakan +25% sebagai nilai tengah)
    # - Normal: tidak ada penyesuaian
    if status == "Gemuk":
        return calories * 0.75  # Kurangi 25%
    elif status == "Kurus":
        return calories * 1.25  # Tambah 25%
    else:
        return calories  # Normal: tidak ada koreksi

#Koreksi kalori berdasarkan usia dan tingkat aktivitas fisik sesuai PERKENI 2024
def apply_corrections(calories: float, age: int, activity: str) -> float:
    # LANGKAH 1: Koreksi Umur (F_usia)
    # Metabolisme menurun seiring bertambahnya usia
    # E_usia = BMR × F_usia
    if age < 40:
        calories *= 1.00      # Tidak ada koreksi
    elif 40 <= age < 50:
        calories *= 0.95      # Kurangi 5%
    elif 50 <= age < 60:
        calories *= 0.90      # Kurangi 10%
    elif 60 <= age < 70:
        calories *= 0.90      # Kurangi 10%
    else:  # >= 70 tahun
        calories *= 0.80      # Kurangi 20%

    # LANGKAH 2: Tabel 2.2 - Koreksi Aktivitas Fisik (F_akt)
    # Tambahkan kebutuhan energi berdasarkan tingkat aktivitas fisik
    # E_aktiv = E_usia × F_akt
    f_akt_values = {
        "rest": 1.10,        # Istirahat: +10%
        "light": 1.20,       # Ringan: +20%
        "moderate": 1.30,    # Sedang: +30%
        "heavy": 1.40,       # Berat: +40%
        "very_heavy": 1.50,  # Sangat berat: +50%
    }
    act_norm = normalize_activity(activity)
    return calories * f_akt_values.get(act_norm, 1.20)

#Cek dan enforce batas minimum kalori aman sesuai PERKENI 2024
def check_minimum_calories(calories: float, gender: str):
    # Batas minimum PERKENI 2024:
    # Wanita: min 1000 kkal/hari
    # Pria: min 1200 kkal/hari
    min_cal = {"pria": 1200, "wanita": 1000}
    minimum = min_cal[gender]
    warning = None

    if calories < minimum:
        warning = (
            f"⚠️ Kebutuhan kalori hasil perhitungan ({calories:.0f} kkal) "
            f"di bawah batas minimum aman ({minimum} kkal untuk {gender}). "
            f"Kalori dinaikkan ke {minimum} kkal untuk menjaga keamanan nutrisi."
        )
        calories = minimum

    return calories, warning

#Distribusi kalori ke 5 jadwal makan (Pagi 20%, Siang 30%, Sore 25%, Snack1 10%, Snack2 15%)
def distribute_calories(cal: float) -> dict:
    # Distribusi proporsi kalori per jadwal makan:
    # Total harus = 100% (0.20 + 0.30 + 0.25 + 0.10 + 0.15 = 1.00)
    return {
        "Pagi": cal * 0.20,         # 20% - Sarapan
        "Siang": cal * 0.30,        # 30% - Makan siang (porsi terbesar)
        "Sore/Malam": cal * 0.25,   # 25% - Makan malam
        "Snack 1": cal * 0.10,      # 10% - Snack pagi
        "Snack 2": cal * 0.15,      # 15% - Snack sore
    }

#Hitung target makronutrien per jadwal (Karbo 55%, Protein 15%, Lemak 30%, Serat 14g/1000kkal)
def calculate_nutrients(cal: float) -> dict:
    # Konversi kalori ke gram makronutrien:
    # Karbohidrat: 55% kalori, 1g = 4 kkal → gram = (kalori × 0.55) / 4
    # Protein    : 15% kalori, 1g = 4 kkal → gram = (kalori × 0.15) / 4
    # Lemak      : 30% kalori, 1g = 9 kkal → gram = (kalori × 0.30) / 9
    # Serat      : 14g per 1000 kkal → gram = kalori × 0.014
    return {
        "karbohidrat": (cal * 0.55) / 4.0,  # 55% energi dari karbo
        "protein": (cal * 0.15) / 4.0,      # 15% energi dari protein
        "lemak": (cal * 0.30) / 9.0,        # 30% energi dari lemak
        "fiber": (cal * 0.014),             # 14g per 1000 kkal
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

@app.route('/blog/diet-3j')
def blog_article_diet_3j():
    return render_template('blog/diet-3j.html')

@app.route('/blog/porsi-nasi')
def blog_article_porsi_nasi():
    return render_template('blog/porsi-nasi.html')

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
        
        # Get number of days for recommendations
        num_days = int(request.form.get('days', 1))
        
        # Get current day index (for multi-day navigation persistence)
        current_day = int(request.form.get('current_day', 0))

        # 1. Hitung BBI (Broca)
        bbi = calculate_bbi(height, gender)
        
        # 2. Hitung IMT dan klasifikasi
        imt = calculate_imt(weight, height)
        imt_status = classify_imt(imt)
        
        # 3. Klasifikasi status berat badan berdasarkan BBI
        status = classify_nutrition_status(weight, bbi)
        
        # Hitung persentase berat badan terhadap BBI
        percentage = (weight / bbi) * 100 if bbi > 0 else 100
        
        # 4. Hitung energi basal
        base_calories = calculate_base_calories(bbi, gender)
        
        # 5. Koreksi usia dan aktivitas
        calories = apply_corrections(base_calories, age, activity_level)
        
        # 6. Koreksi berat badan (kurus/gemuk)
        calories = apply_weight_correction(calories, status)
        
        # 7. Enforce batas minimum klinis
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

        # Generate recommendations for multiple days
        all_days_meals = []
        all_days_rmse = []
        current_exclude = list(exclude_foods) if exclude_foods else []
        
        for day_num in range(1, num_days + 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Generating menu for Day {day_num}/{num_days}")
            logger.info(f"Current exclude list has {len(current_exclude)} items")
            
            try:
                meals = generate_recommendations_per_jadwal(
                    raw_file, jadwal_nutrients_dict,
                    allergies=allergies,
                    exclude_foods=current_exclude
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
            
            all_days_meals.append(meals)
            all_days_rmse.append(rmse_per_jadwal)
            
            # Extract all food names from this day's meals to exclude in next iteration
            if day_num < num_days:  # No need to extract on last day
                for meal_time, meal_items in meals.items():
                    for meal in meal_items:
                        for category in ['Pokok', 'Lauk', 'Sayur', 'Buah']:
                            food_item = meal.get(category)
                            if food_item and food_item.get('name'):
                                food_name = food_item['name']
                                if food_name not in current_exclude:
                                    current_exclude.append(food_name)
                                    logger.debug(f"Added to exclude list: {food_name}")

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
        exclude_foods_str = ', '.join(exclude_foods) if exclude_foods else ''

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
            imt=imt,
            imt_status=imt_status,
            status=status,
            percentage=percentage,
            caloric_needs=final_calories,
            warning=warning,
            distribution=distribution,
            nutrients=nutrients,
            meals=all_days_meals[0] if num_days == 1 else None,  # Keep compatibility for single day
            all_days_meals=all_days_meals,
            num_days=num_days,
            current_day=current_day,
            allergies=allergies,
            exclude_foods=exclude_foods_str,
            active_meal=active_meal,
            rmse_per_jadwal=all_days_rmse[0] if num_days == 1 else None,  # Keep compatibility
            all_days_rmse=all_days_rmse,
        )

    except Exception as e:
        logger.exception("Error in outputs route")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    logger.info("Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=5000)
