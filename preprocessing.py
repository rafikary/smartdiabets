import pandas as pd

# Fungsi untuk memuat dan memproses data
def preprocess_data(file_path):
    # Membaca data dari file Excel (.xlsx)
    df = pd.read_excel(file_path, engine='openpyxl')  # Membaca file Excel

    # Bersihkan nama kolom dari spasi di awal dan akhir
    df.columns = df.columns.str.strip()

    # Tampilkan nama kolom untuk memeriksa apakah kolom sudah benar
    print("Nama kolom yang ditemukan setelah dibersihkan:")
    print(df.columns)

    # Tampilkan 5 baris pertama untuk melihat struktur data
    print("Data sebelum preprocessing:")
    print(df.head())

    # Ganti koma dengan titik dan ubah ke float untuk kolom yang berisi nilai gizi
    columns_to_replace = ['Energi (kal)', 'Protein (g)', 'Lemak (g)', 'Karbohidrat (g)', 'Serat (g)','BDD ( 100% )']
    
    for column in columns_to_replace:
        # Ganti "-" dengan 0, koma dengan titik, dan ubah ke tipe float
        df[column] = df[column].replace('-', 0)  # Ganti "-" dengan 0
        df[column] = df[column].apply(lambda x: str(x).replace(',', '.') if isinstance(x, str) else x)  # Ganti koma dengan titik
        df[column] = pd.to_numeric(df[column], errors='coerce')  # Mengubah ke tipe float

    # Tampilkan 5 baris pertama setelah preprocessing untuk memastikan perubahan
    print("Data setelah preprocessing:")
    print(df.head())

    return df

# Simpan data yang sudah diproses ke file Excel (.xlsx)
def save_processed_data(df, output_file_path):
    # Simpan file dalam format Excel (.xlsx)
    df.to_excel(output_file_path, index=False, engine='openpyxl')
    print(f"Data telah disimpan di {output_file_path}")

# Contoh penggunaan
if __name__ == "__main__":
    # Ganti dengan path file Excel kamu
    file_path = 'Skripsifix.xlsx'  # File data yang asli dalam format Excel (.xlsx)
    output_file_path = 'clean_food_processed_data.xlsx'  # Nama file untuk data yang sudah diproses

    # Proses data
    processed_data = preprocess_data(file_path)

    # Simpan data yang sudah diproses
    save_processed_data(processed_data, output_file_path)
