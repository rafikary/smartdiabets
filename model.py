# model.py
import pandas as pd
import numpy as np
import json
import re
import logging
import warnings
from typing import List, Dict, Optional

warnings.filterwarnings('ignore', message='This pattern is interpreted as a regular expression')
#Load data makanan dari file Excel
def load_raw_data(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path, engine='openpyxl')
    df.columns = df.columns.str.strip()
    return df

FEATURES = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']

logger = logging.getLogger(__name__)

#Pola regex untuk deteksi alergen pada nama makanan
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


#Gabungkan pattern alergen jadi satu regex untuk filtering
def compile_allergen_regex(allergies: Optional[List[str]]) -> Optional[str]:
    if not allergies:
        return None
    
    patterns = []
    for allergen in allergies:
        key = allergen.strip().lower()
        if not key:
            continue
        
        if key in ALLERGEN_PATTERNS:
            # Gunakan pattern predefined
            patterns.append(ALLERGEN_PATTERNS[key])
        else:
            # Fallback: escape user input dan buat word boundary
            escaped = re.escape(key)
            patterns.append(rf'\b{escaped}\b')
    
    if not patterns:
        return None
    
    # Gabungkan dengan OR (|)
    combined = '|'.join(f'({p})' for p in patterns)
    
    logger.debug(f"Compiled allergen regex: {combined[:200]}...")
    return combined


#Filter makanan yang mengandung alergen berdasarkan regex pattern
def exclude_allergens_regex(df: pd.DataFrame, 
                           allergies: Optional[List[str]], 
                           col: str = "Nama_Bahan") -> pd.DataFrame:
    if not allergies or df.empty:
        return df
    
    pattern = compile_allergen_regex(allergies)
    if pattern is None:
        return df
    
    # Hitung jumlah baris awal
    initial_count = len(df)
    
    # Filter: ambil yang TIDAK match (negasi ~)
    mask = df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    df_filtered = df[~mask].copy()
    
    # Log jumlah yang dihapus
    removed_count = initial_count - len(df_filtered)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} items containing allergens: {allergies}")
        # Debug: tampilkan beberapa contoh yang dihapus
        if removed_count <= 5:
            removed_items = df[mask][col].tolist()
            logger.debug(f"Removed items: {removed_items}")
    
    return df_filtered


#Validasi tidak ada alergen yang lolos filter
def validate_no_allergen(df: pd.DataFrame, 
                        allergies: Optional[List[str]], 
                        col: str = "Nama_Bahan") -> bool:
    if not allergies or df.empty:
        return True
    
    pattern = compile_allergen_regex(allergies)
    if pattern is None:
        return True
    
    # Cek apakah ada yang match (seharusnya tidak ada)
    matches = df[col].astype(str).str.contains(pattern, case=False, regex=True, na=False)
    leaked_count = matches.sum()
    
    if leaked_count > 0:
        leaked_items = df[matches][col].tolist()
        logger.warning(f"⚠️ VALIDATION FAILED: {leaked_count} allergen(s) leaked!")
        logger.warning(f"Leaked items: {leaked_items[:10]}")
        return False
    
    logger.debug(f"✓ Validation passed: No allergens found in {len(df)} items")
    return True

#Wrapper untuk kompatibilitas dengan kode lama
def exclude_allergens(df: pd.DataFrame, allergies: Optional[List[str]]) -> pd.DataFrame:
    return exclude_allergens_regex(df, allergies, col="Nama_Bahan")

#Hitung nutrisi makanan berdasarkan porsi yang ditentukan
def get_food_nutrition(name: str, portion_grams: float, raw_df: pd.DataFrame) -> Dict:
    row = raw_df[raw_df['Nama_Bahan'] == name]
    if row.empty:
        # fallback kosong jika tidak ketemu
        return {
            "name": name, "category": None, "portion": round(float(portion_grams), 2),
            "calories": 0.0, "carbs": 0.0, "protein": 0.0, "fat": 0.0, "fiber": 0.0
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

#Hitung porsi optimal makanan menggunakan Least Squares (A×x=b) dengan constraint min-max
def solve_portions_least_squares(items: List[pd.Series], target_vec: np.ndarray,
                                 min_g: float = 30.0, max_g: float = 400.0) -> np.ndarray:
    X = np.column_stack([i[FEATURES].astype(float).to_numpy() / 100.0 for i in items])
    y = target_vec.astype(float)
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    w = np.maximum(w, 0.0)
    w = np.clip(w, min_g, max_g)
    
    return w

#Hitung porsi optimal untuk satu item dengan closed-form: w=(x·y)/(x·x)
def single_item_best_portion(item: pd.Series, target_vec: np.ndarray,
                             min_g: float = 30.0, max_g: float = 400.0) -> float:
    x = (item[FEATURES].astype(float).to_numpy() / 100.0)
    y = target_vec.astype(float)
    denom = float(np.dot(x, x)) if float(np.dot(x, x)) > 0 else 1.0
    w = float(np.dot(x, y) / denom)
    w = max(w, 0.0)
    w = float(np.clip(w, min_g, max_g))
    
    return w

#Hitung RMSE untuk evaluasi akurasi nutrisi (semakin kecil semakin baik)
def rmse_vec(pred: np.ndarray, tgt: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - tgt) ** 2)))

#Terapkan filter kategori pada DataFrame (mendukung value tunggal atau list)
def _apply_filters(df: pd.DataFrame, filters: Optional[Dict[str, object]]) -> pd.DataFrame:
    if not filters:
        return df
    out = df
    for col, val in filters.items():
        if isinstance(val, (list, tuple, set)):
            out = out[out[col].isin(list(val))]
        else:
            out = out[out[col] == val]
    return out

#Buat fallback filter kalau kandidat kosong (lepas Tipe Pokok & Mentahan/Olahan bertahap)
def _fallback_relax(df: pd.DataFrame, filters: Dict[str, object]) -> List[Dict[str, object]]:
    plans = []
    base = dict(filters)
    if 'Tipe Pokok' in base:
        f1 = dict(base); f1.pop('Tipe Pokok', None); plans.append(f1)
    if 'Mentahan / Olahan' in base:
        f2 = dict(base); f2.pop('Mentahan / Olahan', None); plans.append(f2)
    if 'Tipe Pokok' in base or 'Mentahan / Olahan' in base:
        f3 = dict(base); f3.pop('Tipe Pokok', None); f3.pop('Mentahan / Olahan', None); plans.append(f3)
    return plans

#Pilih kandidat makanan berdasarkan filter, alergi, exclude, lalu ranking berdasarkan kedekatan kalori
def choose_candidates(raw_df: pd.DataFrame,
                      filters: Dict[str, object],
                      allergies: Optional[List[str]],
                      exclude_foods: Optional[set],
                      target_calories: float,
                      k: int = 6,
                      seed: Optional[int] = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = _apply_filters(raw_df, filters)
    df = exclude_allergens(df, allergies)
    if exclude_foods:
        df = df[~df['Nama_Bahan'].str.lower().isin({x.lower() for x in exclude_foods})]

    if df.empty:
        # coba fallback pelonggaran filter
        for f in _fallback_relax(raw_df, filters):
            tmp = _apply_filters(raw_df, f)
            tmp = exclude_allergens(tmp, allergies)
            if exclude_foods:
                tmp = tmp[~tmp['Nama_Bahan'].str.lower().isin({x.lower() for x in exclude_foods})]
            if not tmp.empty:
                df = tmp
                break

    if df.empty:
        return df

    df = df.sample(frac=1.0, random_state=int(rng.integers(0, 1_000_000))).reset_index(drop=True)
    df['_cal'] = pd.to_numeric(df['Energi (kal)'], errors='coerce').fillna(0.0)
    df['_score'] = (df['_cal'] - target_calories) ** 2
    df = df.sort_values('_score', kind='mergesort').head(k).reset_index(drop=True)
    return df

#Rekomendasi Pagi/Siang: Pokok+Lauk+Sayur, hitung porsi pakai Least Squares, ranking pakai RMSE
def recommend_morning_afternoon(raw_df: pd.DataFrame,
                                target_vec: np.ndarray,
                                used_foods: set,
                                allergies: Optional[List[str]] = None,
                                seed: Optional[int] = None) -> List[Dict]:
    target_cal = float(target_vec[0])

    base_excl = set(used_foods)

    pk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Makanan pokok', 'Mentahan / Olahan': 'Olahan', 'Tipe Pokok': 'Sederhana'},
        allergies=allergies,
        exclude_foods=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )

    lk = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Lauk', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_foods=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )

    sy = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Sayur', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_foods=base_excl,
        target_calories=target_cal / 3.0,
        k=8,
        seed=seed
    )

    if pk.empty or lk.empty or sy.empty:
        return []

    recommendations = []
    foods_used_this_schedule = set()

    for _, p in pk.head(3).iterrows():
        for _, l in lk.head(3).iterrows():
            for _, s in sy.head(3).iterrows():
                names = {str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])}
                if foods_used_this_schedule.intersection(names) or used_foods.intersection(names):
                    continue

                items = [p, l, s]
                w = solve_portions_least_squares(items, target_vec)
                X = np.column_stack([i[FEATURES].astype(float).to_numpy() / 100.0 for i in items])
                pred = X @ w
                err = rmse_vec(pred, target_vec)

                recommendations.append((err, p, l, s, w))

    recommendations.sort(key=lambda x: x[0])

    out = []
    for err, p, l, s, w in recommendations:
        names = {str(p['Nama_Bahan']), str(l['Nama_Bahan']), str(s['Nama_Bahan'])}
        if foods_used_this_schedule.intersection(names):
            continue

        out.append({
            "Pokok": get_food_nutrition(p['Nama_Bahan'], w[0], raw_df),
            "Lauk":  get_food_nutrition(l['Nama_Bahan'], w[1], raw_df),
            "Sayur": get_food_nutrition(s['Nama_Bahan'], w[2], raw_df),
            "avg_similarity": None,
            "fit_rmse": round(float(err), 2)
        })
        foods_used_this_schedule.update(names)
        used_foods.update(names)
        if len(out) >= 1:
            break

    return out

#Rekomendasi Sore/Malam: Makanan pokok tipe Lengkap (fallback Olahan), porsi closed-form
def recommend_evening(raw_df: pd.DataFrame,
                      target_vec: np.ndarray,
                      used_foods: set,
                      allergies: Optional[List[str]] = None,
                      seed: Optional[int] = None) -> List[Dict]:
    target_cal = float(target_vec[0])
    base_excl = set(used_foods)

    top = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Makanan pokok', 'Tipe Pokok': 'Lengkap', 'Mentahan / Olahan': 'Olahan'},
        allergies=allergies,
        exclude_foods=base_excl,
        target_calories=target_cal,
        k=10,
        seed=seed
    )
    if top.empty:
        top = choose_candidates(
            raw_df,
            filters={'Jenis Makanan': 'Makanan pokok', 'Mentahan / Olahan': 'Olahan'},
            allergies=allergies,
            exclude_foods=base_excl,
            target_calories=target_cal,
            k=10,
            seed=seed
        )

    if top.empty:
        return []

    recommendations = []
    for _, f in top.iterrows():
        name = str(f['Nama_Bahan'])
        if name in used_foods:
            continue
        w = single_item_best_portion(f, target_vec)
        X = (f[FEATURES].astype(float).to_numpy() / 100.0)
        pred = X * w
        err = rmse_vec(pred, target_vec)
        recommendations.append((err, f, w))

    recommendations.sort(key=lambda x: x[0])

    out = []
    for err, f, w in recommendations:
        out.append({
            "Pokok": get_food_nutrition(f['Nama_Bahan'], w, raw_df),
            "Lauk": None,
            "Sayur": None,
            "avg_similarity": None,
            "fit_rmse": round(float(err), 2)
        })
        used_foods.add(str(f['Nama_Bahan']))
        if len(out) >= 1:
            break

    return out

#Rekomendasi Snack: Buah, porsi closed-form
def recommend_snack(raw_df: pd.DataFrame,
                    target_vec: np.ndarray,
                    used_foods: set,
                    allergies: Optional[List[str]] = None,
                    seed: Optional[int] = None) -> List[Dict]:
    target_cal = float(target_vec[0])
    base_excl = set(used_foods)

    fruits = choose_candidates(
        raw_df,
        filters={'Jenis Makanan': 'Buah'},
        allergies=allergies,
        exclude_foods=base_excl,
        target_calories=target_cal,
        k=12,
        seed=seed
    )
    if fruits.empty:
        return []

    recommendations = []
    for _, f in fruits.iterrows():
        name = str(f['Nama_Bahan'])
        if name in used_foods:
            continue
        w = single_item_best_portion(f, target_vec)
        X = (f[FEATURES].astype(float).to_numpy() / 100.0)
        pred = X * w
        err = rmse_vec(pred, target_vec)
        recommendations.append((err, f, w))

    recommendations.sort(key=lambda x: x[0])

    out = []
    for err, f, w in recommendations:
        out.append({
            "Pokok": None,
            "Lauk": None,
            "Sayur": None,
            "Buah": get_food_nutrition(f['Nama_Bahan'], w, raw_df),
            "avg_similarity": None,
            "fit_rmse": round(float(err), 2)
        })
        used_foods.add(str(f['Nama_Bahan']))
        if len(out) >= 1:
            break

    return out

#Generate rekomendasi menu per jadwal makan (Pagi, Siang, Sore/Malam, Snack1, Snack2)
def generate_recommendations_per_jadwal(raw_file: str,
                                        jadwal_nutrients_dict: Dict[str, Dict[str, float]],
                                        allergies: Optional[List[str]] = None,
                                        exclude_foods: Optional[List[str]] = None,
                                        seed: Optional[int] = None) -> Dict[str, List[Dict]]:
    raw_df = load_raw_data(raw_file)

    for col in FEATURES:
        raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0.0)

    output: Dict[str, List[Dict]] = {}
    used_foods = set(x.strip() for x in (exclude_foods or []) if x and x.strip())

    rng = np.random.default_rng(seed)

    for schedule, user_nutrients in jadwal_nutrients_dict.items():
        target_vec = np.array([
            user_nutrients['Energi (kal)'],
            user_nutrients['Protein (g)'],
            user_nutrients['Lemak (g)'],
            user_nutrients['Karbohidrat (g)'],
            user_nutrients['Serat (g)']
        ], dtype=float)

        if schedule in ['Pagi', 'Siang']:
            recs = recommend_morning_afternoon(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                seed=int(rng.integers(0, 1_000_000))
            )
        elif schedule == 'Sore/Malam':
            recs = recommend_evening(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                seed=int(rng.integers(0, 1_000_000))
            )
        else:
            recs = recommend_snack(
                raw_df=raw_df,
                target_vec=target_vec,
                used_foods=used_foods,
                allergies=allergies,
                seed=int(rng.integers(0, 1_000_000))
            )

        output[schedule] = recs

    try:
        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

    return output
