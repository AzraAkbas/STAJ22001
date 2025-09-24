import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageFont
import hashlib
import re
import os
import json
from datetime import datetime, timedelta
import traceback
import bcrypt

from database import get_db_connection
from book_rezervation_app import BookReservationApp
from table_rezervation_app import TableReservationApp
from admin_panel import MainApp

LOGIN_STATE_FILE = "login_state.json"
LOGIN_VALIDITY_DAYS = 30

def hash_sifre(sifre: str) -> str:
    """Güvenli bir şekilde şifreyi hash'ler ve tuz ekler."""
    # Şifreyi bytes'a çevir ve bcrypt ile hashle
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(sifre.encode('utf-8'), salt)
    return hashed.decode('utf-8')  # String olarak döndür

def verify_sifre(girilen_sifre: str, stored_hash: str) -> bool:
    """Girilen şifreyi hashlenmiş şifre ile karşılaştırır."""
    try:
        return bcrypt.checkpw(girilen_sifre.encode('utf-8'), stored_hash.encode('utf-8'))
    except (ValueError, TypeError):
        # Eski SHA256 hash'leri için geriye dönük uyumluluk
        try:
            hashed_girilen = hashlib.sha256(girilen_sifre.encode()).hexdigest()
            return hashed_girilen == stored_hash
        except:
            return False

def make_circle_image(path: str, size: int) -> Image.Image:
    """
    Creates a circular image from a given path.
    If the image file is not found, it creates a placeholder circle.
    """
    try:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image file not found: {path}")
        img = Image.open(path).convert("RGBA")
    except FileNotFoundError:
        img = Image.new('RGBA', (size, size), (200, 200, 200, 255))
        draw = ImageDraw.Draw(img)
        text = "Resim Yok"
        try:
            font = ImageFont.truetype("arial.ttf", size=size // 5)
        except IOError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(((size - text_width) / 2, (size - text_height) / 2), text, fill=(50, 50, 50, 255), font=font)
    except Exception as e:
        print(f"Error loading image {path}: {e}")
        img = Image.new('RGBA', (size, size), (200, 200, 200, 255))
        draw = ImageDraw.Draw(img)
        text = "Hata"
        try:
            font = ImageFont.truetype("arial.ttf", size=size // 5)
        except IOError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        draw.text(((size - text_width) / 2, (size - text_height) / 2), text, fill=(50, 50, 50, 255), font=font)

    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    img.putalpha(mask)
    return img


def save_login_state(username: str, role: str, user_id: int):
    """Saves the current login state (username, role, user_id and timestamp) to a file."""
    state = {
        "username": username,
        "role": role,
        "user_id": user_id,
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open(LOGIN_STATE_FILE, "w") as f:
            json.dump(state, f)
    except IOError as e:
        print(f"Error saving login state: {e}")


def load_login_state() -> tuple[str | None, str | None, int | None]:
    """
    Loads the login state from a file and checks its validity.
    Returns the username, role and user_id if valid, otherwise None.
    """
    if not os.path.exists(LOGIN_STATE_FILE):
        return None, None, None
    try:
        with open(LOGIN_STATE_FILE, "r") as f:
            state = json.load(f)
        username = state.get("username")
        role = state.get("role")
        user_id = state.get("user_id")
        timestamp_str = state.get("timestamp")

        if username and timestamp_str:
            last_login_time = datetime.fromisoformat(timestamp_str)
            if datetime.now() - last_login_time < timedelta(days=LOGIN_VALIDITY_DAYS):
                return username, role, user_id
        clear_login_state()
        return None, None, None
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading login state: {e}")
        clear_login_state()
        return None, None, None


def clear_login_state():
    """Removes the login state file."""
    if os.path.exists(LOGIN_STATE_FILE):
        try:
            os.remove(LOGIN_STATE_FILE)
        except OSError as e:
            print(f"Error clearing login state file: {e}")


# --- Ana Uygulama Sınıfı ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kütüphane Sistemi")
        self.geometry("400x500")
        self.minsize(400, 500)
        self.resizable(False, False)

        self.current_user_name = None
        self.current_user_id = None
        self.current_user_role = None
        self.current_user_penalty_points = 0
        self.book_reservation_window = None
        self.table_reservation_window = None
        self.admin_panel_window = None
        self.user_info_window = None

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=0, pady=0)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self._create_frames()

        remembered_user, remembered_role, remembered_id = load_login_state()
        if remembered_user:
            self.current_user_name = remembered_user
            self.current_user_role = remembered_role
            self.current_user_id = remembered_id
            # Hatırlanan kullanıcı için ceza puanını veritabanından çekme
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT ceza_puani FROM kullanici WHERE kullanici_id = ?", (self.current_user_id,))
                    penalty = cursor.fetchone()
                    if penalty:
                        self.current_user_penalty_points = penalty[0]
                finally:
                    conn.close()
            self.show_frame("main_app")
        else:
            self.show_frame("login")

    def _create_frames(self):
        login_frame = LoginFrame(self.container, self)
        self.frames["login"] = login_frame
        login_frame.grid(row=0, column=0, sticky="nsew")

        register_frame = RegisterFrame(self.container, self)
        self.frames["register"] = register_frame
        register_frame.grid(row=0, column=0, sticky="nsew")

        main_app_frame = MainAppFrame(self.container, self)
        self.frames["main_app"] = main_app_frame
        main_app_frame.grid(row=0, column=0, sticky="nsew")

    def _check_and_reset_penalties(self, user_id: int, conn, cursor):
        """
        Kullanıcının son ceza tarihini kontrol eder ve
        son ceza tarihinden 10 gün geçmişse ceza puanını sıfırlar.
        """
        if not conn or not cursor:
            print("Hata: Geçersiz bağlantı veya imleç.")
            return

        try:
            # Kullanıcının mevcut ceza puanını kontrol et
            cursor.execute(
                "SELECT ceza_puani FROM kullanici WHERE kullanici_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()

            if not result or result[0] == 0:
                return

            # Son ceza tarihini al
            cursor.execute(
                "SELECT MAX(tarih) FROM cezalar WHERE kullanici_id = ?",
                (user_id,)
            )
            last_penalty_date_result = cursor.fetchone()

            if last_penalty_date_result and last_penalty_date_result[0]:
                last_penalty_date = last_penalty_date_result[0]
                if isinstance(last_penalty_date, datetime):
                    last_penalty_date = last_penalty_date.date()

                current_date = datetime.now().date()
                days_passed = (current_date - last_penalty_date).days

                if days_passed >= 10:
                    cursor.execute(
                        "UPDATE kullanici SET ceza_puani = 0 WHERE kullanici_id = ?",
                        (user_id,)
                    )
                    conn.commit()
                    self.current_user_penalty_points = 0
                    messagebox.showinfo(
                        "Ceza Puanı Sıfırlama",
                        f"Son cezanızın üzerinden {days_passed} gün geçtiği için ceza puanınız sıfırlandı."
                    )
            else:
                cursor.execute(
                    "UPDATE kullanici SET ceza_puani = 0 WHERE kullanici_id = ?",
                    (user_id,)
                )
                conn.commit()
                self.current_user_penalty_points = 0

        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", str(e))
            traceback.print_exc()

    def show_frame(self, page_name: str):
        frame = self.frames.get(page_name)
        if frame:
            if page_name == "main_app":
                if self.current_user_name:
                    # Penalty puanını frame'e gönder
                    frame.set_user_name(
                        self.current_user_name,
                        self.current_user_role,
                        self.current_user_penalty_points
                    )
                self.geometry("400x500")
                self.resizable(False, False)
            else:
                self.geometry("400x500")
                self.resizable(False, False)

            if self.state() == "withdrawn":
                self.deiconify()

            frame.tkraise()
        else:
            messagebox.showerror("Hata", f"'{page_name}' adlı sayfa bulunamadı.")

    def _open_book_reservation_window(self):
        if self.book_reservation_window is None or not self.book_reservation_window.winfo_exists():
            self.withdraw()
            self.book_reservation_window = BookReservationApp(
                self,
                show_main_menu_callback=self._return_to_main_window,
                user_name=self.current_user_name
            )
            self.book_reservation_window.protocol("WM_DELETE_WINDOW", self._return_to_main_window)
        else:
            self.book_reservation_window.focus()

    def _open_table_reservation_window(self):
        if self.table_reservation_window is None or not self.table_reservation_window.winfo_exists():
            self.withdraw()  # Ana pencereyi gizle
            # Yeni bir Toplevel pencere oluşturun ve TableReservationApp'i içine yerleştirin
            table_window = ctk.CTkToplevel(self)
            table_window.title("Masa Rezervasyon Sistemi")
            table_window.geometry("1400x800")

            # Pencere kapatıldığında ana pencereyi geri getir
            table_window.protocol("WM_DELETE_WINDOW", self._return_to_main_window)

            # TableReservationApp'i oluştur
            self.table_reservation_window = TableReservationApp(
                table_window,
                current_user=self.current_user_name,
                on_return_to_main=self._return_to_main_window
            )
        else:
            self.table_reservation_window.master.focus()  # Toplevel penceresine odaklan

    def _open_admin_panel_window(self):
        if self.current_user_role == 'admin':
            # Mevcut pencereyi gizle
            self.withdraw()

            # Yeni bir Toplevel pencere oluştur
            admin_window = ctk.CTkToplevel(self)
            admin_window.title("Admin Paneli")
            admin_window.geometry("1200x800")

            # Admin panelini oluştur - MainApp'i Toplevel penceresine yerleştir
            self.admin_panel_window = MainApp(admin_window)
            self.admin_panel_window.pack(fill="both", expand=True)

            # Pencere kapatıldığında ana pencereyi geri getir
            def on_admin_close():
                admin_window.destroy()
                self.admin_panel_window = None
                self.deiconify()
                self.focus_set()

            admin_window.protocol("WM_DELETE_WINDOW", on_admin_close)
            admin_window.focus_set()
        else:
            messagebox.showwarning("Yetkisiz Erişim", "Bu sayfaya erişim yetkiniz bulunmamaktadır.")

    def _open_user_info_window(self):
        if self.user_info_window is None or not self.user_info_window.winfo_exists():
            self.withdraw()
            self.user_info_window = UserInfoWindow(
                self,  # self'i geçirerek controller'a erişim sağla
                self.current_user_id,
                self.current_user_name,
                self.current_user_penalty_points,
                self._return_to_main_window
            )
            self.user_info_window.protocol("WM_DELETE_WINDOW", self._return_to_main_window)
        else:
            self.user_info_window.focus()

    def _refresh_main_after_user_info_close(self):
        """Kullanıcı bilgileri penceresi kapandığında ana ekranı yeniler"""
        if self.user_info_window:
            # Kullanıcı adı değişmiş olabilir, ana ekranı güncelle
            if hasattr(self.user_info_window, 'user_name'):
                self.current_user_name = self.user_info_window.user_name

            self.user_info_window.destroy()
            self.user_info_window = None

        self.deiconify()
        self.focus_set()

        # Ana ekranı yenile
        if hasattr(self, 'frames') and "main_app" in self.frames:
            self.frames["main_app"].set_user_name(
                self.current_user_name,
                self.current_user_role,
                self.current_user_penalty_points
            )

    def _return_to_main_window(self):
        """Masa rezervasyon penceresini kapatır ve ana pencereyi gösterir."""
        if self.table_reservation_window:
            # Toplevel penceresini kapat
            self.table_reservation_window.master.destroy()
            self.table_reservation_window = None

        # Diğer pencereleri de kontrol et
        if self.book_reservation_window:
            self.book_reservation_window.destroy()
            self.book_reservation_window = None
        if self.admin_panel_window:
            self.admin_panel_window.destroy()
            self.admin_panel_window = None
        if self.user_info_window:
            self.user_info_window.destroy()
            self.user_info_window = None

        # Ana pencereyi tekrar göster
        self.deiconify()
        self.focus_set()  # Ana pencereye odaklan
# --- Kullanıcı Bilgileri Penceresi ---
class UserInfoWindow(ctk.CTkToplevel):
    def __init__(self, parent, user_id, user_name, penalty_points, return_callback):
        super().__init__(parent)
        self.user_id = user_id
        self.user_name = user_name
        self.penalty_points = penalty_points
        self.return_callback = return_callback
        self.controller = parent

        self.title("Kullanıcı Bilgileri")
        self.geometry("400x500")
        self.resizable(False, False)

        # Ana çerçeve - minimum padding
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Başlık - çok az boşluk
        title_label = ctk.CTkLabel(
            self.main_frame,
            text="Kullanıcı Bilgileri",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(10, 20))

        # Kullanıcı adı değiştirme bölümü - DOĞRUDAN ANA FRAME'E EKLE
        ctk.CTkLabel(
            self.main_frame,
            text="Kullanıcı Adı Değiştir",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 0))

        self.new_username_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Yeni Kullanıcı Adı",
            width=300
        )
        self.new_username_entry.insert(0, self.user_name)
        self.new_username_entry.pack(pady=(0, 0))

        # Kullanıcı adı kontrolü için label
        self.username_status_label = ctk.CTkLabel(
            self.main_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.username_status_label.pack(pady=(0, 0))

        # Kullanıcı adı değişikliklerini dinle
        self.new_username_entry.bind("<KeyRelease>", self._check_username_availability)

        change_username_button = ctk.CTkButton(
            self.main_frame,
            text="Kullanıcı Adını Değiştir",
            command=self._change_username,
            width=200
        )
        change_username_button.pack(pady=(0, 20))


        # Şifre değiştirme bölümü - DOĞRUDAN ANA FRAME'E EKLE
        ctk.CTkLabel(
            self.main_frame,
            text="Şifre Değiştir",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 5))

        self.current_password_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Mevcut Şifre",
            show="*",
            width=300
        )
        self.current_password_entry.pack(pady=(5, 5))

        self.new_password_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Yeni Şifre",
            show="*",
            width=300
        )
        self.new_password_entry.pack(pady=(5, 5))

        self.confirm_password_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Yeni Şifre (Tekrar)",
            show="*",
            width=300
        )
        self.confirm_password_entry.pack(pady=(5, 5))

        change_password_button = ctk.CTkButton(
            self.main_frame,
            text="Şifreyi Değiştir",
            command=self._change_password,
            width=200
        )
        change_password_button.pack(pady=(25, 15))

        # Ceza puanı bilgisi - DOĞRUDAN ANA FRAME'E EKLE
        ctk.CTkLabel(
            self.main_frame,
            text=f"Ceza Puanı: {penalty_points}",
            font=ctk.CTkFont(size=14)
        ).pack(anchor="w", pady=(15, 15))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _check_username_availability(self, event=None):
        """Kullanıcı adının kullanılabilirliğini kontrol eder"""
        new_username = self.new_username_entry.get().strip()

        if not new_username:
            self.username_status_label.configure(text="", text_color="black")
            return

        if new_username == self.user_name:
            self.username_status_label.configure(text="Bu zaten mevcut kullanıcı adınız", text_color="blue")
            return

        # Kullanıcı adı kullanılabilirliğini kontrol et
        conn = get_db_connection()
        if not conn:
            self.username_status_label.configure(text="Veritabanı bağlantı hatası", text_color="red")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM kullanici WHERE isim = ? AND kullanici_id != ?",
                (new_username, self.user_id)
            )
            result = cursor.fetchone()

            if result and result[0] > 0:
                self.username_status_label.configure(text="Bu kullanıcı adı zaten kullanılıyor", text_color="red")
            else:
                self.username_status_label.configure(text="Kullanıcı adı uygun", text_color="green")

        except Exception as e:
            self.username_status_label.configure(text="Kontrol hatası", text_color="red")
        finally:
            conn.close()

    def _change_username(self):
        new_username = self.new_username_entry.get().strip()

        if not new_username:
            messagebox.showerror("Hata", "Lütfen yeni kullanıcı adını girin.")
            return

        if new_username == self.user_name:
            messagebox.showinfo("Bilgi", "Bu zaten mevcut kullanıcı adınız.")
            return

        # Kullanıcı adı kullanılabilirliğini tekrar kontrol et
        conn = get_db_connection()
        if not conn:
            messagebox.showerror("Hata", "Veritabanına bağlanılamadı.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM kullanici WHERE isim = ? AND kullanici_id != ?",
                (new_username, self.user_id)
            )
            result = cursor.fetchone()

            if result and result[0] > 0:
                messagebox.showerror("Hata", "Bu kullanıcı adı zaten kullanılıyor.")
                return

            # Kullanıcı adını güncelle
            cursor.execute(
                "UPDATE kullanici SET isim = ? WHERE kullanici_id = ?",
                (new_username, self.user_id)
            )
            conn.commit()

            messagebox.showinfo("Başarılı", "Kullanıcı adı başarıyla güncellendi.")
            self.user_name = new_username

            # Ana uygulamayı ve login state'i güncelle
            if hasattr(self.controller, 'current_user_name'):
                self.controller.current_user_name = new_username
                save_login_state(new_username, self.controller.current_user_role, self.user_id)

        except Exception as e:
            messagebox.showerror("Hata", f"Kullanıcı adı güncelleme hatası: {str(e)}")
            traceback.print_exc()
        finally:
            conn.close()

    def _change_password(self):
        current_password = self.current_password_entry.get()
        new_password = self.new_password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        if not all([current_password, new_password, confirm_password]):
            messagebox.showerror("Hata", "Lütfen tüm alanları doldurun.")
            return

        if len(new_password) < 8:
            messagebox.showerror("Hata", "Yeni şifre en az 8 karakter olmalıdır.")
            return

        if new_password != confirm_password:
            messagebox.showerror("Hata", "Yeni şifreler eşleşmiyor.")
            return

        # Mevcut şifreyi doğrula
        conn = get_db_connection()
        if not conn:
            messagebox.showerror("Hata", "Veritabanına bağlanılamadı.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sifre FROM kullanici WHERE kullanici_id = ?",
                (self.user_id,)
            )
            result = cursor.fetchone()

            if not result:
                messagebox.showerror("Hata", "Kullanıcı bulunamadı.")
                return

            stored_password = result[0]

            # Yeni şifre doğrulama metodu
            if not verify_sifre(current_password, stored_password):
                messagebox.showerror("Hata", "Mevcut şifre hatalı.")
                return

            # Şifreyi güncelle (yeni hashleme metodu ile)
            hashed_new_password = hash_sifre(new_password)
            cursor.execute(
                "UPDATE kullanici SET sifre = ? WHERE kullanici_id = ?",
                (hashed_new_password, self.user_id)
            )
            conn.commit()

            messagebox.showinfo("Başarılı", "Şifre başarıyla güncellendi.")
            self.current_password_entry.delete(0, "end")
            self.new_password_entry.delete(0, "end")
            self.confirm_password_entry.delete(0, "end")

        except Exception as e:
            messagebox.showerror("Hata", f"Şifre güncelleme hatası: {str(e)}")
        finally:
            conn.close()


    def _on_close(self):
        self.destroy()
        self.return_callback()


# --- Giriş Sayfası (Frame) ---
class LoginFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        IMAGE_DISPLAY_SIZE = 137
        circle_img = make_circle_image("user.jpg", IMAGE_DISPLAY_SIZE)
        profile = ctk.CTkImage(light_image=circle_img, size=(IMAGE_DISPLAY_SIZE, IMAGE_DISPLAY_SIZE))
        image_label = ctk.CTkLabel(self, image=profile, text="")
        image_label.pack(pady=(30, 10))

        self.email_entry = ctk.CTkEntry(self, placeholder_text="E-posta", width=230, height=40)
        self.email_entry.pack(pady=10, padx=40)

        self.password_entry = ctk.CTkEntry(self, placeholder_text="Şifre", show="*", width=230, height=40)
        self.password_entry.pack(pady=10, padx=40)

        login_button = ctk.CTkButton(self, text="Giriş Yap", command=self._giris_yap, width=150, height=40)
        login_button.pack(pady=(20, 10))

        register_button = ctk.CTkButton(
            self,
            text="Kayıt Ol",
            command=lambda: self.controller.show_frame("register"),
            fg_color="gray",
            hover_color="darkgray",
            width=150,
            height=40
        )
        register_button.pack()

    def _giris_yap(self):
        """
        Kullanıcı girişini doğrular, ceza puanlarını kontrol eder ve başarılıysa
        kullanıcıyı ana uygulamaya yönlendirir.
        """
        email = self.email_entry.get().strip()
        sifre = self.password_entry.get()

        if not all([email, sifre]):
            messagebox.showerror("Giriş Hatası", "Lütfen tüm alanları doldurun.")
            return

        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                messagebox.showerror("Bağlantı Hatası", "Veritabanına bağlanılamadı.")
                return

            cursor = conn.cursor()

            # E-posta ile kullanıcıyı bul
            cursor.execute(
                "SELECT isim, rol, kullanici_id, ceza_puani, sifre FROM kullanici WHERE eposta = ?",
                (email,)
            )
            user = cursor.fetchone()

            if user:
                isim, rol, kullanici_id, ceza_puani, stored_password = user

                # Şifreyi doğrula
                if verify_sifre(sifre, stored_password):
                    # Fonksiyonu conn ve cursor ile çağır
                    self.controller._check_and_reset_penalties(kullanici_id, conn, cursor)

                    # Sıfırlama işleminden sonra güncel ceza puanını al.
                    cursor.execute(
                        "SELECT ceza_puani FROM kullanici WHERE kullanici_id = ?",
                        (kullanici_id,)
                    )
                    updated_penalty_result = cursor.fetchone()
                    updated_penalty = updated_penalty_result[0] if updated_penalty_result else ceza_puani

                    self.controller.current_user_name = isim
                    self.controller.current_user_role = rol
                    self.controller.current_user_id = kullanici_id
                    self.controller.current_user_penalty_points = updated_penalty

                    save_login_state(isim, rol, kullanici_id)
                    messagebox.showinfo("Başarılı", f"Giriş başarılı! Hoş geldiniz {isim}")

                    self.controller.show_frame("main_app")
                else:
                    messagebox.showerror("Hatalı Giriş", "Hatalı e-posta veya şifre girdiniz.")
            else:
                messagebox.showerror("Hatalı Giriş", "Hatalı e-posta veya şifre girdiniz.")

        except Exception as e:
            messagebox.showerror("Veritabanı Hatası", str(e))
            traceback.print_exc()
        finally:
            # Bağlantıyı sadece bu tek noktada kapat.
            if conn:
                conn.close()
# --- Kayıt Sayfası (Frame) ---
class RegisterFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        back_button = ctk.CTkButton(
            self,
            text="⮜",
            width=35,
            height=27,
            command=lambda: self.controller.show_frame("login"),
            fg_color="gray",
            hover_color="darkgray",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        back_button.pack(pady=(10, 10), padx=10, anchor="nw")

        self.name_entry = ctk.CTkEntry(self, placeholder_text="İsim (Kullanıcı Adı)", width=230, height=40)
        self.name_entry.pack(pady=15, padx=40)

        # Kullanıcı adı durum etiketi
        self.username_status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.username_status_label.pack(pady=2)

        # Kullanıcı adı değişikliklerini dinle
        self.name_entry.bind("<KeyRelease>", self._check_username_availability)

        self.email_entry = ctk.CTkEntry(self, placeholder_text="E-posta", width=230, height=40)
        self.email_entry.pack(pady=15, padx=40)

        self.password_entry = ctk.CTkEntry(self, placeholder_text="Şifre", show="*", width=230, height=40)
        self.password_entry.pack(pady=15, padx=40)

        register_button = ctk.CTkButton(self, text="Kayıt Ol", command=self._kayit_ol, width=130, height=40)
        register_button.pack(pady=(20, 10))

    def _check_username_availability(self, event=None):
        """Kullanıcı adının kullanılabilirliğini kontrol eder"""
        username = self.name_entry.get().strip()

        if not username:
            self.username_status_label.configure(text="", text_color="black")
            return

        # Kullanıcı adı kullanılabilirliğini kontrol et
        conn = get_db_connection()
        if not conn:
            self.username_status_label.configure(text="Veritabanı bağlantı hatası", text_color="red")
            return

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM kullanici WHERE isim = ?",
                (username,)
            )
            result = cursor.fetchone()

            if result and result[0] > 0:
                self.username_status_label.configure(text="Bu kullanıcı adı zaten kullanılıyor", text_color="red")
            else:
                self.username_status_label.configure(text="Kullanıcı adı uygun", text_color="green")

        except Exception as e:
            self.username_status_label.configure(text="Kontrol hatası", text_color="red")
        finally:
            conn.close()

    def _kayit_ol(self):
        email = self.email_entry.get().strip()
        sifre = self.password_entry.get().strip()
        isim = self.name_entry.get().strip()

        if not all([email, sifre, isim]):
            messagebox.showerror("Kayıt Hatası", "Lütfen tüm alanları doldurun.")
            return

        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            messagebox.showerror("Geçersiz E-posta", "Lütfen geçerli bir e-posta adresi girin.")
            return

        if len(sifre) < 8:
            messagebox.showerror("Geçersiz Şifre", "Şifre en az 8 karakter olmalıdır.")
            return

        # Kullanıcı adı benzersizlik kontrolü
        conn = get_db_connection()
        if not conn:
            messagebox.showerror("Bağlantı Hatası", "Veritabanına bağlanılamadı.")
            return

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM kullanici WHERE isim = ?", (isim,))
            username_count = cursor.fetchone()[0]

            if username_count > 0:
                messagebox.showerror("Hata",
                                     "Bu kullanıcı adı zaten kullanılıyor. Lütfen farklı bir kullanıcı adı seçin.")
                return

            cursor.execute("SELECT COUNT(*) FROM kullanici WHERE eposta = ?", (email,))
            email_count = cursor.fetchone()[0]

            if email_count > 0:
                messagebox.showerror("Hata", "Bu e-posta adresi zaten kayıtlı.")
                return

            # Yeni güvenli hashleme metodu
            hashed_password = hash_sifre(sifre)

            # Yeni kullanıcıyı ekle
            cursor.execute(
                "INSERT INTO kullanici (eposta, sifre, isim, rol, ceza_puani) VALUES (?, ?, ?, ?, ?)",
                (email, hashed_password, isim, 'user', 0)
            )
            conn.commit()
            messagebox.showinfo("Başarılı", "Kayıt işlemi başarılı oldu!")
            self.controller.show_frame("login")

        except Exception as e:
            messagebox.showerror("Hata", f"Kayıt hatası: {str(e)}")
            traceback.print_exc()
        finally:
            conn.close()
# --- Ana Menü (Frame) ---
class MainAppFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.welcome_label = ctk.CTkLabel(self, text="Hoş Geldiniz!", font=ctk.CTkFont(size=24, weight="bold"))
        self.welcome_label.pack(pady=20)

        self.user_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=18))
        self.user_label.pack(pady=10)

        # Butonlar için ortak bir çerçeve oluşturun
        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(pady=10, fill="x", expand=False)
        self.buttons_frame.grid_columnconfigure(0, weight=1)

        # Buton referanslarını sakla
        self.table_reservation_button = ctk.CTkButton(
            self.buttons_frame,
            text="Masa Rezervasyon",
            command=lambda: self.controller._open_table_reservation_window(),
            width=200,
            height=40,
            fg_color="green",
            hover_color="darkgreen"
        )
        self.table_reservation_button.pack(pady=10)

        self.book_reservation_button = ctk.CTkButton(
            self.buttons_frame,
            text="Kitap Rezervasyon",
            command=lambda: self.controller._open_book_reservation_window(),
            width=200,
            height=40,
            fg_color="purple"
        )
        self.book_reservation_button.pack(pady=10)

        self.user_info_button = ctk.CTkButton(
            self.buttons_frame,
            text="Bilgilerim",
            command=lambda: self.controller._open_user_info_window(),
            width=200,
            height=40,
            fg_color="blue",
            hover_color="darkblue"
        )
        self.user_info_button.pack(pady=10)

        self.admin_button = ctk.CTkButton(
            self.buttons_frame,
            text="Admin Paneli",
            command=lambda: self.controller._open_admin_panel_window(),
            width=200,
            height=40,
            fg_color="orange",
            hover_color="darkorange"
        )
        self.admin_button.pack(pady=10)

        logout_button = ctk.CTkButton(
            self,
            text="Çıkış Yap",
            command=lambda: (clear_login_state(), self.controller.show_frame("login")),
            fg_color="red",
            hover_color="darkred",
            width=150,
            height=40
        )
        logout_button.pack(pady=30)

    def set_user_name(self, user_name: str, user_role: str, penalty_points: int):
        """Kullanıcı adını, rolünü ve ceza puanını ayarlar, admin butonunu gösterir ve cezaları kontrol eder."""
        self.user_label.configure(text=f"Sayın {user_name}, kütüphane sistemine hoş geldiniz!")
        if user_role == 'admin':
            self.admin_button.pack(pady=10)
        else:
            self.admin_button.pack_forget()

        # Giriş yapıldığında ceza puanını kontrol et ve sıfırla
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                self.controller._check_and_reset_penalties(self.controller.current_user_id, conn, cursor)
                # Buradaki conn.close() çağrısını kaldırın, çünkü aşağıdaki kod da bir bağlantı açacak.
            except Exception as e:
                print(f"Hata: {e}")
            finally:
                if conn:
                    conn.close()

        # Güncel ceza puanını al ve buton durumlarını ayarla
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT ceza_puani FROM kullanici WHERE kullanici_id = ?",
                    (self.controller.current_user_id,)
                )
                result = cursor.fetchone()
                if result:
                    current_penalty = result[0]
                    self._check_penalties(current_penalty)
            finally:
                if conn:
                    conn.close()
    def _check_penalties(self, penalty_points: int):
        """Kullanıcının ceza puanlarını kontrol eder ve rezervasyon butonlarını pasif yapar."""
        if penalty_points > 10:
            messagebox.showwarning(
                "Ceza Puanı Uyarısı",
                f"Ceza puanınız ({penalty_points}) 10'u aştığı için rezervasyon yapamazsınız. Lütfen ceza puanınızı düşürmek için yönetim ile iletişime geçin."
            )
            self.table_reservation_button.configure(state="disabled")
            self.book_reservation_button.configure(state="disabled")
        else:
            self.table_reservation_button.configure(state="normal")
            self.book_reservation_button.configure(state="normal")


# --- Ana Programı Çalıştırma ---
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = App()
    app.mainloop()
