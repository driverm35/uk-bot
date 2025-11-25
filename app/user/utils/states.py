from aiogram.fsm.state import State, StatesGroup
from enum import Enum

# Состояния регистрации
class RegStates(StatesGroup):
    name = State()
    phone = State()
    street = State()
    house = State()
    apartment = State()

class EditProfile(StatesGroup):
    new_data = State()

class TicketStates(StatesGroup):
    waiting_text = State()
    preview = State()
    attachments = State()

class MeterStates(StatesGroup):
    waiting_reading = State()
    preview = State()

class AttachmentType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    VOICE = "voice"
    AUDIO = "audio"
    TEXT = "text"