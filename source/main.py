import sys
import os
import locale
import configparser
import datetime as dt
import traceback
from collections.abc import KeysView
from numbers import Number
from decimal import Decimal, ConversionSyntax, InvalidOperation
import requests
import pyperclip
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt, pyqtSlot, QThreadPool, QObject, QRunnable, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QApplication, QGridLayout, QWidget, \
     QPushButton, QLabel, QComboBox, QTableWidget, QMenu, QTableWidgetItem, \
     QDialog, QVBoxLayout

VERSION = '2.1b'

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

def get_servers() -> dict:
    '''
    Gets list of servers from `settings.ini`.
    '''
    print('getting servers...')
    servers = dict(config['сервера'])
    print(servers)
    print('servers received.')
    return servers

def get_terms() -> set:
    '''
    Gets list of available terms.
    '''
    print('getting terms...')
    terms = set()
    for serv_name, serv_addr in SERVERS.items():
        last_id = 0
        while True:
            resp = get_json(
                serv_addr,
                'get',
                {
                    'streams': 0,
                    'stations': server_stations[serv_name],
                    'lastid': last_id,
                }
            )
            if not resp:
                break
            for row in resp:
                moment = row['point_at']
                last_id = row['id']
                terms.add(moment)
    print('terms received...')
    return terms

def get_stations() -> tuple[dict, dict]:
    '''
    Gets station list from `settings.ini`.
    '''
    print('getting stations...')
    serv_stations = {}
    sidx_name = {}
    for serv in SERVERS:
        serv_stations[serv] = list(config[serv])
        for idx, name in config[serv].items():
            sidx_name[idx] = name
    print(serv_stations)
    print(sidx_name)
    print('stations received.')
    return (serv_stations, sidx_name)

def get_measurements(point: int) -> dict:
    '''
    Gets measurements.
    '''
    print('getting measurements...')
    meas_for_table = {}
    ready = {}
    for serv_name, serv_addr in SERVERS.items():
        print(serv_name, serv_addr)
        for station in server_stations[serv_name]:
            print(station, sindex_sname[station])
            resp = get_json(
                serv_addr,
                'get',
                {'stations': station, 'streams': 0, 'point_at': point}
            )
            for r in resp:
                _id = r['id']
                bufr = r['code']
                unit = r['unit']
                prev = ready.get((bufr, station), float('inf'))
                if prev < _id:
                    continue
                ready[(bufr, station)] = _id
                try:
                    value = Decimal(r['value'])
                except (ConversionSyntax, InvalidOperation):
                    print('invalid:', r['value'])
                    value = '---'
                match (wu:=wanted_unit.get(unit, unit)):
                    case 'C':
                        text = format_unit(value, unit, wu, prec=1)
                    case _:
                        text = format_unit(value, unit, wu)
                if meas_for_table.get(bufr, None) is None:
                    meas_for_table[bufr] = {}
                meas_for_table[bufr][station] = text
    print('measurements received.')
    return meas_for_table

def get_json(server: str, page: str, parameters: dict={}) -> list:
    '''
    Gets json from `server` using given `page` with given `parameters`.
    Returns list.

    :param server: The server address.
    :type server: string
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
        return requests.get(url, timeout=1).json()
    except (
        requests.exceptions.JSONDecodeError,
        requests.exceptions.ConnectionError,
        requests.exceptions.ReadTimeout
    ) as e:
        print(type(e), e)
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

        self.timer_interval = config['настройки'].getint('период', 30) * 1000
        print(f'Timer interval set to: {self.timer_interval}')

        self.settings = QtCore.QSettings('n1tr0xs', 'Stations measurement views')

        self.layout = QGridLayout()
        self.centralWidget = QWidget()
        self.centralWidget.setLayout(self.layout)
        self.setCentralWidget(self.centralWidget)

        self.restore_settings()
        self.show()

        self.font = QtGui.QFont('Times New Roman', 12)
        self.table_header_font = QtGui.QFont('Times New Roman', 12, QtGui.QFont.Weight.Bold)
        self.setFont(self.font)
        self.setWindowTitle('Просмотр данных метеорологических станций ЛНР')
        self.setWindowIcon(QtGui.QIcon('icon.ico'))

        self.update_terms_btn = QPushButton('Обновить список сроков')
        self.update_terms_btn.clicked.connect(self.set_terms)
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
        self.table.cellDoubleClicked.connect(
            lambda i, j: pyperclip.copy(self.table.item(i, j).text())
        )
        self.layout.addWidget(self.table, 1, 0, 1, 4)

        self.create_menu()
        self.get_measurements_types()
        self.set_headers()
        self.set_terms()
        self.term_box.currentIndexChanged.connect(self.create_worker)
        QtCore.QTimer.singleShot(0, self.create_worker)

    def create_menu(self):
        '''
        Creates menu.
        '''
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
        '''
        Shows Help window.
        '''
        try:
            HelpDialog(self).exec()
        except Exception as e:
            print(type(e), e)

    def create_worker(self):
        '''
        Creates and starts worker for info update.
        '''
        print('selected term №:', self.term_box.currentIndex())
        worker = Worker(self.update_data)
        QThreadPool.globalInstance().start(worker)

    def set_terms(self):
        '''
        Setting list of terms for `self.term_box`.
        '''
        print('setting terms...')
        self.term_box.clear()
        self.term_box.setEnabled(False)
        self.terms = sorted(filter(bool, get_terms()), reverse=True)
        for term in self.terms:
            str_term = dt.datetime.utcfromtimestamp(term).strftime('%c')
            self.term_box.addItem(f'{str_term} UTC')
        self.term_box.setEnabled(True)
        print('terms set.')

    def get_measurements_types(self):
        '''
        Gets types of measurements for wanted stations.
        Gets meas units for each measurement type.
        '''
        print('getting measurements types...')
        self.bufr_name = {}
        self.bufr_unit = {}
        bufrs = set()
        for serv_name, stations in server_stations.items():
            serv_addr = SERVERS[serv_name]
            for station in stations:
                for row in get_json(serv_addr, 'station_taking.json', {'station': station}):
                    bufrs.add(row['code'])
            for row in get_json(serv_addr, 'measurement.json'):
                bufr = row['bufrcode']
                if bufr not in bufrs:
                    continue
                self.bufr_name[bufr] = row['caption']
                self.bufr_unit[bufr] = wanted_unit.get(row['unit'], row['unit'])
        print('measurements types received.')

    def set_headers(self):
        '''
        Sets horizontal header labels.
        Sets vertical header labels.
        '''
        print('setting headers...')
        names = [
            sindex_sname[i]
            for i in sorted(
                (i for v in server_stations.values() for i in v),
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

    def update_table_values(self, meas_for_table):
        '''
        Updates values of `self.table` items.
        '''
        print('updating table values...')
        for i, bufr in enumerate(sorted(self.bufr_name)):
            for j, station in enumerate(sorted(sindex_sname)):
                try:
                    item = QTableWidgetItem(meas_for_table[bufr][station])
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
        self.label_last_update.setText('Обновление, подождите...')

        try:
            self.update_table_values(get_measurements(self.terms[self.term_box.currentIndex()]))
        except IndexError:
            return

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
                self.set_terms()


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
        link = 'https://github.com/n1tr0xs/LPR-stations-data-viewer/releases/latest'
        app_link.clicked.connect(lambda x: os.system(f'start {link}'))
        self.layout.addWidget(app_link)

        self.setLayout(self.layout)
        self.show()


if __name__ == "__main__":
    SERVERS = get_servers()
    server_stations, sindex_sname = get_stations()
    app = QApplication(sys.argv)
    w = MainWindow()
    sys.exit(app.exec())
