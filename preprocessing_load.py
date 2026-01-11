# processing_load.py
"""
Modul untuk load dan preprocessing data TKPI tanpa normalisasi/scaling.

PENTING: 
- Data harus tetap dalam basis per 100 gram (nilai asli)
- TIDAK boleh ada normalisasi/scaling ke range 0-1
- Ini sesuai dengan requirement bahwa model regresi linier akan menghitung porsi dalam gram
"""
import pandas as pd
from pathlib import Path

FEATURES = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']
REQUIRED_COLS = FEATURES + ['Nama_Bahan', 'Jenis Makanan']

def _normalize_commas_to_dot(x):
    """Konversi koma desimal ke titik, handle simbol kosong"""
    if isinstance(x, str):
        x = x.strip()
        if x == '-':
            return 0
        return x.replace(',', '.')
    return x

def preprocess_data_no_scaling(input_xlsx: str, output_xlsx: str, sheet_name: str | int | None = None) -> pd.DataFrame:
    """
    Load dan bersihkan data TKPI tanpa normalisasi.
    
    PENTING: Fungsi ini TIDAK melakukan scaling/normalisasi.
    Semua nilai nutrisi tetap dalam bentuk asli per 100 gram.
    
    Args:
        input_xlsx: Path file Excel sumber (data TKPI asli)
        output_xlsx: Path file output yang sudah dibersihkan
        sheet_name: Nama sheet (opsional)
    
    Returns:
        DataFrame dengan nilai asli per 100g (TANPA scaling)
    """
    # 1) Load
    df = pd.read_excel(input_xlsx, engine='openpyxl', sheet_name=sheet_name)
    if isinstance(df, dict):  # multi-sheet: ambil sheet pertama
        df = list(df.values())[0]
    df.columns = df.columns.astype(str).str.strip()

    # 2) Validasi kolom wajib
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom wajib hilang: {missing}. Kolom yang ada: {list(df.columns)}")

    # 3) Trim string penting
    for c in ['Nama_Bahan', 'Jenis Makanan']:
        df[c] = df[c].astype(str).str.strip()

    # 4) Bersihkan kolom gizi (koma→titik, dash→0, tapi TIDAK normalisasi)
    for col in FEATURES:
        dash_count = df[col].astype(str).str.strip().eq('-').sum()
        df[col] = df[col].map(_normalize_commas_to_dot)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        neg_count = (df[col] < 0).sum()
        if neg_count:
            print(f"[WARN] {neg_count} nilai negatif pada kolom {col} → diset 0.")
            df.loc[df[col] < 0, col] = 0.0
        print(f"[INFO] '{col}': '-' ditemukan {dash_count} kali sebelum dibersihkan.")

    # 5) Validasi bahwa data TIDAK di-normalisasi
    max_energi = df['Energi (kal)'].max()
    if max_energi < 10:
        print(f"\n[ERROR] ❌ Data terdeteksi sudah di-normalisasi!")
        print(f"[ERROR] ❌ Energi maksimal = {max_energi} (terlalu rendah)")
        print(f"[ERROR] ❌ Data TKPI seharusnya memiliki energi 0-900 kkal/100g")
        print(f"[ERROR] ❌ Gunakan file sumber asli yang belum di-normalisasi!")
        raise ValueError("Data sudah di-normalisasi, gunakan file sumber asli!")
    
    # 6) Ringkasan cepat (pastikan nilai dalam range normal)
    print("\n[SUMMARY] Statistik kolom gizi (per 100g, TANPA scaling):")
    print(df[FEATURES].describe().T)
    print(f"\n✓ Validasi: Data dalam basis per 100 gram (nilai asli)")
    print(f"✓ Energi range: {df['Energi (kal)'].min():.1f} - {df['Energi (kal)'].max():.1f} kkal/100g")

    # 7) Simpan
    Path(output_xlsx).parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_xlsx, index=False, engine='openpyxl')
    print(f"\n[OK] ✓ Data bersih (per 100g, tanpa scaling) disimpan ke: {output_xlsx}")

    return df

if __name__ == "__main__":
    # contoh pemakaian
    input_file = "Skripsifix.xlsx"                   # ganti sesuai file kamu
    output_file = "clean_food_processed_no_scaling.xlsx"
    preprocess_data_no_scaling(input_file, output_file)
