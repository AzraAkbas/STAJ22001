import customtkinter as ctk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import pyodbc
from datetime import datetime, timedelta
import requests
from io import BytesIO
import threading

from database import get_db_connection

# Renkler ve yazı boyutları
DARK_BLUE = "#0a0a1a"
MEDIUM_BLUE = "#12122e"
LIGHT_BLUE = "#1a1a3c"
ACCENT = "#e94560"
TEXT_COLOR = "#ffffff"

TITLE_FONT_SIZE = 28
HEADING_FONT_SIZE = 18
NORMAL_FONT_SIZE = 16
LARGE_FONT_SIZE = 20


def get_image_from_url(url, callback=None):
    """URL'den resmi arka planda yükler ve callback ile döndürür."""

    def download_image():
        try:
            if not url:
                if callback:
                    callback(None)
                return None

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            img_data = response.content
            img = Image.open(BytesIO(img_data)).resize((120, 180), Image.LANCZOS)
            photo_image = ImageTk.PhotoImage(img)

            if callback:
                callback(photo_image)
            return photo_image

        except Exception as e:
            print(f"Resim yükleme hatası: {e}")
            if callback:
                callback(None)
            return None

    # Arka planda indirmeyi başlat
    thread = threading.Thread(target=download_image)
    thread.daemon = True
    thread.start()

    # Hemen None döndür, callback ile resim gelecek
    return None


class BookReservationApp(ctk.CTkToplevel):
    def __init__(self, master, show_main_menu_callback, user_name):
        super().__init__(master)
        self.master = master
        self.show_main_menu_callback = show_main_menu_callback
        self.user_name = user_name
        self.user_id = self.get_user_id()
        self.books = []
        # Tüm Kitaplar sayfası filtreleri
        self.current_author_filter = ""
        self.current_genre_filter = ""
        self.current_year_filter = ""
        self.current_publisher_filter = ""
        self.current_availability_filter = "Tümü"
        # Geçmiş Rezervasyonlar sayfası filtreleri
        self.current_past_search_term = ""
        self.current_past_author_filter = ""
        self.current_past_genre_filter = ""
        self.current_past_year_filter = ""
        self.current_past_publisher_filter = ""

        # Arayüzü yapılandır
        self.title("Kitap Rezervasyon Uygulaması")
        self.geometry("1100x750")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.resizable(True, True)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Navigasyon Çubuğu (Navbar)
        self.navbar_frame = ctk.CTkFrame(self, fg_color=MEDIUM_BLUE, width=200)
        self.navbar_frame.grid(row=0, column=0, sticky="nswe")
        self.navbar_frame.grid_rowconfigure(4, weight=1)

        # İçerik Çerçevesi (Sağ taraf)
        self.content_frame = ctk.CTkFrame(self, fg_color=DARK_BLUE)
        self.content_frame.grid(row=0, column=1, sticky="nswe", padx=10, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self._create_navbar()
        self.show_page("Kitaplar")  # Uygulama açılışında varsayılan sayfayı göster

        # Uygulama açıldığı anda ceza kontrolü yap
        self.check_penalties()

    def on_closing(self):
        self.show_main_menu_callback()
        self.destroy()

    def get_user_id(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT kullanici_id FROM kullanici WHERE isim = ?", self.user_name)
                result = cursor.fetchone()
                return result[0] if result else None
        except pyodbc.Error as ex:
            messagebox.showerror("Hata", f"Kullanıcı bilgileri alınırken veritabanı hatası: {ex}")
            return None
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")
            return None

    def check_penalties(self):
        """14 gün içinde iade edilmeyen kitaplar için ceza puanı uygular,
        cezalara tablosuna kaydeder ve kullanıcıyı uyarır."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # 14 günü geçen ve henüz teslim edilmemiş rezervasyonları bul
                bugun = datetime.now().date()
                cursor.execute("""
                               SELECT kr.kitap_rezervasyon_id, kr.kullanici_id, k.isim, kit.ad, kr.son_iade_tarihi
                               FROM kitap_rezervasyon kr
                                        JOIN kullanici k ON kr.kullanici_id = k.kullanici_id
                                        JOIN kitap kit ON kr.kitap_id = kit.kitap_id
                               WHERE kr.teslim_edildi_mi = 0
                                 AND kr.son_iade_tarihi < ?
                                 AND kr.durum = 'aktif'
                               """, bugun)

                geciken_rezervasyonlar = cursor.fetchall()

                for rezervasyon_id, kullanici_id, kullanici_adi, kitap_adi, son_iade_tarihi in geciken_rezervasyonlar:
                    # Durumu gecikti olarak güncelle
                    cursor.execute("""
                                   UPDATE kitap_rezervasyon
                                   SET durum      = 'gecikti',
                                       gecikti_mi = 1
                                   WHERE kitap_rezervasyon_id = ?
                                   """, rezervasyon_id)

                    # Ceza puanı uygula
                    cursor.execute("""
                                   UPDATE kullanici
                                   SET ceza_puani = ISNULL(ceza_puani, 0) + 5
                                   WHERE kullanici_id = ?
                                   """, kullanici_id)

                    # Ceza detaylarını cezalara tablosuna ekle
                    cursor.execute("""
                                   INSERT INTO cezalar (kullanici_id, aciklama, tarih,
                                                        masa_rezervasyon_id, kitap_rezervasyon_id)
                                   VALUES (?, ?, GETDATE(), NULL, NULL, ?)
                                   """, kullanici_id, f"Kitap zamanında iade edilmedi: {kitap_adi}", rezervasyon_id)

                    print(
                        f"Kullanıcı {kullanici_adi} için 5 ceza puanı uygulandı. Rezervasyon ID: {rezervasyon_id}")

                    # Eğer ceza alan kullanıcı şu anki kullanıcıysa uyarı göster
                    if kullanici_id == self.user_id:
                        messagebox.showwarning(
                            "Ceza Uyarısı",
                            f"'{kitap_adi}' kitabını zamanında iade etmediğiniz için 5 ceza puanı aldınız!\n\n"
                            f"Lütfen en kısa sürede kitabı iade ediniz."
                        )

                conn.commit()

        except pyodbc.Error as ex:
            print(f"Ceza kontrolü sırasında hata: {ex}")
        except Exception as e:
            print(f"Beklenmedik hata: {e}")
    def _create_navbar(self):
        """Navigasyon çubuğunu oluşturur."""
        ctk.CTkLabel(self.navbar_frame, text="Navigasyon", font=ctk.CTkFont(size=HEADING_FONT_SIZE, weight="bold"),
                     text_color=TEXT_COLOR).pack(pady=(20, 10))

        # Butonları oluştur
        self.all_books_button = ctk.CTkButton(self.navbar_frame, text="Tüm Kitaplar",
                                              font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                              command=lambda: self.show_page("Kitaplar"))
        self.all_books_button.pack(fill="x", padx=10, pady=5)

        self.active_reservations_button = ctk.CTkButton(self.navbar_frame, text="Aktif Rezervasyonlarım",
                                                        font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                                        command=lambda: self.show_page("Aktif Rezervasyonlarım"))
        self.active_reservations_button.pack(fill="x", padx=10, pady=5)

        self.past_reservations_button = ctk.CTkButton(self.navbar_frame, text="Geçmiş Rezervasyonlarım",
                                                      font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                                      command=lambda: self.show_page("Geçmiş Rezervasyonlarım"))
        self.past_reservations_button.pack(fill="x", padx=10, pady=5)

    def show_page(self, page_name):
        """Belirtilen sayfayı gösterir."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if page_name == "Kitaplar":
            self._create_all_books_widgets()
        elif page_name == "Aktif Rezervasyonlarım":
            self._create_active_reservations_widgets()
        elif page_name == "Geçmiş Rezervasyonlarım":
            self._create_past_reservations_widgets()

    def _create_all_books_widgets(self):
        # Arama ve filtreleme çerçevesini oluştur
        search_filter_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        search_filter_frame.pack(fill="x", padx=10, pady=(10, 0))
        search_filter_frame.grid_columnconfigure(0, weight=1)

        # Arama kutusu
        self.search_entry = ctk.CTkEntry(search_filter_frame, placeholder_text="Kitap, yazar veya türe göre ara...",
                                         font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.search_books)

        # Arama ve filtreleme butonları
        self.search_button = ctk.CTkButton(search_filter_frame, text="Ara",
                                           font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                                           command=self.search_books)
        self.search_button.grid(row=0, column=1)

        self.filter_button = ctk.CTkButton(search_filter_frame, text="Filtreler",
                                           font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                                           command=lambda: self._open_filter_popup("Kitaplar"))
        self.filter_button.grid(row=0, column=2, padx=(10, 0))

        # Treeview stilini ayarla
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=MEDIUM_BLUE,
                        foreground=TEXT_COLOR,
                        fieldbackground=MEDIUM_BLUE,
                        bordercolor=MEDIUM_BLUE,
                        borderwidth=0,
                        rowheight=30,
                        font=("", NORMAL_FONT_SIZE))
        style.map('Treeview',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', TEXT_COLOR)])
        style.configure("Treeview.Heading",
                        background=LIGHT_BLUE,
                        foreground=TEXT_COLOR,
                        font=("", NORMAL_FONT_SIZE, "bold"))

        # Treeview'ı oluştur
        self.book_tree = ttk.Treeview(self.content_frame,
                                      columns=("Ad", "Yazar", "Tür", "Sayfa Sayısı", "Mevcut Adet"),
                                      show="headings")
        self.book_tree.heading("Ad", text="Kitap Adı", anchor="w")
        self.book_tree.heading("Yazar", text="Yazar", anchor="w")
        self.book_tree.heading("Tür", text="Tür", anchor="w")
        self.book_tree.heading("Sayfa Sayısı", text="Sayfa Sayısı", anchor="center")
        self.book_tree.heading("Mevcut Adet", text="Mevcut Adet", anchor="center")

        self.book_tree.column("Ad", width=300, anchor="w")
        self.book_tree.column("Yazar", width=200, anchor="w")
        self.book_tree.column("Tür", width=150, anchor="w")
        self.book_tree.column("Sayfa Sayısı", width=100, anchor="center")
        self.book_tree.column("Mevcut Adet", width=100, anchor="center")

        self.book_tree.pack(fill="both", expand=True, padx=10, pady=10)

        # Treeview'a çift tıklama olayını bağla
        self.book_tree.bind("<Double-1>", self.on_double_click)
        self.load_books()

    def _open_filter_popup(self, page_name):
        popup = FilterPopup(self, page_name)
        popup.grab_set()
        popup.wait_window()

    def _create_active_reservations_widgets(self):
        self.active_reservations_frame = ctk.CTkScrollableFrame(self.content_frame, fg_color=DARK_BLUE)
        self.active_reservations_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.load_active_reservations()

    def _create_past_reservations_widgets(self):
        search_filter_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        search_filter_frame.pack(fill="x", padx=10, pady=(10, 0))
        search_filter_frame.grid_columnconfigure(0, weight=1)

        self.past_search_entry = ctk.CTkEntry(search_filter_frame,
                                              placeholder_text="Kitap, yazar veya türe göre ara...",
                                              font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        self.past_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.past_search_entry.bind("<KeyRelease>", self.search_past_reservations)

        self.past_search_button = ctk.CTkButton(search_filter_frame, text="Ara",
                                                font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                                                command=self.search_past_reservations)
        self.past_search_button.grid(row=0, column=1)

        self.past_filter_button = ctk.CTkButton(search_filter_frame, text="Filtreler",
                                                font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                                                command=lambda: self._open_filter_popup("Geçmiş Rezervasyonlarım"))
        self.past_filter_button.grid(row=0, column=2, padx=(10, 0))

        # Treeview stilini ayarla
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=MEDIUM_BLUE,
                        foreground=TEXT_COLOR,
                        fieldbackground=MEDIUM_BLUE,
                        bordercolor=MEDIUM_BLUE,
                        borderwidth=0,
                        rowheight=30,
                        font=("", NORMAL_FONT_SIZE))
        style.map('Treeview',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', TEXT_COLOR)])
        style.configure("Treeview.Heading",
                        background=LIGHT_BLUE,
                        foreground=TEXT_COLOR,
                        font=("", NORMAL_FONT_SIZE, "bold"))

        # Treeview'ı oluştur
        self.past_reservations_tree = ttk.Treeview(self.content_frame,
                                                   columns=("Ad", "Yazar", "Alış Tarihi", "İade Tarihi"),
                                                   show="headings")
        self.past_reservations_tree.heading("Ad", text="Kitap Adı", anchor="w")
        self.past_reservations_tree.heading("Yazar", text="Yazar", anchor="w")
        self.past_reservations_tree.heading("Alış Tarihi", text="Alış Tarihi", anchor="center")
        self.past_reservations_tree.heading("İade Tarihi", text="İade Tarihi", anchor="center")

        self.past_reservations_tree.column("Ad", width=300, anchor="w")
        self.past_reservations_tree.column("Yazar", width=200, anchor="w")
        self.past_reservations_tree.column("Alış Tarihi", width=150, anchor="center")
        self.past_reservations_tree.column("İade Tarihi", width=150, anchor="center")

        self.past_reservations_tree.pack(fill="both", expand=True, padx=10, pady=10)

        self.load_past_reservations()

    def on_double_click(self, event):
        item_id = self.book_tree.selection()
        if not item_id:
            return

        selected_item = self.book_tree.item(item_id)
        book_id = selected_item["tags"][0]

        book_details = self.get_book_details(book_id)
        if book_details:
            self.display_book_info(book_details)
        else:
            messagebox.showerror("Hata", "Kitap detayları alınamadı.")

    def load_books(self, search_term=None, author=None, genre=None, year=None, publisher=None, availability=None):
        """Tüm kitapları veritabanından alır ve arayüzde listeler."""
        try:
            self.book_tree.delete(*self.book_tree.get_children())

            if search_term is None: search_term = self.search_entry.get().strip()
            if author is None: author = self.current_author_filter
            if genre is None: genre = self.current_genre_filter
            if year is None: year = self.current_year_filter
            if publisher is None: publisher = self.current_publisher_filter
            if availability is None: availability = self.current_availability_filter

            with get_db_connection() as conn:
                cursor = conn.cursor()

                sorgu = """
                        SELECT k.kitap_id,
                               k.ad,
                               k.yayin_yili,
                               k.yayinevi,
                               k.kapak_resmi_url,
                               k.sayfa_sayisi,
                               k.isbn,
                               k.ozet,
                               STRING_AGG(T.ad, ', ')                                             AS Turler,
                               STRING_AGG(Y.ad, ', ')                                             AS Yazarlar,
                               k.adet,
                               ISNULL(SUM(CASE WHEN r.teslim_edildi_mi = 0 THEN 1 ELSE 0 END), 0) AS rezerve_edilen,
                               CASE
                                   WHEN EXISTS (SELECT 1 \
                                                FROM kitap_rezervasyon \
                                                WHERE kitap_id = k.kitap_id \
                                                  AND kullanici_id = ? \
                                                  AND teslim_edildi_mi = 0) THEN 1
                                   ELSE 0 END                                                     AS is_reserved
                        FROM Kitap k
                                 LEFT JOIN kitap_tur kt ON k.kitap_id = kt.kitap_id
                                 LEFT JOIN tur T ON kt.tur_id = T.tur_id
                                 LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                 LEFT JOIN yazar Y ON ky.yazar_id = Y.yazar_id
                                 LEFT JOIN kitap_rezervasyon r ON k.kitap_id = r.kitap_id
                        WHERE (T.ad LIKE ? OR Y.ad LIKE ? OR k.ad LIKE ?)
                          AND (? = '' OR Y.ad LIKE ?)
                          AND (? = '' OR T.ad LIKE ?)
                          AND (? = '' OR k.yayin_yili = ?)
                          AND (? = '' OR k.yayinevi LIKE ?)
                        GROUP BY k.kitap_id, k.ad, k.yayin_yili, k.yayinevi, k.kapak_resmi_url, k.sayfa_sayisi, k.isbn, k.ozet, k.adet
                        HAVING (? = 'Tümü' OR
                                (? = 'Evet' AND \
                                 k.adet > ISNULL(SUM(CASE WHEN r.teslim_edildi_mi = 0 THEN 1 ELSE 0 END), 0)) OR
                                (? = 'Hayır' AND \
                                 k.adet <= ISNULL(SUM(CASE WHEN r.teslim_edildi_mi = 0 THEN 1 ELSE 0 END), 0)))
                        ORDER BY k.ad;
                        """

                # Parametreleri düzenle
                search_term_like = f"%{search_term}%"
                author_like = f"%{author}%" if author else '%'
                genre_like = f"%{genre}%" if genre else '%'
                publisher_like = f"%{publisher}%" if publisher else '%'

                # Yıl filtresi için özel durum
                year_param = int(year) if year and year.isdigit() else None

                params = (
                    self.user_id,
                    search_term_like, search_term_like, search_term_like,
                    author, author_like,
                    genre, genre_like,
                    year, year_param,
                    publisher, publisher_like,
                    availability, availability, availability
                )

                cursor.execute(sorgu, params)
                self.books = cursor.fetchall()

            if not self.books:
                self.book_tree.insert("", "end", values=("Filtrelere uygun kitap bulunamadı.", "", "", "", ""),
                                      tags=("no_books",))
                return

            for book_row in self.books:
                (kitap_id, ad, yayin_yili, yayinevi, kapak_resmi_url, sayfa_sayisi, isbn, ozet, turler, yazarlar,
                 adet, rezerve_edilen, is_reserved) = book_row

                mevcut_adet = adet

                self.book_tree.insert("", "end",
                                      values=(ad, yazarlar, turler, sayfa_sayisi, mevcut_adet),
                                      tags=(kitap_id, 'normal'))

        except pyodbc.Error as ex:
            messagebox.showerror("Veritabanı Hatası", f"Veritabanı hatası: {ex.args[1]}")
            self.book_tree.insert("", "end", values=("Bir hata oluştu. Lütfen tekrar deneyin.", "", "", "", ""),
                                  tags=("error",))
            print(f"Hata detayı: {ex}")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")

    def load_active_reservations(self):
        """Kullanıcının aktif rezervasyonlarını veritabanından alır ve listeler."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sorgu = """
                        SELECT k.ad, \
                               STRING_AGG(y.ad, ', ') AS Yazarlar,
                               r.alis_tarihi, \
                               r.son_iade_tarihi, \
                               r.durum, \
                               r.kitap_rezervasyon_id
                        FROM kitap_rezervasyon r
                                 JOIN kitap k ON r.kitap_id = k.kitap_id
                                 LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                 LEFT JOIN yazar y ON ky.yazar_id = y.yazar_id
                        WHERE r.kullanici_id = ?
                          AND r.durum IN ('aktif', 'gecikti')
                        GROUP BY k.ad, r.alis_tarihi, r.son_iade_tarihi, r.durum, r.kitap_rezervasyon_id
                        ORDER BY r.alis_tarihi DESC;
                        """
                cursor.execute(sorgu, self.user_id)
                reservations = cursor.fetchall()

            for widget in self.active_reservations_frame.winfo_children():
                widget.destroy()

            if not reservations:
                ctk.CTkLabel(
                    self.active_reservations_frame,
                    text="Aktif rezervasyonunuz bulunmamaktadır.",
                    font=ctk.CTkFont(size=HEADING_FONT_SIZE),
                    text_color=TEXT_COLOR,
                ).pack(pady=20)
                return

            for res in reservations:
                book_name, authors, reserve_date, return_date, durum, reservation_id = res

                # Tarih değerlerini kontrol et
                reserve_date_str = reserve_date.strftime('%d.%m.%Y') if reserve_date else "Bilinmiyor"
                return_date_str = return_date.strftime('%d.%m.%Y') if return_date else "Bilinmiyor"

                res_frame = ctk.CTkFrame(self.active_reservations_frame, fg_color=LIGHT_BLUE)
                res_frame.pack(fill="x", padx=5, pady=5, ipadx=5, ipady=5)

                # Duruma göre renk belirle
                status_color = ACCENT if durum == 'gecikti' else TEXT_COLOR

                ctk.CTkLabel(
                    res_frame,
                    text=f"Kitap: {book_name}",
                    font=ctk.CTkFont(size=HEADING_FONT_SIZE, weight="bold"),
                    anchor="w",
                ).pack(fill="x", padx=10, pady=2)

                ctk.CTkLabel(
                    res_frame,
                    text=f"Durum: {durum.upper()}",
                    font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                    anchor="w",
                    text_color=status_color,
                ).pack(fill="x", padx=10, pady=2)

                ctk.CTkLabel(
                    res_frame,
                    text=f"Yazar: {authors if authors else 'Bilinmiyor'}",
                    font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                    anchor="w",
                ).pack(fill="x", padx=10, pady=2)

                # ... diğer labellar aynı şekilde devam eder ...


                ctk.CTkLabel(
                    res_frame,
                    text=f"Rezervasyon Tarihi: {reserve_date_str}",
                    font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                    anchor="w",
                ).pack(fill="x", padx=10, pady=2)

                # Son teslim tarihi hesaplama ve renk kontrolü
                if return_date:
                    # Bugünün tarihini date tipinde al
                    today = datetime.now().date()

                    # Kalan günleri hesapla
                    days_remaining = (return_date - today).days

                    text_color = "orange" if days_remaining <= 3 else TEXT_COLOR
                    ctk.CTkLabel(
                        res_frame,
                        text=f"Son Teslim Tarihi: {return_date_str}",
                        font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                        anchor="w",
                        text_color=text_color,
                    ).pack(fill="x", padx=10, pady=2)
                else:
                    ctk.CTkLabel(
                        res_frame,
                        text="Son Teslim Tarihi: Bilinmiyor",
                        font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                        anchor="w",
                    ).pack(fill="x", padx=10, pady=2)

        except pyodbc.Error as ex:
            messagebox.showerror("Hata", f"Veritabanı hatası: {ex}")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")

    def load_past_reservations(self, search_term=None, author=None, genre=None, year=None, publisher=None):
        """Kullanıcının geçmiş rezervasyonlarını veritabanından alır ve listeler."""
        try:
            self.past_reservations_tree.delete(*self.past_reservations_tree.get_children())

            if search_term is None: search_term = self.past_search_entry.get().strip()
            if author is None: author = self.current_past_author_filter
            if genre is None: genre = self.current_past_genre_filter
            if year is None: year = self.current_past_year_filter
            if publisher is None: publisher = self.current_past_publisher_filter

            with get_db_connection() as conn:
                cursor = conn.cursor()
                sorgu = """
                        SELECT r.kitap_rezervasyon_id,
                               k.ad,
                               STRING_AGG(y.ad, ', ') AS Yazarlar,
                               STRING_AGG(t.ad, ', ') AS Turler,
                               k.yayin_yili,
                               k.yayinevi,
                               r.alis_tarihi,
                               r.iade_tarihi
                        FROM kitap_rezervasyon r
                                 JOIN kitap k ON r.kitap_id = k.kitap_id
                                 LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                 LEFT JOIN yazar y ON ky.yazar_id = y.yazar_id
                                 LEFT JOIN kitap_tur kt ON k.kitap_id = kt.kitap_id
                                 LEFT JOIN tur t ON kt.tur_id = t.tur_id
                        WHERE r.kullanici_id = ?
                          AND r.teslim_edildi_mi = 1
                          AND (k.ad LIKE ? OR y.ad LIKE ? OR t.ad LIKE ?)
                          AND (? = '' OR y.ad LIKE ?)
                          AND (? = '' OR t.ad LIKE ?)
                          AND (? = '' OR k.yayin_yili = ?)
                          AND (? = '' OR k.yayinevi LIKE ?)
                        GROUP BY k.ad, r.alis_tarihi, r.iade_tarihi, r.kitap_rezervasyon_id, k.yayin_yili, k.yayinevi
                        ORDER BY r.iade_tarihi DESC;
                        """

                search_term_like = f"%{search_term}%"
                author_like = f"%{author}%" if author else '%'
                genre_like = f"%{genre}%" if genre else '%'
                publisher_like = f"%{publisher}%" if publisher else '%'

                # Yıl filtresi için özel durum
                year_param = int(year) if year and year.isdigit() else None

                params = (
                    self.user_id,
                    search_term_like, search_term_like, search_term_like,
                    author, author_like,
                    genre, genre_like,
                    year, year_param,
                    publisher, publisher_like
                )

                cursor.execute(sorgu, params)
                reservations = cursor.fetchall()

            if not reservations:
                self.past_reservations_tree.insert("", "end",
                                                   values=("Filtrelere uygun geçmiş rezervasyon bulunamadı.", "", "",
                                                           ""),
                                                   tags=("no_books",))
                return

            for res in reservations:
                rezervasyon_id, book_name, authors, genres, year_val, publisher_val, reserve_date, return_date = res

                # Tarih değerlerini kontrol et
                reserve_date_str = reserve_date.strftime('%d.%m.%Y') if reserve_date else "Bilinmiyor"
                return_date_str = return_date.strftime('%d.%m.%Y') if return_date else "Bilinmiyor"

                self.past_reservations_tree.insert("", "end",
                                                   values=(book_name, authors, reserve_date_str,
                                                           return_date_str),
                                                   tags=(rezervasyon_id,))

        except pyodbc.Error as ex:
            messagebox.showerror("Hata", f"Veritabanı hatası: {ex}")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")

    def search_books(self, event=None):
        search_term = self.search_entry.get().strip()
        self.load_books(search_term=search_term,
                        author=self.current_author_filter,
                        genre=self.current_genre_filter,
                        year=self.current_year_filter,
                        publisher=self.current_publisher_filter,
                        availability=self.current_availability_filter)

    def search_past_reservations(self, event=None):
        search_term = self.past_search_entry.get().strip()
        self.load_past_reservations(search_term=search_term,
                                    author=self.current_past_author_filter,
                                    genre=self.current_past_genre_filter,
                                    year=self.current_past_year_filter,
                                    publisher=self.current_past_publisher_filter)

    def reserve_book(self, book_id):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Kullanıcının aktif rezervasyon sayısını kontrol et
                cursor.execute("""
                               SELECT COUNT(*)
                               FROM kitap_rezervasyon
                               WHERE kullanici_id = ?
                                 AND durum = 'aktif'
                               """, self.user_id)
                active_reservations_count = cursor.fetchone()[0]

                if active_reservations_count >= 5:
                    messagebox.showerror("Hata",
                                         "Aktif rezervasyon sayınız 5 ile sınırlıdır. Başka bir kitap rezerve etmek için mevcut rezervasyonlarınızı iade etmelisiniz.")
                    return

                # Kitabın mevcut olup olmadığını kontrol et (adet alanına göre)
                cursor.execute("""
                               SELECT adet
                               FROM kitap
                               WHERE kitap_id = ?
                               """, book_id)
                result = cursor.fetchone()
                if not result:
                    messagebox.showerror("Hata", "Kitap bulunamadı.")
                    return

                adet = result[0]
                if adet <= 0:
                    messagebox.showerror("Hata", "Kitap stokta bulunmamaktadır.")
                    return

                # Kullanıcının zaten rezerve edip etmediğini kontrol et
                cursor.execute("""
                               SELECT 1
                               FROM kitap_rezervasyon
                               WHERE kitap_id = ?
                                 AND kullanici_id = ?
                                 AND durum = 'aktif'
                               """, book_id, self.user_id)
                if cursor.fetchone():
                    messagebox.showinfo("Bilgi", "Bu kitabı zaten rezerve etmişsiniz.")
                    return

                # Rezervasyonu ekle (son_iade_tarihi 14 gün sonra olacak şekilde)
                son_iade_tarihi = (datetime.now() + timedelta(days=14)).date()
                cursor.execute("""
                               INSERT INTO kitap_rezervasyon (kullanici_id, kitap_id, alis_tarihi, teslim_edildi_mi,
                                                              gecikti_mi, son_iade_tarihi, durum)
                               VALUES (?, ?, GETDATE(), 0, 0, ?, 'aktif');
                               """, self.user_id, book_id, son_iade_tarihi)

                # Adet alanını 1 azalt
                cursor.execute("""
                               UPDATE kitap
                               SET adet = adet - 1
                               WHERE kitap_id = ?
                               """, book_id)

                conn.commit()
                messagebox.showinfo("Başarılı", "Kitap başarıyla rezerve edildi! 14 gün içinde iade edilmelidir.")

            self.load_books()  # Listeyi güncelle

        except pyodbc.Error as ex:
            messagebox.showerror("Hata", f"Veritabanı hatası: {ex}")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")
    def display_book_info(self, book_details):
        if not book_details:
            messagebox.showerror("Hata", "Kitap bilgileri bulunamadı.")
            return

        info_window = ctk.CTkToplevel(self)
        info_window.title(book_details["ad"])
        info_window.geometry("500x600")
        info_window.configure(fg_color=DARK_BLUE)
        info_window.resizable(False, False)

        main_frame = ctk.CTkScrollableFrame(info_window, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Kitap Adı
        ctk.CTkLabel(main_frame, text=book_details["ad"], font=ctk.CTkFont(size=TITLE_FONT_SIZE, weight="bold"),
                     text_color=ACCENT, wraplength=450, justify="center").pack(pady=(20, 5), anchor="center")

        # Yazar Adı
        ctk.CTkLabel(main_frame, text=f"Yazar: {book_details['yazar']}",
                     font=ctk.CTkFont(size=HEADING_FONT_SIZE, weight="bold"), text_color=TEXT_COLOR, wraplength=450,
                     justify="center").pack(pady=(0, 20), anchor="center")

        # Kitap Kapağı için placeholder
        image_label = ctk.CTkLabel(main_frame, text="Resim yükleniyor...",
                                   font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                   text_color=TEXT_COLOR)
        image_label.pack(pady=15, anchor="center")

        # Detaylar Kutusu
        details_frame = ctk.CTkFrame(main_frame, fg_color=MEDIUM_BLUE)
        details_frame.pack(fill="x", padx=10, pady=(25, 15))

        ctk.CTkLabel(details_frame, text="Detaylar", font=ctk.CTkFont(size=HEADING_FONT_SIZE, weight="bold"),
                     text_color=TEXT_COLOR).pack(pady=(10, 5), padx=10, anchor="w")

        ctk.CTkLabel(details_frame, text=f"Yayın Yılı: {book_details['yayin_yili']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 5),
                                                                                                          padx=20)
        ctk.CTkLabel(details_frame, text=f"Yayınevi: {book_details['yayinevi']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 5),
                                                                                                          padx=20)
        ctk.CTkLabel(details_frame, text=f"Sayfa Sayısı: {book_details['sayfa_sayisi']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 5),
                                                                                                          padx=20)
        ctk.CTkLabel(details_frame, text=f"ISBN: {book_details['isbn']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 5),
                                                                                                          padx=20)
        ctk.CTkLabel(details_frame, text=f"Türler: {book_details['tur']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 5),
                                                                                                          padx=20)
        ctk.CTkLabel(details_frame, text=f"Mevcut Adet: {book_details['mevcut_adet']} / {book_details['adet']}",
                     font=ctk.CTkFont(size=NORMAL_FONT_SIZE), text_color=TEXT_COLOR, justify="left").pack(anchor="w",
                                                                                                          pady=(5, 20),
                                                                                                          padx=20)

        # Özet Kutusu
        summary_frame = ctk.CTkFrame(main_frame, fg_color=MEDIUM_BLUE)
        summary_frame.pack(fill="x", padx=10, pady=15)

        ctk.CTkLabel(summary_frame, text="Özet", font=ctk.CTkFont(size=HEADING_FONT_SIZE, weight="bold"),
                     text_color=TEXT_COLOR).pack(pady=(10, 5), padx=10, anchor="w")

        summary_label = ctk.CTkLabel(summary_frame, text=book_details['ozet'], font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                     text_color=TEXT_COLOR, wraplength=450, justify="left")
        summary_label.pack(fill="x", padx=10, pady=(0, 20))

        # Rezervasyon Butonu
        is_available = book_details['mevcut_adet'] > 0
        if book_details['is_reserved']:
            reserve_button = ctk.CTkButton(main_frame, text="Rezerve Edildi", state="disabled", fg_color=ACCENT)
        elif is_available:
            reserve_button = ctk.CTkButton(main_frame, text="Rezerve Et",
                                           command=lambda: self.reserve_book(book_details['id']))
        else:
            reserve_button = ctk.CTkButton(main_frame, text="Stokta Yok", state="disabled", fg_color=ACCENT)

        reserve_button.pack(pady=20)

        # Resmi arka planda yükle ve callback ile güncelle
        def update_image(image):
            if image:
                image_label.configure(image=image, text="")
                # Resmin garbage collection'dan silinmemesi için referans tut
                image_label.image = image
            else:
                image_label.configure(text="Görsel bulunamadı",
                                      font=ctk.CTkFont(size=NORMAL_FONT_SIZE),
                                      text_color=TEXT_COLOR)

        # Resmi arka planda yükle
        get_image_from_url(book_details['kapak_resmi'], update_image)

    def get_book_details(self, book_id):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sorgu = """
                        SELECT k.kitap_id,
                               k.ad,
                               k.yayin_yili,
                               k.yayinevi,
                               k.kapak_resmi_url,
                               k.sayfa_sayisi,
                               k.isbn,
                               k.ozet,
                               STRING_AGG(T.ad, ', ')                                             AS Turler,
                               STRING_AGG(Y.ad, ', ')                                             AS Yazarlar,
                               k.adet,
                               ISNULL(SUM(CASE WHEN r.teslim_edildi_mi = 0 THEN 1 ELSE 0 END), 0) AS rezerve_edilen,
                               CASE
                                   WHEN EXISTS (SELECT 1
                                                FROM kitap_rezervasyon
                                                WHERE kitap_id = k.kitap_id
                                                  AND kullanici_id = ?
                                                  AND teslim_edildi_mi = 0) THEN 1
                                   ELSE 0 END                                                     as is_reserved
                        FROM Kitap k
                                 LEFT JOIN kitap_tur kt ON k.kitap_id = kt.kitap_id
                                 LEFT JOIN tur T ON kt.tur_id = T.tur_id
                                 LEFT JOIN kitap_yazar ky ON k.kitap_id = ky.kitap_id
                                 LEFT JOIN yazar Y ON ky.yazar_id = Y.yazar_id
                                 LEFT JOIN kitap_rezervasyon r ON k.kitap_id = r.kitap_id
                        WHERE k.kitap_id = ?
                        GROUP BY k.kitap_id, k.ad, k.yayin_yili, k.yayinevi, k.kapak_resmi_url, k.sayfa_sayisi, k.isbn,
                                  k.adet;
                        """
                cursor.execute(sorgu, self.user_id, book_id)
                book_row = cursor.fetchone()

                if not book_row:
                    return None

                (kitap_id, ad, yayin_yili, yayinevi, kapak_resmi_url, sayfa_sayisi, isbn, ozet, turler, yazarlar,
                 adet, rezerve_edilen, is_reserved) = book_row
                rezerve_edilen = rezerve_edilen if rezerve_edilen is not None else 0
                mevcut_adet = adet - rezerve_edilen

                return {
                    "id": kitap_id,
                    "ad": ad,
                    "yazar": yazarlar if yazarlar else "Bilinmiyor",
                    "yayin_yili": yayin_yili,
                    "mevcut_adet": mevcut_adet,
                    "adet": adet,
                    "kapak_resmi": kapak_resmi_url,
                    "is_reserved": bool(is_reserved),
                    "tur": turler if turler else "Bilinmiyor",
                    "yayinevi": yayinevi,
                    "sayfa_sayisi": sayfa_sayisi,
                    "isbn": isbn,
                    "ozet": ozet
                }

        except pyodbc.Error as ex:
            messagebox.showerror("Hata", f"Veritabanı hatası: {ex}")
            return None
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")
            return None


class FilterPopup(ctk.CTkToplevel):
    def __init__(self, master, page_name):
        super().__init__(master)
        self.master = master
        self.page_name = page_name
        self.title("Kitapları Filtrele")
        self.geometry("350x350")
        self.resizable(False, False)
        self.configure(fg_color=DARK_BLUE)
        self.transient(master)

        self._create_widgets()

    def _create_widgets(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        main_frame.grid_columnconfigure(1, weight=1)

        # Yazar Filtresi
        ctk.CTkLabel(main_frame, text="Yazar:", font=ctk.CTkFont(size=NORMAL_FONT_SIZE)).grid(row=0, column=0,
                                                                                              sticky="w", pady=5)
        self.author_filter = ctk.CTkEntry(main_frame, placeholder_text="Yazar adı...",
                                          font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        if self.page_name == "Kitaplar":
            self.author_filter.insert(0, self.master.current_author_filter)
        else:
            self.author_filter.insert(0, self.master.current_past_author_filter)
        self.author_filter.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # Tür Filtresi
        ctk.CTkLabel(main_frame, text="Tür:", font=ctk.CTkFont(size=NORMAL_FONT_SIZE)).grid(row=1, column=0, sticky="w",
                                                                                            pady=5)
        self.genre_filter = ctk.CTkEntry(main_frame, placeholder_text="Tür adı...",
                                         font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        if self.page_name == "Kitaplar":
            self.genre_filter.insert(0, self.master.current_genre_filter)
        else:
            self.genre_filter.insert(0, self.master.current_past_genre_filter)
        self.genre_filter.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        # Yıl Filtresi
        ctk.CTkLabel(main_frame, text="Yayın Yılı:", font=ctk.CTkFont(size=NORMAL_FONT_SIZE)).grid(row=2, column=0,
                                                                                                   sticky="w", pady=5)
        self.year_filter = ctk.CTkEntry(main_frame, placeholder_text="Yıl...", font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        if self.page_name == "Kitaplar":
            self.year_filter.insert(0, self.master.current_year_filter)
        else:
            self.year_filter.insert(0, self.master.current_past_year_filter)
        self.year_filter.grid(row=2, column=1, sticky="ew", padx=(10, 0))

        # Yayınevi Filtresi
        ctk.CTkLabel(main_frame, text="Yayınevi:", font=ctk.CTkFont(size=NORMAL_FONT_SIZE)).grid(row=3, column=0,
                                                                                                 sticky="w", pady=5)
        self.publisher_filter = ctk.CTkEntry(main_frame, placeholder_text="Yayınevi adı...",
                                             font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
        if self.page_name == "Kitaplar":
            self.publisher_filter.insert(0, self.master.current_publisher_filter)
        else:
            self.publisher_filter.insert(0, self.master.current_past_publisher_filter)
        self.publisher_filter.grid(row=3, column=1, sticky="ew", padx=(10, 0))

        # Mevcut Var mı Filtresi (Sadece "Tüm Kitaplar" sayfası için)
        if self.page_name == "Kitaplar":
            availability_options = ["Tümü", "Evet", "Hayır"]
            ctk.CTkLabel(main_frame, text="Mevcut mu?", font=ctk.CTkFont(size=NORMAL_FONT_SIZE)).grid(row=4, column=0,
                                                                                                      sticky="w",
                                                                                                      pady=5)
            self.availability_filter = ctk.CTkOptionMenu(main_frame, values=availability_options,
                                                         font=ctk.CTkFont(size=NORMAL_FONT_SIZE))
            self.availability_filter.set(self.master.current_availability_filter)
            self.availability_filter.grid(row=4, column=1, sticky="ew", padx=(10, 0))

        # Filtreleme butonu
        filter_button = ctk.CTkButton(main_frame, text="Filtrele",
                                      font=ctk.CTkFont(size=NORMAL_FONT_SIZE, weight="bold"),
                                      command=self._apply_filters)
        filter_button.grid(row=5, column=0, columnspan=2, pady=20)

    def _apply_filters(self):
        author = self.author_filter.get().strip()
        genre = self.genre_filter.get().strip()
        year = self.year_filter.get().strip()
        publisher = self.publisher_filter.get().strip()

        if self.page_name == "Kitaplar":
            availability = self.availability_filter.get()
            self.master.current_author_filter = author
            self.master.current_genre_filter = genre
            self.master.current_year_filter = year
            self.master.current_publisher_filter = publisher
            self.master.current_availability_filter = availability
            self.master.load_books(author=author, genre=genre, year=year, publisher=publisher,
                                   availability=availability)
        else:
            self.master.current_past_author_filter = author
            self.master.current_past_genre_filter = genre
            self.master.current_past_year_filter = year
            self.master.current_past_publisher_filter = publisher
            self.master.load_past_reservations(author=author, genre=genre, year=year, publisher=publisher)

        self.destroy()