"""
Model Optimasi Menu Diabetes menggunakan Constrained Least Squares

ALGORITMA INTI:
- Mencari porsi (gram) yang meminimalkan error: ||A·x - b||²
- A: Matriks nutrisi per-gram (5 nutrisi × n items)
- x: Vektor porsi (gram) yang dicari
- b: Vektor target nutrisi (Energi, Protein, Lemak, Karbo, Serat)
- Constraint: 20g ≤ x ≤ 400g (porsi realistis)

STRUKTUR MENU (Diet 3J):
- Pagi/Siang: Pokok + Lauk + Sayur (3 items)
- Sore/Malam: Pokok + Lauk + Sayur (3 items)
- Snack 1/2: Buah (1 item)
"""
import pandas as pd
import numpy as np
import json
import re
import logging
from typing import List, Dict, Optional, Tuple
from scipy.optimize import lsq_linear, nnls

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konstanta
FEATURES = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']
MIN_PORTION = 20.0   # Porsi minimum (gram)
MAX_PORTION = 400.0  # Porsi maksimum (gram)

# ==================== PATTERN ALERGEN ====================
ALLERGEN_PATTERNS: Dict[str, str] = {
    'ikan': r'\b(ikan|kakap|tuna|salmon|gurame|lele|nila|tongkol|bandeng|teri|baronang|cakalang|kembung|tenggiri|patin|bawal|mujair|gabus|mas|dori|cod|haddock|mackerel)\b',
    'udang': r'\b(udang|shrimp|rebon|ebi|lobster|kepiting|rajungan|crab)\b',
    'cumi': r'\b(cumi|sotong|squid|octopus|gurita)\b',
    'kerang': r'\b(kerang|tiram|oyster|mussel|scallop|clam)\b',
    'seafood': r'\b(ikan|kakap|tuna|salmon|gurame|lele|nila|tongkol|bandeng|teri|udang|shrimp|rebon|ebi|cumi|sotong|kerang|kepiting|rajungan|lobster|terasi|petis|rumput\s*laut|nori)\b',
    'kacang': r'\b(kacang|peanut|almond|mede|mete|kenari|pistachio|pecan|walnut|cashew|hazelnut|macadamia)\b',
    'kedelai': r'\b(kedelai|soy|tempe|tahu|tofu|kecap|tauco|miso|edamame|shoyu)\b',
    'susu': r'\b(susu|milk|keju|cheese|yogurt|yoghurt|mentega|butter|krim|cream|whey|kasein|laktosa|lactose|kental\s*manis|skim)\b',
    'telur': r'\b(telur|telor|egg|ovum)\b',
    'gandum': r'\b(gandum|wheat|terigu|gluten|roti|mie|mi|pasta|spaghetti|udon|ramen|makaroni|fettuccine|linguine|penne)\b',
    'gluten': r'\b(gandum|wheat|terigu|gluten|roti|mie|mi|pasta|spaghetti|udon|ramen|makaroni|barley|jelai|rye)\b',
}


# ==================== LOAD DATA ====================
def load_raw_data(file_path: str) -> pd.DataFrame:
    """Load data makanan dari Excel dan validasi struktur"""
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        df.columns = df.columns.str.strip()
        
        # Validasi kolom wajib
        required_cols = FEATURES + ['Nama_Bahan', 'Jenis Makanan']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Kolom wajib hilang: {missing}")
        
        # Konversi nutrisi ke numerik
        for col in FEATURES:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        logger.info(f"Loaded {len(df)} food items from {file_path}")
        return df
        
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise


# ==================== FILTER ALERGEN ====================
def compile_allergen_regex(allergies: Optional[List[str]]) -> Optional[str]:
    """Compile pattern regex untuk filter alergen"""
    if not allergies:
        return None
    
    patterns = []
    for allergen in allergies:
        key = allergen.strip().lower()
        if key in ALLERGEN_PATTERNS:
            patterns.append(ALLERGEN_PATTERNS[key])
        else:
            # Fallback: escape user input
            escaped = re.escape(key)
            patterns.append(rf'\b{escaped}\b')
    
    if not patterns:
        return None
    
    combined = '|'.join(f'({p})' for p in patterns)
    logger.debug(f"Compiled allergen regex: {combined[:200]}...")
    return combined


def exclude_allergens(df: pd.DataFrame, 
                     allergies: Optional[List[str]], 
                     col: str = "Nama_Bahan") -> pd.DataFrame:
    """Filter makanan yang mengandung alergen"""
    if not allergies or df.empty:
        return df
    
    pattern = compile_allergen_regex(allergies)
    if pattern is None:
        return df
    
    initial_count = len(df)
    mask = df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    df_filtered = df[~mask].copy()
    
    removed = initial_count - len(df_filtered)
    if removed > 0:
        logger.info(f"Removed {removed} items with allergens: {allergies}")
        if removed <= 5:
            removed_items = df[mask][col].tolist()
            logger.debug(f"Removed items: {removed_items}")
    
    return df_filtered


# ==================== FILTER EXCLUDE FOODS ====================
def exclude_foods(df: pd.DataFrame, 
                 exclude_list: Optional[List[str]], 
                 col: str = "Nama_Bahan") -> pd.DataFrame:
    """
    Filter makanan yang di-exclude user menggunakan keyword matching.
    Contoh: 'ayam' akan memblokir 'ayam goreng', 'rendang ayam', 'sate ayam', dll.
    """
    if not exclude_list or df.empty:
        return df
    
    # Clean dan prepare keywords
    exclude_keywords = [x.strip().lower() for x in exclude_list if x and x.strip()]
    if not exclude_keywords:
        return df
    
    # Build regex pattern dengan word boundaries untuk partial matching
    patterns = []
    for keyword in exclude_keywords:
        # Escape special regex characters, tapi allow partial matching
        escaped = re.escape(keyword)
        # Gunakan word boundary untuk menghindari false positive
        patterns.append(rf'\b{escaped}\b')
    
    # Combine patterns dengan OR operator
    combined_pattern = '|'.join(f'({p})' for p in patterns)
    
    initial_count = len(df)
    # Filter rows yang mengandung keywords
    mask = df[col].astype(str).str.contains(combined_pattern, case=False, regex=True, na=False)
    df_filtered = df[~mask].copy()
    
    removed = initial_count - len(df_filtered)
    if removed > 0:
        logger.info(f"Excluded {removed} items from user preferences: {exclude_keywords}")
        if removed <= 5:
            removed_items = df[mask][col].tolist()
            logger.debug(f"Excluded items: {removed_items}")
    
    return df_filtered


# ==================== CANDIDATE SELECTION ====================
def choose_candidates(raw_df: pd.DataFrame,
                     filters: Dict[str, object],
                     allergies: Optional[List[str]],
                     exclude_list: Optional[List[str]],
                     target_calories: float,
                     k: int = 8,
                     seed: Optional[int] = None) -> pd.DataFrame:
    """
    Hybrid Filtering + Heuristic Ranking untuk pilih kandidat terbaik
    
    Pipeline:
    1. Filter kategori (Jenis Makanan, Tipe Pokok, dll)
    2. Filter alergen
    3. Filter exclude foods
    4. Ranking berdasarkan kedekatan kalori per-100g dengan target
    5. Ambil top-k kandidat
    """
    rng = np.random.default_rng(seed)
    
    # Step 1: Filter kategori
    df = raw_df.copy()
    for col, val in filters.items():
        if isinstance(val, (list, tuple, set)):
            df = df[df[col].isin(list(val))]
        else:
            df = df[df[col] == val]
    
    # Step 2: Filter alergen
    df = exclude_allergens(df, allergies)
    
    # Step 3: Filter exclude foods
    df = exclude_foods(df, exclude_list)
    
    # Fallback: longgarkan filter jika kosong
    if df.empty:
        logger.warning(f"No candidates with filters {filters}. Relaxing filters...")
        
        # Fallback 1: Lepas Tipe Pokok
        if 'Tipe Pokok' in filters:
            relaxed = dict(filters)
            relaxed.pop('Tipe Pokok', None)
            df = raw_df.copy()
            for col, val in relaxed.items():
                if isinstance(val, (list, tuple, set)):
                    df = df[df[col].isin(list(val))]
                else:
                    df = df[df[col] == val]
            df = exclude_allergens(df, allergies)
            df = exclude_foods(df, exclude_list)
        
        # Fallback 2: Lepas Mentahan/Olahan
        if df.empty and 'Mentahan / Olahan' in filters:
            relaxed = dict(filters)
            relaxed.pop('Mentahan / Olahan', None)
            relaxed.pop('Tipe Pokok', None)
            df = raw_df.copy()
            for col, val in relaxed.items():
                if isinstance(val, (list, tuple, set)):
                    df = df[df[col].isin(list(val))]
                else:
                    df = df[df[col] == val]
            df = exclude_allergens(df, allergies)
            df = exclude_foods(df, exclude_list)
    
    if df.empty:
        logger.warning(f"Still no candidates after relaxing. Returning empty.")
        return df
    
    # Step 4: Ranking berdasarkan kedekatan kalori
    df = df.sample(frac=1.0, random_state=int(rng.integers(0, 1_000_000))).reset_index(drop=True)
    df['_cal_score'] = (df['Energi (kal)'] - target_calories) ** 2
    df = df.sort_values('_cal_score', kind='mergesort').head(k).reset_index(drop=True)
    
    logger.debug(f"Selected {len(df)} candidates (target_cal={target_calories:.0f})")
    return df


# ==================== OPTIMIZATION: LEAST SQUARES ====================
def solve_portions_least_squares(items: List[pd.Series], 
                                 target_vec: np.ndarray) -> np.ndarray:
    """
    Constrained Least Squares untuk hitung porsi optimal (gram)
    
    Minimize: ||A·x - b||²
    Subject to: MIN_PORTION ≤ x ≤ MAX_PORTION
    
    Args:
        items: List of food items (Series dengan kolom FEATURES)
        target_vec: Target nutrisi [energi, protein, lemak, karbo, serat]
    
    Returns:
        np.ndarray: Vektor porsi (gram) untuk setiap item
    """
    # Konversi per-100g → per-1g (dibagi 100)
    A = np.column_stack([
        item[FEATURES].astype(float).to_numpy() / 100.0 
        for item in items
    ])
    b = target_vec.astype(float)
    
    n_items = len(items)
    bounds = ([MIN_PORTION] * n_items, [MAX_PORTION] * n_items)
    
    try:
        # Gunakan bounded-variable least squares
        result = lsq_linear(A, b, bounds=bounds, method='bvls', verbose=0)
        x = result.x
        
        # Validasi hasil
        if np.any(np.isnan(x)) or np.any(np.isinf(x)):
            logger.warning("Optimization result contains NaN/Inf. Using NNLS fallback.")
            x_nnls, _ = nnls(A, b)
            x = np.clip(x_nnls, MIN_PORTION, MAX_PORTION)
        
        return x
        
    except Exception as e:
        logger.error(f"Optimization error: {e}. Using equal distribution fallback.")
        # Fallback: bagi rata kalori target
        avg_cal_per_gram = 2.0  # Asumsi rata-rata
        fallback_portion = min(MAX_PORTION, max(MIN_PORTION, target_vec[0] / (n_items * avg_cal_per_gram)))
        return np.full(n_items, fallback_portion)


def single_item_best_portion(item: pd.Series, target_vec: np.ndarray) -> float:
    """
    Closed-form solution untuk single item (Snack: Buah)
    
    Minimize: ||w·x - y||²
    Solution: w = (x·y) / (x·x)
    
    Args:
        item: Food item (Series)
        target_vec: Target nutrisi
    
    Returns:
        float: Porsi optimal (gram)
    """
    x = item[FEATURES].astype(float).to_numpy() / 100.0  # Per-1g
    y = target_vec.astype(float)
    
    x_norm = float(np.dot(x, x))
    if x_norm < 1e-6:
        logger.warning(f"Item '{item.get('Nama_Bahan', 'unknown')}' has near-zero nutrients. Using min portion.")
        return MIN_PORTION
    
    w = float(np.dot(x, y) / x_norm)
    w = max(0.0, w)  # Tidak boleh negatif
    w = float(np.clip(w, MIN_PORTION, MAX_PORTION))
    
    return w


def calculate_rmse(pred: np.ndarray, target: np.ndarray) -> float:
    """Hitung Root Mean Square Error untuk evaluasi"""
    return float(np.sqrt(np.mean((pred - target) ** 2)))


# ==================== GET NUTRITION INFO ====================
def get_food_nutrition(name: str, portion_grams: float, raw_df: pd.DataFrame) -> Dict:
    """Hitung nutrisi makanan berdasarkan porsi"""
    row = raw_df[raw_df['Nama_Bahan'] == name]
    
    if row.empty:
        return {
            "name": name,
            "category": None,
            "portion": round(float(portion_grams), 2),
            "calories": 0.0,
            "carbs": 0.0,
            "protein": 0.0,
            "fat": 0.0,
            "fiber": 0.0
        }
    
    row = row.iloc[0].fillna(0)
    scale = float(portion_grams) / 100.0
    
    return {
        "name": name,
        "category": row.get("Jenis Makanan", None),
        "portion": round(float(portion_grams), 2),
        "calories": round(float(row["Energi (kal)"]) * scale, 2),
        "carbs": round(float(row["Karbohidrat (g)"]) * scale, 2),
        "protein": round(float(row["Protein (g)"]) * scale, 2),
        "fat": round(float(row["Lemak (g)"]) * scale, 2),
        "fiber": round(float(row["Serat (g)"]) * scale, 2)
    }


# ==================== REKOMENDASI PAGI/SIANG ====================
def recommend_morning_afternoon(raw_df: pd.DataFrame,
                                target_vec: np.ndarray,
                                used_foods: set,
                                allergies: Optional[List[str]] = None,
                                exclude_list: Optional[List[str]] = None,
                                seed: Optional[int] = None) -> List[Dict]:
    """
    Rekomendasi Pagi/Siang: Pokok + Lauk + Sayur (3 items)
    
    Algoritma:
    1. Pilih kandidat Pokok, Lauk, Sayur (top-8 terdekat kalori)
    2. Kombinasi 3x3x3 = 27 kombinasi
    3. Solve Least Squares untuk setiap kombinasi
    4. Hitung RMSE
    5. Pilih 1 kombinasi dengan RMSE terkecil
    """
    target_cal = float(target_vec[0])
    base_excl = list(used_foods) + (exclude_list or [])
    
    # Pilih kandidat Pokok (Sederhana)
    pk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Makanan pokok', 'Mentahan / Olahan': 'Olahan', 'Tipe Pokok': 'Sederhana'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    # Pilih kandidat Lauk
    lk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Lauk', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    # Pilih kandidat Sayur
    sy = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Sayur', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    if pk.empty or lk.empty or sy.empty:
        logger.warning("Insufficient candidates for morning/afternoon menu")
        return []
    
    # Kombinasi & Optimasi
    recommendations = []
    foods_used_this_schedule = set()
    
    for _, p in pk.head(3).iterrows():
        for _, l in lk.head(3).iterrows():
            for _, s in sy.head(3).iterrows():
                names = {str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])}
                
                # Skip jika ada duplikasi
                if foods_used_this_schedule.intersection(names) or used_foods.intersection(names):
                    continue
                
                # Solve Least Squares
                items = [p, l, s]
                portions = solve_portions_least_squares(items, target_vec)
                
                # Hitung prediksi nutrisi
                A = np.column_stack([i[FEATURES].astype(float).to_numpy() / 100.0 for i in items])
                pred = A @ portions
                rmse = calculate_rmse(pred, target_vec)
                
                recommendations.append((rmse, p, l, s, portions))
    
    if not recommendations:
        return []
    
    # Ranking: pilih RMSE terkecil
    recommendations.sort(key=lambda x: x[0])
    
    # Ambil 1 terbaik
    rmse, p, l, s, portions = recommendations[0]
    used_foods.update({str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])})
    
    return [{
        "Pokok": get_food_nutrition(p['Nama_Bahan'], portions[0], raw_df),
        "Lauk": get_food_nutrition(l['Nama_Bahan'], portions[1], raw_df),
        "Sayur": get_food_nutrition(s['Nama_Bahan'], portions[2], raw_df),
        "Buah": None,
        "avg_similarity": None,
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== REKOMENDASI SORE/MALAM ====================
def recommend_evening(raw_df: pd.DataFrame,
                     target_vec: np.ndarray,
                     used_foods: set,
                     allergies: Optional[List[str]] = None,
                     exclude_list: Optional[List[str]] = None,
                     seed: Optional[int] = None) -> List[Dict]:
    """
    Rekomendasi Sore/Malam: Pokok + Lauk + Sayur (3 items)
    
    FIX: Sekarang SAMA dengan Pagi/Siang (3 items) untuk nutrisi seimbang
    """
    target_cal = float(target_vec[0])
    base_excl = list(used_foods) + (exclude_list or [])
    
    # Pilih kandidat Pokok
    pk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Makanan pokok', 'Mentahan / Olahan': 'Olahan', 'Tipe Pokok': 'Sederhana'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    # Pilih kandidat Lauk
    lk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Lauk', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    # Pilih kandidat Sayur
    sy = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Sayur', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )
    
    if pk.empty or lk.empty or sy.empty:
        logger.warning("Insufficient candidates for evening menu")
        return []
    
    # Kombinasi & Optimasi (sama dengan Pagi/Siang)
    recommendations = []
    foods_used_this_schedule = set()
    
    for _, p in pk.head(3).iterrows():
        for _, l in lk.head(3).iterrows():
            for _, s in sy.head(3).iterrows():
                names = {str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])}
                
                if foods_used_this_schedule.intersection(names) or used_foods.intersection(names):
                    continue
                
                items = [p, l, s]
                portions = solve_portions_least_squares(items, target_vec)
                
                A = np.column_stack([i[FEATURES].astype(float).to_numpy() / 100.0 for i in items])
                pred = A @ portions
                rmse = calculate_rmse(pred, target_vec)
                
                recommendations.append((rmse, p, l, s, portions))
    
    if not recommendations:
        return []
    
    recommendations.sort(key=lambda x: x[0])
    rmse, p, l, s, portions = recommendations[0]
    used_foods.update({str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])})
    
    return [{
        "Pokok": get_food_nutrition(p['Nama_Bahan'], portions[0], raw_df),
        "Lauk": get_food_nutrition(l['Nama_Bahan'], portions[1], raw_df),
        "Sayur": get_food_nutrition(s['Nama_Bahan'], portions[2], raw_df),
        "Buah": None,
        "avg_similarity": None,
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== REKOMENDASI SNACK ====================
def recommend_snack(raw_df: pd.DataFrame,
                   target_vec: np.ndarray,
                   used_foods: set,
                   allergies: Optional[List[str]] = None,
                   exclude_list: Optional[List[str]] = None,
                   seed: Optional[int] = None) -> List[Dict]:
    """
    Rekomendasi Snack: Buah (1 item)
    
    Algoritma:
    1. Pilih kandidat Buah (top-12 terdekat kalori)
    2. Hitung porsi optimal dengan closed-form solution
    3. Hitung RMSE
    4. Pilih 1 buah dengan RMSE terkecil
    """
    target_cal = float(target_vec[0])
    base_excl = list(used_foods) + (exclude_list or [])
    
    fruits = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Buah'},
        allergies=allergies,
        exclude_list=base_excl,
        target_calories=target_cal,
        k=12,
        seed=seed
    )
    
    if fruits.empty:
        logger.warning("No fruit candidates for snack")
        return []
    
    recommendations = []
    for _, f in fruits.iterrows():
        name = str(f['Nama_Bahan'])
        if name in used_foods:
            continue
        
        portion = single_item_best_portion(f, target_vec)
        
        # Hitung prediksi
        x = f[FEATURES].astype(float).to_numpy() / 100.0
        pred = x * portion
        rmse = calculate_rmse(pred, target_vec)
        
        recommendations.append((rmse, f, portion))
    
    if not recommendations:
        return []
    
    recommendations.sort(key=lambda x: x[0])
    rmse, f, portion = recommendations[0]
    used_foods.add(str(f['Nama_Bahan']))
    
    return [{
        "Pokok": None,
        "Lauk": None,
        "Sayur": None,
        "Buah": get_food_nutrition(f['Nama_Bahan'], portion, raw_df),
        "avg_similarity": None,
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== MAIN FUNCTION ====================
def generate_recommendations_per_jadwal(raw_file: str,
                                       jadwal_nutrients_dict: Dict[str, Dict[str, float]],
                                       allergies: Optional[List[str]] = None,
                                       exclude_foods: Optional[List[str]] = None,
                                       seed: Optional[int] = None) -> Dict[str, List[Dict]]:
    """
    Generate rekomendasi menu untuk semua jadwal makan
    
    Args:
        raw_file: Path ke file Excel data makanan
        jadwal_nutrients_dict: Target nutrisi per jadwal
            {
                'Pagi': {'Energi (kal)': 360, 'Protein (g)': 13.5, ...},
                'Siang': {...},
                ...
            }
        allergies: List alergi user
        exclude_foods: List makanan yang di-exclude
        seed: Random seed untuk reproducibility
    
    Returns:
        Dict dengan struktur:
        {
            'Pagi': [{'Pokok': {...}, 'Lauk': {...}, 'Sayur': {...}, 'Buah': None}],
            'Siang': [...],
            ...
        }
    """
    # Load data
    raw_df = load_raw_data(raw_file)
    
    output: Dict[str, List[Dict]] = {}
    used_foods = set(x.strip() for x in (exclude_foods or []) if x and x.strip())
    
    rng = np.random.default_rng(seed)
    
    for schedule, user_nutrients in jadwal_nutrients_dict.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing schedule: {schedule}")
        logger.info(f"Target: {user_nutrients['Energi (kal)']:.0f} kkal")
        
        # Konversi target ke vector
        target_vec = np.array([
            user_nutrients['Energi (kal)'],
            user_nutrients['Protein (g)'],
            user_nutrients['Lemak (g)'],
            user_nutrients['Karbohidrat (g)'],
            user_nutrients['Serat (g)']
        ], dtype=float)
        
        # Pilih fungsi rekomendasi berdasarkan jadwal
        if schedule in ['Pagi', 'Siang']:
            recs = recommend_morning_afternoon(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        elif schedule == 'Sore/Malam':
            recs = recommend_evening(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        else:  # Snack 1 & Snack 2
            recs = recommend_snack(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        
        output[schedule] = recs
        
        if recs:
            logger.info(f"✓ Generated recommendation with RMSE: {recs[0]['fit_rmse']:.2f}")
        else:
            logger.warning(f"✗ No recommendation generated for {schedule}")
    
    # Save output untuk debugging
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        logger.info("\nOutput saved to output.json")
    except Exception:
        pass
    
    return output
