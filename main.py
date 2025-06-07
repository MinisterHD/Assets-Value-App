from PySide6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem
from ui_mainwindow import Ui_MainWindow
from farabi_scrap import scrape_with_requests
import plotly.graph_objects as go

import sys

from PySide6.QtCore import QSettings

class MyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.settings = QSettings("YourCompany", "YourAppName")
        self.load_inputs()
        self.ui.pushButton.clicked.connect(self.convert)

    def load_inputs(self):
        self.ui.lineEdit.setText(self.settings.value("18gold", ""))
        self.ui.lineEdit_2.setText(self.settings.value("firouze", ""))
        self.ui.lineEdit_3.setText(self.settings.value("exir", ""))
        self.ui.lineEdit_4.setText(self.settings.value("usd", ""))

    def save_inputs(self):
        self.settings.setValue("18gold", self.ui.lineEdit.text())
        self.settings.setValue("firouze", self.ui.lineEdit_2.text())
        self.settings.setValue("exir", self.ui.lineEdit_3.text())
        self.settings.setValue("usd", self.ui.lineEdit_4.text())


    def convert(self):
        self.save_inputs()
        try:
            amount_18gold = float(self.ui.lineEdit.text() or 0)
        except Exception:
            amount_18gold = 0
        try:
            amount_firouze = float(self.ui.lineEdit_2.text() or 0)
        except Exception:
            amount_firouze = 0
        try:
            amount_exir = float(self.ui.lineEdit_3.text() or 0)
        except Exception:
            amount_exir = 0
        try:
            amount_usd = float(self.ui.lineEdit_4.text() or 0)
        except Exception:
            amount_usd = 0

        prices_list = scrape_with_requests()
        # prices_list: [exir, firouze, 18gold, usd]

        value_exir = amount_exir * prices_list[0]
        value_firouze = amount_firouze * prices_list[1]
        value_18gold = amount_18gold * prices_list[2]
        value_usd = amount_usd * prices_list[3]

        total_rials = value_exir + value_firouze + value_18gold + value_usd

        total_usd = total_rials / prices_list[3] if prices_list[3] else 0


        self.ui.tableWidget.setItem(0, 0, QTableWidgetItem(str(value_usd)))
        self.ui.tableWidget.setItem(0, 1, QTableWidgetItem(str(value_firouze)))
        self.ui.tableWidget.setItem(0, 2, QTableWidgetItem(str(value_exir)))
        self.ui.tableWidget.setItem(0, 3, QTableWidgetItem(str(total_rials)))
        self.ui.tableWidget.setItem(0, 4, QTableWidgetItem(str(total_usd)))

        values = [value_18gold, value_firouze, value_exir, value_usd]
        labels = ["18Gold", "Firouze", "Exir", "USD"]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.3)])
        html = fig.to_html(include_plotlyjs='cdn')
        self.ui.WebEngineView.setHtml(html)


app = QApplication(sys.argv)
window = MyApp()
window.show()
sys.exit(app.exec())
