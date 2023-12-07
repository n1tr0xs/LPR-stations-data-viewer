import sys
import requests
import datetime as dt
import locale
from collections.abc import Iterable, Mapping
from numbers import Number
from decimal import Decimal, ConversionSyntax, InvalidOperation
import pyperclip

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSlot, QThreadPool, QObject, QRunnable, pyqtSignal
from PyQt6.QtWidgets import *

convert_table = {
    'k': {
      'C': lambda val: val - Decimal('273.15'),
    },
    'pa': {
        'гПа': lambda val: val / 100,
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
    }
}

wanted_unit = {
    'k': 'C',
    'pa': 'гПа',
    'code table': 'кодовая таблица',
    'degree true': '°',
    'kg m-2': 'мм',
    'm': 'м',
    'm/s': 'м/с',
}

locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')

def get_json(page: str, parameters: Mapping={}, *, server: str='http://10.55.1.30:8640') -> list:
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
        url += ','.join(map(str, v)) if isinstance(v, Iterable) else str(v)
        url += '&'
    print(url)
    try:
        return requests.get(url).json()
    except requests.exceptions.JSONDecodeError:
        return list()

def format_unit(value: Number, base: str, target: str, table: dict=convert_table) -> str:
    '''
    Converts given value from unit to unit.
    Formats the result to string `value unit`.
    '''
    try:
        return f'{table[base][target](value)}'
    except KeyError:
        return f'{value}'
    
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
        super(Worker, self).__init__()
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
    keyPressed = QtCore.pyqtSignal(int)
    
    def __init__(self):
        '''
        Creates main window.
        '''
        super().__init__()
        
        self.settings = QtCore.QSettings('n1tr0xs', 'sinop measurement view')
        self.threadpool = QThreadPool.globalInstance()
                        
        self.layout = QGridLayout()

        self.centralWidget = QWidget()
        self.centralWidget.setLayout(self.layout)
        self.setCentralWidget(self.centralWidget)

        self.timer = QtCore.QTimer()
        self.timer.setInterval(10*1000)
        self.timer.timeout.connect(self.create_worker)

        self.setFont(QtGui.QFont('Times New Roman', 12))
        self.setWindowTitle('Просмотр данных метеорологических станций ЛНР')

        self.label_term = QLabel('Срок:')
        self.label_term.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.label_term, 0, 0)

        self.term_box = QComboBox()
        self.layout.addWidget(self.term_box, 0, 1)

        self.label_last_update = QLabel('Последнее обновление:')
        self.label_last_update.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.label_last_update, 0, 2)
        
        self.table = QTableWidget()
        self.table.cellDoubleClicked.connect(lambda i, j: pyperclip.copy(self.table.item(i, j).text()))
        self.layout.addWidget(self.table, 1, 0, 1, 3)
        
        self.get_stations()
        self.get_measurements_types()
        self.set_headers()
        self.term_box.currentIndexChanged.connect(self.timer.timeout.emit)
        self.get_terms()
        self.timer.start()
        
        self.restore_settings()
        self.show()        
        
    def create_worker(self):
        '''
        Creates and starts worker for info update.
        '''
        worker = Worker(self.update_data)
        worker.signals.finished.connect(self.on_data_update)
        self.threadpool.start(worker)
        
    def on_data_update(self):
        '''
        Changes `self.label_last_update` text after data in table updated.
        '''
        self.label_last_update.setText(f'Последнее обновление: {dt.datetime.now()}')
        
    def get_stations(self):
        '''
        Gets station list.
        '''
        print('getting stations...')
        self.stations = dict()
        for row in get_json('stations.json'):
            index, name = row['sindex'], row['station_name']
            if name.startswith('МС'):
                self.stations[index] = name
        print('stations received.')
        
    def get_terms(self):
        '''
        Gets available terms.
        Adds them into the `self.term_box`.
        '''
        print('getting terms...')
        self.terms = set()
        last_id = 0
        while (resp := get_json('get', {'streams': 0, 'stations': self.stations.keys(), 'lastid': last_id})):
            for row in resp:
                moment = row['point_at']
                last_id = row['id']
                self.terms.add(moment)            
        self.terms = sorted(filter(bool, self.terms), reverse=True)
        for term in self.terms:
            str_term = dt.datetime.utcfromtimestamp(term).strftime('%c')
            self.term_box.addItem(f'{str_term} UTC')
        print('terms received.')

    def get_measurements_types(self):
        '''
        Gets types of measurements for wanted stations.
        Gets meas units for each measurement type.
        '''
        print('getting measurements types...')
        self.bufr_name = dict()
        self.bufr_unit = dict()
        bufrs = set()        
        for station in self.stations:
            for row in get_json('station_taking.json', {'station': station}):
                bufrs.add(row['code'])
        
        for row in get_json('measurement.json'):
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
        names = [f'{name}' for _, name in sorted(self.stations.items(), key=lambda x: x[0])]
        self.table.setColumnCount(len(names))
        self.table.setHorizontalHeaderLabels(names)

        names = [f'{self.bufr_name[bufr]}, [{self.bufr_unit[bufr]}]' for bufr in sorted(self.bufr_name)]
        self.table.setRowCount(len(names))
        self.table.setVerticalHeaderLabels(names)
        print('headers set.')
        
    def get_measurements(self):
        '''
        Gets measurements.
        '''
        print('getting measurements...')
        self.meas_for_table = dict()
        ready = dict()
        for station in self.stations:
            print(station, self.stations[station])
            for r in get_json('get', {'stations': station, 'streams': 0, 'point_at': self.point}):
                _id = r['id']
                bufr = r['code']
                station = r['station']
                value = r['value']
                unit = r['unit']                
                prev = ready.get((bufr, station), None)
                if (prev is not None) and (prev < _id):
                    continue
                ready[(bufr, station)] = _id
                if self.meas_for_table.get(bufr, None) is None:
                    self.meas_for_table[bufr] = dict()
                try:
                    value = Decimal(value)
                except (ConversionSyntax, InvalidOperation):
                    value = '#'                
                text = format_unit(value, unit, wanted_unit.get(unit, unit))
                self.meas_for_table[bufr][station] = text
        print('measurements received.')
                
    def update_table_values(self):
        '''
        Updates values of `self.table` items.
        '''
        print('updating table values...')
        for i, bufr in enumerate(sorted(self.bufr_name)):
            for j, station in enumerate(sorted(self.stations)):
                try:
                    item = QTableWidgetItem(self.meas_for_table[bufr][station])
                except KeyError:
                    item = QTableWidgetItem('-'*3)
                finally:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(i, j, item)
        print('table values updated.')
                    
    def update_data(self):
        '''
        Gets info using REST API from server.
        Updates info in `self.table`.
        '''
        print('updating data...')
        self.label_last_update.setText(f'Обновление, подождите...')
        self.point = self.terms[self.term_box.currentIndex()]        
        self.get_measurements()
        self.update_table_values()
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        print('data updated.')
        
    def closeEvent(self, event:QtGui.QCloseEvent):
        '''
        Overrides closeEvent.
        Saves window settings (geomtry, position).
        Stops the `self.timer`.
        '''
        self.save_settings()
        self.timer.stop()
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
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    sys.exit(app.exec())
