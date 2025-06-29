import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import pickle

def preprocess_and_scale(file_path, output_excel_path, scaler_pickle_path, normalized_pickle_path):
    # 1. Load data
    df = pd.read_excel(file_path, engine='openpyxl')

    # 2. Bersihkan nama kolom dari spasi di awal/akhir
    df.columns = df.columns.str.strip()

    # 3. Kolom gizi yang akan diproses
    cols_gizi = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']

    # 4. Validasi kolom
    for col in cols_gizi:
        if col not in df.columns:
            raise ValueError(f"Kolom '{col}' tidak ditemukan di dataset!")

    # 5. Hitung jumlah "-" sebelum preprocessing
    print("Jumlah nilai '-' sebelum preprocessing:")
    for col in cols_gizi:
        count_dash = df[col].astype(str).apply(lambda x: x.strip() == "-").sum()
        print(f"{col}: {count_dash} nilai '-'")

    # 6. Bersihkan data gizi: ganti "-" dengan 0, koma jadi titik, konversi ke numeric
    for col in cols_gizi:
        df[col] = df[col].replace('-', 0)
        df[col] = df[col].apply(lambda x: str(x).replace(',', '.') if isinstance(x, str) else x)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 7. Verifikasi nilai "-" sudah hilang
    print("\nVerifikasi nilai '-' setelah preprocessing:")
    for col in cols_gizi:
        remaining_dash = df[col].astype(str).apply(lambda x: x.strip() == "-").sum()
        print(f"{col}: {remaining_dash} nilai '-' tersisa")

    # 8. Tampilkan min dan max asli sebelum scaling
    print("\nMin nilai asli sebelum scaling:\n", df[cols_gizi].min())
    print("Max nilai asli sebelum scaling:\n", df[cols_gizi].max())

    # 9. Normalisasi Min-Max
    scaler = MinMaxScaler()
    df[cols_gizi] = scaler.fit_transform(df[cols_gizi])

    # 10. Tampilkan min dan max setelah scaling
    print("\nMin nilai setelah scaling:\n", df[cols_gizi].min())
    print("Max nilai setelah scaling:\n", df[cols_gizi].max())

    # 11. Simpan hasil preprocessing ke Excel
    df.to_excel(output_excel_path, index=False, engine='openpyxl')
    print(f"\nData hasil preprocessing disimpan ke {output_excel_path}")

    # 12. Simpan scaler ke file pickle untuk dipakai ulang
    with open(scaler_pickle_path, 'wb') as f:
        pickle.dump(scaler, f)
    print(f"Scaler disimpan ke {scaler_pickle_path}")

    # 13. Simpan dataset yang sudah dinormalisasi ke pickle (untuk load di model)
    df.to_pickle(normalized_pickle_path)
    print(f"Dataset normalisasi disimpan ke {normalized_pickle_path}")

    return df, scaler


if __name__ == "__main__":
    input_file = 'Skripsifix.xlsx'  # Ganti sesuai nama file kamu
    output_file = 'data_preprocessed_normalized.xlsx' #ini untuk menyimpan hasil preprocessing dalam bentuk Excel
    scaler_file = 'minmax_scaler.pkl' #ini untuk menyimpan scaler agar bisa digunakan kembali
    normalized_pickle_file = 'data_normalized.pkl' # File untuk menyimpan dataset yang sudah dinormalisasi dalam format pickle

    df_processed, scaler = preprocess_and_scale(input_file, output_file, scaler_file, normalized_pickle_file)
