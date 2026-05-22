"""Launch the Task One Target Localization desktop application."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from task_one_localizer.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Task One Target Localization")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
