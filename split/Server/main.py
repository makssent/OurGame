import socket


def start_server(host='0.0.0.0', port=65432): # Создание коннекта для сервера
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen()
        print(f"Сервер запущен на {host}:{port}")

        while True:
            client_socket, client_address = server_socket.accept()
            with client_socket:
                print(f"Подключился клиент: {client_address}")
                client_socket.sendall(b"You are connected")

if __name__ == "__main__":
    start_server()