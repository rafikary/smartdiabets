import pandas as pd

# Fungsi untuk memuat dan memproses data tanpa normalisasi
def preprocess_data_no_scaling(file_path):
    # Membaca data dari file Excel (.xlsx)
    df = pd.read_excel(file_path, engine='openpyxl')

    # Bersihkan nama kolom dari spasi di awal dan akhir
    df.columns = df.columns.str.strip()

    # Tampilkan nama kolom untuk memeriksa apakah kolom sudah benar
    print("Nama kolom yang ditemukan setelah dibersihkan:")
    print(df.columns)

    # Tampilkan 5 baris pertama untuk melihat struktur data
    print("Data sebelum preprocessing:")
    print(df.head())

    # Kolom nilai gizi yang akan dibersihkan
    columns_to_replace = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)']

    for column in columns_to_replace:
        # Ganti "-" dengan 0, koma dengan titik, dan ubah ke tipe float
        df[column] = df[column].replace('-', 0)
        df[column] = df[column].apply(lambda x: str(x).replace(',', '.') if isinstance(x, str) else x)
        df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0)

    # Tampilkan nilai maksimum dan minimum asli (tanpa scaling)
    print("Nilai maksimum asli:")
    print(df[columns_to_replace].max().to_dict())
    print("Nilai minimum asli:")
    print(df[columns_to_replace].min().to_dict())

    # Tampilkan 5 baris pertama setelah preprocessing untuk memastikan perubahan
    print("Data setelah preprocessing (tanpa scaling):")
    print(df.head())

    return df

# Simpan data yang sudah diproses ke file Excel (.xlsx)
def save_processed_data(df, output_file_path):
    df.to_excel(output_file_path, index=False, engine='openpyxl')
    print(f"Data telah disimpan di {output_file_path}")

# Contoh penggunaan
if __name__ == "__main__":
    file_path = 'Skripsifix.xlsx'  # Sesuaikan dengan file aslimu
    output_file_path = 'clean_food_processed_no_scaling.xlsx'  # Output tanpa normalisasi

    df_processed = preprocess_data_no_scaling(file_path)
    save_processed_data(df_processed, output_file_path)
