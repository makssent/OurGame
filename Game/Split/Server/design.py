import math
import sys
import random
import socket
import threading
from datetime import datetime
from contextlib import closing
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QLabel, QSlider, QHBoxLayout, QMessageBox, QInputDialog, QColorDialog, QTextEdit)
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QBuffer, QIODevice, QRect, QSize
from PyQt6.QtGui import QColor, QPainter, QImage, QPen, QBrush

def is_port_in_use(port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex(('localhost', port)) == 0

def recvall(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

class ServerThread(QThread):
    message_received = pyqtSignal(str)
    top_players_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.server_socket = None
        self.running = False
        self.clients = []
        self.draw_area = None  # Будет установлено позже
        self.secret_word = None
        self.player_scores = {}

    def run(self):
        self.running = True
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            port = 12345
            while is_port_in_use(port):
                port += 1
            self.server_socket.bind(('192.168.30.88', port))
            self.server_socket.listen(5)
            self.message_received.emit(f"Ожидается подключение на порту {port}...")

            while self.running:
                client_socket, addr = self.server_socket.accept()
                # При подключении ожидаем, что клиент отправит свой ник в виде обычного текста
                nickname = client_socket.recv(1024).decode().replace("Ник: ", "")
                self.message_received.emit(f"Подключился игрок: {nickname} ({addr[0]})")
                self.clients.append((client_socket, nickname))
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, nickname))
                client_thread.start()
        except Exception as e:
            self.message_received.emit(f"Ошибка: {e}")

    def update_top_players(self):
        # Сортируем игроков по количеству очков (в порядке убывания)
        sorted_players = sorted(self.player_scores.items(), key=lambda x: x[1], reverse=True)
        top_players_message = "Топ игроков:\n"
        for i, (player, score) in enumerate(sorted_players, start=1):
            top_players_message += f"{i}. {player}: {score} очков\n"

        # Отправляем сообщение с топом игроков на сервер
        self.message_received.emit(top_players_message)

        return top_players_message

    def handle_client(self, client_socket, nickname):
        try:
            # Отправляем приветственное сообщение с типом T
            welcome = "Добро пожаловать на сервер!"
            data = b'T' + len(welcome.encode()).to_bytes(4, 'big') + welcome.encode()
            client_socket.sendall(data)
            while self.running:
                type_byte = client_socket.recv(1)
                if not type_byte:
                    break
                length_bytes = recvall(client_socket, 4)
                if not length_bytes:
                    break
                msg_length = int.from_bytes(length_bytes, 'big')
                payload = recvall(client_socket, msg_length)
                if payload is None:
                    break
                if type_byte == b'T':
                    text = payload.decode().strip()
                    full_message = f"{nickname}: {text}"
                    self.message_received.emit(full_message)

                    # Проверяем, угадано ли слово
                    if self.secret_word and text.lower() == self.secret_word.lower():
                        result_message = f"Загаданное слово: {self.secret_word}!"
                        self.message_received.emit(result_message)

                        # Начисляем 100 очков игроку, который отгадал слово
                        if nickname not in self.player_scores:
                            self.player_scores[nickname] = 0
                        self.player_scores[nickname] += 100

                        # Обновляем топ игроков
                        top_players_message = self.update_top_players()
                        self.top_players_updated.emit(top_players_message)


                        # Отправляем сообщение всем клиентам
                        for client, _ in self.clients:
                            try:
                                client.sendall(
                                    b'T' + len(result_message.encode()).to_bytes(4, 'big') + result_message.encode())
                                client.sendall(
                                    b'T' + len(top_players_message.encode()).to_bytes(4,
                                                                                      'big') + top_players_message.encode())
                            except Exception as e:
                                print(f"Ошибка отправки сообщения клиенту: {e}")

                        # Обновляем топ игроков на сервере
                        if self.draw_area and hasattr(self.draw_area.parent(), 'update_top_players_display'):
                            self.draw_area.parent().update_top_players_display()

                        # Сбрасываем загаданное слово и переходим в состояние ожидания нового слова
                        self.secret_word = None
                        self.message_received.emit("Ожидание нового слова...")

                    # Рассылаем текстовое сообщение всем клиентам
                    for client, _ in self.clients:
                        try:
                            client.sendall(b'T' + len(full_message.encode()).to_bytes(4, 'big') + full_message.encode())
                        except Exception as e:
                            print(f"Ошибка отправки сообщения клиенту: {e}")
        except Exception as e:
            self.message_received.emit(f"Ошибка: {e}")
        finally:
            # Закрываем сокет только при завершении потока
            client_socket.close()
            self.clients = [(client, nick) for client, nick in self.clients if client != client_socket]

    def broadcast_image(self):
        if not self.draw_area:
            return
        image_bytes = self.draw_area.get_image_bytes()
        data = b'I' + len(image_bytes).to_bytes(4, 'big') + image_bytes
        for client, _ in self.clients:
            try:
                client.sendall(data)
            except Exception as e:
                print(f"Ошибка отправки изображения: {e}")

    def stop(self):
        self.running = False
        for client, _ in self.clients:
            try:
                client.close()
            except Exception as e:
                print(f"Ошибка при закрытии сокета: {e}")
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None

class DrawArea(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #ffffff; border: 3px solid #7f8c8d; border-radius: 15px;")
        self.drawing = False
        self.drawing_shape = False
        self.shape_type = None  # "circle", "square", "triangle"
        self.start_point = QPoint()
        self.image = QImage(self.size(), QImage.Format.Format_ARGB32)
        self.image.fill(Qt.GlobalColor.white)
        self.pen_size = 5
        self.current_color = QColor(Qt.GlobalColor.black)
        self.eraser_mode = False
        self.setEnabled(False)

    def clear_canvas(self):
        self.image.fill(Qt.GlobalColor.white)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            if self.shape_type:
                self.drawing_shape = True
                self.start_point = event.position().toPoint()
            else:
                self.drawing = True
                self.last_point = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.drawing and self.isEnabled() and not self.drawing_shape:
            painter = QPainter(self.image)
            pen = QPen(self.current_color, self.pen_size) if not self.eraser_mode else QPen(Qt.GlobalColor.white, self.pen_size)
            painter.setPen(pen)
            current_point = event.position().toPoint()
            painter.drawLine(self.last_point, current_point)
            self.last_point = current_point
            self.update()
            # Отправляем обновлённое изображение всем клиентам
            if self.parent() and hasattr(self.parent(), 'server_thread'):
                self.parent().server_thread.broadcast_image()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            if self.drawing_shape:
                painter = QPainter(self.image)
                painter.setPen(QPen(self.current_color, self.pen_size))  # Убираем заливку

                end_point = event.position().toPoint()
                rect = QRect(self.start_point, end_point)

                if self.shape_type == "circle":
                    painter.drawEllipse(rect)
                elif self.shape_type == "square":
                    side = min(abs(rect.width()), abs(rect.height()))
                    square_rect = QRect(self.start_point, QSize(side, side))
                    painter.drawRect(square_rect)
                elif self.shape_type == "right_triangle":
                    # Длина катетов (равных)
                    base_length = abs(end_point.x() - self.start_point.x())  # Длина по оси X
                    height_length = abs(end_point.y() - self.start_point.y())  # Длина по оси Y

                    # Делаем катеты равными
                    side_length = min(base_length, height_length)

                    # Точки для равнобедренного прямоугольного треугольника
                    p1 = self.start_point  # Левый нижний угол
                    p2 = QPoint(self.start_point.x() + side_length, self.start_point.y())  # Нижний правый угол
                    p3 = QPoint(self.start_point.x() + side_length // 2,
                                self.start_point.y() - side_length)  # Верхний угол

                    # Рисуем треугольник
                    painter.drawPolygon(p1, p2, p3)

                self.drawing_shape = False
                self.shape_type = None
                self.update()
            else:
                self.drawing = False

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.drawImage(self.rect(), self.image, self.image.rect())
        painter.setBrush(QBrush(self.current_color))
        painter.drawEllipse(10, 10, 30, 30)

    def resizeEvent(self, event):
        new_image = QImage(self.size(), QImage.Format.Format_ARGB32)
        new_image.fill(Qt.GlobalColor.white)
        painter = QPainter(new_image)
        painter.drawImage(QPoint(0, 0), self.image)
        self.image = new_image
        super().resizeEvent(event)

    def set_pen_size(self, size):
        self.pen_size = size

    def set_pen_color(self, color):
        self.current_color = color
        self.update()

    def set_eraser_mode(self, enabled):
        self.eraser_mode = enabled

    def get_image_bytes(self):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.image.save(buffer, "PNG")
        return bytes(buffer.data())

    def set_shape(self, shape):
        self.shape_type = shape

class StartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.time_left = 60
        self.server_thread = ServerThread()
        self.server_thread.message_received.connect(self.update_chat)
        self.server_thread.top_players_updated.connect(self.update_top_players_display)
        self.server_thread.draw_area = self.squareDraw
        self.server_thread.start()

    def initUI(self):
        self.setFixedSize(1460, 800)
        self.setWindowTitle('Pictionary Party')
        self.setStyleSheet("background-color: #2c3e50; color: #ecf0f1;")

        self.squareChat = QTextEdit(self)
        self.squareChat.setGeometry(25, 225, 250, 400)
        self.squareChat.setStyleSheet(
            "background-color: #34495e; border: 2px solid #7f8c8d; border-radius: 10px; padding: 10px; font-family: 'Arial'; font-size: 14px;")

        # Поле для отображения топа игроков
        self.squareTop = QLabel("Топ игроков:\n", self)
        self.squareTop.setGeometry(25, 25, 250, 175)
        self.squareTop.setStyleSheet(
            "background-color: #34495e; border: 2px solid #7f8c8d; border-radius: 10px; padding: 10px; font-weight: bold; font-size: 16px;")
        self.squareTop.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.squareWord = QLabel(self)
        self.squareWord.setGeometry(25, 650, 250, 75)
        self.squareWord.setStyleSheet(
            "background-color: #27ae60; border-radius: 15px; color: white; font-size: 24px; font-weight: bold;")
        self.squareWord.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_container = QWidget(self)
        button_container.setGeometry(25, 735, 250, 40)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_style = ("QPushButton { background-color: #3498db; border: none; border-radius: 8px; "
                        "color: white; padding: 8px; font-size: 14px; } "
                        "QPushButton:hover { background-color: #2980b9; } "
                        "QPushButton:pressed { background-color: #1f6aad; }")
        self.generateWordButton = QPushButton("🎲 Случайное")
        self.generateWordButton.setStyleSheet(button_style)
        self.generateWordButton.clicked.connect(self.generate_random_word)
        self.customWordButton = QPushButton("✏️ Свое слово")
        self.customWordButton.setStyleSheet(button_style)
        self.customWordButton.clicked.connect(self.set_custom_word)
        button_layout.addWidget(self.generateWordButton)
        button_layout.addWidget(self.customWordButton)

        self.squareDraw = DrawArea(self)
        self.squareDraw.setGeometry(300, 25, 1000, 700)

        tools_style = ("QPushButton { border: 2px solid transparent; border-radius: 8px; padding: 8px; "
                       "min-width: 80px; font-size: 14px; transition: all 0.3s; } "
                       "QPushButton:hover { transform: scale(1.05); }")
        self.color_button = QPushButton("🎨 Цвет", self)
        self.color_button.setGeometry(300, 735, 100, 40)
        self.color_button.setStyleSheet(tools_style + "background-color: #9b59b6; color: white; border: 2px solid #8e44ad;")
        self.color_button.clicked.connect(self.choose_color)
        self.pen_button = QPushButton("✍️ Ручка", self)
        self.pen_button.setGeometry(410, 735, 100, 40)
        self.pen_button.setStyleSheet(tools_style + "background-color: #2ecc71; color: white; border: 2px solid #27ae60;")
        self.pen_button.clicked.connect(self.set_pen_mode)
        self.eraser_button = QPushButton("🧹 Ластик", self)
        self.eraser_button.setGeometry(520, 735, 100, 40)
        self.eraser_button.setStyleSheet(tools_style + "background-color: #e74c3c; color: white; border: 2px solid #c0392b;")
        self.eraser_button.clicked.connect(self.set_eraser_mode)

        slider_container = QWidget(self)
        slider_container.setGeometry(1320, 25, 50, 700)
        slider_layout = QVBoxLayout(slider_container)
        slider_layout.addWidget(QLabel("Размер", styleSheet="color: #bdc3c7;"))
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setStyleSheet(
            "QSlider::groove:vertical { background: #34495e; width: 6px; border-radius: 3px; } "
            "QSlider::handle:vertical { background: #3498db; height: 20px; width: 20px; margin: -5px 0; border-radius: 10px; }")
        self.slider.setMinimum(1)
        self.slider.setMaximum(25)
        self.slider.setValue(5)
        self.slider.valueChanged.connect(self.change_pen_size)
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(QLabel(str(self.slider.value()), styleSheet="color: #bdc3c7; font-weight: bold;"))

        self.start_button = QPushButton("🚀 СТАРТ", self)
        self.start_button.setGeometry(600, 300, 200, 100)
        self.start_button.setStyleSheet(
            "QPushButton { background-color: #27ae60; border-radius: 20px; color: white; font-size: 32px; font-weight: bold; } "
            "QPushButton:hover { background-color: #219a52; } "
            "QPushButton:pressed { background-color: #1d8348; }")
        self.start_button.clicked.connect(self.activate_drawing_area)
        self.timer_label = QLabel("60", self)
        self.timer_label.setGeometry(1380, 15, 50, 50)
        self.timer_label.setStyleSheet(
            "background-color: #e74c3c; border-radius: 25px; color: white; font-size: 24px; font-weight: bold;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.circle_button = QPushButton("⚪ Круг", self)
        self.circle_button.setGeometry(630, 735, 100, 40)
        self.circle_button.setStyleSheet(
            tools_style + "background-color: #f1c40f; color: black; border: 2px solid #f39c12;")
        self.circle_button.clicked.connect(lambda: self.squareDraw.set_shape("circle"))

        self.square_button = QPushButton("⬛ Квадрат", self)
        self.square_button.setGeometry(740, 735, 100, 40)
        self.square_button.setStyleSheet(
            tools_style + "background-color: #e67e22; color: white; border: 2px solid #d35400;")
        self.square_button.clicked.connect(lambda: self.squareDraw.set_shape("square"))

        self.right_triangle_button = QPushButton('△ Треугольник', self)
        self.right_triangle_button.setGeometry(850, 735, 100, 40)  # Расположение кнопки
        self.right_triangle_button.setStyleSheet(
            tools_style + "background-color: #f39c12; color: white; border: 2px solid #e67e22;")
        self.right_triangle_button.clicked.connect(lambda: self.squareDraw.set_shape("right_triangle"))

        self.center()

    def get_timestamp(self):
        return f"[{datetime.now().strftime('%H:%M:%S')}] "

    def update_top_players_display(self):
        # Получаем текущий топ игроков из серверного потока
        top_players_message = self.server_thread.update_top_players()
        # Обновляем поле с топом игроков на сервере
        self.squareTop.setText(top_players_message)

    def update_chat(self, message):
        self.squareChat.append(self.get_timestamp() + message)
        if message.startswith("Загаданное слово:"):
            self.timer.stop()
            self.squareDraw.setEnabled(False)
            QMessageBox.information(self, "Игра окончена", message)
            self.squareDraw.clear_canvas()  # Очистка после завершения игры
            self.squareChat.clear()  # Очищаем чат после завершения раунда

            # Возвращаемся к состоянию выбора слова
            self.squareWord.clear()  # Очищаем поле с загаданным словом
            self.server_thread.secret_word = None  # Сбрасываем загаданное слово на сервере
            self.start_button.show()  # Показываем кнопку "СТАРТ"
            self.time_left = 60  # Сбрасываем таймер
            self.timer_label.setText(str(self.time_left))

    def start_new_round(self):
        self.squareDraw.clear_canvas()  # Очищаем поле для рисования
        self.squareWord.clear()  # Очищаем поле с загаданным словом
        self.server_thread.secret_word = None  # Сбрасываем загаданное слово
        self.start_button.show()  # Показываем кнопку "СТАРТ"
        self.time_left = 60  # Сбрасываем таймер
        self.timer_label.setText(str(self.time_left))  # Обновляем отображение таймера
        self.squareChat.clear()  # Очищаем чат
        self.squareChat.append("Ожидание нового слова...")



    def change_pen_size(self, value):
        self.squareDraw.set_pen_size(value)

    def generate_random_word(self):
        words = ["Яблоко", "Солнце", "Море", "Гора", "Книга", "Компьютер", "Собака", "Кошка", "Дом", "Машина"]
        random_word = random.choice(words)
        self.squareWord.setText(random_word)
        self.server_thread.secret_word = random_word

    def set_custom_word(self):
        custom_word, ok = QInputDialog.getText(self, "Загадать слово", "Введите слово:")
        if ok and custom_word:
            self.squareWord.setText(custom_word)
            self.server_thread.secret_word = custom_word  # Устанавливаем загаданное слово на сервере

    def activate_drawing_area(self):
        if not self.squareWord.text():
            QMessageBox.warning(self, "Ошибка", "Сначала задайте слово!")
            return
        self.squareDraw.setEnabled(True)
        self.start_button.hide()
        self.time_left = 60
        self.timer_label.setText(str(self.time_left))
        self.timer.start(1000)

    def update_timer(self):
        self.time_left -= 1
        self.timer_label.setText(str(self.time_left))
        if self.time_left <= 0:
            self.timer.stop()
            QMessageBox.information(self, "Время вышло", "Время закончилось!")
            self.squareDraw.setEnabled(False)

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.squareDraw.set_pen_color(color)

    def set_pen_mode(self):
        self.squareDraw.set_eraser_mode(False)

    def set_eraser_mode(self):
        self.squareDraw.set_eraser_mode(True)

    def center(self):
        screen_geometry = QApplication.primaryScreen().geometry()
        center_point = screen_geometry.center()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def closeEvent(self, event):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait()
        event.accept()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setFixedSize(600, 400)
        self.setWindowTitle('Pictionary Party')
        self.setStyleSheet("background-color: #2c3e50; color: #ecf0f1;")
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(50, 50, 50, 50)
        main_layout.setSpacing(30)
        title = QLabel("🎨 Pictionary Party")
        title.setStyleSheet("font-size: 42px; font-weight: bold; color: #3498db;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_style = ("QPushButton { background-color: #3498db; border: none; border-radius: 15px; "
                        "color: white; padding: 15px; font-size: 20px; } "
                        "QPushButton:hover { background-color: #2980b9; } "
                        "QPushButton:pressed { background-color: #1f6aad; }")
        self.start_button = QPushButton('🎮 Начать игру')
        self.start_button.setStyleSheet(button_style)
        self.start_button.clicked.connect(self.start_game)
        self.exit_button = QPushButton('🚪 Выход')
        self.exit_button.setStyleSheet(button_style)
        self.exit_button.clicked.connect(self.close)
        main_layout.addWidget(title)
        main_layout.addWidget(self.start_button)
        main_layout.addWidget(self.exit_button)
        self.setLayout(main_layout)
        self.center()

    def center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def start_game(self):
        self.start_window = StartWindow()
        self.start_window.show()
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
