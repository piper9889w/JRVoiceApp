"""Reusable visual language for the first UI milestone."""

APP_STYLE = """
QMainWindow, QDialog { background: #0a1422; color: #e8f0ff; }
QWidget { font-family: Inter, Arial, sans-serif; font-size: 14px; }
QFrame#panel { background: #0d1a2a; border: 1px solid #1d3048; border-radius: 16px; }
QFrame#sidebar { background: #0b1727; border-right: 1px solid #1d3048; }
QLabel#brand { color: #eef4ff; font-size: 28px; font-weight: 700; }
QLabel#brandAccent { color: #2c83ff; font-size: 28px; font-weight: 700; }
QLabel#heading { font-size: 28px; font-weight: 700; }
QLabel#subtle { color: #9baeca; }
QLabel#online { color: #4ce29a; font-weight: 600; }
QLabel#section { font-size: 18px; font-weight: 700; }
QPushButton { color: #dbe8fb; background: #15243a; border: 1px solid #29415d; border-radius: 11px; padding: 10px 14px; }
QPushButton:hover { background: #203655; }
QPushButton:pressed { background: #122037; }
QPushButton#nav { text-align: left; border: 0; background: transparent; padding: 12px 18px; }
QPushButton#nav:checked { background: #15365f; color: #64a7ff; border-left: 3px solid #2c83ff; border-radius: 8px; }
QPushButton#dial { min-width: 68px; min-height: 56px; border-radius: 34px; font-size: 24px; font-weight: 600; background: #14243a; }
QPushButton#dial:hover { background: #203a5f; }
QPushButton#call { min-width: 85px; min-height: 62px; border: 0; border-radius: 37px; background: #1975f3; font-size: 27px; }
QPushButton#call:hover { background: #3186ff; }
QPushButton#end { background: #ed3157; border: 0; border-radius: 26px; font-size: 22px; }
QLineEdit { background: #0e1c2e; color: #edf4ff; border: 1px solid #2a405c; border-radius: 13px; padding: 14px 18px; font-size: 18px; }
QLineEdit:focus { border: 1px solid #3b8bff; }
QScrollArea { border: 0; background: transparent; }
QDialog { background: #0d1a2a; }
"""
