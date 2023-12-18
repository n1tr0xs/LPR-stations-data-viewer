import sys
import os
import locale
import configparser
import datetime as dt
import traceback
from collections.abc import KeysView
from numbers import Number
from decimal import Decimal
import requests
import pyperclip
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt, pyqtSlot, QThreadPool, QObject, QRunnable, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QApplication, QGridLayout, QWidget, QPushButton, QLabel, QComboBox,\
     QTableWidget, QMenu, QTableWidgetItem, QDialog, QVBoxLayout

VERSION = '2.1'

locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
config = configparser.ConfigParser()
config.read('settings.ini', encoding='UTF-8')
wanted_unit = config['единицы']
convert_table = {
    'k': {
      'C': lambda x: x - Decimal('273.15'),
    },
    'pa': {
        'гПа': lambda x: x / 100,
    },
    'code table': {
        'кодовая таблица': lambda x: x,
    },
    'degree true': {
        '°': lambda x: x,
    },
    'kg m-2': {
        'мм': lambda x: x,
    },
    'm': {
        'м': lambda x: x,
    },
    'm/s': {
        'м/с': lambda x: x,
    },
    'min': {
        'мин': lambda x: x,
    }
}

def get_json(server: str, page: str, parameters: dict={}) -> list:
    '''
    Gets json from `server` using given `page` with given `parameters`.
    Returns list.

    :param page: The rest api page on server.
    :type page: string
    :param parameters: GET parameters for rest api page.
    :type parameters: dictionary
    :param server: Server base url.
    :type server: string
    '''
    url = f'{server}/{page}?'
    for k, v in parameters.items():
        url += f'{k}='
        if isinstance(v, (tuple, set, list, KeysView)):
            url += ','.join(map(str, v))
        else:
            url += str(v)
        url += '&'
    print(url)
    try:
        return requests.get(url, timeout=5).json()
    except (requests.exceptions.JSONDecodeError, ) as e:
        print(e)
        return []
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
        print(e)
        return []

def format_unit(value: Number, base: str, target: str, prec=None, table: dict=convert_table) -> str:
    '''
    Converts given value from unit to unit.
    Formats the result to string `value unit`.
    '''
    try:
        res = table[base][target](value)
    except KeyError:
        res = value
    if prec is not None:
        return f'{round(res, prec)}'
    return f'{res}'

class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.
    Supported signals are:
    '''
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal()

class Worker(QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function
    '''
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit()
        finally:
            self.signals.finished.emit()

class MainWindow(QMainWindow):
    keyPressed = pyqtSignal(int)

    def __init__(self):
        '''
        Creates main window.
        '''
        super().__init__()

        self.settings = QtCore.QSettings('n1tr0xs', 'sinop measurement view')
        self.threadpool = QThreadPool.globalInstance()
        self.meas_for_table = {}

        self.layout = QGridLayout()

        self.centralWidget = QWidget()
        self.centralWidget.setLayout(self.layout)
        self.setCentralWidget(self.centralWidget)
        self.timer_interval = 5 * 1000

        self.font = QtGui.QFont('Times New Roman', 12)
        self.table_header_font = QtGui.QFont('Times New Roman', 12, QtGui.QFont.Weight.Bold)
        self.setFont(self.font)
        self.setWindowTitle('Просмотр данных метеорологических станций ЛНР')
        self.setWindowIcon(QtGui.QIcon('icon.ico'))

        self.update_terms_btn = QPushButton('Обновить список сроков')
        self.update_terms_btn.clicked.connect(self.get_terms)
        self.layout.addWidget(self.update_terms_btn)

        self.label_term = QLabel('Срок:')
        self.label_term.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.layout.addWidget(self.label_term, 0, 1)

        self.term_box = QComboBox()
        self.layout.addWidget(self.term_box, 0, 2)

        self.label_last_update = QLabel('Последнее обновление:')
        self.label_last_update.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.layout.addWidget(self.label_last_update, 0, 3)

        self.table = QTableWidget()
        self.table.cellDoubleClicked.connect(lambda i, j: pyperclip.copy(self.table.item(i, j).text()))
        self.layout.addWidget(self.table, 1, 0, 1, 4)
        
        self.create_menu()
        self.get_servers()
        self.get_stations()
        self.get_measurements_types()
        self.set_headers()
        self.get_terms()
        self.term_box.currentIndexChanged.connect(self.create_worker)
        QtCore.QTimer.singleShot(0, self.create_worker)

        self.restore_settings()
        self.show()

    def create_menu(self):
        # Меню "Файл"
        file_menu = QMenu('Файл', self)
        # Выход
        exit_act = QtGui.QAction('Выход', self)
        exit_act.setStatusTip('Выход')
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Меню "Помощь"
        help_menu = QMenu('Помощь', self)
        # О приложении
        about_act = QtGui.QAction('О приложении', self)
        about_act.setStatusTip('О приложении')
        about_act.triggered.connect(self.show_help)
        help_menu.addAction(about_act)
        
        self.menuBar().addMenu(file_menu)
        self.menuBar().addMenu(help_menu)

    def show_help(self):
        try: HelpDialog(self).exec()
        except Exception as e: print(e)
        
    def create_worker(self):
        '''
        Creates and starts worker for info update.
        '''
        worker = Worker(self.update_data)
        self.threadpool.start(worker)

    def get_servers(self):
        '''
        Gets list of servers from `settings.ini`.
        '''
        print('getting servers...')
        self.servers = dict(config['сервера'])
        print(self.servers)
        print('servers received.')

    def get_stations(self):
        '''
        Gets station list from `settings.ini`.
        '''
        print('getting stations...')
        self.serv_stations = {}
        self.sidx_name = {}
        for serv in self.servers:
            self.serv_stations[serv] = list(config[serv])
            for idx, name in config[serv].items():
                self.sidx_name[idx] = name
        print(self.serv_stations)
        print('stations received.')

    def get_terms(self):
        '''
        Gets available terms.
        Adds them into the `self.term_box`.
        '''
        print('getting terms...')
        self.terms = set()
        self.term_box.clear()
        self.term_box.setEnabled(False)
        for serv_name, serv_addr in self.servers.items():
            last_id = 0
            while (resp := get_json(
                serv_addr,
                'get',
                {
                    'streams': 0,
                    'stations': self.serv_stations[serv_name],
                    'lastid': last_id
                }
            )):
                for row in resp:
                    moment = row['point_at']
                    last_id = row['id']
                    self.terms.add(moment)
        self.terms = sorted(filter(bool, self.terms), reverse=True)
        for term in self.terms:
            str_term = dt.datetime.utcfromtimestamp(term).strftime('%c')
            self.term_box.addItem(f'{str_term} UTC')
        self.term_box.setEnabled(True)
        print('terms received.')

    def get_measurements_types(self):
        '''
        Gets types of measurements for wanted stations.
        Gets meas units for each measurement type.
        '''
        print('getting measurements types...')
        self.bufr_name = {}
        self.bufr_unit = {}
        bufrs = set()
        for serv_name, stations in self.serv_stations.items():
            serv_addr = self.servers[serv_name]
            for station in stations:
                for row in get_json(serv_addr, 'station_taking.json', {'station': station}):
                    bufrs.add(row['code'])
            for row in get_json(serv_addr, 'measurement.json'):
                bufr = row['bufrcode']
                if bufr not in bufrs:
                    continue
                name = row['caption']
                unit = wanted_unit.get(row['unit'], row['unit'])
                self.bufr_name[bufr] = name
                self.bufr_unit[bufr] = unit
        print('measurements types received.')

    def set_headers(self):
        '''
        Sets horizontal header labels.
        Sets vertical header labels.
        '''
        print('setting headers...')
        names = [
            self.sidx_name[i]
            for i in sorted(
                (i for v in self.serv_stations.values() for i in v),
                key=int,
        )]
        self.table.setColumnCount(len(names))
        self.table.setHorizontalHeaderLabels(names)
        self.table.horizontalHeader().setFont(self.table_header_font)
        self.table.resizeColumnsToContents()
        
        names = [
            f'{self.bufr_name[bufr]}, [{self.bufr_unit[bufr]}]'
            for bufr in sorted(self.bufr_name)
        ]
        self.table.setRowCount(len(names))
        self.table.setVerticalHeaderLabels(names)
        self.table.verticalHeader().setFont(self.table_header_font)        
        self.table.resizeRowsToContents()
        print('headers set.')

    def get_measurements(self):
        '''
        Gets measurements.
        '''
        print('getting measurements...')
        self.meas_for_table.clear()
        ready = {}
        try:
            point = self.terms[self.term_box.currentIndex()]
        except IndexError:
            pass
        for serv_name, serv_addr in self.servers.items():
            print(serv_name, serv_addr)
            for station in self.serv_stations[serv_name]:
                name = self.sidx_name[station]
                print(station, name)
                for r in get_json(serv_addr, 'get', {'stations': station, 'streams': 0, 'point_at': point}):
                    _id = r['id']
                    bufr = r['code']
                    value = r['value']
                    unit = r['unit']
                    prev = ready.get((bufr, station), float('inf'))
                    if prev < _id:
                        continue
                    ready[(bufr, station)] = _id
                    value = Decimal(value)
                    match (wu:=wanted_unit.get(unit, unit)):
                        case 'C':
                            text = format_unit(value, unit, wu, prec=1)
                        case _:
                            text = format_unit(value, unit, wu)
                    if self.meas_for_table.get(bufr, None) is None:
                        self.meas_for_table[bufr] = {}
                    self.meas_for_table[bufr][station] = text
        print('measurements received.')

    def update_table_values(self):
        '''
        Updates values of `self.table` items.
        '''
        print('updating table values...')
        for i, bufr in enumerate(sorted(self.bufr_name)):
            for j, station in enumerate(sorted(self.sidx_name)):
                try:
                    item = QTableWidgetItem(self.meas_for_table[bufr][station])
                except KeyError:
                    item = QTableWidgetItem('-'*3)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        print('table values updated.')

    def update_data(self):
        '''
        Gets info using REST API from server.
        Updates info in `self.table`.
        '''
        print('updating data...')
        widgets = (self.term_box, )
        for widget in widgets:
            widget.setEnabled(False)
        self.label_last_update.setText('Обновление, подождите...')

        self.get_measurements()
        self.update_table_values()

        for widget in widgets:
            widget.setEnabled(True)
        QtCore.QTimer.singleShot(self.timer_interval, self.create_worker)
        self.label_last_update.setText(f'Последнее обновление: {dt.datetime.now()}')
        print('data updated.')

    def closeEvent(self, event:QtGui.QCloseEvent):
        '''
        Overrides closeEvent.
        Saves window settings (geometry, position).
        '''
        self.save_settings()
        super().closeEvent(event)

    def save_settings(self):
        '''
        Saves current window geometry.
        '''
        self.settings.setValue("geometry", self.saveGeometry())

    def restore_settings(self):
        '''
        Restores last window geometry.
        '''
        self.restoreGeometry(self.settings.value("geometry", type=QtCore.QByteArray))

    def keyPressEvent(self, event):
        '''
        Bindings in window.
        '''
        super().keyPressEvent(event)
        match event.key():
            case QtCore.Qt.Key.Key_Escape:
                self.close()
            case QtCore.Qt.Key.Key_F5:
                self.get_terms()


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('О приложении')
        self.setModal(True)
        self.layout = QVBoxLayout()

        vers_label = QLabel(f'Версия приложения: {VERSION}')
        self.layout.addWidget(vers_label)
        
        dev_label = QLabel('Разработчик: Никита "n1tr0xs" Троянов')
        self.layout.addWidget(dev_label)

        app_link = QPushButton('Скачать актуальную версию приложения')
        app_link.clicked.connect(lambda x: os.system('start https://github.com/n1tr0xs/LPR-stations-data-viewer/releases/latest'))
        self.layout.addWidget(app_link)
                        
        self.setLayout(self.layout)
        self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    sys.exit(app.exec())
