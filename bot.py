# -*- coding: utf-8 -*-
"""
TELEGRAM-БОТ САЛОНА КРАСОТЫ - РАСШИРЕННАЯ ВЕРСИЯ С АДМИН-УПРАВЛЕНИЕМ
Добавлена возможность управления мастерами и услугами через бот
"""

import asyncio
import logging
import sys
import signal
from datetime import datetime, timedelta
from typing import Dict, List
import sqlite3

# Проверка библиотеки
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
    from telegram.error import NetworkError, TimedOut, TelegramError
    print("✅ Библиотека telegram найдена")
except ImportError:
    print("❌ Установите: pip install python-telegram-bot==20.3")
    sys.exit(1)

# Расширенная настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('salon_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ✅ ВАШ ТОКЕН
BOT_TOKEN = "8483702267:AAFgPjNjcx07qlDM47t43Ykt_2c7yIYdCMY"

print("🤖 ЗАПУСК РАСШИРЕННОЙ ВЕРСИИ БОТА С АДМИН-УПРАВЛЕНИЕМ")
print("🔑 Токен установлен")

# Состояния
class UserState:
    MAIN_MENU = "main_menu"
    SELECTING_SERVICE = "selecting_service"
    AWAITING_NAME = "awaiting_name"
    AWAITING_PHONE = "awaiting_phone"
    # Новые состояния для управления
    ADDING_MASTER = "adding_master"
    ADDING_MASTER_SERVICE = "adding_master_service"
    ADDING_SERVICE = "adding_service"
    ADDING_SERVICE_ITEMS = "adding_service_items"
    ADDING_SERVICE_DURATION = "adding_service_duration"

# Настройки салона (используются для инициализации)
SERVICES = {
    "nails": {
        "name": "💅 Ногтевой сервис",
        "services": ["Маникюр - 1500₽", "Педикюр - 2000₽", "Гель-лак - 1200₽"],
        "duration": 90
    },
    "hair": {
        "name": "💇‍♀️ Парикмахерские услуги", 
        "services": ["Стрижка женская - 2500₽", "Окрашивание - 4500₽", "Укладка - 1500₽"],
        "duration": 120
    },
    "makeup": {
        "name": "💄 Перманентный макияж",
        "services": ["Брови - 8000₽", "Губы - 12000₽", "Веки - 10000₽"],
        "duration": 150
    }
}

MASTERS = {
    "nails": ["Анна Иванова", "Мария Петрова"],
    "hair": ["Елена Сидорова", "Ольга Козлова"],
    "makeup": ["Светлана Николаева"]
}

WORK_HOURS = list(range(9, 19))

SALON_INFO = {
    "name": "Салон красоты 'Элеганс'",
    "phone": "+7 (999) 123-45-67", 
    "address": "ул. Красоты, дом 10"
}

# ============ АДМИНИСТРАТОРЫ ============
ADMIN_IDS = [
    412594355, 1360974844, 930316589
]

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS

print(f"👑 Настроено администраторов: {len(ADMIN_IDS)}")

class Database:
    def __init__(self):
        self.init_db()
        logger.info("💾 База данных инициализирована")
    
    def init_db(self):
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    service_type TEXT,
                    master TEXT,
                    appointment_date TEXT,
                    appointment_time TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для услуг
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_key TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    service_items TEXT NOT NULL,
                    duration INTEGER DEFAULT 90,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для мастеров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS masters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    master_name TEXT NOT NULL,
                    service_key TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(master_name, service_key)
                )
            ''')
            
            # Инициализация данных из глобальных переменных (если таблицы пустые)
            cursor.execute('SELECT COUNT(*) FROM services')
            if cursor.fetchone()[0] == 0:
                self._init_default_services(cursor)
            
            cursor.execute('SELECT COUNT(*) FROM masters')
            if cursor.fetchone()[0] == 0:
                self._init_default_masters(cursor)
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    def _init_default_services(self, cursor):
        """Инициализация услуг из SERVICES"""
        for key, service_data in SERVICES.items():
            service_items = '\n'.join(service_data['services'])
            cursor.execute('''
                INSERT INTO services (service_key, service_name, service_items, duration)
                VALUES (?, ?, ?, ?)
            ''', (key, service_data['name'], service_items, service_data['duration']))
        logger.info("✅ Услуги инициализированы из конфигурации")
    
    def _init_default_masters(self, cursor):
        """Инициализация мастеров из MASTERS"""
        for service_key, masters_list in MASTERS.items():
            for master_name in masters_list:
                cursor.execute('''
                    INSERT INTO masters (master_name, service_key)
                    VALUES (?, ?)
                ''', (master_name, service_key))
        logger.info("✅ Мастера инициализированы из конфигурации")
    
    # ============ МЕТОДЫ ДЛЯ УПРАВЛЕНИЯ УСЛУГАМИ ============
    
    def get_all_services(self) -> List[Dict]:
        """Получить все активные услуги"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM services WHERE is_active = 1')
            services = cursor.fetchall()
            conn.close()
            
            result = []
            for service in services:
                result.append({
                    'id': service[0],
                    'key': service[1],
                    'name': service[2],
                    'items': service[3],
                    'duration': service[4]
                })
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения услуг: {e}")
            return []
    
    def add_service(self, service_key: str, service_name: str, service_items: str, duration: int):
        """Добавить новую услугу"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO services (service_key, service_name, service_items, duration)
                VALUES (?, ?, ?, ?)
            ''', (service_key, service_name, service_items, duration))
            conn.commit()
            conn.close()
            logger.info(f"✅ Услуга добавлена: {service_name}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ Услуга с ключом {service_key} уже существует")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления услуги: {e}")
            return False
    
    def delete_service(self, service_key: str):
        """Удалить услугу (деактивировать)"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE services SET is_active = 0 WHERE service_key = ?', (service_key,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Услуга деактивирована: {service_key}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления услуги: {e}")
            return False
    
    # ============ МЕТОДЫ ДЛЯ УПРАВЛЕНИЯ МАСТЕРАМИ ============
    
    def get_all_masters(self) -> List[Dict]:
        """Получить всех активных мастеров"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.id, m.master_name, m.service_key, s.service_name
                FROM masters m
                LEFT JOIN services s ON m.service_key = s.service_key
                WHERE m.is_active = 1
                ORDER BY m.service_key, m.master_name
            ''')
            masters = cursor.fetchall()
            conn.close()
            
            result = []
            for master in masters:
                result.append({
                    'id': master[0],
                    'name': master[1],
                    'service_key': master[2],
                    'service_name': master[3] or 'Неизвестная услуга'
                })
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения мастеров: {e}")
            return []
    
    def get_masters_by_service(self, service_key: str) -> List[str]:
        """Получить мастеров по типу услуги"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT master_name FROM masters 
                WHERE service_key = ? AND is_active = 1
            ''', (service_key,))
            masters = cursor.fetchall()
            conn.close()
            return [m[0] for m in masters]
        except Exception as e:
            logger.error(f"❌ Ошибка получения мастеров услуги: {e}")
            return []
    
    def add_master(self, master_name: str, service_key: str):
        """Добавить нового мастера"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO masters (master_name, service_key)
                VALUES (?, ?)
            ''', (master_name, service_key))
            conn.commit()
            conn.close()
            logger.info(f"✅ Мастер добавлен: {master_name} ({service_key})")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ Мастер {master_name} уже работает с услугой {service_key}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления мастера: {e}")
            return False
    
    def delete_master(self, master_id: int):
        """Удалить мастера (деактивировать)"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE masters SET is_active = 0 WHERE id = ?', (master_id,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Мастер деактивирован: ID {master_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления мастера: {e}")
            return False
    
    # ============ СУЩЕСТВУЮЩИЕ МЕТОДЫ ============
    
    def is_user_registered(self, user_id: int) -> bool:
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки пользователя: {e}")
            return False
    
    def register_user(self, user_id: int, name: str, phone: str):
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO users (user_id, name, phone) VALUES (?, ?, ?)',
                (user_id, name, phone)
            )
            conn.commit()
            conn.close()
            logger.info(f"👤 Зарегистрирован: {name} (ID: {user_id})")
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации пользователя: {e}")
    
    def create_appointment(self, user_id: int, service_type: str, master: str, date: str, time: str):
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO appointments (user_id, service_type, master, appointment_date, appointment_time) VALUES (?, ?, ?, ?, ?)',
                (user_id, service_type, master, date, time)
            )
            conn.commit()
            conn.close()
            logger.info(f"📅 Запись создана: {date} {time} для пользователя {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания записи: {e}")
    
    def get_user_appointments(self, user_id: int) -> List[Dict]:
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute(
                'SELECT service_type, master, appointment_date, appointment_time FROM appointments WHERE user_id = ? AND status = "active"',
                (user_id,)
            )
            appointments = cursor.fetchall()
            conn.close()
            
            result = []
            for apt in appointments:
                result.append({
                    'service_type': apt[0],
                    'master': apt[1],
                    'date': apt[2],
                    'time': apt[3]
                })
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения записей: {e}")
            return []
    
    def is_time_available(self, master: str, date: str, time: str) -> bool:
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id FROM appointments WHERE master = ? AND appointment_date = ? AND appointment_time = ? AND status = "active"',
                (master, date, time)
            )
            result = cursor.fetchone()
            conn.close()
            return result is None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки доступности времени: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """Получить статистику салона (для админа)"""
        try:
            conn = sqlite3.connect('salon_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM appointments WHERE status = "active"')
            active_appointments = cursor.fetchone()[0]
            
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status = "active"', (today,))
            today_appointments = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM appointments')
            total_appointments = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_users': total_users,
                'active_appointments': active_appointments,
                'today_appointments': today_appointments,
                'total_appointments': total_appointments
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                'total_users': 0,
                'active_appointments': 0,
                'today_appointments': 0,
                'total_appointments': 0
            }

# Глобальные переменные
db = Database()
user_states = {}
user_data = {}

class SalonBot:
    def __init__(self):
        self.application = (
            Application.builder()
            .token(BOT_TOKEN)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(30.0)
            .get_updates_read_timeout(42.0)
            .build()
        )
        self.setup_handlers()
        self.running = False
        logger.info("⚙️ Обработчики настроены")
    
    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_error_handler(self.error_handler)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"❌ Ошибка при обработке обновления: {context.error}")
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "😔 Произошла ошибка. Попробуйте еще раз или используйте /start"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения об ошибке: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        try:
            user_id = update.effective_user.id
            username = update.effective_user.first_name or "Гость"
            user_states[user_id] = UserState.MAIN_MENU
            
            admin_badge = " 👑" if is_admin(user_id) else ""
            
            logger.info(f"👋 Пользователь: {username} (ID: {user_id}){admin_badge}")
            
            welcome_text = (
                f"👋 Добро пожаловать в {SALON_INFO['name']}, {username}!{admin_badge}\n\n"
                f"🌟 Я помогу вам:\n"
                f"📅 Записаться на процедуру\n"
                f"📋 Узнать цены\n"
                f"👩‍💻 Познакомиться с мастерами\n\n"
                f"📍 {SALON_INFO['address']}\n"
                f"📞 {SALON_INFO['phone']}\n\n"
                f"Что вас интересует?"
            )
            
            keyboard = [
                [InlineKeyboardButton("📅 Записаться", callback_data="book")],
                [InlineKeyboardButton("📋 Услуги и цены", callback_data="services")],
                [InlineKeyboardButton("👩‍💻 Наши мастера", callback_data="masters")],
                [InlineKeyboardButton("🎯 Акции", callback_data="promotions")],
                [InlineKeyboardButton("📱 Мои записи", callback_data="my_bookings")]
            ]
            
            if is_admin(user_id):
                keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"❌ Ошибка в start_command: {e}")
            await update.message.reply_text("😔 Произошла ошибка. Попробуйте еще раз: /start")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        logger.info(f"📘 Кнопка: {data} от пользователя {user_id}")
        
        try:
            if data == "services":
                await self.show_services(query)
            elif data == "book":
                await self.start_booking(query)
            elif data == "masters":
                await self.show_masters(query)
            elif data == "promotions":
                await self.show_promotions(query)
            elif data == "my_bookings":
                await self.show_user_bookings(query)
            elif data == "admin_panel":
                if is_admin(user_id):
                    await self.show_admin_panel(query)
                else:
                    await query.answer("❌ У вас нет доступа к админ-панели", show_alert=True)
            # Новые админ-обработчики
            elif data == "admin_manage_services":
                if is_admin(user_id):
                    await self.show_services_management(query)
            elif data == "admin_manage_masters":
                if is_admin(user_id):
                    await self.show_masters_management(query)
            elif data == "admin_add_service":
                if is_admin(user_id):
                    await self.start_add_service(query)
            elif data == "admin_add_master":
                if is_admin(user_id):
                    await self.start_add_master(query)
            elif data.startswith("admin_delete_service_"):
                if is_admin(user_id):
                    service_key = data.replace("admin_delete_service_", "")
                    await self.delete_service(query, service_key)
            elif data.startswith("admin_delete_master_"):
                if is_admin(user_id):
                    master_id = int(data.replace("admin_delete_master_", ""))
                    await self.delete_master(query, master_id)
            elif data.startswith("admin_add_master_service_"):
                if is_admin(user_id):
                    service_key = data.replace("admin_add_master_service_", "")
                    # Инициализация user_data если нет
                    if user_id not in user_data:
                        user_data[user_id] = {}
                    user_data[user_id]['new_master_service'] = service_key
                    user_states[user_id] = UserState.ADDING_MASTER
                    text = f"👤 **Добавление мастера**\n\nНапишите имя мастера:"
                    await query.edit_message_text(text, parse_mode='Markdown')
            elif data.startswith("service_"):
                await self.select_service(query, data)
            elif data.startswith("date_"):
                await self.select_date(query, data)
            elif data.startswith("time_"):
                await self.select_time(query, data)
            elif data == "back_to_menu":
                await self.back_to_main_menu(query)
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_callback: {e}")
            await query.message.reply_text("😔 Произошла ошибка. Попробуйте еще раз: /start")
    
    # ============ НОВЫЕ АДМИН-МЕТОДЫ ============
    
    async def show_admin_panel(self, query):
        """Главное меню админ-панели"""
        try:
            text = (
                f"👑 **АДМИН-ПАНЕЛЬ**\n"
                f"{SALON_INFO['name']}\n\n"
                f"Выберите действие:"
            )
            
            keyboard = [
                [InlineKeyboardButton("👥 Управление мастерами", callback_data="admin_manage_masters")],
                [InlineKeyboardButton("💅 Управление услугами", callback_data="admin_manage_services")],
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_admin_panel: {e}")
    
    async def show_services_management(self, query):
        """Управление услугами"""
        try:
            services = db.get_all_services()
            
            text = f"💅 **УПРАВЛЕНИЕ УСЛУГАМИ**\n\nВсего услуг: {len(services)}\n\n"
            
            if services:
                for service in services:
                    text += f"▪️ **{service['name']}**\n"
                    text += f"   Ключ: `{service['key']}`\n"
                    text += f"   Длительность: {service['duration']} мин\n\n"
            else:
                text += "❌ Услуг пока нет"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить услугу", callback_data="admin_add_service")]
            ]
            
            # Кнопки удаления
            for service in services:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 Удалить: {service['name']}", 
                        callback_data=f"admin_delete_service_{service['key']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_services_management: {e}")
    
    async def show_masters_management(self, query):
        """Управление мастерами"""
        try:
            masters = db.get_all_masters()
            
            text = f"👥 **УПРАВЛЕНИЕ МАСТЕРАМИ**\n\nВсего мастеров: {len(masters)}\n\n"
            
            if masters:
                current_service = None
                for master in masters:
                    if current_service != master['service_name']:
                        current_service = master['service_name']
                        text += f"\n**{current_service}:**\n"
                    text += f"▪️ {master['name']}\n"
            else:
                text += "❌ Мастеров пока нет"
            
            keyboard = []
            
            # Кнопки добавления по услугам
            services = db.get_all_services()
            for service in services:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ Добавить в: {service['name']}", 
                        callback_data=f"admin_add_master_service_{service['key']}"
                    )
                ])
            
            # Кнопки удаления
            for master in masters:
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑 Удалить: {master['name']}", 
                        callback_data=f"admin_delete_master_{master['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_masters_management: {e}")
    
    async def start_add_service(self, query):
        """Начать добавление услуги"""
        user_id = query.from_user.id
        user_states[user_id] = UserState.ADDING_SERVICE
        # Инициализация user_data если нет
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['adding_service'] = {}
        
        text = (
            f"💅 **Добавление новой услуги**\n\n"
            f"Шаг 1 из 4: Введите ключ услуги\n"
            f"(например: `nails`, `hair`, `massage`)\n\n"
            f"Ключ должен быть уникальным, на английском, без пробелов"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    async def start_add_master(self, query):
        """Начать добавление мастера (выбор услуги уже произошел)"""
        # Состояние устанавливается в обработчике callback admin_add_master_service_
        pass
    
    async def delete_service(self, query, service_key):
        """Удалить услугу"""
        try:
            success = db.delete_service(service_key)
            
            if success:
                text = f"✅ Услуга успешно удалена: {service_key}"
            else:
                text = f"❌ Ошибка удаления услуги"
            
            keyboard = [[InlineKeyboardButton("🔙 Управление услугами", callback_data="admin_manage_services")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"❌ Ошибка в delete_service: {e}")
    
    async def delete_master(self, query, master_id):
        """Удалить мастера"""
        try:
            success = db.delete_master(master_id)
            
            if success:
                text = f"✅ Мастер успешно удален"
            else:
                text = f"❌ Ошибка удаления мастера"
            
            keyboard = [[InlineKeyboardButton("🔙 Управление мастерами", callback_data="admin_manage_masters")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"❌ Ошибка в delete_master: {e}")
    
    # ============ СУЩЕСТВУЮЩИЕ МЕТОДЫ (укороченные для экономии места) ============
    
    async def show_services(self, query):
        """Показать услуги"""
        try:
            services = db.get_all_services()
            text = f"📋 **Услуги {SALON_INFO['name']}**\n\n"
            
            for service in services:
                text += f"**{service['name']}**\n"
                for item in service['items'].split('\n'):
                    text += f"• {item}\n"
                text += f"⏱ {service['duration']} мин\n\n"
            
            text += f"📞 {SALON_INFO['phone']}\n"
            text += f"📍 {SALON_INFO['address']}"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_services: {e}")
    
    async def start_booking(self, query):
        """Начать процесс записи"""
        try:
            user_id = query.from_user.id
            user_states[user_id] = UserState.SELECTING_SERVICE
            
            services = db.get_all_services()
            text = "📅 **Выберите услугу:**"
            
            keyboard = []
            for service in services:
                keyboard.append([InlineKeyboardButton(
                    service['name'], 
                    callback_data=f"service_{service['key']}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в start_booking: {e}")
    
    async def select_service(self, query, callback_data):
        """Выбор услуги и отображение дат"""
        try:
            user_id = query.from_user.id
            service_key = callback_data.replace("service_", "")
            
            if user_id not in user_data:
                user_data[user_id] = {}
            user_data[user_id]['service_type'] = service_key
            
            # Получаем услугу из БД
            services = db.get_all_services()
            service_info = next((s for s in services if s['key'] == service_key), None)
            
            if not service_info:
                await query.answer("❌ Услуга не найдена", show_alert=True)
                return
            
            text = f"**{service_info['name']}**\n\n"
            for item in service_info['items'].split('\n'):
                text += f"• {item}\n"
            text += f"\n⏱ {service_info['duration']} мин\n\n"
            
            # Генерация дат
            available_dates = []
            for i in range(1, 8):
                date = datetime.now() + timedelta(days=i)
                if date.weekday() < 6:
                    available_dates.append(date)
            
            if available_dates:
                text += "📅 **Выберите дату:**"
                keyboard = []
                for date in available_dates:
                    date_str = date.strftime("%Y-%m-%d")
                    date_display = date.strftime("%d.%m (%a)")
                    days = {'Mon': 'Пн', 'Tue': 'Вт', 'Wed': 'Ср', 'Thu': 'Чт', 'Fri': 'Пт', 'Sat': 'Сб'}
                    for eng, rus in days.items():
                        date_display = date_display.replace(eng, rus)
                    keyboard.append([InlineKeyboardButton(date_display, callback_data=f"date_{date_str}")])
                
                keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="book")])
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                text += "❌ **Нет дат**"
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в select_service: {e}")
    
    async def select_date(self, query, callback_data):
        """Выбор даты и отображение времени"""
        try:
            user_id = query.from_user.id
            selected_date = callback_data.replace("date_", "")
            user_data[user_id]['date'] = selected_date
            
            service_type = user_data[user_id]['service_type']
            masters = db.get_masters_by_service(service_type)
            
            date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            
            text = f"📅 **{formatted_date}**\n⏰ **Выберите время:**"
            
            keyboard = []
            for hour in WORK_HOURS:
                time_str = f"{hour:02d}:00"
                available = any(db.is_time_available(master, selected_date, time_str) for master in masters)
                if available:
                    keyboard.append([InlineKeyboardButton(time_str, callback_data=f"time_{time_str}")])
            
            if keyboard:
                keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"service_{service_type}")])
            else:
                text += "\n❌ **Нет времени**"
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"service_{service_type}")]]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в select_date: {e}")
    
    async def select_time(self, query, callback_data):
        """Выбор времени"""
        try:
            user_id = query.from_user.id
            selected_time = callback_data.replace("time_", "")
            user_data[user_id]['time'] = selected_time
            
            if not db.is_user_registered(user_id):
                user_states[user_id] = UserState.AWAITING_NAME
                
                text = (
                    f"📝 **Для записи нужна регистрация**\n\n"
                    f"👤 Введите ваше имя:"
                )
                await query.edit_message_text(text, parse_mode='Markdown')
            else:
                await self.confirm_booking(query)
        except Exception as e:
            logger.error(f"❌ Ошибка в select_time: {e}")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        try:
            user_id = update.effective_user.id
            text = update.message.text
            
            if user_id not in user_states:
                await self.start_command(update, context)
                return
            
            state = user_states[user_id]
            
            if state == UserState.AWAITING_NAME:
                user_data[user_id]['name'] = text.strip()
                user_states[user_id] = UserState.AWAITING_PHONE
                
                await update.message.reply_text(f"👍 Приятно познакомиться, {text}!\n📞 Введите номер телефона:")
            
            elif state == UserState.AWAITING_PHONE:
                user_data[user_id]['phone'] = text.strip()
                
                db.register_user(user_id, user_data[user_id]['name'], user_data[user_id]['phone'])
                await self.complete_booking(update)
            
            # Новые состояния для админа
            elif state == UserState.ADDING_SERVICE:
                await self.process_add_service(update, text)
            
            elif state == UserState.ADDING_SERVICE_ITEMS:
                await self.process_add_service_items(update, text)
            
            elif state == UserState.ADDING_SERVICE_DURATION:
                await self.process_add_service_duration(update, text)
            
            elif state == UserState.ADDING_MASTER:
                await self.process_add_master(update, text)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_text: {e}")
    
    async def process_add_service(self, update, text):
        """Обработка добавления услуги - шаг 1 (ключ)"""
        user_id = update.effective_user.id
        service_key = text.strip().lower().replace(' ', '_')
        
        user_data[user_id]['adding_service']['key'] = service_key
        
        reply_text = (
            f"💅 **Добавление новой услуги**\n\n"
            f"Ключ: `{service_key}`\n\n"
            f"Шаг 2 из 4: Введите название услуги\n"
            f"(например: 💅 Ногтевой сервис)"
        )
        
        await update.message.reply_text(reply_text, parse_mode='Markdown')
        
        # Переходим к следующему шагу (название)
        user_data[user_id]['adding_service_step'] = 'name'
    
    async def process_add_service_items(self, update, text):
        """Обработка добавления услуги - шаг 2 (название)"""
        user_id = update.effective_user.id
        
        if 'adding_service_step' in user_data[user_id] and user_data[user_id]['adding_service_step'] == 'name':
            service_name = text.strip()
            user_data[user_id]['adding_service']['name'] = service_name
            user_data[user_id]['adding_service_step'] = 'items'
            user_states[user_id] = UserState.ADDING_SERVICE_ITEMS
            
            reply_text = (
                f"💅 **Добавление новой услуги**\n\n"
                f"Название: {service_name}\n\n"
                f"Шаг 3 из 4: Введите список услуг и цены\n"
                f"(каждая услуга с новой строки, например:\n"
                f"Маникюр - 1500₽\n"
                f"Педикюр - 2000₽)"
            )
            
            await update.message.reply_text(reply_text, parse_mode='Markdown')
        
        elif user_states[user_id] == UserState.ADDING_SERVICE_ITEMS:
            service_items = text.strip()
            user_data[user_id]['adding_service']['items'] = service_items
            user_states[user_id] = UserState.ADDING_SERVICE_DURATION
            
            reply_text = (
                f"💅 **Добавление новой услуги**\n\n"
                f"Услуги добавлены\n\n"
                f"Шаг 4 из 4: Введите длительность процедуры (в минутах)\n"
                f"(например: 90)"
            )
            
            await update.message.reply_text(reply_text, parse_mode='Markdown')
    
    async def process_add_service_duration(self, update, text):
        """Обработка добавления услуги - шаг 3 (длительность)"""
        user_id = update.effective_user.id
        
        try:
            duration = int(text.strip())
            
            service_data = user_data[user_id]['adding_service']
            success = db.add_service(
                service_data['key'],
                service_data['name'],
                service_data['items'],
                duration
            )
            
            if success:
                reply_text = (
                    f"✅ **Услуга успешно добавлена!**\n\n"
                    f"**{service_data['name']}**\n"
                    f"Ключ: `{service_data['key']}`\n"
                    f"Длительность: {duration} мин\n\n"
                    f"Используйте /start для возврата в главное меню"
                )
            else:
                reply_text = (
                    f"❌ **Ошибка добавления услуги**\n\n"
                    f"Возможно, услуга с таким ключом уже существует.\n"
                    f"Используйте /start для возврата"
                )
            
            await update.message.reply_text(reply_text, parse_mode='Markdown')
            
            # Очистка состояния
            user_states[user_id] = UserState.MAIN_MENU
            if 'adding_service' in user_data[user_id]:
                del user_data[user_id]['adding_service']
            if 'adding_service_step' in user_data[user_id]:
                del user_data[user_id]['adding_service_step']
                
        except ValueError:
            await update.message.reply_text(
                "❌ Введите корректное число (количество минут)"
            )
    
    async def process_add_master(self, update, text):
        """Обработка добавления мастера"""
        user_id = update.effective_user.id
        master_name = text.strip()
        service_key = user_data[user_id].get('new_master_service')
        
        if not service_key:
            await update.message.reply_text(
                "❌ Ошибка: не выбрана услуга. Используйте /start"
            )
            return
        
        success = db.add_master(master_name, service_key)
        
        if success:
            reply_text = (
                f"✅ **Мастер успешно добавлен!**\n\n"
                f"👤 {master_name}\n"
                f"Услуга: {service_key}\n\n"
                f"Используйте /start для возврата в главное меню"
            )
        else:
            reply_text = (
                f"❌ **Ошибка добавления мастера**\n\n"
                f"Возможно, такой мастер уже работает с этой услугой.\n"
                f"Используйте /start для возврата"
            )
        
        await update.message.reply_text(reply_text, parse_mode='Markdown')
        
        # Очистка состояния
        user_states[user_id] = UserState.MAIN_MENU
        if 'new_master_service' in user_data[user_id]:
            del user_data[user_id]['new_master_service']
    
    async def confirm_booking(self, query):
        """Подтверждение записи для зарегистрированного пользователя"""
        try:
            user_id = query.from_user.id
            await self._finalize_booking(user_id, query)
        except Exception as e:
            logger.error(f"❌ Ошибка в confirm_booking: {e}")
    
    async def complete_booking(self, update):
        """Завершение записи для нового пользователя"""
        try:
            user_id = update.effective_user.id
            await self._finalize_booking(user_id, update)
            user_states[user_id] = UserState.MAIN_MENU
        except Exception as e:
            logger.error(f"❌ Ошибка в complete_booking: {e}")
    
    async def _finalize_booking(self, user_id, update_or_query):
        """Финализация записи"""
        try:
            service_type = user_data[user_id]['service_type']
            date = user_data[user_id]['date']
            time = user_data[user_id]['time']
            
            masters = db.get_masters_by_service(service_type)
            available_master = None
            for master in masters:
                if db.is_time_available(master, date, time):
                    available_master = master
                    break
            
            if available_master:
                db.create_appointment(user_id, service_type, available_master, date, time)
                
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d.%m.%Y")
                
                # Получаем название услуги
                services = db.get_all_services()
                service_info = next((s for s in services if s['key'] == service_type), None)
                service_name = service_info['name'] if service_info else service_type
                
                text = (
                    f"🎉 **ЗАПИСЬ ПОДТВЕРЖДЕНА!**\n\n"
                    f"📅 Дата: {formatted_date}\n"
                    f"⏰ Время: {time}\n"
                    f"👩‍💻 Мастер: {available_master}\n"
                    f"💅 Услуга: {service_name}\n\n"
                    f"📍 {SALON_INFO['address']}\n"
                    f"📞 {SALON_INFO['phone']}\n\n"
                    f"✨ Ждем вас!"
                )
            else:
                text = "😔 Время занято. Выберите другое."
            
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update_or_query, 'edit_message_text'):
                await update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в _finalize_booking: {e}")
    
    async def show_masters(self, query):
        """Показать информацию о мастерах"""
        try:
            masters = db.get_all_masters()
            text = f"👩‍💻 **Мастера {SALON_INFO['name']}:**\n\n"
            
            if masters:
                current_service = None
                for master in masters:
                    if current_service != master['service_name']:
                        current_service = master['service_name']
                        text += f"\n**{current_service}:**\n"
                    text += f"• {master['name']}\n"
            else:
                text += "❌ Мастеров пока нет"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_masters: {e}")
    
    async def show_promotions(self, query):
        """Показать акции"""
        try:
            text = (
                f"🎯 **Акции {SALON_INFO['name']}:**\n\n"
                f"🌟 Скидка 20% на первое посещение\n"
                f"💅 Маникюр + педикюр = скидка 15%\n"
                f"👯‍♀️ Приведи подругу - скидка 10%\n"
                f"🎂 В день рождения - скидка 25%\n\n"
                f"📞 Подробности: {SALON_INFO['phone']}"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_promotions: {e}")
    
    async def show_user_bookings(self, query):
        """Показать записи пользователя"""
        try:
            user_id = query.from_user.id
            appointments = db.get_user_appointments(user_id)
            
            if appointments:
                text = "📱 **Ваши записи:**\n\n"
                
                # Получаем все услуги для сопоставления
                services = db.get_all_services()
                services_dict = {s['key']: s['name'] for s in services}
                
                for apt in appointments:
                    service_name = services_dict.get(apt['service_type'], apt['service_type'])
                    date_obj = datetime.strptime(apt['date'], "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                    
                    text += f"• {service_name}\n"
                    text += f"📅 {formatted_date} в {apt['time']}\n"
                    text += f"👩‍💻 {apt['master']}\n\n"
                
                text += f"📞 Для изменения: {SALON_INFO['phone']}"
            else:
                text = "📱 У вас нет записей\n\n📅 Хотите записаться?"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в show_user_bookings: {e}")
    
    async def back_to_main_menu(self, query):
        """Возврат в главное меню"""
        try:
            user_id = query.from_user.id
            user_states[user_id] = UserState.MAIN_MENU
            
            admin_badge = " 👑" if is_admin(user_id) else ""
            
            text = f"🏠 **Главное меню {SALON_INFO['name']}**{admin_badge}\n\nВыберите действие:"
            
            keyboard = [
                [InlineKeyboardButton("📅 Записаться", callback_data="book")],
                [InlineKeyboardButton("📋 Услуги и цены", callback_data="services")],
                [InlineKeyboardButton("👩‍💻 Наши мастера", callback_data="masters")],
                [InlineKeyboardButton("🎯 Акции", callback_data="promotions")],
                [InlineKeyboardButton("📱 Мои записи", callback_data="my_bookings")]
            ]
            
            if is_admin(user_id):
                keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"❌ Ошибка в back_to_main_menu: {e}")
    
    async def shutdown(self):
        """Корректное завершение работы бота"""
        logger.info("ℹ️ Начало корректного завершения работы...")
        self.running = False
        
        try:
            await self.application.stop()
            await self.application.shutdown()
            logger.info("✅ Бот корректно остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке бота: {e}")
    
    def run(self):
        """Запуск бота с обработкой ошибок"""
        self.running = True
        
        def signal_handler(signum, frame):
            logger.info(f"🛑 Получен сигнал {signum}, завершение работы...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("🤖 БОТ ЗАПУЩЕН С АДМИН-УПРАВЛЕНИЕМ!")
        logger.info("📱 Проверьте бота в Telegram")
        logger.info("📊 Логи сохраняются в salon_bot.log")
        logger.info("👑 Администраторов: " + str(len(ADMIN_IDS)))
        logger.info("🔄 Для остановки: Ctrl+C")
        
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                self.application.run_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                    stop_signals=None
                )
                break
                
            except (NetworkError, TimedOut) as e:
                retry_count += 1
                logger.warning(f"🔄 Сетевая ошибка (попытка {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    wait_time = min(30 * retry_count, 300)
                    logger.info(f"⏳ Переподключение через {wait_time} секунд...")
                    asyncio.run(asyncio.sleep(wait_time))
                else:
                    logger.error("❌ Превышено максимальное количество попыток переподключения")
                    break
                    
            except KeyboardInterrupt:
                logger.info("⌨️ Получен Ctrl+C, завершение работы...")
                break
                
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка: {e}")
                retry_count += 1
                
                if retry_count < max_retries:
                    wait_time = 30
                    logger.info(f"⏳ Перезапуск через {wait_time} секунд...")
                    asyncio.run(asyncio.sleep(wait_time))
                else:
                    logger.error("❌ Превышено максимальное количество попыток переподключения")
                    break

def main():
    """Главная функция запуска"""
    try:
        logger.info("🎯 Инициализация бота с админ-управлением...")
        bot = SalonBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("\nℹ️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        logger.info("👋 Завершение работы программы")

if __name__ == '__main__':
    print("🚀 ЗАПУСК БОТА С АДМИН-УПРАВЛЕНИЕМ...")
    print("=" * 50)
    main()
