import pandas as pd
import numpy as np
import pickle
from sklearn.metrics.pairwise import cosine_similarity
import json

# Fungsi load data asli (Excel)
def load_raw_data(file_path):
    df = pd.read_excel(file_path, engine='openpyxl')
    df.columns = df.columns.str.strip()
    return df

# Fungsi load data normalisasi (pickle)
def load_normalized_data(pickle_path):
    df_norm = pd.read_pickle(pickle_path)
    return df_norm

# Fungsi load objek scaler (pickle)
def load_scaler(pickle_path):
    with open(pickle_path, 'rb') as f:
        scaler = pickle.load(f)
    return scaler

# Fungsi hitung similarity antara profil user dan makanan
def calc_similarity(user_profile, foods_df, features):
    user_vec = user_profile[features].values.reshape(1, -1)
    foods_vecs = foods_df[features].values
    similarities = cosine_similarity(user_vec, foods_vecs).flatten()
    return similarities

# Pilih top N makanan berdasar similarity dengan filter dan exclude
def select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=None, exclude_foods=None):
    df_filtered = raw_df.copy()
    if filters:
        for k, v in filters.items():
            df_filtered = df_filtered[df_filtered[k] == v]
    if exclude_foods:
        df_filtered = df_filtered[~df_filtered['Nama_Bahan'].isin(exclude_foods)]

    if df_filtered.empty:
        return pd.DataFrame()

    idx_filtered = df_filtered.index
    norm_filtered = norm_df.loc[idx_filtered]

    similarities = calc_similarity(user_profile, norm_filtered, features)
    df_filtered = df_filtered.copy()
    df_filtered['similarity'] = similarities
    top_foods = df_filtered.sort_values(by='similarity', ascending=False).head(n)
    return top_foods

# Ambil info nutrisi berdasarkan porsi (bukan 100g, tapi sudah dikalikan porsi)
def get_food_nutrition(name, portion, raw_df):
    row = raw_df[raw_df['Nama_Bahan'] == name].iloc[0]
    scale = portion / 100
    return {
        "name": name,
        "category": row["Jenis Makanan"],
        "portion": round(portion, 2),
        "calories": round(row["Energi (kal)"] * scale, 2),
        "carbs": round(row["Karbohidrat (g)"] * scale, 2),
        "protein": round(row["Protein (g)"] * scale, 2),
        "fat": round(row["Lemak (g)"] * scale, 2),
        "fiber": round(row["Serat (g)"] * scale, 2)
    }

# Kombinasi paket makanan pokok + lauk + sayur (top n=2, exclude makanan dobel di 1 jadwal & jadwal lain)
def combine_foods(top_pokok, top_lauk, top_sayur, used_foods, n=2):
    combos = []
    for _, pokok in top_pokok.iterrows():
        if pokok['Nama_Bahan'] in used_foods:
            continue
        for _, lauk in top_lauk.iterrows():
            if lauk['Nama_Bahan'] in used_foods or lauk['Nama_Bahan'] == pokok['Nama_Bahan']:
                continue
            for _, sayur in top_sayur.iterrows():
                if (sayur['Nama_Bahan'] in used_foods or
                    sayur['Nama_Bahan'] == pokok['Nama_Bahan'] or
                    sayur['Nama_Bahan'] == lauk['Nama_Bahan']):
                    continue
                avg_sim = np.mean([pokok['similarity'], lauk['similarity'], sayur['similarity']])
                combos.append({
                    'pokok': pokok,
                    'lauk': lauk,
                    'sayur': sayur,
                    'avg_similarity': avg_sim
                })
    
    combos_sorted = sorted(combos, key=lambda x: x['avg_similarity'], reverse=True)
    return combos_sorted[:n]

# Hitung porsi gram agar kalori paket sesuai target
def calculate_portions(combo, target_calories):
    cal_pokok = combo['pokok']['Energi (kal)']
    cal_lauk = combo['lauk']['Energi (kal)']
    cal_sayur = combo['sayur']['Energi (kal)']
    total_cal_per_100g = cal_pokok + cal_lauk + cal_sayur
    if total_cal_per_100g == 0:
        return 100, 100, 100
    porsi_total = target_calories / total_cal_per_100g * 100
    return round(porsi_total, 2), round(porsi_total, 2), round(porsi_total, 2)

# Rekomendasi pagi/siang (pakai top 2, exclude makanan yang sudah dipakai)
def recommend_morning_afternoon(raw_df, norm_df, user_profile, target_calories, features, used_foods):
    filters_pokok = {'Jenis Makanan': 'Makanan pokok', 'Mentahan / Olahan': 'Olahan', 'Tipe Pokok': 'Sederhana'}
    top_pokok = select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=filters_pokok, exclude_foods=used_foods)

    filters_lauk = {'Jenis Makanan': 'Lauk', 'Mentahan / Olahan': 'Olahan'}
    top_lauk = select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=filters_lauk, exclude_foods=used_foods)

    filters_sayur = {'Jenis Makanan': 'Sayur', 'Mentahan / Olahan': 'Olahan'}
    top_sayur = select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=filters_sayur, exclude_foods=used_foods)

    # Kombinasikan dan pastikan tidak ada makanan yang sama dalam 1 jadwal atau sudah dipakai jadwal sebelumnya
    combos = combine_foods(top_pokok, top_lauk, top_sayur, used_foods, n=5)  # Get more combinations to choose from
    recommendations = []
    foods_used_this_schedule = set()

    for c in combos:
        food_set = {c['pokok']['Nama_Bahan'], c['lauk']['Nama_Bahan'], c['sayur']['Nama_Bahan']}
        # Cegah kombinasi dengan makanan dobel dalam 1 jadwal maupun dengan jadwal lain
        if not foods_used_this_schedule.intersection(food_set):
            p_pokok, p_lauk, p_sayur = calculate_portions(c, target_calories)
            recommendations.append({
                'pokok': c['pokok']['Nama_Bahan'],
                'lauk': c['lauk']['Nama_Bahan'],
                'sayur': c['sayur']['Nama_Bahan'],
                'portion_pokok': p_pokok,
                'portion_lauk': p_lauk,
                'portion_sayur': p_sayur,
                'avg_similarity': round(c['avg_similarity'], 4)
            })
            foods_used_this_schedule.update(food_set)
            used_foods.update(food_set)
        if len(recommendations) >= 2:  # Ambil 2 rekomendasi terbaik
            break
    return recommendations

# Rekomendasi sore/malam (top 2, exclude makanan yang sudah dipakai)
def recommend_evening(raw_df, norm_df, user_profile, target_calories, features, used_foods):
    filters = {'Jenis Makanan': 'Makanan pokok', 'Tipe Pokok': 'Lengkap', 'Mentahan / Olahan': 'Olahan'}
    top_pokok = select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=filters, exclude_foods=used_foods)

    recommendations = []
    for _, food in top_pokok.iterrows():
        if food['Nama_Bahan'] in used_foods:
            continue
        cal = food['Energi (kal)']
        portion = round(target_calories / cal * 100, 2) if cal > 0 else 100
        recommendations.append({
            'pokok_lengkap': food['Nama_Bahan'],
            'portion': portion,
            'similarity': round(food['similarity'], 4)
        })
        used_foods.add(food['Nama_Bahan'])
        if len(recommendations) >= 2:  # Ambil 2 rekomendasi terbaik
            break
    return recommendations

# Rekomendasi snack buah (top 2, exclude makanan yang sudah dipakai)
def recommend_snack(raw_df, norm_df, user_profile, target_calories, features, used_foods):
    filters = {'Jenis Makanan': 'Buah'}
    top_buah = select_top_n_foods(raw_df, norm_df, user_profile, features, n=5, filters=filters, exclude_foods=used_foods)

    recommendations = []
    for _, food in top_buah.iterrows():
        if food['Nama_Bahan'] in used_foods:
            continue
        cal = food['Energi (kal)']
        portion = round(target_calories / cal * 100, 2) if cal > 0 else 100
        recommendations.append({
            'snack': food['Nama_Bahan'],
            'portion': portion,
            'similarity': round(food['similarity'], 4)
        })
        used_foods.add(food['Nama_Bahan'])
        if len(recommendations) >= 2:  # Ambil 2 rekomendasi terbaik
            break
    return recommendations

# Fungsi utama: generate rekomendasi dengan kebutuhan GIZI PER JADWAL (top 2 tiap jadwal, no kembar)
def generate_recommendations_per_jadwal(raw_file, norm_pickle, scaler_pickle, jadwal_nutrients_dict):
    raw_df = load_raw_data(raw_file)
    norm_df = load_normalized_data(norm_pickle)
    scaler = load_scaler(scaler_pickle)
    features = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']

    output = {}
    used_foods = set()  # Kumpulan makanan yang sudah pernah dipakai di seluruh jadwal

    for schedule, user_nutrients in jadwal_nutrients_dict.items():
        user_profile_raw = pd.DataFrame([user_nutrients])
        user_profile_norm = user_profile_raw.copy()
        user_profile_norm[features] = scaler.transform(user_profile_raw[features])
        target_calories = user_nutrients['Energi (kal)']

        if schedule in ['Pagi', 'Siang']:
            recs = recommend_morning_afternoon(raw_df, norm_df, user_profile_norm.iloc[0], target_calories, features, used_foods)
            enriched_meals = []
            for r in recs:
                pokok_info = get_food_nutrition(r['pokok'], r['portion_pokok'], raw_df)
                lauk_info = get_food_nutrition(r['lauk'], r['portion_lauk'], raw_df)
                sayur_info = get_food_nutrition(r['sayur'], r['portion_sayur'], raw_df)
                enriched_meals.append({
                    "Pokok": pokok_info,
                    "Lauk": lauk_info,
                    "Sayur": sayur_info,
                    "avg_similarity": r['avg_similarity']
                })
            output[schedule] = enriched_meals

        elif schedule == 'Sore/Malam':
            recs = recommend_evening(raw_df, norm_df, user_profile_norm.iloc[0], target_calories, features, used_foods)
            enriched_meals = []
            for r in recs:
                pokok_info = get_food_nutrition(r['pokok_lengkap'], r['portion'], raw_df)
                enriched_meals.append({
                    "Pokok Lengkap": pokok_info,
                    "similarity": r['similarity']
                })
            output[schedule] = enriched_meals

        else:  # Snack 1 & Snack 2
            recs = recommend_snack(raw_df, norm_df, user_profile_norm.iloc[0], target_calories, features, used_foods)
            enriched_meals = []
            for r in recs:
                snack_info = get_food_nutrition(r['snack'], r['portion'], raw_df)
                enriched_meals.append({
                    "Buah": snack_info,
                    "similarity": r['similarity']
                })
            output[schedule] = enriched_meals

    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print("Rekomendasi telah disimpan ke output.json")
    return output

# ---- CONTOH PANGGILAN UTAMA
if __name__ == '__main__':
    raw_data_path = 'clean_food_processed_no_scaling.xlsx'
    normalized_pickle_path = 'data_normalized.pkl'
    scaler_pickle_path = 'minmax_scaler.pkl'

    jadwal_nutrients_dict = {
        'Pagi': {
            'Energi (kal)': 491.4,
            'Protein (g)': 18.43,
            'Lemak (g)': 13.65,
            'Karbohidrat (g)': 73.71,
            'Serat (g)': 4
        },
        'Siang': {
            'Energi (kal)': 737.1,
            'Protein (g)': 27.63,
            'Lemak (g)': 20.47,
            'Karbohidrat (g)': 110.57,
            'Serat (g)': 6
        },
        'Sore/Malam': {
            'Energi (kal)': 614.25,
            'Protein (g)': 23.04,
            'Lemak (g)': 17.08,
            'Karbohidrat (g)': 92.14,
            'Serat (g)': 5
        },
        'Snack 1': {
            'Energi (kal)': 245.7,
            'Protein (g)': 9.21,
            'Lemak (g)': 6.82,
            'Karbohidrat (g)': 36.43,
            'Serat (g)': 2
        },
        'Snack 2': {
            'Energi (kal)': 368.55,
            'Protein (g)': 13.81,
            'Lemak (g)': 10.24,
            'Karbohidrat (g)': 54.64,
            'Serat (g)': 3
        }
    }

    generate_recommendations_per_jadwal(
        raw_data_path, normalized_pickle_path, scaler_pickle_path, jadwal_nutrients_dict
    )
