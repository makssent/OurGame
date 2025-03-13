import sys
import socket
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QLabel, QTextEdit, QMessageBox, QInputDialog,
                             QLineEdit, QHBoxLayout)
from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QImage, QPen, QBrush

def recvall(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

class ClientThread(QThread):
    message_received = pyqtSignal(str)
    image_received = pyqtSignal(bytes)

    def __init__(self, host, port, nickname):
        super().__init__()
        self.host = host
        self.port = port
        self.nickname = nickname
        self.client_socket = None
        self.running = False

    def run(self):
        self.running = True
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            # Отправляем ник как обычный текст (начальное рукопожатие)
            self.client_socket.send(f"Ник: {self.nickname}".encode())
            self.message_received.emit(f"Подключение к серверу {self.port} установлено!")
            while self.running:
                type_byte = recvall(self.client_socket, 1)
                if type_byte is None:
                    self.message_received.emit("Сервер закрыл соединение.")
                    break
                length_bytes = recvall(self.client_socket, 4)
                if length_bytes is None:
                    self.message_received.emit("Сервер закрыл соединение.")
                    break
                msg_length = int.from_bytes(length_bytes, 'big')
                payload = recvall(self.client_socket, msg_length)
                if payload is None:
                    self.message_received.emit("Сервер закрыл соединение.")
                    break
                if type_byte == b'T':
                    self.message_received.emit(payload.decode())
                elif type_byte == b'I':
                    self.image_received.emit(payload)
        except Exception as e:
            self.message_received.emit(f"Ошибка: {e}")
        finally:
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None

    def send_message(self, message):
        if self.client_socket:
            try:
                data = b'T' + len(message.encode()).to_bytes(4, 'big') + message.encode()
                self.client_socket.sendall(data)
            except Exception as e:
                self.message_received.emit(f"Ошибка при отправке сообщения: {e}")

    def stop(self):
        self.running = False
        if self.client_socket:
            self.client_socket.close()
            self.client_socket = None

class DrawArea(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #ffffff; border: 3px solid #7f8c8d; border-radius: 15px;")
        self.drawing = False
        self.last_point = QPoint()
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
            self.drawing = True
            self.last_point = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.drawing and self.isEnabled():
            painter = QPainter(self.image)
            pen = QPen(Qt.GlobalColor.white if self.eraser_mode else self.current_color, self.pen_size)
            painter.setPen(pen)
            current_point = event.position().toPoint()
            painter.drawLine(self.last_point, current_point)
            self.last_point = current_point
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
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

class StartWindow(QWidget):
    def __init__(self, host, port, nickname):
        super().__init__()
        self.host = host
        self.port = port
        self.nickname = nickname
        self.initUI()
        self.client_thread = ClientThread(self.host, self.port, self.nickname)
        self.client_thread.message_received.connect(self.update_chat)
        self.client_thread.image_received.connect(self.update_image)
        self.client_thread.start()

    def initUI(self):
        self.setFixedSize(1460, 800)
        self.setWindowTitle('Pictionary Party - Client')
        self.setStyleSheet("background-color: #2c3e50; color: #ecf0f1;")
        self.squareChat = QTextEdit(self)
        self.squareChat.setGeometry(25, 225, 250, 400)
        self.squareChat.setStyleSheet(
            "background-color: #34495e; border: 2px solid #7f8c8d; border-radius: 10px; padding: 10px; font-family: 'Arial'; font-size: 14px;")
        self.squareTop = QLabel(f"Ник: {self.nickname}\nСервер: {self.host}:{self.port}", self)
        self.squareTop.setGeometry(25, 25, 250, 175)
        self.squareTop.setStyleSheet(
            "background-color: #34495e; border: 2px solid #7f8c8d; border-radius: 10px; padding: 10px; font-size: 16px;")
        self.squareTop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.squareDraw = DrawArea(self)
        self.squareDraw.setGeometry(300, 25, 1000, 700)
        self.message_input = QLineEdit(self)
        self.message_input.setGeometry(25, 635, 200, 40)
        self.message_input.setStyleSheet(
            "background-color: #34495e; border: 2px solid #7f8c8d; border-radius: 8px; padding: 5px; color: #ecf0f1; font-size: 14px;")
        self.message_input.setPlaceholderText("Введите сообщение...")
        self.send_button = QPushButton("➤", self)
        self.send_button.setGeometry(230, 635, 40, 40)
        self.send_button.setStyleSheet(
            "QPushButton { background-color: #3498db; border: none; border-radius: 8px; color: white; font-size: 18px; } "
            "QPushButton:hover { background-color: #2980b9; } "
            "QPushButton:pressed { background-color: #1f6aad; }")
        self.send_button.clicked.connect(self.send_message)
        self.center()

    def get_timestamp(self):
        return f"[{datetime.now().strftime('%H:%M:%S')}] "

    def update_chat(self, message):
        self.squareChat.append(self.get_timestamp() + message)
        if message.startswith("Загаданное слово:"):
            QMessageBox.information(self, "Игра окончена", message)
            self.squareDraw.clear_canvas()  # Очистка холста
            self.squareChat.clear()  # Очищаем чат после завершения раунда
            self.squareChat.append("Ожидание нового слова...")

    def update_image(self, image_data):
        image = QImage()
        if not image.loadFromData(image_data):
            print("Ошибка загрузки изображения")
            return
        self.squareDraw.image = image
        self.squareDraw.update()

    def send_message(self):
        message = self.message_input.text()
        if message:
            self.client_thread.send_message(message)
            self.message_input.clear()

    def center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def closeEvent(self, event):
        if self.client_thread:
            self.client_thread.stop()
            self.client_thread.wait()
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
        self.start_button = QPushButton('🎮 Подключиться')
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
        host = "localhost"
        port, ok = QInputDialog.getInt(self, "Подключение", "Порт сервера:", 12345, 1, 65535)
        if not ok:
            return
        nickname, ok = QInputDialog.getText(self, "Никнейм", "Введите ваш ник:")
        if not ok or not nickname:
            QMessageBox.warning(self, "Ошибка", "Ник не может быть пустым!")
            return
        self.start_window = StartWindow(host, port, nickname)
        self.start_window.show()
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
