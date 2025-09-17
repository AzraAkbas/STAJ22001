import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import os
from datetime import datetime, date, timedelta
import pyodbc
from database import get_db_connection
class DateSelectionPopup(ctk.CTkToplevel):
    """Kullanıcının rezervasyon için bir tarih seçmesi için açılan pencere."""

    def __init__(self, parent, on_confirm):
        super().__init__(parent)
        self.title("Tarih Seçimi")
        self.geometry("300x200")
        self.on_confirm = on_confirm
        self.parent = parent

        self.grab_set()
        self.transient(parent)

        ctk.CTkLabel(self, text="Rezervasyon Tarihini Seçin").pack(pady=10)

        # Bugün ve sonraki 6 gün için tarih seçenekleri oluştur
        today = date.today()
        dates = [today + timedelta(days=i) for i in range(7)]
        date_options = [d.strftime("%d/%m/%Y") for d in dates]

        self.date_combobox = ctk.CTkComboBox(self, values=date_options)
        self.date_combobox.set(date_options[0])
        self.date_combobox.pack(pady=5)

        ctk.CTkButton(self, text="İleri", command=self.confirm).pack(pady=5)
        ctk.CTkButton(self, text="İptal", command=self.close_popup).pack(pady=5)

        self.protocol("WM_DELETE_WINDOW", self.close_popup)

    def close_popup(self):
        """Pop-up penceresini kapatır ve ana pencereye odaklanmayı geri verir."""
        self.grab_release()
        self.parent.focus_set()
        self.destroy()

    def confirm(self):
        """Seçilen tarihi ana fonksiyona gönderir."""
        selected_date = self.date_combobox.get()
        self.grab_release()
        self.parent.focus_set()
        self.on_confirm(selected_date)
        self.destroy()

class TimeSelectionPopup(ctk.CTkToplevel):
    """Kullanıcının başlangıç ve bitiş saatlerini seçmesi için açılan pencere."""

    def __init__(self, parent, seat_id, masa_adi, selected_date, on_confirm):
        super().__init__(parent)
        self.title("Saat Seçimi")
        self.geometry("300x200")
        self.seat_id = seat_id
        self.selected_date = selected_date
        self.on_confirm = on_confirm
        self.parent = parent

        self.grab_set()
        self.transient(parent)

        ctk.CTkLabel(self, text=f"'{masa_adi}' için saat seçin\nTarih: {self.selected_date}").pack(pady=10)

        time_options = self.generate_time_options()
        self.start_time = ctk.CTkComboBox(self, values=time_options)
        self.start_time.set("Başlangıç")
        self.start_time.pack(pady=5)

        self.end_time = ctk.CTkComboBox(self, values=time_options)
        self.end_time.set("Bitiş")
        self.end_time.pack(pady=5)

        ctk.CTkButton(self, text="Onayla", command=self.confirm).pack(pady=5)
        ctk.CTkButton(self, text="İptal", command=self.close_popup).pack(pady=5)

        self.protocol("WM_DELETE_WINDOW", self.close_popup)

    def close_popup(self):
        """Pop-up penceresini kapatır ve ana pencereye odaklanmayı geri verir."""
        self.grab_release()
        self.parent.focus_set()
        self.destroy()

    def generate_time_options(self):
        """Saat seçeneklerini 09:00'dan 20:00'a kadar oluşturur."""
        return [f"{h:02d}:00" for h in range(9, 21)]

    def confirm(self):
        """Seçilen saatleri kontrol eder ve ana fonksiyona iletir."""
        start = self.start_time.get()
        end = self.end_time.get()

        if start == "Başlangıç" or end == "Bitiş":
            messagebox.showerror("Hata", "Lütfen başlangıç ve bitiş saatlerini seçin.")
            return

        try:
            start_dt = datetime.strptime(start, "%H:%M").time()
            end_dt = datetime.strptime(end, "%H:%M").time()
            selected_date_dt = datetime.strptime(self.selected_date, "%d/%m/%Y").date()
            current_date = date.today()
            current_time = datetime.now().time()

            # Bitiş saati başlangıç saatinden sonra olmalıdır.
            if end_dt <= start_dt:
                messagebox.showerror("Hata", "Bitiş saati başlangıç saatinden sonra olmalıdır.")
                return

            # Eğer seçilen tarih bugün ise, başlangıç saati mevcut saatten sonra olmalıdır.
            if selected_date_dt == current_date and start_dt <= current_time:
                messagebox.showerror("Hata", "Geçmiş bir saat için rezervasyon yapamazsınız.")
                return

        except ValueError:
            messagebox.showerror("Hata", "Geçersiz saat veya tarih formatı.")
            return

        self.grab_release()
        self.parent.focus_set()
        self.on_confirm(self.seat_id, self.selected_date, start, end)
        self.destroy()

class TableReservationApp(ctk.CTkFrame):
    def __init__(self, master, current_user, on_return_to_main=None):
        super().__init__(master)
        self.pack(fill="both", expand=True)

        self.current_user = current_user
        self.on_return_to_main = on_return_to_main
        self.seat_drawing_ids = {}
        self.after_id = None  # Zamanlayıcı ID'si için

        self.seat_coordinates = {
            "sesli_oda_1_sandalye_1": {"x": 135, "y": 100, "w": 30, "h": 30},
            "sesli_oda_1_sandalye_2": {"x": 85, "y": 60, "w": 30, "h": 30},
            "sesli_oda_1_sandalye_3": {"x": 30, "y": 100, "w": 30, "h": 30},
            "sesli_oda_1_sandalye_4": {"x": 85, "y": 145, "w": 30, "h": 30},
            "sesli_oda_2_sandalye_1": {"x": 135, "y": 270, "w": 30, "h": 30},
            "sesli_oda_2_sandalye_2": {"x": 85, "y": 230, "w": 30, "h": 30},
            "sesli_oda_2_sandalye_3": {"x": 30, "y": 270, "w": 30, "h": 30},
            "sesli_oda_2_sandalye_4": {"x": 85, "y": 315, "w": 30, "h": 30},
            "sesli_oda_3_sandalye_1": {"x": 135, "y": 440, "w": 30, "h": 30},
            "sesli_oda_3_sandalye_2": {"x": 85, "y": 400, "w": 30, "h": 30},
            "sesli_oda_3_sandalye_3": {"x": 30, "y": 440, "w": 30, "h": 30},
            "sesli_oda_3_sandalye_4": {"x": 85, "y": 485, "w": 30, "h": 30},
            "sesli_oda_4_sandalye_1": {"x": 135, "y": 610, "w": 30, "h": 30},
            "sesli_oda_4_sandalye_2": {"x": 85, "y": 570, "w": 30, "h": 22},
            "sesli_oda_4_sandalye_3": {"x": 30, "y": 610, "w": 30, "h": 30},
            "sesli_oda_4_sandalye_4": {"x": 85, "y": 655, "w": 30, "h": 30},
            "masa_1_sandalye_1": {"x": 330, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_2": {"x": 400, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_3": {"x": 470, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_4": {"x": 540, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_5": {"x": 610, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_6": {"x": 680, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_7": {"x": 750, "y": 95, "w": 30, "h": 30},
            "masa_1_sandalye_8": {"x": 750, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_9": {"x": 330, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_10": {"x": 400, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_11": {"x": 470, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_12": {"x": 540, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_13": {"x": 610, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_14": {"x": 680, "y": 175, "w": 30, "h": 30},
            "masa_1_sandalye_15": {"x": 750, "y": 175, "w": 30, "h": 30},
            "masa_2_sandalye_1": {"x": 330, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_2": {"x": 400, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_3": {"x": 470, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_4": {"x": 540, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_5": {"x": 610, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_6": {"x": 680, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_7": {"x": 750, "y": 250, "w": 30, "h": 30},
            "masa_2_sandalye_8": {"x": 750, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_9": {"x": 330, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_10": {"x": 400, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_11": {"x": 470, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_12": {"x": 540, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_13": {"x": 610, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_14": {"x": 680, "y": 330, "w": 30, "h": 30},
            "masa_2_sandalye_15": {"x": 750, "y": 330, "w": 30, "h": 30},
            "masa_3_sandalye_1": {"x": 330, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_2": {"x": 400, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_3": {"x": 470, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_4": {"x": 540, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_5": {"x": 610, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_6": {"x": 680, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_7": {"x": 750, "y": 400, "w": 30, "h": 30},
            "masa_3_sandalye_8": {"x": 750, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_9": {"x": 330, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_10": {"x": 400, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_11": {"x": 470, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_12": {"x": 540, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_13": {"x": 610, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_14": {"x": 680, "y": 480, "w": 30, "h": 30},
            "masa_3_sandalye_15": {"x": 750, "y": 480, "w": 30, "h": 30},
            "masa_4_sandalye_1": {"x": 330, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_2": {"x": 400, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_3": {"x": 470, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_4": {"x": 540, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_5": {"x": 610, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_6": {"x": 680, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_7": {"x": 750, "y": 545, "w": 30, "h": 30},
            "masa_4_sandalye_8": {"x": 750, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_9": {"x": 330, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_10": {"x": 400, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_11": {"x": 470, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_12": {"x": 540, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_13": {"x": 610, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_14": {"x": 680, "y": 625, "w": 30, "h": 30},
            "masa_4_sandalye_15": {"x": 750, "y": 625, "w": 30, "h": 30},
            "bireysel_1": {"x": 975, "y": 90, "w": 30, "h": 30},
            "bireysel_2": {"x": 1075, "y": 90, "w": 30, "h": 30},
            "bireysel_3": {"x": 975, "y": 250, "w": 30, "h": 30},
            "bireysel_4": {"x": 1075, "y": 250, "w": 30, "h": 30},
            "bireysel_5": {"x": 970, "y": 405, "w": 30, "h": 30},
            "bireysel_6": {"x": 1070, "y": 405, "w": 30, "h": 30},
            "bireysel_7": {"x": 970, "y": 560, "w": 30, "h": 30},
            "bireysel_8": {"x": 1070, "y": 560, "w": 30, "h": 30},
            "bilgisayar_1": {"x": 1240, "y": 125, "w": 30, "h": 30},
            "bilgisayar_2": {"x": 1240, "y": 245, "w": 30, "h": 30},
            "bilgisayar_3": {"x": 1240, "y": 365, "w": 30, "h": 30},
            "bilgisayar_4": {"x": 1240, "y": 480, "w": 30, "h": 30},
            "bilgisayar_5": {"x": 1240, "y": 600, "w": 30, "h": 30},
        }

        # Gerekli verileri başlangıçta yükle
        self.kullanici_id = self._get_user_id_from_username(self.current_user)
        self.masa_data = self._load_all_masa_data()

        # Veri yükleme hatalarını kontrol et
        if self.kullanici_id is None or not self.masa_data:
            self._handle_initial_load_error()
            return

        # Uygulama başladığında ceza kontrolü yap
        self._check_and_apply_penalties()

        # Periyodik olarak ceza kontrolü yapmak için zamanlayıcı başlat
        self.start_periodic_check()

        self.reserved_seats_data = self._load_reservations_from_db()
        self.user_active_reservation_seat_id = self._load_user_active_reservation_name_from_db()

        # UI bileşenlerini oluştur
        self._create_ui_components()

    def _handle_initial_load_error(self):
        """Uygulama başlamadan önce oluşan veri yükleme hatalarını yönetir."""
        if self.kullanici_id is None:
            messagebox.showerror("Kullanıcı Hatası",
                                 f"'{self.current_user}' kullanıcısı veritabanında bulunamadı. "
                                 "Lütfen tekrar giriş yapın.")
        if not self.masa_data:
            messagebox.showerror("Veritabanı Hatası",
                                 "Masa verileri veritabanından yüklenemedi. "
                                 "Lütfen 'masa' tablosunu kontrol edin.")
        # Ana menüye dönmek için callback fonksiyonunu çağırıyoruz.
        if self.on_return_to_main:
            self.on_return_to_main()
        else:
            self.master.destroy()

    def _create_ui_components(self):
        """Tüm UI bileşenlerini oluşturur and yerleştirir."""
        back_button = ctk.CTkButton(
            self,
            text="⮜ Ana Menüye Dön",
            command=self._go_back_to_main_menu,
            fg_color="gray",
            hover_color="darkgray",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=160,
            height=30
        )
        back_button.pack(pady=10, padx=10, anchor="nw")

        image_path = "oturma_plan.png"
        if not os.path.exists(image_path):
            messagebox.showerror("Hata", f"'{image_path}' dosyası bulunamadı.")
            self._go_back_to_main_menu()
            return

        canvas_width = 1400
        canvas_height = 750
        self.bg_image_pil = Image.open(image_path).resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        self.bg_photo_image = ImageTk.PhotoImage(self.bg_image_pil)

        appearance_mode = ctk.get_appearance_mode().lower()
        index = 0 if appearance_mode == "light" else 1
        theme_fg_color = ctk.ThemeManager.theme["CTk"]["fg_color"][index]

        self.canvas = tk.Canvas(self, width=canvas_width, height=canvas_height, highlightthickness=0, bg=theme_fg_color)
        self.canvas.pack(padx=20, pady=10)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo_image)

        self._create_seat_areas()
        self._create_buttons()

        user_info_frame = ctk.CTkFrame(self)
        user_info_frame.pack(pady=5)
        ctk.CTkLabel(user_info_frame, text=f"Kullanıcı: {self.current_user}", font=ctk.CTkFont(size=14)).pack(
            side="left", padx=10)

        self._update_seat_visuals()

        if self.user_active_reservation_seat_id:
            okunabilir_masa_adi = self.user_active_reservation_seat_id.replace("_", " ").title()
            self._display_message(
                f"Hoş geldiniz, {self.current_user}! Aktif bir rezervasyonunuz var: {okunabilir_masa_adi}",
                title="Aktif Rezervasyon Bilgisi"
            )

    def _go_back_to_main_menu(self):
        """Masa Rezervasyon penceresini kapatır ve ana menüye döner."""
        self.destroy()
        if self.on_return_to_main:
            # Ana pencereye dönüş callback fonksiyonunu çağır
            self.on_return_to_main()

    def _get_user_id_from_username(self, username: str) -> int | None:
        """Veritabanından kullanıcı adına göre kullanıcı ID'sini çeker."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT kullanici_id FROM kullanici WHERE isim = ?", (username,))
            result = cursor.fetchone()

            if result:
                try:
                    return int(result[0])
                except (ValueError, IndexError):
                    messagebox.showerror("Veri Tipi Hatası",
                                         f"Veritabanında '{username}' kullanıcısının ID'si geçersiz bir formatta. "
                                         "Lütfen veritabanındaki 'kullanici_id' sütununu kontrol edin.")
                    return None

            messagebox.showerror("Kullanıcı Bulunamadı", f"'{username}' adında bir kullanıcı bulunamadı.")
            return None

        except pyodbc.Error as e:
            messagebox.showerror("Veritabanı Hatası", f"Kullanıcı ID çekilirken veritabanı hatası oluştu: {e}")
            return None
        finally:
            if conn:
                conn.close()
    def start_periodic_check(self):
        """Her 60 saniyede bir ceza kontrolü yapar"""
        self._check_and_apply_penalties()
        self.after_id = self.after(60000, self.start_periodic_check)  # 60 saniye

    def destroy(self):
        """Pencere kapatıldığında zamanlayıcıyı durdur"""
        if self.after_id:
            self.after_cancel(self.after_id)
        super().destroy()

    def _check_and_apply_penalties(self):
        """Rezervasyon süresi geçmiş olanlara ceza uygular."""
        try:
            conn = get_db_connection()
            with conn:
                with conn.cursor() as cursor:
                    current_datetime = datetime.now()
                    cursor.execute("""
                                   SELECT mr.masa_rezervasyon_id, mr.kullanici_id, mr.tarih, mr.saat_bitis, m.numara
                                   FROM masa_rezervasyon mr
                                            JOIN masa m ON mr.masa_id = m.masa_id
                                   WHERE mr.iptal_durumu = 0
                                     AND (mr.durum IS NULL OR mr.durum != 'Tamamlandı')
                                     AND (mr.tarih < CONVERT(date, GETDATE())
                                       OR (mr.tarih = CONVERT(date, GETDATE())
                                           AND mr.saat_bitis <= CONVERT(time, GETDATE())))
                                   """)
                    reservations = cursor.fetchall()

                    for masa_rezervasyon_id, kullanici_id, tarih, bitis_saati, masa_numara in reservations:
                        reservation_end = datetime.combine(tarih, bitis_saati)

                        if reservation_end < current_datetime:
                            # Kullanıcıya 5 puan ceza ver
                            cursor.execute("""
                                           UPDATE kullanici
                                           SET ceza_puani = ISNULL(ceza_puani, 0) + 5
                                           WHERE kullanici_id = ?
                                           """, (kullanici_id,))

                            # Ceza kaydını tabloya yaz
                            cursor.execute("""
                                           INSERT INTO cezalar (kullanici_id, aciklama, tarih, masa_rezervasyon_id)
                                           VALUES (?, ?, ?, ?)
                                           """, (
                                               kullanici_id, 5,
                                               f"Masa rezervasyonuna gelinmedi - Tarih: {tarih}, Saat: {bitis_saati}",
                                               current_datetime.date(),
                                               masa_rezervasyon_id
                                           ))

                            # Rezervasyonu 'Ceza' durumuna geçir
                            cursor.execute("""
                                           UPDATE masa_rezervasyon
                                           SET durum        = 'Ceza',
                                               iptal_durumu = 1
                                           WHERE masa_rezervasyon_id = ?
                                           """, (masa_rezervasyon_id,))

                            # Eğer bu kullanıcı giriş yapan kullanıcıysa popup göster
                            if kullanici_id == self.kullanici_id:
                                self._display_message(
                                    f"{masa_numara.replace('_', ' ').title()} rezervasyonuna gitmediğiniz için 5 puan ceza aldınız.",
                                    title="Ceza Uygulandı",
                                    error=True
                                )

                    conn.commit()
        except Exception as e:
            print(f"Ceza uygulama hatası: {e}")
        finally:
            self.reserved_seats_data = self._load_reservations_from_db()
            self.user_active_reservation_seat_id = self._load_user_active_reservation_name_from_db()
            self._update_seat_visuals()

    def _load_all_masa_data(self) -> dict:
        """Veritabanından tüm masa numaralarını ve ID'lerini yükler."""
        masa_data = {}
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT masa_id, numara FROM masa")
            for row in cursor.fetchall():
                masa_id, numara = row
                masa_data[numara] = masa_id
            return masa_data
        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", f"Masa verileri yüklenirken hata oluştu: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def _load_user_active_reservation_name_from_db(self) -> str | None:
        """Mevcut kullanıcının aktif rezervasyonunu veritabanından çekerek masa adını döndürür."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT m.numara
                           FROM masa_rezervasyon mr
                                    JOIN masa m ON mr.masa_id = m.masa_id
                           WHERE mr.kullanici_id = ?
                             AND mr.iptal_durumu = 0
                             AND (mr.durum IS NULL OR mr.durum != 'Tamamlandı')
                             AND (mr.tarih > CONVERT(date, GETDATE())
                               OR (mr.tarih = CONVERT(date, GETDATE())
                                   AND mr.saat_bitis > CONVERT(time, GETDATE())))
                           """, (self.kullanici_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None
        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", f"Kullanıcının aktif rezervasyonu çekilirken hata oluştu: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def _load_reservations_from_db(self) -> dict:
        """Veritabanından tüm aktif masa rezervasyonlarını yükler."""
        reservations = {}
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT mr.saat_baslangic, mr.saat_bitis, m.numara, k.isim, mr.tarih
                           FROM masa_rezervasyon mr
                                    JOIN masa m ON mr.masa_id = m.masa_id
                                    JOIN kullanici k ON mr.kullanici_id = k.kullanici_id
                           WHERE mr.iptal_durumu = 0
                             AND (mr.durum IS NULL OR mr.durum != 'Tamamlandı')
                             AND (mr.tarih > CONVERT(date, GETDATE())
                               OR (mr.tarih = CONVERT(date, GETDATE())
                                   AND mr.saat_bitis > CONVERT(time, GETDATE())))
                           """)
            for row in cursor.fetchall():
                start_time, end_time, seat_numara, username, res_date = row
                reservations[seat_numara] = {
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "reserved_by": username,
                    "date": res_date
                }
            return reservations
        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", f"Rezervasyonlar yüklenirken hata oluştu: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def _display_message(self, message, title="Bilgi", error=False):
        """Kullanıcıya bilgi veya hata mesajı gösterir."""
        if error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)

    def _seat_clicked(self, seat_id):
        """Bir sandalye alanına tıklandığında çalışır."""
        # Rezervasyon işleminden önce ceza kontrolü yap
        self._check_and_apply_penalties()

        masa_adi_okunakli = seat_id.replace("_", " ").title()

        masa_id = self.masa_data.get(seat_id)
        if masa_id is None:
            messagebox.showerror("Hata",
                                 f"'{masa_adi_okunakli}' için masa ID bulunamadı. Veritabanındaki 'masa' tablosunu kontrol edin.")
            return

        if seat_id in self.reserved_seats_data:
            reservation_info = self.reserved_seats_data[seat_id]
            reserved_by = reservation_info.get("reserved_by", "Bilinmeyen Kullanıcı")
            self._display_message(
                f"Bu sandalye dolu:\n"
                f"Kullanıcı: {reserved_by}\n"
                f"Tarih: {reservation_info['date'].strftime('%d/%m/%Y')}\n"
                f"Başlangıç: {reservation_info['start_time']}\n"
                f"Bitiş: {reservation_info['end_time']}",
                title="Sandalye Dolu",
                error=True
            )
            return

        if self.user_active_reservation_seat_id:
            self._display_message(
                f"Sayın {self.current_user}, zaten '{self.user_active_reservation_seat_id.replace('_', ' ').title()}' numaralı sandalyede aktif bir rezervasyonunuz var.",
                title="Çoklu Rezervasyon Hatası",
                error=True
            )
            return

        def on_date_selected(selected_date):
            TimeSelectionPopup(self.master, seat_id, masa_adi_okunakli, selected_date, self._on_time_confirmed)

        self._reset_all_seat_outlines()
        if seat_id in self.seat_drawing_ids:
            drawing_id = self.seat_drawing_ids[seat_id]
            self.canvas.itemconfig(drawing_id, outline="#00A86B", width=3)
            DateSelectionPopup(self.master, on_date_selected)

    def _on_time_confirmed(self, seat_id, selected_date, start, end):
        """Saat seçimi onaylandıktan sonra rezervasyon işlemini yapar."""
        try:
            # 'with' ifadesiyle bağlantı yönetimi
            with get_db_connection() as conn:
                cursor = conn.cursor()

                masa_id_for_reservation = self.masa_data.get(seat_id)
                if masa_id_for_reservation is None:
                    messagebox.showerror("Hata", f"'{seat_id}' için masa ID bulunamadı. Rezervasyon yapılamadı.")
                    return

                # Tarih ve saat stringlerini SQL Server'ın kabul edeceği formata dönüştürme
                rezervasyon_tarihi_str = datetime.strptime(selected_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                baslangic_saati_str = datetime.strptime(start, "%H:%M").strftime("%H:%M:%S")
                bitis_saati_str = datetime.strptime(end, "%H:%M").strftime("%H:%M:%S")

                cursor.execute("""
                               INSERT INTO masa_rezervasyon (kullanici_id, masa_id, tarih, saat_baslangic, saat_bitis,
                                                             iptal_durumu)
                               VALUES (?, ?, ?, ?, ?, ?)
                               """,
                               (self.kullanici_id, masa_id_for_reservation, rezervasyon_tarihi_str, baslangic_saati_str,
                                bitis_saati_str, 0))

                conn.commit()

                self.reserved_seats_data = self._load_reservations_from_db()
                self.user_active_reservation_seat_id = self._load_user_active_reservation_name_from_db()
                self._update_seat_visuals()
                self._display_message(f"Rezervasyonunuz başarıyla yapıldı: {selected_date} {start} - {end}")

        except pyodbc.Error as e:
            messagebox.showerror("Veritabanı Hatası", f"Rezervasyon kaydedilirken hata oluştu.\nDetay: {e}")
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmedik bir hata oluştu: {e}")
    def _reset_all_seat_outlines(self):
        """Tüm sandalye kenarlıklarını varsayılan duruma döndürür."""
        for drawing_id in self.seat_drawing_ids.values():
            self.canvas.itemconfig(drawing_id, outline="", width=0)

    def _show_past_reservations(self):
        """Geçmiş rezervasyonları gösteren yeni bir pencere açar."""
        PastReservationsPopup(self.master, self.kullanici_id)

    def _create_buttons(self):
        """Uygulamanın ana butonlarını oluşturur."""
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=10)

        ctk.CTkButton(button_frame, text="Rezervasyonu İptal Et", command=self._cancel_my_reservation,
                      fg_color="#FF9800", hover_color="#E68A00").pack(side="left", padx=5)

        # Yeni buton: Geçmiş Rezervasyonları Görüntüle
        ctk.CTkButton(button_frame, text="Geçmiş Rezervasyonları Görüntüle", command=self._show_past_reservations,
                      fg_color="#5865F2", hover_color="#4752C4").pack(side="left", padx=5)

    def _cancel_my_reservation(self):
        """Kullanıcının aktif rezervasyonunu iptal eder."""
        # İptal işleminden önce ceza kontrolü yap
        self._check_and_apply_penalties()

        if not self.user_active_reservation_seat_id:
            self._display_message("Aktif bir rezervasyonunuz bulunmamaktadır.", error=True)
            return

        masa_adi_okunakli = self.user_active_reservation_seat_id.replace("_", " ").title()
        confirm = messagebox.askyesno("Rezervasyon İptali",
                                      f"'{masa_adi_okunakli}' rezervasyonunuzu iptal etmek istediğinizden emin misiniz?")
        if not confirm:
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            masa_id_to_cancel = self.masa_data.get(self.user_active_reservation_seat_id)
            if masa_id_to_cancel is None:
                messagebox.showerror("Hata", f"İptal edilecek sandalye ID'si için masa ID bulunamadı.")
                return

            cursor.execute("""
                           UPDATE masa_rezervasyon
                           SET iptal_durumu = 1
                           WHERE kullanici_id = ?
                             AND masa_id = ?
                             AND iptal_durumu = 0
                           """, (self.kullanici_id, masa_id_to_cancel))
            conn.commit()

            self.reserved_seats_data = self._load_reservations_from_db()
            self.user_active_reservation_seat_id = self._load_user_active_reservation_name_from_db()
            self._display_message(f"'{masa_adi_okunakli}' numaralı rezervasyonunuz iptal edildi.")
            self._update_seat_visuals()

        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", f"Rezervasyon iptal edilirken hata oluştu: {e}")
        finally:
            if conn:
                conn.close()

    def _update_seat_visuals(self):
        """Sandalyelerin renklerini ve kenarlıklarını rezervasyon durumuna göre günceller."""
        UNRESERVED_COLOR = "#66BB6A"  # Yeşil
        MY_RESERVATION_COLOR = "#42A5F5"  # Mavi
        RESERVED_COLOR = "#FF7043"  # Turuncu

        for seat_id, drawing_id in self.seat_drawing_ids.items():
            self.canvas.itemconfig(drawing_id, outline="", width=0)

            if seat_id in self.reserved_seats_data:
                if self.reserved_seats_data[seat_id].get("reserved_by") == self.current_user:
                    self.canvas.itemconfig(drawing_id, fill=MY_RESERVATION_COLOR)
                else:
                    self.canvas.itemconfig(drawing_id, fill=RESERVED_COLOR)
            else:
                self.canvas.itemconfig(drawing_id, fill=UNRESERVED_COLOR)

    def _create_seat_areas(self):
        """Resim üzerindeki tıklanabilir sandalye alanlarını çizer."""
        for seat_id, coords in self.seat_coordinates.items():
            self._add_rounded_seat_area(seat_id, coords["x"], coords["y"], coords["w"], coords["h"], radius=4)

    def _add_rounded_seat_area(self, seat_id, x, y, w, h, radius=5):
        """Yuvarlak köşeli dikdörtgen şeklinde tıklanabilir bir sandalye alanı oluşturur."""
        radius = min(radius, w // 2, h // 2)
        points = [
            x + radius, y,
            x + w - radius, y,
            x + w, y + radius,
            x + w, y + h - radius,
            x + w - radius, y + h,
            x + radius, y + h,
            x, y + h - radius,
            x, y + radius
        ]

        drawing_id = self.canvas.create_polygon(
            points,
            outline="",
            fill=self.canvas["bg"],
            tags=seat_id
        )

        self.seat_drawing_ids[seat_id] = drawing_id
        self.canvas.tag_bind(drawing_id, "<Button-1>", lambda e, sid=seat_id: self._seat_clicked(sid))
        self.canvas.tag_bind(drawing_id, "<Enter>", self._on_seat_hover_enter)
        self.canvas.tag_bind(drawing_id, "<Leave>", self._on_seat_hover_leave)

    def _on_seat_hover_enter(self, event):
        """Masanın üzerine gelindiğinde kenarlığı vurgular."""
        drawing_id = self.canvas.find_closest(event.x, event.y)[0]
        for seat_id, d_id in self.seat_drawing_ids.items():
            if d_id == drawing_id:
                if (seat_id in self.reserved_seats_data and
                    self.reserved_seats_data[seat_id].get("reserved_by") != self.current_user) or \
                        (self.user_active_reservation_seat_id and self.user_active_reservation_seat_id != seat_id):
                    return
                self.canvas.itemconfig(drawing_id, outline="#64B5F6", width=2)
                break

    def _on_seat_hover_leave(self, event):
        """Masanın üzerinden ayrıldığında kenarlığı kaldırır."""
        drawing_id = self.canvas.find_closest(event.x, event.y)[0]
        for seat_id, d_id in self.seat_drawing_ids.items():
            if d_id == drawing_id:
                # Seçili sandalyeyi vurgulayan kenarlık varsa onu koru
                current_outline_color = self.canvas.itemcget(drawing_id, "outline")
                if current_outline_color == "#00a86b":  # Vurgulu kenarlık rengi
                    return
                # Değilse, varsayılan duruma döndür
                self.canvas.itemconfig(drawing_id, outline="", width=0)
                break

class PastReservationsPopup(ctk.CTkToplevel):
    def __init__(self, parent, user_id):
        super().__init__(parent)
        self.title("Geçmiş Rezervasyonlarım")
        self.geometry("600x400")
        self.grab_set()
        self.transient(parent)
        self.user_id = user_id

        ctk.CTkLabel(self, text="Geçmiş Rezervasyonlarınız", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        self.scrollable_frame = ctk.CTkScrollableFrame(self, width=550, height=300)
        self.scrollable_frame.pack(pady=10)

        self.load_past_reservations()

    def load_past_reservations(self):
        """Kullanıcının geçmiş rezervasyonlarını veritabanından çeker ve listeler."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                    SELECT m.numara, \
                           mr.tarih, \
                           mr.saat_baslangic, \
                           mr.saat_bitis, \
                           mr.durum
                    FROM masa_rezervasyon mr
                             JOIN masa m ON mr.masa_id = m.masa_id
                    WHERE mr.kullanici_id = ?
                      AND (
                            mr.tarih < CONVERT(date, GETDATE())
                            OR (mr.tarih = CONVERT(date, GETDATE()) AND mr.saat_bitis < CONVERT(time, GETDATE()))
                          )
                    """
            cursor.execute(query, (self.user_id,))
            reservations = cursor.fetchall()

            if not reservations:
                ctk.CTkLabel(self.scrollable_frame, text="Geçmiş rezervasyonunuz bulunmamaktadır.",
                             font=ctk.CTkFont(size=14, slant="italic")).pack(pady=20)
                return

            # Başlık satırı
            header_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
            header_frame.pack(fill="x", padx=10, pady=(0, 5))
            ctk.CTkLabel(header_frame, text="Masa", font=ctk.CTkFont(weight="bold")).pack(side="left", expand=True)
            ctk.CTkLabel(header_frame, text="Tarih", font=ctk.CTkFont(weight="bold")).pack(side="left", expand=True)
            ctk.CTkLabel(header_frame, text="Saat", font=ctk.CTkFont(weight="bold")).pack(side="left", expand=True)
            ctk.CTkLabel(header_frame, text="Durum", font=ctk.CTkFont(weight="bold")).pack(side="left", expand=True)

            # Rezervasyonları listele
            for numara, tarih, baslangic, bitis, durum in reservations:
                item_frame = ctk.CTkFrame(self.scrollable_frame)
                item_frame.pack(fill="x", padx=5, pady=2)

                masa_adi_okunakli = numara.replace("_", " ").title()
                tarih_str = tarih.strftime("%d/%m/%Y")
                saat_str = f"{baslangic.strftime('%H:%M')} - {bitis.strftime('%H:%M')}"

                ctk.CTkLabel(item_frame, text=masa_adi_okunakli).pack(side="left", expand=True)
                ctk.CTkLabel(item_frame, text=tarih_str).pack(side="left", expand=True)
                ctk.CTkLabel(item_frame, text=saat_str).pack(side="left", expand=True)

                # Durum etiketi için renk belirleme
                if durum == "Ceza":
                    color = "red"
                elif durum == "Tamamlandı":
                    color = "#66BB6A"
                else:
                    color = "orange"
                ctk.CTkLabel(item_frame, text=durum, text_color=color).pack(side="left", expand=True)
        except Exception as e:
            messagebox.showerror("Hata", f"Geçmiş rezervasyonlar yüklenirken hata oluştu: {e}")
        finally:
            if conn:
                conn.close()