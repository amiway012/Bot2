from aiogram.fsm.state import State, StatesClass


class CaptchaStates(StatesClass):
    captcha = State()


class UserStates(StatesClass):
    greeting = State()


class AdminStates(StatesClass):
    name = State()
    loading = State()
    wait_unblock = State()
    wait_unmute = State()
    wait_reply = State()
    wait_mute_custom = State()