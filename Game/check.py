import socket


def handle_client(client_socket):
    try:
        # Обработка сообщений
        while True:
            message = client_socket.recv(1024).decode()
            if not message:
                break  # Если соединение закрыто
            print(f"Получено сообщение: {message}")
            # Отправить ответ клиенту (если необходимо)
            client_socket.send("Ответ от сервера".encode())
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        client_socket.close()  # Обязательно закрыть сокет
        print("Соединение закрыто")


# Серверный код
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('localhost', 12345))
    server.listen(5)
    print("Ожидается подключение на порту 12345...")

    while True:
        client_socket, addr = server.accept()
        print(f"Подключился игрок: {addr}")
        handle_client(client_socket)


if __name__ == "__main__":
    start_server()
