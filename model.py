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

⚕️ PROTOKOL KEAMANAN MEDIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistem diet medis siap saji - DILARANG merekomendasikan bahan mentah.

Filter 'Mentahan / Olahan' = 'Olahan' adalah NON-NEGOTIABLE:
  ✓ Fallback boleh melonggarkan 'Tipe Pokok' (aman)
  ✗ Fallback TIDAK BOLEH melonggarkan 'Mentahan / Olahan' (berbahaya)
  
Jika kandidat olahan habis → Return empty dataframe → Error handler
JANGAN kompromi keamanan medis demi kelengkapan data.

Catatan: Buah segar dengan status 'Tunggal' tetap aman untuk Snack.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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


# ==================== MUAT DATA ====================
def load_raw_data(file_path: str) -> pd.DataFrame:
    """Muat data makanan dari file Excel dan validasi struktur kolom yang diperlukan"""
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


# ==================== FILTER ALERGEN (CONTENT-BASED) ====================
def compile_allergen_regex(allergies: Optional[List[str]]) -> Optional[str]:
    """Susun pattern regex untuk memfilter makanan yang mengandung alergen"""
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
    """Filter makanan yang mengandung alergen berdasarkan keyword matching pada kolom Nama_Bahan"""
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


# ==================== FILTER MAKANAN YANG DIHINDARI (CONTENT-BASED) ====================
def exclude_foods(df: pd.DataFrame, 
                 exclude_list: Optional[List[str]], 
                 col: str = "Nama_Bahan") -> pd.DataFrame:
    """
    Filter makanan yang dihindari user berdasarkan keyword matching pada Nama_Bahan.
    Contoh: keyword 'ayam' akan memblokir 'ayam goreng', 'rendang ayam', 'sate ayam', dll.
    Ini mendukung fitur preferensi personal dan fitur Ganti Menu.
    """
    if not exclude_list or df.empty:
        return df
    
    # Bersihkan dan siapkan keywords
    exclude_keywords = [x.strip().lower() for x in exclude_list if x and x.strip()]
    if not exclude_keywords:
        return df
    
    # Bangun pola regex dengan word boundary untuk partial matching
    patterns = []
    for keyword in exclude_keywords:
        # Escape karakter spesial regex, tapi tetap izinkan partial matching
        escaped = re.escape(keyword)
        # Gunakan word boundary (\b) untuk menghindari false positive
        patterns.append(rf'\b{escaped}\b')
    
    # Gabungkan semua pattern dengan operator OR
    combined_pattern = '|'.join(f'({p})' for p in patterns)
    
    initial_count = len(df)
    # Filter baris yang mengandung keywords (hapus yang cocok)
    mask = df[col].astype(str).str.contains(combined_pattern, case=False, regex=True, na=False)
    df_filtered = df[~mask].copy()  # Negasi mask (~) untuk buang yang match
    
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
    
    MEDICAL SAFETY:
    - Filter 'Mentahan / Olahan' TIDAK BOLEH dilonggarkan dalam fallback
    - Jika kandidat olahan habis, return empty dataframe untuk error handling
    """
    rng = np.random.default_rng(seed)
    
    # Tahap 1: Filter kategori (rule-based - berdasarkan kolom terstruktur)
    df = raw_df.copy()
    for col, val in filters.items():
        if isinstance(val, (list, tuple, set)):
            df = df[df[col].isin(list(val))]
        else:
            df = df[df[col] == val]
    
    # Tahap 2: Filter alergen (content-based - keyword matching)
    df = exclude_allergens(df, allergies)
    
    # Tahap 3: Filter makanan dihindari (content-based - keyword matching)
    df = exclude_foods(df, exclude_list)
    
    # Mekanisme Fallback: longgarkan filter jika kosong (KECUALI 'Mentahan / Olahan')
    if df.empty:
        logger.warning(f"Tidak ada kandidat dengan filter {filters}. Mencoba relaksasi aman...")
        
        # Fallback Tahap 1: Lepas 'Tipe Pokok' saja (aman dilonggarkan)
        # Alasan: Tipe Pokok (Sederhana/Lengkap) hanya preferensi, bukan keamanan medis
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
            
            if not df.empty:
                logger.info(f"Fallback berhasil: Ditemukan {len(df)} kandidat setelah longgarkan 'Tipe Pokok'")
        
        # Fallback Tahap 2: DIHAPUS - TIDAK AMAN melonggarkan 'Mentahan / Olahan'
        # Jika masih kosong, biarkan empty untuk ditangani error handler di level atas
    
    if df.empty:
        logger.warning(
            f"Tidak ada kandidat aman setelah filtering. Mengembalikan dataframe kosong. "
            f"Filter: {filters}, Jumlah exclude: {len(exclude_list or [])}"
        )
        return df
    
    # Tahap 4: Ranking heuristik berdasarkan kedekatan kalori dengan target
    # Acak urutan dulu agar tidak bias urutan asli dataset
    df = df.sample(frac=1.0, random_state=int(rng.integers(0, 1_000_000))).reset_index(drop=True)
    # Hitung skor kedekatan: semakin kecil error kuadrat, semakin baik
    df['_cal_score'] = (df['Energi (kal)'] - target_calories) ** 2
    # Urutkan ascending (terkecil = terbaik) dan ambil top-k
    df = df.sort_values('_cal_score', kind='mergesort').head(k).reset_index(drop=True)
    
    logger.debug(f"Terpilih {len(df)} kandidat (target_cal={target_calories:.0f})")
    return df


# ==================== OPTIMASI PORSI: LEAST SQUARES ====================
def solve_portions_least_squares(items: List[pd.Series], 
                                 target_vec: np.ndarray) -> np.ndarray:
    """
    Metode Constrained Least Squares untuk menghitung porsi optimal (dalam gram).
    
    Formulasi Matematika:
    - Minimize: ||A·x - b||²  (meminimalkan error kuadrat)
    - Subject to: MIN_PORTION ≤ x ≤ MAX_PORTION  (constraint porsi realistis)
    
    Dimana:
    - A: Matriks nutrisi per-gram (5 nutrisi × n makanan)
    - x: Vektor porsi yang dicari (variabel optimasi)
    - b: Vektor target nutrisi [energi, protein, lemak, karbo, serat]
    
    Args:
        items: List item makanan (pandas Series dengan kolom FEATURES)
        target_vec: Target nutrisi untuk jadwal makan ini
    
    Returns:
        np.ndarray: Vektor porsi optimal (gram) untuk setiap makanan
    """
    # Konversi nutrisi dari per-100g (TKPI) menjadi per-1g untuk perhitungan
    A = np.column_stack([
        item[FEATURES].astype(float).to_numpy() / 100.0 
        for item in items
    ])
    b = target_vec.astype(float)
    
    n_items = len(items)
    # Batasan porsi: 20g - 400g (realistis untuk porsi makan)
    bounds = ([MIN_PORTION] * n_items, [MAX_PORTION] * n_items)
    
    try:
        # Gunakan metode bounded-variable least squares (BVLS) dari scipy
        result = lsq_linear(A, b, bounds=bounds, method='bvls', verbose=0)
        x = result.x  # Solusi optimal
        
        # Validasi hasil optimasi
        if np.any(np.isnan(x)) or np.any(np.isinf(x)):
            logger.warning("Hasil optimasi mengandung NaN/Inf. Menggunakan fallback NNLS.")
            # Fallback ke Non-Negative Least Squares (lebih sederhana)
            x_nnls, _ = nnls(A, b)
            x = np.clip(x_nnls, MIN_PORTION, MAX_PORTION)
        
        return x
        
    except Exception as e:
        logger.error(f"Error optimasi: {e}. Menggunakan fallback distribusi merata.")
        # Fallback terakhir: bagi rata kalori ke semua item
        avg_cal_per_gram = 2.0  # Asumsi kalori rata-rata per gram
        fallback_portion = min(MAX_PORTION, max(MIN_PORTION, target_vec[0] / (n_items * avg_cal_per_gram)))
        return np.full(n_items, fallback_portion)  # Semua item porsi sama


def single_item_best_portion(item: pd.Series, target_vec: np.ndarray) -> float:
    """
    Solusi closed-form (analitik) untuk single item - digunakan untuk Snack (Buah).
    
    Formulasi:
    - Minimize: ||w·x - y||²
    - Solusi analitik: w = (x·y) / (x·x)  [dot product]
    
    Args:
        item: Item makanan (pandas Series)
        target_vec: Target nutrisi untuk snack
    
    Returns:
        float: Porsi optimal dalam gram
    """
    x = item[FEATURES].astype(float).to_numpy() / 100.0  # Konversi per-100g ke per-1g
    y = target_vec.astype(float)
    
    x_norm = float(np.dot(x, x))  # Norma kuadrat vektor nutrisi
    if x_norm < 1e-6:
        logger.warning(f"Item '{item.get('Nama_Bahan', 'unknown')}' memiliki nutrisi nyaris nol. Menggunakan porsi minimum.")
        return MIN_PORTION
    
    # Hitung porsi optimal dengan rumus closed-form
    w = float(np.dot(x, y) / x_norm)
    w = max(0.0, w)  # Pastikan tidak negatif
    w = float(np.clip(w, MIN_PORTION, MAX_PORTION))  # Enforce constraint
    
    return w


def calculate_rmse(pred: np.ndarray, target: np.ndarray) -> float:
    """Hitung Root Mean Square Error (RMSE) untuk evaluasi akurasi nutrisi"""
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


# ==================== REKOMENDASI PAGI/SIANG (MENU UTAMA) ====================
def recommend_morning_afternoon(raw_df: pd.DataFrame,
                                target_vec: np.ndarray,
                                used_foods: set,
                                allergies: Optional[List[str]] = None,
                                exclude_list: Optional[List[str]] = None,
                                seed: Optional[int] = None) -> List[Dict]:
    """
    Generate rekomendasi untuk jadwal Pagi dan Siang: Pokok + Lauk + Sayur (3 item).
    
    Algoritma:
    1. Pilih kandidat Pokok, Lauk, Sayur (masing-masing top-8 terdekat kalori)
    2. Generate kombinasi 3×3×3 = 27 kemungkinan menu
    3. Solve Least Squares untuk setiap kombinasi (hitung porsi optimal)
    4. Hitung RMSE (akurasi nutrisi) untuk tiap kombinasi
    5. Pilih 1 kombinasi dengan RMSE terkecil (paling mendekati target)
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
        logger.warning("Kandidat tidak cukup untuk menu pagi/siang")
        return []
    
    # Kombinasi dan Optimasi: coba berbagai kombinasi menu
    recommendations = []
    foods_used_this_schedule = set()  # Tracking duplikasi dalam jadwal yang sama
    
    for _, p in pk.head(3).iterrows():
        for _, l in lk.head(3).iterrows():
            for _, s in sy.head(3).iterrows():
                names = {str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])}
                
                # Skip jika ada duplikasi nama (dalam jadwal yang sama atau antar jadwal)
                if foods_used_this_schedule.intersection(names) or used_foods.intersection(names):
                    continue
                
                # Solve Least Squares: hitung porsi optimal untuk kombinasi ini
                items = [p, l, s]
                portions = solve_portions_least_squares(items, target_vec)
                
                # Hitung prediksi nutrisi aktual dengan porsi yang didapat
                A = np.column_stack([i[FEATURES].astype(float).to_numpy() / 100.0 for i in items])
                pred = A @ portions  # Perkalian matriks: nutrisi prediksi
                rmse = calculate_rmse(pred, target_vec)  # Ukur akurasi
                
                recommendations.append((rmse, p, l, s, portions))
    
    if not recommendations:
        return []
    
    # Ranking: urutkan berdasarkan RMSE (ascending = terkecil terbaik)
    recommendations.sort(key=lambda x: x[0])
    
    # Ambil 1 kombinasi terbaik (RMSE terkecil)
    rmse, p, l, s, portions = recommendations[0]
    # Tandai makanan ini sebagai sudah digunakan (agar tidak diulang di jadwal lain)
    used_foods.update({str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])})
    
    return [{
        "Pokok": get_food_nutrition(p['Nama_Bahan'], portions[0], raw_df),
        "Lauk": get_food_nutrition(l['Nama_Bahan'], portions[1], raw_df),
        "Sayur": get_food_nutrition(s['Nama_Bahan'], portions[2], raw_df),
        "Buah": None,
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== REKOMENDASI SORE/MALAM (MENU UTAMA) ====================
def recommend_evening(raw_df: pd.DataFrame,
                     target_vec: np.ndarray,
                     used_foods: set,
                     allergies: Optional[List[str]] = None,
                     exclude_list: Optional[List[str]] = None,
                     seed: Optional[int] = None) -> List[Dict]:
    """
    Generate rekomendasi untuk jadwal Sore/Malam: Pokok + Lauk + Sayur (3 item).
    
    Catatan: Struktur SAMA dengan Pagi/Siang (3 items) untuk menjaga keseimbangan nutrisi.
             Tidak menggunakan struktur 2-item untuk mencegah defisit serat dan protein.
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
        logger.warning("Kandidat tidak cukup untuk menu sore/malam")
        return []
    
    # Kombinasi dan Optimasi (sama dengan algoritma Pagi/Siang)
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
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== REKOMENDASI SNACK (BUAH) ====================
def recommend_snack(raw_df: pd.DataFrame,
                   target_vec: np.ndarray,
                   used_foods: set,
                   allergies: Optional[List[str]] = None,
                   exclude_list: Optional[List[str]] = None,
                   seed: Optional[int] = None) -> List[Dict]:
    """
    Generate rekomendasi Snack: Buah (1 item saja, bukan kombinasi).
    
    Algoritma:
    1. Pilih kandidat Buah (top-12 terdekat kalori)
    2. Hitung porsi optimal dengan closed-form solution (formula analitik)
    3. Hitung RMSE untuk tiap buah
    4. Pilih 1 buah dengan RMSE terkecil (paling mendekati target snack)
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
        logger.warning("Tidak ada kandidat buah untuk snack")
        return []
    
    recommendations = []
    for _, f in fruits.iterrows():
        name = str(f['Nama_Bahan'])
        if name in used_foods:  # Skip jika sudah dipakai di jadwal lain
            continue
        
        # Hitung porsi optimal dengan closed-form
        portion = single_item_best_portion(f, target_vec)
        
        # Hitung prediksi nutrisi
        x = f[FEATURES].astype(float).to_numpy() / 100.0
        pred = x * portion  # Nutrisi = nutrisi per-gram × porsi
        rmse = calculate_rmse(pred, target_vec)
        
        recommendations.append((rmse, f, portion))
    
    if not recommendations:
        return []
    
    # Pilih buah dengan RMSE terkecil
    recommendations.sort(key=lambda x: x[0])
    rmse, f, portion = recommendations[0]
    used_foods.add(str(f['Nama_Bahan']))  # Tandai sebagai terpakai
    
    return [{
        "Pokok": None,
        "Lauk": None,
        "Sayur": None,
        "Buah": get_food_nutrition(f['Nama_Bahan'], portion, raw_df),
        "fit_rmse": round(float(rmse), 2)
    }]


# ==================== FUNGSI UTAMA (MAIN) ====================
def generate_recommendations_per_jadwal(raw_file: str,  # Target nutrisi akan diterima di parameter ini
                                       jadwal_nutrients_dict: Dict[str, Dict[str, float]],
                                       allergies: Optional[List[str]] = None,
                                       exclude_foods: Optional[List[str]] = None,
                                       seed: Optional[int] = None) -> Dict[str, List[Dict]]:
    """
    Generate rekomendasi menu untuk SEMUA jadwal makan (Pagi, Siang, Sore/Malam, Snack 1, Snack 2).
    
    Ini adalah fungsi UTAMA yang dipanggil dari Flask route /outputs.
    
    Args:
        raw_file: Path ke file Excel data makanan TKPI
        jadwal_nutrients_dict: Target nutrisi untuk setiap jadwal
            Contoh struktur:
            {
                'Pagi': {'Energi (kal)': 360, 'Protein (g)': 13.5, ...},
                'Siang': {'Energi (kal)': 540, ...},
                'Sore/Malam': {'Energi (kal)': 450, ...},
                'Snack 1': {'Energi (kal)': 180, ...},
                'Snack 2': {'Energi (kal)': 270, ...}
            }
        allergies: List alergi user (e.g., ['seafood', 'kacang'])
        exclude_foods: List makanan yang dihindari/di-exclude user
        seed: Random seed untuk reproducibility hasil
    
    Returns:
        Dictionary berisi rekomendasi untuk tiap jadwal:
        {
            'Pagi': [{'Pokok': {...}, 'Lauk': {...}, 'Sayur': {...}, 'Buah': None, 'fit_rmse': ...}],
            'Siang': [...],
            'Sore/Malam': [...],
            'Snack 1': [{'Pokok': None, 'Lauk': None, 'Sayur': None, 'Buah': {...}, ...}],
            'Snack 2': [...]
        }
    """
    # Muat data makanan dari Excel
    raw_df = load_raw_data(raw_file)
    
    output: Dict[str, List[Dict]] = {}  # Container hasil rekomendasi
    # Set makanan yang sudah digunakan (dimulai dari exclude_foods user)
    used_foods = set(x.strip() for x in (exclude_foods or []) if x and x.strip())
    
    rng = np.random.default_rng(seed)  # Random generator untuk reproducibility
    
    # Loop untuk setiap jadwal makan
    for schedule, user_nutrients in jadwal_nutrients_dict.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Memproses jadwal: {schedule}")
        logger.info(f"Target kalori: {user_nutrients['Energi (kal)']:.0f} kkal")
        
        # Konversi target nutrisi ke vektor numpy untuk komputasi
        target_vec = np.array([
            user_nutrients['Energi (kal)'],
            user_nutrients['Protein (g)'],
            user_nutrients['Lemak (g)'],
            user_nutrients['Karbohidrat (g)'],
            user_nutrients['Serat (g)']
        ], dtype=float)
        
        # Pilih fungsi rekomendasi yang sesuai berdasarkan jadwal
        if schedule in ['Pagi', 'Siang']:
            # Menu utama: Pokok + Lauk + Sayur
            recs = recommend_morning_afternoon(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        elif schedule == 'Sore/Malam':
            # Menu utama sore: juga Pokok + Lauk + Sayur
            recs = recommend_evening(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        else:  # Snack 1 & Snack 2
            # Snack: hanya Buah (single item)
            recs = recommend_snack(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                exclude_list=exclude_foods,
                seed=int(rng.integers(0, 1_000_000))
            )
        
        output[schedule] = recs
        
        # Log hasil rekomendasi
        if recs:
            logger.info(f"✓ Rekomendasi berhasil dibuat dengan RMSE: {recs[0]['fit_rmse']:.2f}")
        else:
            logger.warning(f"✗ Tidak ada rekomendasi yang dibuat untuk {schedule}")
    
    # Simpan output ke file JSON untuk debugging dan validasi
    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        logger.info("\nOutput disimpan ke output.json")
    except Exception:
        pass  # Abaikan error jika gagal menyimpan (tidak kritikal)
    
    return output
