import customtkinter as ctk
from tkinter import messagebox, ttk
import pyodbc
import requests
import re
from datetime import datetime
from database import get_db_connection

# --- ISBN Formatting Functions ---
def format_isbn_for_display(isbn):
    """ISBN numarasını sadece görüntüleme için formatlar"""
    cleaned = re.sub(r'[^\dX]', '', isbn.upper())

    if len(cleaned) == 10:
        return f"{cleaned[0]}-{cleaned[1:5]}-{cleaned[5:9]}-{cleaned[9]}"
    elif len(cleaned) == 13:
        return f"{cleaned[0:3]}-{cleaned[3]}-{cleaned[4:8]}-{cleaned[8:12]}-{cleaned[12]}"
    else:
        return isbn


def clean_isbn(isbn):
    """ISBN'den formatlama karakterlerini temizler"""
    return re.sub(r'[^\dX]', '', isbn.upper())


def is_valid_isbn(isbn):
    """ISBN'in geçerli olup olmadığını kontrol eder"""
    if not isbn:
        return False

    cleaned = clean_isbn(isbn)

    if len(cleaned) == 10:
        if not cleaned[:-1].isdigit() and not (cleaned[:-1].isdigit() and cleaned[-1].upper() == 'X'):
            return False
        return True
    elif len(cleaned) == 13:
        if not cleaned.isdigit():
            return False
        return True

    return False


# --- Modern Düğme Sınıfı ---
class ModernButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        super().__init__(master,
                         font=ctk.CTkFont(size=14, weight="bold"),
                         corner_radius=10,
                         **kwargs)


# --- Kitap Düzenleme Penceresi (Modal Dialog) ---
class BookEditorPopup(ctk.CTkToplevel):
    def __init__(self, master, book_id=None, refresh_callback=None):
        super().__init__(master)
        self.master = master
        self.book_id = book_id
        self.refresh_callback = refresh_callback
        self.is_editing = self.book_id is not None
        self.is_destroyed = False

        self.title("📖 Kitap Düzenle" if self.is_editing else "📖 Yeni Kitap Ekle")
        self.geometry("500x700")
        self.transient(self.master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=40, pady=40)

        title_label = ctk.CTkLabel(main_frame,
                                   text="Kitap Bilgileri" if self.is_editing else "Yeni Kitap Ekle",
                                   font=ctk.CTkFont(size=28, weight="bold"))
        title_label.pack(pady=(0, 10))

        description_label = ctk.CTkLabel(main_frame,
                                         text="Kitap bilgilerini girin veya ISBN ile otomatik doldurun.",
                                         font=ctk.CTkFont(size=14),
                                         text_color="gray70")
        description_label.pack(pady=(0, 25))

        self.scrollable_frame = ctk.CTkScrollableFrame(main_frame, fg_color="transparent")
        self.scrollable_frame.pack(fill="both", expand=True)

        isbn_section = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        isbn_section.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(isbn_section, text="🔢 ISBN Numarası",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))

        isbn_input_frame = ctk.CTkFrame(isbn_section, fg_color="transparent")
        isbn_input_frame.pack(fill="x")

        self.isbn_entry = ctk.CTkEntry(isbn_input_frame,
                                       placeholder_text="9780123456789 veya 0123456789",
                                       font=ctk.CTkFont(size=12),
                                       height=45)
        self.isbn_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ModernButton(isbn_input_frame, text="ISBN ile Getir",
                     width=140, command=self.fetch_book_by_isbn).pack(side="right")

        self.isbn_status_label = ctk.CTkLabel(isbn_section, text="",
                                              font=ctk.CTkFont(size=11), text_color="gray60")
        self.isbn_status_label.pack(anchor="w", pady=(5, 0))

        self.isbn_entry.bind("<KeyRelease>", self.check_isbn_format)

        fields = [
            ("📚 Kitap Adı", "ad"),
            ("✍️ Yazar Adı", "yazar"),
            ("🏷️ Tür Adı", "tur"),
            ("📅 Yayın Yılı", "yayin_yili"),
            ("🔢 Toplam Adet", "adet"),
            ("🏢 Yayınevi", "yayinevi"),
            ("🌐 Kapak Resmi URL", "kapak_resmi_url"),
            ("📄 Sayfa Sayısı", "sayfa_sayisi")
        ]

        self.entries = {}
        for label_text, field_name in fields:
            frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
            frame.pack(fill="x", pady=(0, 15))

            ctk.CTkLabel(frame, text=label_text,
                         font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))

            entry = ctk.CTkEntry(frame, font=ctk.CTkFont(size=12), height=45)
            entry.pack(fill="x")
            self.entries[field_name] = entry

        summary_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        summary_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(summary_frame, text="📝 Özet",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))

        self.ozet_textbox = ctk.CTkTextbox(summary_frame, font=ctk.CTkFont(size=12), height=150)
        self.ozet_textbox.pack(fill="x")

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(20, 0))

        # Bu satırı ekleyin:
        if self.is_editing:
            ModernButton(button_frame, text="🗑️ Kitabı Sil",
                         fg_color="#ef4444", hover_color="#b91c1c",
                         command=self.delete_book).pack(side="left")

        self.save_button = ModernButton(button_frame, text="💾 Kaydet",
                                        fg_color="#22c55e", hover_color="#15803d",
                                        command=self.save_book)
        self.save_button.pack(side="right")

        if self.is_editing:
            self.load_book_data()
            self.save_button.configure(text="🔄 Güncelle", fg_color="#3b82f6", hover_color="#2563eb")

    def delete_book(self):
        """Kitabı veritabanından siler."""
        if not self.is_editing:
            return

        if messagebox.askyesno("Onay", "Kitabı kalıcı olarak silmek istediğinize emin misiniz?", parent=self):
            conn = get_db_connection()
            if not conn:
                return

            try:
                cursor = conn.cursor()

                # Önce ilişkili kayıtları sil
                cursor.execute("DELETE FROM kitap_rezervasyon WHERE kitap_id=?", (self.book_id,))
                cursor.execute("DELETE FROM kitap_yazar WHERE kitap_id=?", (self.book_id,))
                cursor.execute("DELETE FROM kitap_tur WHERE kitap_id=?", (self.book_id,))

                # Sonra kitabı sil
                cursor.execute("DELETE FROM kitap WHERE kitap_id=?", (self.book_id,))

                conn.commit()
                messagebox.showinfo("Başarılı", "Kitap başarıyla silindi.", parent=self)
                self.destroy()
                if self.refresh_callback:
                    self.refresh_callback()
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Hata", f"Silme işlemi sırasında bir hata oluştu: {e}", parent=self)
            finally:
                conn.close()

    def on_close(self):
        self.is_destroyed = True
        self.destroy()

    def check_isbn_format(self, event=None):
        if self.is_destroyed: return
        isbn = self.isbn_entry.get().strip()

        if not isbn:
            self.isbn_status_label.configure(text="")
            return

        if is_valid_isbn(isbn):
            self.isbn_status_label.configure(text="✅ Geçerli ISBN formatı", text_color="#22c55e")
        else:
            self.isbn_status_label.configure(text="⚠️ Geçersiz ISBN formatı", text_color="#f59e0b")

    def fetch_book_by_isbn(self):
        if self.is_destroyed: return
        raw_isbn = clean_isbn(self.isbn_entry.get())
        if not raw_isbn:
            messagebox.showwarning("Uyarı", "Lütfen ISBN girin.", parent=self)
            return

        if not is_valid_isbn(raw_isbn):
            if not messagebox.askyesno("Uyarı",
                                       "Girdiğiniz ISBN numarası geçerli bir formatta değil. "
                                       "Yine de devam etmek istiyor musunuz?", parent=self):
                return

        self.isbn_status_label.configure(text="⏳ Veriler alınıyor...", text_color="gray60")
        self.update_idletasks()

        try:
            url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{raw_isbn}&jscmd=data&format=json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or f"ISBN:{raw_isbn}" not in data:
                messagebox.showerror("Hata", "Kitap bulunamadı.", parent=self)
                self.isbn_status_label.configure(text="❌ Kitap bulunamadı.", text_color="#ef4444")
                return

            book_entry = data[f"ISBN:{raw_isbn}"]

            if 'details' in book_entry:
                book_data = book_entry['details']
            else:
                book_data = book_entry

            self.clear_other_fields()

            title = book_data.get('title', 'Bilinmiyor')
            self.entries['ad'].insert(0, title)

            authors = book_data.get('authors', [])
            author_names = [author.get('name', '') if isinstance(author, dict) else author for author in authors]
            self.entries['yazar'].insert(0, ", ".join(author_names))

            publishers = book_data.get('publishers', [])
            publisher_names = [pub.get('name', '') if isinstance(pub, dict) else pub for pub in publishers]
            self.entries['yayinevi'].insert(0, ", ".join(publisher_names))

            publish_date = book_data.get('publish_date', '')
            if publish_date:
                # Tarih metninden sadece 4 haneli yılı bul ve al
                year_match = re.search(r'\b(\d{4})\b', publish_date)
                if year_match:
                    self.entries['yayin_yili'].insert(0, year_match.group(1))

            page_count = book_data.get('number_of_pages', book_data.get('pagination', ''))
            if page_count:
                self.entries['sayfa_sayisi'].insert(0, str(page_count))

            description = book_data.get('description', '')
            if isinstance(description, dict) and 'value' in description:
                self.ozet_textbox.insert("1.0", description['value'])
            elif isinstance(description, str):
                self.ozet_textbox.insert("1.0", description)
            else:
                self.ozet_textbox.insert("1.0", "Özet bulunamadı.")

            raw_subjects = book_data.get('subjects', [])
            subject_names = []
            for subject in raw_subjects:
                name = subject.get('name', '') if isinstance(subject, dict) else subject
                if name and len(name) <= 50 and len(name.split()) <= 5:
                    subject_names.append(name)

            subject_names = subject_names[:5]

            self.entries['tur'].insert(0, ", ".join(subject_names))

            cover_url = f"https://covers.openlibrary.org/b/isbn/{raw_isbn}-M.jpg"
            self.entries['kapak_resmi_url'].insert(0, cover_url)

            self.entries['adet'].insert(0, "1")

            self.isbn_status_label.configure(text="✅ Veriler başarıyla dolduruldu.", text_color="#22c55e")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                messagebox.showerror("Hata", "Kitap bulunamadı.", parent=self)
                self.isbn_status_label.configure(text="❌ Kitap bulunamadı.", text_color="#ef4444")
            else:
                messagebox.showerror("Hata", f"API hatası: HTTP {e.response.status_code}", parent=self)
                self.isbn_status_label.configure(text="❌ API hatası.", text_color="#ef4444")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Hata", f"Ağ hatası: {e}", parent=self)
            self.isbn_status_label.configure(text="❌ Ağ hatası.", text_color="#ef4444")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}", parent=self)
            self.isbn_status_label.configure(text="❌ Bir hata oluştu.", text_color="#ef4444")
    def clear_other_fields(self):
        if self.is_destroyed: return
        for entry in self.entries.values():
            entry.delete(0, "end")
        self.ozet_textbox.delete("1.0", "end")

    def load_book_data(self):
        if self.is_destroyed: return
        conn = get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT k.ad,
                                  y.ad,
                                  t.ad,
                                  k.yayin_yili,
                                  k.adet,
                                  k.yayinevi,
                                  k.kapak_resmi_url,
                                  k.sayfa_sayisi,
                                  k.isbn,
                                  k.ozet
                           FROM kitap k
                                    LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                    LEFT JOIN yazar y ON ky.yazar_id = y.yazar_id
                                    LEFT JOIN kitap_tur kt ON k.kitap_id = kt.kitap_id
                                    LEFT JOIN tur t ON kt.tur_id = t.tur_id
                           WHERE k.kitap_id = ?
                           """, (self.book_id,))

            data = cursor.fetchone()
            if data:
                ad, yazar_ad, tur_ad, yayin_yili, adet, yayinevi, kapak, sayfa, isbn, ozet = data

                self.entries['ad'].insert(0, ad or "")
                self.entries['yazar'].insert(0, yazar_ad or "")
                self.entries['tur'].insert(0, tur_ad or "")
                self.entries['yayin_yili'].insert(0, yayin_yili or "")
                self.entries['adet'].insert(0, adet or "")
                self.entries['yayinevi'].insert(0, yayinevi or "")
                self.entries['kapak_resmi_url'].insert(0, kapak or "")
                self.entries['sayfa_sayisi'].insert(0, sayfa or "")

                if isbn:
                    self.isbn_entry.insert(0, isbn)
                    self.check_isbn_format()

                self.ozet_textbox.insert("1.0", ozet or "")

        except Exception as e:
            messagebox.showerror("Hata", f"Kitap yüklenirken hata: {e}", parent=self)
        finally:
            conn.close()

    def check_duplicate_book(self, isbn, book_title, author_name):
        if self.is_destroyed: return False
        conn = get_db_connection()
        if not conn: return False

        try:
            cursor = conn.cursor()

            if isbn:
                cursor.execute("SELECT COUNT(*) FROM kitap WHERE isbn = ?", (isbn,))
                if cursor.fetchone()[0] > 0:
                    return True

            cursor.execute("""
                           SELECT COUNT(*)
                           FROM kitap k
                                    JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                    JOIN yazar y ON ky.yazar_id = y.yazar_id
                           WHERE k.ad = ?
                             AND y.ad = ?
                           """, (book_title, author_name))

            return cursor.fetchone()[0] > 0

        except Exception as e:
            print(f"Çift kayıt kontrol hatası: {e}")
            return False
        finally:
            conn.close()

    def save_book(self):
        if self.is_destroyed: return
        ad = self.entries['ad'].get().strip()
        yazar_ad = self.entries['yazar'].get().strip()
        tur_ad = self.entries['tur'].get().strip()
        yayin_yili = self.entries['yayin_yili'].get().strip()
        adet = self.entries['adet'].get().strip()
        yayinevi = self.entries['yayinevi'].get().strip()
        kapak_resmi_url = self.entries['kapak_resmi_url'].get().strip()
        sayfa_sayisi = self.entries['sayfa_sayisi'].get().strip()
        isbn = clean_isbn(self.isbn_entry.get())
        ozet = self.ozet_textbox.get("1.0", "end-1c").strip()

        if not all([ad, yazar_ad, tur_ad]):
            messagebox.showerror("Hata", "Kitap adı, yazar ve tür zorunludur.", parent=self)
            return

        if isbn and not is_valid_isbn(isbn):
            if not messagebox.askyesno("Uyarı",
                                       "Girdiğiniz ISBN numarası geçerli bir formatta değil. "
                                       "Yine de kaydetmek istiyor musunuz?", parent=self):
                return

        if not self.is_editing:
            is_duplicate = self.check_duplicate_book(isbn, ad, yazar_ad)
            if is_duplicate:
                messagebox.showerror("Hata",
                                     "Bu kitap zaten kayıtlı!",
                                     parent=self)
                return

        conn = get_db_connection()
        if not conn:
            messagebox.showerror("Hata", "Veritabanına bağlanılamadı.", parent=self)
            return

        try:
            cursor = conn.cursor()

            cursor.execute("SELECT yazar_id FROM yazar WHERE ad=?", (yazar_ad,))
            res = cursor.fetchone()
            if res:
                yazar_id = res[0]
            else:
                cursor.execute("INSERT INTO yazar (ad) VALUES (?)", (yazar_ad,))
                cursor.execute("SELECT @@IDENTITY")
                yazar_id = cursor.fetchone()[0]

            cursor.execute("SELECT tur_id FROM tur WHERE ad=?", (tur_ad,))
            res = cursor.fetchone()
            if res:
                tur_id = res[0]
            else:
                cursor.execute("INSERT INTO tur (ad) VALUES (?)", (tur_ad,))
                cursor.execute("SELECT @@IDENTITY")
                tur_id = cursor.fetchone()[0]

            if self.is_editing:
                cursor.execute("""
                               UPDATE kitap
                               SET ad=?,
                                   yayin_yili=?,
                                   adet=?,
                                   yayinevi=?,
                                   kapak_resmi_url=?,
                                   sayfa_sayisi=?,
                                   isbn=?,
                                   ozet=?
                               WHERE kitap_id = ?
                               """, (ad, yayin_yili or None, int(adet) if adet.isdigit() else 1,
                                     yayinevi or None, kapak_resmi_url or None,
                                     int(sayfa_sayisi) if sayfa_sayisi.isdigit() else None,
                                     isbn or None, ozet or None, self.book_id))

                kitap_id = self.book_id
                cursor.execute("DELETE FROM kitap_yazar WHERE kitap_id=?", (kitap_id,))
                cursor.execute("DELETE FROM kitap_tur WHERE kitap_id=?", (kitap_id,))

                messagebox.showinfo("Başarılı", "Kitap güncellendi.", parent=self)
            else:
                cursor.execute("""
                               INSERT INTO kitap (ad, yayin_yili, adet, yayinevi,
                                                  kapak_resmi_url, sayfa_sayisi, isbn, ozet) OUTPUT INSERTED.kitap_id
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                               """, (ad, yayin_yili or None, int(adet) if adet.isdigit() else 1,
                                     yayinevi or None, kapak_resmi_url or None,
                                     int(sayfa_sayisi) if sayfa_sayisi.isdigit() else None,
                                     isbn or None, ozet or None))

                kitap_id = cursor.fetchone()[0]
                messagebox.showinfo("Başarılı", "Kitap başarıyla eklendi.", parent=self)

            cursor.execute("INSERT INTO kitap_yazar (kitap_id,yazar_id) VALUES (?,?)", (kitap_id, yazar_id))
            cursor.execute("INSERT INTO kitap_tur (kitap_id,tur_id) VALUES (?,?)", (kitap_id, tur_id))

            conn.commit()
            self.destroy()
            if self.refresh_callback:
                self.refresh_callback()

        except pyodbc.IntegrityError:
            conn.rollback()
            messagebox.showerror("Hata", "Bu kitap zaten kayıtlı!", parent=self)
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Kaydetme hatası: {e}", parent=self)
        finally:
            conn.close()


# --- Rezervasyon Yönetim Çerçevesi ---
class ReservationManagerFrame(ctk.CTkFrame):
    def __init__(self, master, switch_callback):
        super().__init__(master)
        self.switch_callback = switch_callback
        self.all_book_reservations = []
        self.all_table_reservations = []
        self.active_filters = {}
        self.after_id = None
        self.is_destroyed = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        # Geri dönüş butonu ekle
        back_button = ModernButton(header_frame, text="⬅️ Kitaplara Dön",
                                   command=lambda: self.switch_callback("book"),
                                   fg_color="transparent", border_color="gray", border_width=1)
        back_button.grid(row=0, column=1, sticky="w", padx=(0, 20))

        ctk.CTkLabel(header_frame, text="📅 Rezervasyonları Yönet",
                     font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, sticky="w")

        search_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        search_frame.grid(row=0, column=2, sticky="e")

        self.search_entry = ctk.CTkEntry(search_frame,
                                         placeholder_text="🔍 Rezervasyon ara...",
                                         font=ctk.CTkFont(size=14),
                                         width=300)
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_key_release)

        ModernButton(search_frame, text="🔄 Yenile", command=self.fetch_all_reservations, width=100).pack(side="left")

        # Tab View
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.tab_view.add("📖 Kitap Rezervasyonları")
        self.tab_view.add("🪑 Masa Rezervasyonları")
        self.tab_view.configure(command=self.on_tab_change)

        self.book_tab = self.tab_view.tab("📖 Kitap Rezervasyonları")
        self.table_tab = self.tab_view.tab("🪑 Masa Rezervasyonları")

        self.book_tab.grid_columnconfigure(0, weight=1)
        self.book_tab.grid_rowconfigure(0, weight=1)
        self.table_tab.grid_columnconfigure(0, weight=1)
        self.table_tab.grid_rowconfigure(0, weight=1)

        # Kitap rezervasyonları için Treeview
        columns_book = ("ID", "Kitap Adı", "Üye", "Alış Tarihi", "Son İade Tarihi", "Durum")
        self.book_tree = ttk.Treeview(self.book_tab, columns=columns_book, show="headings")
        self.book_tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        self.book_tree.heading("Kitap Adı", text="Kitap Adı")
        self.book_tree.heading("Üye", text="Üye")
        self.book_tree.heading("Alış Tarihi", text="Alış Tarihi")
        self.book_tree.heading("Son İade Tarihi", text="Son İade Tarihi")
        self.book_tree.heading("Durum", text="Durum")

        # ID sütununu gizlemek için genişliği 0 yapın.
        self.book_tree.column("ID", width=0, stretch=False)
        for col in columns_book[1:]:  # ID hariç diğer sütunlar için
            self.book_tree.column(col, anchor="center")
        self.book_tree.bind("<<TreeviewSelect>>", lambda e: self.update_buttons())

        # Masa rezervasyonları için Treeview - DEĞİŞTİRİLDİ
        columns_table = ("ID", "Masa", "Üye", "Tarih", "Saat Aralığı", "Durum")  # "Masa No" yerine "Masa"
        self.table_tree = ttk.Treeview(self.table_tab, columns=columns_table, show="headings")
        self.table_tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.table_tree.heading("Masa", text="Masa")  # "Masa No" yerine "Masa"
        self.table_tree.heading("Üye", text="Üye")
        self.table_tree.heading("Tarih", text="Tarih")
        self.table_tree.heading("Saat Aralığı", text="Saat Aralığı")
        self.table_tree.heading("Durum", text="Durum")

        # ID sütununu gizlemek için genişliği 0 yapın.
        self.table_tree.column("ID", width=0, stretch=False)
        for col in columns_table[1:]:  # ID hariç diğer sütunlar için
            self.table_tree.column(col, anchor="center")
        self.table_tree.bind("<<TreeviewSelect>>", lambda e: self.update_buttons())

        # İşlem butonlarını ekle
        self.button_frame_book = ctk.CTkFrame(self.book_tab, fg_color="transparent")
        self.button_frame_book.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.button_frame_book.grid_columnconfigure(0, weight=1)

        # Teslim Alındı butonunu ekleyin
        self.complete_btn = ModernButton(self.button_frame_book, text="✅ Teslim Alındı", fg_color="#22c55e",
                                         hover_color="#15803d", command=self.complete_book_reservation)
        self.complete_btn.pack(side="left", padx=(0, 10))

        self.delete_book_btn = ModernButton(self.button_frame_book, text="🗑️ Sil", fg_color="#ef4444",
                                            hover_color="#dc2626", command=self.delete_book_reservation)
        self.delete_book_btn.pack(side="left")

        self.button_frame_table = ctk.CTkFrame(self.table_tab, fg_color="transparent")
        self.button_frame_table.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        self.button_frame_table.grid_columnconfigure(0, weight=1)

        self.arrived_btn = ModernButton(self.button_frame_table, text="✅ Geldi", fg_color="#22c55e",
                                        hover_color="#15803d", command=self.mark_as_arrived)
        self.arrived_btn.pack(side="left", padx=(0, 10))

        self.cancel_table_btn = ModernButton(self.button_frame_table, text="❌ İptal Et", fg_color="#ef4444",
                                             hover_color="#dc2626", command=self.cancel_table_reservation)
        self.cancel_table_btn.pack(side="left", padx=(0, 10))

        self.delete_table_btn = ModernButton(self.button_frame_table, text="🗑️ Sil", fg_color="#9ca3af",
                                             hover_color="#4b5563", command=self.delete_table_reservation)
        self.delete_table_btn.pack(side="left")

        # Buton durumunu ayarla ve veri çek
        self.update_buttons()
        self.fetch_all_reservations()

        self.after_id = self.master.after(1000, self.check_alive)

    # update_buttons metodunu güncelleyin:
    def update_buttons(self):
        """Seçilen öğeye göre butonların durumunu günceller"""
        current_tab = self.tab_view.get()
        if current_tab == "📖 Kitap Rezervasyonları":
            selected_items = self.book_tree.selection()

            # Kitap butonlarını sıfırla
            self.complete_btn.configure(state="disabled")
            self.delete_book_btn.configure(state="disabled")

            if selected_items:
                item_values = self.book_tree.item(selected_items[0], 'values')
                if len(item_values) >= 6:  # En az 6 değer olduğundan emin ol
                    status = item_values[5]  # Durum 6. sütunda (index 5)

                    # Aktif veya Gecikmiş rezervasyonlar için teslim alındı butonunu etkinleştir
                    if status in ["aktif", "gecikti"]:
                        self.complete_btn.configure(state="normal")

                    # Tüm durumlar için silme butonunu etkinleştir
                    self.delete_book_btn.configure(state="normal")

        elif current_tab == "🪑 Masa Rezervasyonları":
            selected_items = self.table_tree.selection()

            # Masa butonlarını sıfırla
            self.arrived_btn.configure(state="disabled")
            self.cancel_table_btn.configure(state="disabled")
            self.delete_table_btn.configure(state="disabled")

            if selected_items:
                item_values = self.table_tree.item(selected_items[0], 'values')
                if len(item_values) >= 6:  # En az 6 değer olduğundan emin ol
                    status = item_values[5]  # Durum 6. sütunda (index 5)

                    # Sadece aktif rezervasyonlar için "Geldi" butonunu etkinleştir
                    if status == "Aktif":
                        self.arrived_btn.configure(state="normal")
                        self.cancel_table_btn.configure(state="normal")

                    # Tüm durumlar için silme butonunu etkinleştir
                    self.delete_table_btn.configure(state="normal")

    def complete_book_reservation(self):
        """Seçilen kitap rezervasyonunu 'tamamlandı' olarak işaretler ve stok ile ceza puanını günceller."""
        selected_item = self.book_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen bir rezervasyon seçin.")
            return

        item_values = self.book_tree.item(selected_item, 'values')
        if len(item_values) < 6:
            messagebox.showerror("Hata", "Geçersiz rezervasyon verisi.")
            return

        res_id = item_values[0]
        current_status = item_values[5]

        if current_status == "tamamlandı":
            messagebox.showinfo("Bilgi", "Bu rezervasyon zaten tamamlanmış.")
            return

        if not messagebox.askyesno("Onay", "Bu kitabı teslim alındı olarak işaretlemek istediğinizden emin misiniz?"):
            return

        conn = get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()

            # Önce rezervasyon bilgilerini al
            cursor.execute("""
                           SELECT kullanici_id, son_iade_tarihi, kitap_id
                           FROM kitap_rezervasyon
                           WHERE kitap_rezervasyon_id = ?
                           """, (res_id,))

            reservation = cursor.fetchone()
            if not reservation:
                messagebox.showerror("Hata", "Rezervasyon bulunamadı.")
                return

            user_id, return_date, kitap_id = reservation

            # Gecikme kontrolü yap - tarih türlerini uyumlu hale getir
            is_delayed = False
            if return_date:
                # Tarih karşılaştırması için her iki tarafı da datetime nesnesine çevir
                from datetime import datetime as dt
                now = dt.now()

                # return_date'i datetime nesnesine çevir
                if hasattr(return_date, 'date') and hasattr(return_date, 'time'):
                    # Zaten datetime nesnesi
                    return_datetime = return_date
                else:
                    # date nesnesi ise datetime'a çevir
                    return_datetime = dt.combine(return_date, dt.min.time())

                if return_datetime < now:
                    is_delayed = True

                    # Ceza puanı ekle (5 puan)
                    cursor.execute("""
                                   UPDATE kullanici
                                   SET ceza_puani = ISNULL(ceza_puani, 0) + 5
                                   WHERE kullanici_id = ?
                                   """, (user_id,))

            # Rezervasyonu tamamla ve durumu güncelle
            # Eğer gecikme varsa durumu "Ceza" olarak güncelle
            new_status = "Ceza" if is_delayed else "tamamlandı"

            # Kitabın iade tarihini şu anki tarih ve saat olarak ayarla
            iade_tarihi = datetime.now()

            cursor.execute("""
                           UPDATE kitap_rezervasyon
                           SET durum            = ?,
                               teslim_edildi_mi = 1,
                               iade_tarihi      = ?
                           WHERE kitap_rezervasyon_id = ?
                           """, (new_status, iade_tarihi, res_id))

            # Kitabın stok adedini güncelle
            cursor.execute("""
                           UPDATE kitap
                           SET adet = adet + 1
                           WHERE kitap_id = ?
                           """, (kitap_id,))

            conn.commit()

            if is_delayed:
                messagebox.showinfo("Başarılı",
                                    f"Kitap rezervasyonu başarıyla teslim alındı. \n"
                                    f"Gecikme tespit edildiği için kullanıcıya 5 ceza puanı eklendi ve durum 'Ceza' olarak güncellendi.")
            else:
                messagebox.showinfo("Başarılı", "Kitap rezervasyonu başarıyla teslim alındı.")

            self.fetch_all_reservations()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Rezervasyon güncellenirken hata: {e}")
        finally:
            conn.close()
    def mark_as_arrived(self):
        """Masa rezervasyonu için 'Geldi' işlevini gerçekleştirir"""
        selected_item = self.table_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen bir masa rezervasyonu seçin.")
            return

        item_values = self.table_tree.item(selected_item, 'values')
        if len(item_values) < 6:
            messagebox.showerror("Hata", "Geçersiz rezervasyon verisi.")
            return

        reservation_id = item_values[0]
        user_name = item_values[2]
        masa_adi = item_values[1]
        reservation_date_str = item_values[3]
        reservation_time_range_str = item_values[4]
        current_status = item_values[5]

        # Sadece "Aktif" rezervasyonlar için işleme devam et
        if current_status not in ["Aktif"]:
            messagebox.showwarning("Uyarı", "Sadece aktif rezervasyonlar için 'Geldi' işaretlenebilir.")
            return

        # Tarih ve saat bilgisini kontrol et
        try:
            # Rezervasyon başlangıç saatini al
            start_time_str = reservation_time_range_str.split(' - ')[0]
            # Rezervasyon tarihini ve saatini birleştirerek datetime nesnesi oluştur
            reservation_datetime = datetime.strptime(f"{reservation_date_str} {start_time_str}", "%d.%m.%Y %H:%M")

            # Rezervasyon saatinden önce işaretlenmesini önle
            if datetime.now() < reservation_datetime:
                messagebox.showwarning("Uyarı", "Rezervasyon saati gelmeden 'Geldi' olarak işaretleyemezsiniz.")
                return

        except ValueError as e:
            messagebox.showerror("Hata", f"Tarih/saat formatı hatası: {e}")
            return

        if messagebox.askyesno("Onay", f"{user_name} kullanıcısının {masa_adi} için geldiğini onaylıyor musunuz?"):
            conn = get_db_connection()
            if not conn:
                return
            try:
                cursor = conn.cursor()
                cursor.execute("UPDATE masa_rezervasyon SET durum = 'Tamamlandı' WHERE masa_rezervasyon_id = ?",
                               (reservation_id,))
                conn.commit()
                messagebox.showinfo("Başarılı", "Masa rezervasyon durumu 'Tamamlandı' olarak güncellendi.")
                self.fetch_all_reservations()
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Hata", f"Rezervasyon güncellenirken hata: {e}")
            finally:
                conn.close()
    def on_treeview_select(self, event):
        # Bu metot, treeview'de bir öğe seçildiğinde tetiklenir.
        selected_items = self.reservation_treeview.selection()
        if selected_items:
            item = selected_items[0]
            item_values = self.reservation_treeview.item(item, 'values')

            # Seçili öğenin statüsünü kontrol et
            status = item_values[6]  # Statü kolonu 7. sırada (index 6)

            if status == "Aktif":
                self.geldi_button.configure(state="normal")
            else:
                self.geldi_button.configure(state="disabled")
        else:
            self.geldi_button.configure(state="disabled")

    def on_tab_change(self, tab_name=None):
        if tab_name:
            # Your existing logic
            self.update_buttons()
            self.search_entry.delete(0, "end")
            self.filter_reservations_by_search()


    def apply_filters(self, filters):
        self.active_filters = filters
        self.fetch_all_reservations()

    def check_alive(self):
        if not self.master.is_alive:
            self.cancel_after_job()
            return
        if self.after_id is not None:
            self.after_id = self.master.after(1000, self.check_alive)

    def cancel_after_job(self):
        if self.after_id is not None:
            self.master.after_cancel(self.after_id)
            self.after_id = None

    def fetch_all_reservations(self):
        self.fetch_book_reservations()
        self.fetch_table_reservations()

    def fetch_book_reservations(self):
        self.book_tree.delete(*self.book_tree.get_children())
        conn = get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            query = """
                    SELECT kr.kitap_rezervasyon_id,
                           k.ad,
                           u.isim,
                           kr.alis_tarihi,
                           kr.son_iade_tarihi,
                           kr.durum -- Yeni durum sütunu
                    FROM kitap_rezervasyon kr
                             JOIN kitap k ON kr.kitap_id = k.kitap_id
                             JOIN kullanici u ON kr.kullanici_id = u.kullanici_id
                    ORDER BY CASE
                                 WHEN kr.durum = 'aktif' THEN 0
                                 WHEN kr.durum = 'gecikti' THEN 1
                                 WHEN kr.durum = 'ceza' THEN 2
                                 ELSE 3 END,
                             kr.alis_tarihi DESC
                    """
            cursor.execute(query)
            self.all_book_reservations = cursor.fetchall()

            # Uygulanan filtreleri kullanarak veriyi filtrele
            filtered_list = self.all_book_reservations
            book_status_filter = self.active_filters.get('book_status')
            if book_status_filter and book_status_filter != "Tümü":
                filtered_list = [r for r in filtered_list if r[5] == book_status_filter]

            self.display_book_reservations(filtered_list)
            self.on_search_key_release()

        except Exception as e:
            messagebox.showerror("Hata", f"Kitap rezervasyonları yüklenirken hata: {e}")
        finally:
            conn.close()

    def display_book_reservations(self, reservations):
        self.book_tree.delete(*self.book_tree.get_children())
        if not reservations:
            self.book_tree.insert("", "end", values=("", "Kayıtlı kitap rezervasyonu bulunamadı.", "", "", "", ""))
            return

        for r in reservations:
            alis_tarihi_str = r[3].strftime("%d.%m.%Y") if r[3] else "Bilinmiyor"
            son_iade_tarihi_str = r[4].strftime("%d.%m.%Y") if r[4] else "Bilinmiyor"

            # Durumu doğrudan veritabanından al
            durum = r[5]

            self.book_tree.insert("", "end", values=(r[0], r[1], r[2], alis_tarihi_str, son_iade_tarihi_str, durum))


    def format_masa_adi(self, masa_no):
        """Masa numarasını daha okunabilir bir formata dönüştürür ve alt çizgileri kaldırır"""
        if masa_no is None:
            return "Bilinmeyen Masa"

        # Önce string'e çevir ve alt çizgileri kaldır
        masa_str = str(masa_no).replace('_', ' ').strip()

        # Eğer sadece sayılardan oluşuyorsa "Masa" önekini ekle
        if masa_str.isdigit():
            return f"Masa {masa_str}"

        # Değilse, olduğu gibi döndür (ama alt çizgileri kaldırarak)
        return masa_str

        return str(masa_no).replace('_', '')

    def fetch_table_reservations(self):
        """Veritabanından tüm masa rezervasyonlarını çeker ve görüntüler."""
        self.table_tree.delete(*self.table_tree.get_children())
        conn = get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            query = """
                    SELECT mr.masa_rezervasyon_id,
                           m.numara,
                           u.isim,
                           mr.tarih,
                           mr.saat_baslangic,
                           mr.saat_bitis,
                           mr.iptal_durumu,
                           mr.durum
                    FROM masa_rezervasyon mr
                             JOIN masa m ON mr.masa_id = m.masa_id
                             JOIN kullanici u ON mr.kullanici_id = u.kullanici_id
                    ORDER BY CASE
                                 WHEN mr.iptal_durumu = 0 AND (mr.tarih > GETDATE() OR
                                                               (mr.tarih = CAST(GETDATE() AS DATE) AND
                                                                mr.saat_bitis > CAST(GETDATE() AS TIME))) THEN 0
                                 WHEN mr.iptal_durumu = 0 THEN 1
                                 ELSE 2 END,
                             mr.tarih DESC, mr.saat_baslangic DESC
                    """
            cursor.execute(query)
            raw_reservations = cursor.fetchall()

            # Rezervasyon durumlarını manuel olarak hesapla ve tek bir döngüde liste oluştur
            self.all_table_reservations = []
            for reservation in raw_reservations:
                reservation_id, masa_no, uye, tarih, baslangic, bitis, iptal_durumu, durum_from_db = reservation

                # Masa adını formatla
                masa_adi = self.format_masa_adi(masa_no)

                # Durumu belirle
                if durum_from_db and durum_from_db.strip():
                    durum_to_display = durum_from_db
                elif iptal_durumu:
                    durum_to_display = "İptal Edildi"
                else:
                    now = datetime.now()
                    rezervasyon_bitis = datetime.combine(tarih, bitis) if tarih and bitis else None

                    if rezervasyon_bitis and rezervasyon_bitis < now:
                        durum_to_display = "Tamamlandı"
                    else:
                        durum_to_display = "Aktif"

                # Güncellenmiş rezervasyon bilgilerini sakla
                self.all_table_reservations.append((
                    reservation_id, masa_adi, uye, tarih, baslangic, bitis, durum_to_display
                ))

            # Filtreleme ve görüntüleme
            filtered_list = self.all_table_reservations
            table_status_filter = self.active_filters.get('table_status')
            table_date_filter = self.active_filters.get('date')

            if table_status_filter and table_status_filter != "Tümü":
                if table_status_filter == "Aktif":
                    filtered_list = [r for r in filtered_list if r[6] == "Aktif"]
                elif table_status_filter == "İptal Edildi":
                    filtered_list = [r for r in filtered_list if r[6] == "İptal Edildi"]
                elif table_status_filter == "Tamamlandı":
                    filtered_list = [r for r in filtered_list if r[6] == "Tamamlandı"]
                elif table_status_filter == "Ceza":
                    filtered_list = [r for r in filtered_list if r[6] == "Ceza"]

            if table_date_filter:
                filtered_list = [r for r in filtered_list if r[3] and r[3].date() == table_date_filter]

            self.display_table_reservations(filtered_list)
            self.on_search_key_release()

        except Exception as e:
            messagebox.showerror("Hata", f"Masa rezervasyonları yüklenirken hata: {e}")
        finally:
            conn.close()
    def display_table_reservations(self, reservations):
        self.table_tree.delete(*self.table_tree.get_children())
        if not reservations:
            self.table_tree.insert("", "end", values=("", "Kayıtlı masa rezervasyonu bulunamadı.", "", "", "", ""))
            return

        for r in reservations:
            reservation_id, masa_adi, uye, tarih, baslangic, bitis, durum = r

            tarih_str = tarih.strftime("%d.%m.%Y") if tarih else "Bilinmiyor"
            saat_baslangic_str = baslangic.strftime("%H:%M") if baslangic else "Bilinmiyor"
            saat_bitis_str = bitis.strftime("%H:%M") if bitis else "Bilinmiyor"

            self.table_tree.insert("", "end",
                                   values=(reservation_id, masa_adi, uye, tarih_str,
                                           f"{saat_baslangic_str} - {saat_bitis_str}", durum))

    # Diğer metodlar aynı kalacak...
    # ... (diğer metodlar burada kalacak)
    def on_search_key_release(self, event=None):
        self.filter_reservations_by_search()

    def filter_reservations_by_search(self):
        search_term = self.search_entry.get().strip().lower()
        active_tab = self.tab_view.get()

        if active_tab == "📖 Kitap Rezervasyonları":
            filtered_list = [r for r in self.all_book_reservations if
                             search_term in str(r[1]).lower() or  # Kitap adı
                             search_term in str(r[2]).lower()]  # Üye

            book_status_filter = self.active_filters.get('book_status')
            if book_status_filter and book_status_filter != "Tümü":
                if book_status_filter == "Aktif":
                    filtered_list = [r for r in filtered_list if not r[5]]
                elif book_status_filter == "Tamamlandı":
                    filtered_list = [r for r in filtered_list if r[5]]
                elif book_status_filter == "Gecikti":
                    filtered_list = [r for r in filtered_list if
                                     not r[5] and r[4] and r[4].date() < datetime.now().date()]

            self.display_book_reservations(filtered_list)

        elif active_tab == "🪑 Masa Rezervasyonları":
            filtered_list = [r for r in self.all_table_reservations if
                             search_term in str(r[1]).lower() or  # Masa no
                             search_term in str(r[2]).lower()]  # Üye

            table_status_filter = self.active_filters.get('table_status')
            table_date_filter = self.active_filters.get('date')

            if table_status_filter and table_status_filter != "Tümü":
                if table_status_filter == "Aktif":
                    filtered_list = [r for r in filtered_list if not r[6]]
                elif table_status_filter == "İptal Edildi":
                    filtered_list = [r for r in filtered_list if r[6]]

            if table_date_filter:
                filtered_list = [r for r in filtered_list if r[3] and r[3].date() == table_date_filter.date()]

            self.display_table_reservations(filtered_list)

    def delete_book_reservation(self):
        selected_item = self.book_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen bir rezervasyon seçin.")
            return
        res_id = self.book_tree.item(selected_item, 'values')[0]
        if not messagebox.askyesno("Onay", "Bu rezervasyonu kalıcı olarak silmek istediğinize emin misiniz?"):
            return
        conn = get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM kitap_rezervasyon WHERE kitap_rezervasyon_id=?", (res_id,))
            conn.commit()
            messagebox.showinfo("Başarılı", "Kitap rezervasyonu başarıyla silindi.")
            self.fetch_all_reservations()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Rezervasyon silinirken hata: {e}")
        finally:
            conn.close()

    def cancel_table_reservation(self):
        selected_item = self.table_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen bir rezervasyon seçin.")
            return
        res_id = self.table_tree.item(selected_item, 'values')[0]
        if not messagebox.askyesno("Onay", "Bu masa rezervasyonunu iptal etmek istediğinize emin misiniz?"):
            return
        conn = get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE masa_rezervasyon SET iptal_durumu=1 WHERE masa_rezervasyon_id=?", (res_id,))
            conn.commit()
            messagebox.showinfo("Başarılı", "Masa rezervasyonu başarıyla iptal edildi.")
            self.fetch_all_reservations()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Masa rezervasyonu iptal edilirken hata: {e}")
        finally:
            conn.close()

    def delete_table_reservation(self):
        selected_item = self.table_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen bir rezervasyon seçin.")
            return
        res_id = self.table_tree.item(selected_item, 'values')[0]
        if not messagebox.askyesno("Onay", "Bu masa rezervasyonunu kalıcı olarak silmek istediğinize emin misiniz?"):
            return
        conn = get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM masa_rezervasyon WHERE masa_rezervasyon_id=?", (res_id,))
            conn.commit()
            messagebox.showinfo("Başarılı", "Masa rezervasyonu başarıyla silindi.")
            self.fetch_all_reservations()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Masa rezervasyonu silinirken hata: {e}")
        finally:
            conn.close()

    def destroy(self):
        self.is_destroyed = True
        if self.after_id:
            self.master.after_cancel(self.after_id)
        super().destroy()


# --- Modern Kitap Listesi Yöneticisi Çerçevesi ---
class BookListManagerFrame(ctk.CTkFrame):
    def __init__(self, master, switch_callback):
        super().__init__(master)
        self.switch_callback = switch_callback
        self.all_books = []
        self.after_id = None
        self.is_destroyed = False

        # Grid yapılandırması
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Treeview'un olduğu satıra weight veriyoruz

        # Header Frame
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=40, pady=10, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_frame, text="📖 Kütüphane Yönetim Sistemi",
                     font=ctk.CTkFont(size=32, weight="bold")).grid(row=0, column=0, sticky="w")

        button_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        button_frame.grid(row=0, column=1, sticky="e")

        ModernButton(button_frame, text="📅 Rezervasyonları Yönet",
                     command=lambda: self.switch_callback("reservation"), fg_color="#facc15",
                     hover_color="#eab308").pack(side="left", padx=5)

        ModernButton(button_frame, text="➕ Yeni Kitap Ekle",
                     command=self.add_new_book, fg_color="#3b82f6", hover_color="#2563eb").pack(side="left", padx=5)

        ModernButton(button_frame, text="🔄 Yenile",
                     command=self.fetch_and_display_books, fg_color="transparent", border_color="gray",
                     border_width=1).pack(side="left", padx=5)

        # Arama Frame - YUKARI TAŞINDI
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.grid(row=1, column=0, padx=40, pady=(0, 10), sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(search_frame,
                                         placeholder_text="🔍 Kitap adı, yazar, tür, ISBN veya yayınevi ara...",
                                         font=ctk.CTkFont(size=14),
                                         height=40)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search_key_release)

        ModernButton(search_frame, text="🗑️ Temizle", width=100,
                     command=self.clear_search, fg_color="transparent",
                     border_color="gray", border_width=1).grid(row=0, column=1)

        # Treeview Frame
        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.grid(row=2, column=0, padx=40, pady=(0, 10), sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        # Scrollbar ekleme
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll.pack(side="right", fill="y")

        columns = ("ID", "Kitap Adı", "Yazar", "Tür", "Yayın Yılı", "Adet")
        self.book_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                      yscrollcommand=tree_scroll.set)
        self.book_tree.pack(expand=True, fill="both")
        tree_scroll.config(command=self.book_tree.yview)

        self.book_tree.bind("<Double-1>", self.on_book_double_click)

        # Sütun başlıkları ve yapılandırması
        self.book_tree.heading("Kitap Adı", text="Kitap Adı")
        self.book_tree.heading("Yazar", text="Yazar")
        self.book_tree.heading("Tür", text="Tür")
        self.book_tree.heading("Yayın Yılı", text="Yayın Yılı")
        self.book_tree.heading("Adet", text="Adet")

        # Sütun genişlikleri ve hizalaması
        self.book_tree.column("ID", width=0, stretch=False, anchor="center")  # Gizli sütun
        self.book_tree.column("Kitap Adı", width=250, anchor="center", minwidth=150)
        self.book_tree.column("Yazar", width=150, anchor="center", minwidth=100)
        self.book_tree.column("Tür", width=120, anchor="center", minwidth=80)
        self.book_tree.column("Yayın Yılı", width=100, anchor="center", minwidth=80)
        self.book_tree.column("Adet", width=80, anchor="center", minwidth=60)

        self.book_tree.bind("<<TreeviewSelect>>", self.on_item_select)

        # Durum etiketi - daha düzgün konumlandırma
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=14),
                                         text_color="gray60", height=20)
        self.status_label.grid(row=3, column=0, pady=(0, 10), sticky="ew")

    def on_book_double_click(self, event):
        """Listede bir kitaba çift tıklanınca düzenleme pop-up'ını aç."""
        # Fare konumundaki satırı al
        item_id = self.book_tree.identify_row(event.y)
        if not item_id:
            return

        values = self.book_tree.item(item_id, "values")
        if not values:
            return

        book_id = values[0]  # İlk sütun kitap_id
        BookEditorPopup(self.master, book_id=book_id, refresh_callback=self.fetch_and_display_books)

    def on_item_select(self, event):
        selected_item = self.book_tree.focus()


    def on_search_key_release(self, event):
        search_term = self.search_entry.get().strip()
        if len(search_term) >= 2 or len(search_term) == 0:
            self.filter_books()
        elif len(search_term) == 1:
            self.status_label.configure(text="🔍 Daha fazla karakter girin...")
        else:
            self.status_label.configure(text="")

    def clear_search(self):
        self.search_entry.delete(0, "end")
        self.filter_books()
        self.status_label.configure(text="")

    def add_new_book(self):
        BookEditorPopup(self.master, refresh_callback=self.fetch_and_display_books)

    def fetch_and_display_books(self):
        self.book_tree.delete(*self.book_tree.get_children())
        self.status_label.configure(text="⏳ Kitaplar yükleniyor...")
        self.update()

        conn = get_db_connection()
        if not conn:
            self.status_label.configure(text="❌ Veritabanı bağlantı hatası.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT k.kitap_id,
                                  k.ad,
                                  k.yayin_yili,
                                  k.adet,
                                  k.yayinevi,
                                  k.kapak_resmi_url,
                                  k.sayfa_sayisi,
                                  k.isbn,
                                  k.ozet,
                                  y.ad as yazar_ad,
                                  t.ad as tur_ad
                           FROM kitap k
                                    LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                    LEFT JOIN yazar y ON ky.yazar_id = y.yazar_id
                                    LEFT JOIN kitap_tur kt ON k.kitap_id = kt.kitap_id
                                    LEFT JOIN tur t ON kt.tur_id = t.tur_id
                           ORDER BY k.ad
                           """)

            books = cursor.fetchall()
            self.status_label.configure(text="")

            self.all_books = []
            book_dict = {}

            for book in books:
                kitap_id = book[0]
                if kitap_id not in book_dict:
                    book_dict[kitap_id] = {
                        'kitap_id': kitap_id,
                        'ad': book[1],
                        'yayin_yili': book[2],
                        'adet': book[3],
                        'yayinevi': book[4],
                        'kapak_resmi_url': book[5],
                        'sayfa_sayisi': book[6],
                        'isbn': book[7],
                        'ozet': book[8],
                        'yazar_ad': book[9] or 'Bilinmiyor',
                        'tur_ad': book[10] or 'Bilinmiyor'
                    }
                else:
                    if book[9] and book[9] not in book_dict[kitap_id]['yazar_ad']:
                        book_dict[kitap_id]['yazar_ad'] += f", {book[9]}"
                    if book[10] and book[10] not in book_dict[kitap_id]['tur_ad']:
                        book_dict[kitap_id]['tur_ad'] += f", {book[10]}"

            self.all_books = list(book_dict.values())

            search_term = self.search_entry.get().strip().lower()
            if search_term:
                self.filter_books()
            else:
                self.display_books(self.all_books)

        except Exception as e:
            self.status_label.configure(text=f"❌ Kitaplar yüklenirken hata: {e}")
            messagebox.showerror("Hata", f"Kitaplar yüklenirken hata: {e}")
        finally:
            conn.close()

    def display_books(self, books_to_display):
        self.book_tree.delete(*self.book_tree.get_children())
        if not books_to_display:
            self.status_label.configure(text="🔍 Arama kriterlerine uygun kitap bulunamadı.")
            return

        self.status_label.configure(text="")

        for book_info in books_to_display:
            self.book_tree.insert("", "end",
                                  values=(book_info['kitap_id'],
                                          book_info['ad'],
                                          book_info['yazar_ad'],
                                          book_info['tur_ad'],
                                          book_info['yayin_yili'],
                                          book_info['adet']))

    def filter_books(self):
        search_term = self.search_entry.get().strip().lower()
        if not search_term:
            self.display_books(self.all_books)
            return

        filtered_books = []
        for book in self.all_books:
            if (search_term in str(book['ad']).lower() or
                    search_term in str(book['yazar_ad']).lower() or
                    search_term in str(book['tur_ad']).lower() or
                    search_term in str(book['isbn']).lower() or
                    search_term in str(book['yayinevi']).lower()):
                filtered_books.append(book)

        self.display_books(filtered_books)
        if not filtered_books:
            self.status_label.configure(text=" Arama kriterlerine uygun kitap bulunamadı.")

    def edit_book(self):
        selected_item = self.book_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen düzenlemek için bir kitap seçin.")
            return

        book_id = self.book_tree.item(selected_item, 'values')[0]
        BookEditorPopup(self.master, book_id=book_id, refresh_callback=self.fetch_and_display_books)

    def delete_book_wrapper(self):
        selected_item = self.book_tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen silmek için bir kitap seçin.")
            return

        values = self.book_tree.item(selected_item, 'values')
        book_id, book_title = values[0], values[1]
        self.delete_book(book_id, book_title)

    def delete_book(self, book_id, book_title):
        if not messagebox.askyesno("Onay", f"'{book_title}' adlı kitabı silmek istediğinize emin misiniz?"):
            return

        conn = get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()

            # ÖNCE: Tüm ilişkili tablolardaki kayıtları sil
            # Kitap rezervasyonlarını sil
            try:
                cursor.execute("DELETE FROM kitap_rezervasyon WHERE kitap_id=?", (book_id,))
            except:
                pass  # Tablo yoksa veya hata olursa devam et

            # Kitap-yazar ilişkilerini sil
            try:
                cursor.execute("DELETE FROM kitap_yazar WHERE kitap_id=?", (book_id,))
            except Exception as e:
                messagebox.showerror("Hata", f"Kitap-yazar ilişkileri silinirken hata: {e}")
                conn.rollback()
                return

            # Kitap-tür ilişkilerini sil
            try:
                cursor.execute("DELETE FROM kitap_tur WHERE kitap_id=?", (book_id,))
            except Exception as e:
                messagebox.showerror("Hata", f"Kitap-tür ilişkileri silinirken hata: {e}")
                conn.rollback()
                return

            # SONRA: Kitabı sil
            cursor.execute("DELETE FROM kitap WHERE kitap_id=?", (book_id,))

            conn.commit()
            messagebox.showinfo("Başarılı", f"'{book_title}' kitabı silindi.")
            self.fetch_and_display_books()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Kitap silinirken hata: {e}")
        finally:
            conn.close()


# MainApp sınıfını CTkFrame olarak değiştirin
class MainApp(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ttk.Treeview stilini burada (root var iken) yap
        style = ttk.Style()
        style.theme_use("clam")

        default_font = ctk.CTkFont(size=16)
        header_font = ctk.CTkFont(size=16, weight="bold")

        style.configure("Treeview",
                        background="#1c2b59",
                        foreground="white",
                        fieldbackground="#1c2b59",
                        bordercolor="#3b3b3b",
                        borderwidth=1,
                        rowheight=30,
                        font=default_font)
        style.map("Treeview", background=[('selected', '#2563eb')])

        style.configure("Treeview.Heading",
                        font=header_font,
                        background="#21336c",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading", background=[('active', '#4b4b4b')])

        # --- ÇERÇEVELERİ OLUŞTUR + YERLEŞTİR ---
        self.book_frame = BookListManagerFrame(self, self.switch_frame)
        self.reservation_frame = ReservationManagerFrame(self, self.switch_frame)

        self.book_frame.grid(row=0, column=0, sticky="nsew")
        self.reservation_frame.grid(row=0, column=0, sticky="nsew")

        # Başlangıçta kitap listesi görünür olsun
        self.switch_frame("book")

    def switch_frame(self, frame_name):
        if frame_name == "book":
            self.book_frame.tkraise()
            # İstersen ilk açılışta hemen listeyi çek
            self.book_frame.fetch_and_display_books()
        elif frame_name == "reservation":
            self.reservation_frame.tkraise()
            self.reservation_frame.fetch_all_reservations()
    def on_closing(self):
        self.is_alive = False
        self.destroy()
