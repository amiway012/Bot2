from aiogram.fsm.state import State, StatesGroup


class CaptchaStates(StatesGroup):
    captcha = State()


class UserStates(StatesGroup):
    greeting = State()


class AdminStates(StatesGroup):
    name = State()
    loading = State()
    wait_unblock = State()
    wait_unmute = State()
    wait_reply = State()
    wait_mute_custom = State()
